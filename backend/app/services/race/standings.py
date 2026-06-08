"""Service: season cumulative standings aggregated from base tables.

Public surface
--------------
``get_event_standings(db, race_event_id, *, category_id, club_only,
                       allowed_athlete_ids)``
    → ``EventStandingsRead | None``

Design constraints
------------------
- Aggregates directly from ``race_results`` + ``race_competitors`` +
  ``race_categories`` + ``race_events`` + ``race_series``.  Does NOT query
  the ``season_standings`` VIEW because that view may not exist in the SQLite
  test database.
- Single aggregated SQL query (no N+1): uses ``GROUP BY (category_id,
  competitor_id)`` with SUM / COUNT / MIN.
- Ranking is computed in Python after the aggregate (avoids a window-function
  portability issue with SQLite); the dataset per category is small.
- Rank tie-breaking: total_points DESC → podiums DESC → best_position ASC.
- Soft-deleted rows (``deleted_at IS NOT NULL``) are excluded at SQL level.
- ``is_our_club = aggregate row's competitor_id has athlete_id IS NOT NULL``
  (any result row in the season where athlete_id is set counts).

Privacy (Ley 1581)
------------------
- Logs contain only ids and counts — no names.
- Parent scoping: when ``allowed_athlete_ids`` is a ``set``, only aggregate
  rows whose competitor maps to an athlete in that set are returned.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import Integer, and_, asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.schemas.race_results import CategoryStandings, EventStandingsRead, StandingRow

logger = logging.getLogger(__name__)


async def get_event_standings(
    db: AsyncSession,
    race_event_id: int,
    *,
    category_id: Optional[int] = None,
    club_only: bool = False,
    allowed_athlete_ids: Optional[set[int]] = None,
) -> Optional[EventStandingsRead]:
    """Return the season cumulative standings for the series of the given event.

    Parameters
    ----------
    db:
        Async SQLAlchemy session.
    race_event_id:
        PK of the ``race_events`` row whose series is used for the standings.
    category_id:
        When provided, only standings for this category are returned.
    club_only:
        When ``True``, only rows with a confirmed club athlete link are included.
    allowed_athlete_ids:
        ``None`` → no restriction (coach / admin).
        ``set``  → parent scope; only rows whose competitor maps to an athlete
                   in this set are included.  Empty set → zero rows returned.

    Returns
    -------
    ``EventStandingsRead`` when the event and its series exist, or ``None``
    when the event does not exist or has no series.
    """
    # 1. Resolve event → series → season in one query.
    evt_row = (
        await db.execute(
            select(
                RaceEvent.id,
                RaceEvent.series_id,
                RaceSeries.season_year,
            )
            .join(RaceSeries, RaceSeries.id == RaceEvent.series_id)
            .where(RaceEvent.id == race_event_id)
        )
    ).mappings().one_or_none()

    if evt_row is None:
        return None

    series_id: int = evt_row["series_id"]
    season_year: int = evt_row["season_year"]

    # 2. Parent-scope early exit.
    if allowed_athlete_ids is not None and not allowed_athlete_ids:
        return EventStandingsRead(
            race_event_id=race_event_id,
            series_id=series_id,
            season_year=season_year,
            categories=[],
        )

    # 3. Aggregate query across ALL events in the same series.
    #
    #    We compute per (category_id, competitor_id):
    #      - total_points  = SUM(points_awarded)
    #      - races_run     = COUNT(*)  — one row per event the competitor ran
    #      - podiums       = SUM(position IN (1,2,3))  → using CASE
    #      - best_position = MIN(position)
    #
    #    We also pull max(athlete_id) to determine is_our_club for rows where
    #    the competitor is linked to a club athlete in at least one event.
    #
    #    Soft-deleted rows are excluded.  Only events in the same series.

    subq_events = select(RaceEvent.id).where(RaceEvent.series_id == series_id)

    podium_case = func.sum(
        func.cast(
            and_(RaceResult.position.is_not(None), RaceResult.position <= 3),
            Integer,
        )
    ).label("podiums")

    stmt = (
        select(
            RaceResult.category_id,
            RaceResult.competitor_id,
            func.sum(RaceResult.points_awarded).label("total_points"),
            func.count().label("races_run"),
            podium_case,
            func.min(RaceResult.position).label("best_position"),
            # Use max(athlete_id) — non-null wins over null in the group.
            func.max(RaceResult.athlete_id).label("athlete_id"),
            RaceCompetitor.display_name,
            RaceCompetitor.club_text,
            RaceCategory.code.label("category_code"),
            RaceCategory.label.label("category_label"),
            RaceCategory.sort_order.label("category_sort_order"),
        )
        .join(RaceCompetitor, RaceCompetitor.id == RaceResult.competitor_id)
        .join(RaceCategory, RaceCategory.id == RaceResult.category_id)
        .where(
            RaceResult.event_id.in_(subq_events),
            RaceResult.deleted_at.is_(None),
        )
        .group_by(
            RaceResult.category_id,
            RaceResult.competitor_id,
            RaceCompetitor.display_name,
            RaceCompetitor.club_text,
            RaceCategory.code,
            RaceCategory.label,
            RaceCategory.sort_order,
        )
        .order_by(asc(RaceCategory.sort_order))
    )

    if category_id is not None:
        stmt = stmt.where(RaceResult.category_id == category_id)

    if club_only:
        stmt = stmt.where(RaceResult.athlete_id.is_not(None))

    if allowed_athlete_ids is not None:
        stmt = stmt.where(RaceResult.athlete_id.in_(allowed_athlete_ids))

    agg_rows = (await db.execute(stmt)).mappings().all()

    # 4. Group aggregate rows by category and rank within each category.
    #    Tie-breaking: total_points DESC → podiums DESC → best_position ASC.

    cat_buckets: dict[int, dict] = {}
    for row in agg_rows:
        cat_id = row["category_id"]
        if cat_id not in cat_buckets:
            cat_buckets[cat_id] = {
                "category_id": cat_id,
                "code": row["category_code"],
                "label": row["category_label"],
                "sort_order": row["category_sort_order"],
                "raw_rows": [],
            }
        cat_buckets[cat_id]["raw_rows"].append(row)

    # Sort categories by sort_order (already from SQL, but defensive).
    sorted_cats = sorted(cat_buckets.values(), key=lambda c: c["sort_order"])

    categories: list[CategoryStandings] = []
    for cat in sorted_cats:
        raw = cat["raw_rows"]
        # Sort for ranking.
        def _sort_key(r):  # noqa: E306  (inline closure is fine here)
            bp = r["best_position"] if r["best_position"] is not None else 9999
            return (-(r["total_points"] or 0), -(r["podiums"] or 0), bp)

        raw_sorted = sorted(raw, key=_sort_key)

        standing_rows: list[StandingRow] = []
        for rank, row in enumerate(raw_sorted, start=1):
            standing_rows.append(
                StandingRow(
                    rank=rank,
                    competitor_id=row["competitor_id"],
                    display_name=row["display_name"],
                    club_text=row["club_text"],
                    athlete_id=row["athlete_id"],
                    is_our_club=(row["athlete_id"] is not None),
                    total_points=row["total_points"] or 0,
                    races_run=row["races_run"] or 0,
                    podiums=row["podiums"] or 0,
                    best_position=row["best_position"],
                )
            )

        categories.append(
            CategoryStandings(
                category_id=cat["category_id"],
                code=cat["code"],
                label=cat["label"],
                rows=standing_rows,
            )
        )

    logger.info(
        "race_standings_read event_id=%s series_id=%s categories=%s",
        race_event_id,
        series_id,
        len(categories),
    )

    return EventStandingsRead(
        race_event_id=race_event_id,
        series_id=series_id,
        season_year=season_year,
        categories=categories,
    )
