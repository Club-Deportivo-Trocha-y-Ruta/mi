"""Service: per-event finishing order grouped by category.

Public surface
--------------
``get_event_results(db, race_event_id, *, category_id, club_only,
                    allowed_athlete_ids)``
    → ``EventResultsRead | None``

Design constraints
------------------
- Single aggregated query (one round-trip) joining race_results → race_competitors
  → race_categories.  No N+1.
- Soft-deleted rows (``deleted_at IS NOT NULL``) are excluded at SQL level.
- ``is_our_club = RaceResult.athlete_id IS NOT NULL`` (single-club app; any
  confirmed competitor link means "our club").
- Parent scoping: when ``allowed_athlete_ids`` is a ``set`` (not ``None``),
  only rows whose ``athlete_id`` is in that set are returned.
- Returns ``None`` when the race event does not exist (caller raises 404).

Privacy (Ley 1581)
------------------
- Logs contain only ``event_id`` and row count — no competitor names.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.schemas.race_results import CategoryResults, EventResultsRead, ResultRow

logger = logging.getLogger(__name__)


async def get_event_results(
    db: AsyncSession,
    race_event_id: int,
    *,
    category_id: Optional[int] = None,
    club_only: bool = False,
    allowed_athlete_ids: Optional[set[int]] = None,
) -> Optional[EventResultsRead]:
    """Return the per-event finishing order grouped by category.

    Parameters
    ----------
    db:
        Async SQLAlchemy session.
    race_event_id:
        PK of the ``race_events`` row to read results for.
    category_id:
        When provided, only results for this category are returned.
    club_only:
        When ``True``, only rows with ``athlete_id IS NOT NULL`` (i.e. confirmed
        Trocha y Ruta athletes) are included.
    allowed_athlete_ids:
        ``None`` → no restriction (coach / admin).
        ``set``  → parent scope: only rows whose ``athlete_id`` is in this set
                   are included.  An empty set returns zero rows.

    Returns
    -------
    ``EventResultsRead`` when the event exists (categories may be empty lists
    if there are no non-deleted results), or ``None`` if the event does not exist.
    """
    # 1. Verify the event exists and fetch metadata — single lightweight check.
    event_row = (
        await db.execute(
            select(
                RaceEvent.id,
                RaceEvent.name,
                RaceEvent.event_date,
                RaceEvent.location,
                RaceEvent.status,
            ).where(RaceEvent.id == race_event_id)
        )
    ).mappings().one_or_none()
    if event_row is None:
        return None

    # 2. Build the aggregated query: results → competitors → categories.
    #    ORDER BY: category sort_order then position ASC (NULLs last via CASE).
    #
    #    SQLite and MySQL both support ``asc().nullslast()`` via SQLAlchemy 2.
    stmt = (
        select(
            RaceResult.id,
            RaceResult.position,
            RaceResult.competitor_id,
            RaceResult.athlete_id,
            RaceResult.status,
            RaceResult.race_time_ms,
            RaceResult.laps_behind,
            RaceResult.points_awarded,
            RaceResult.bib_number,
            RaceResult.category_id,
            RaceCompetitor.display_name,
            RaceCompetitor.club_text,
            RaceCategory.code.label("category_code"),
            RaceCategory.label.label("category_label"),
            RaceCategory.sort_order.label("category_sort_order"),
        )
        .join(RaceCompetitor, RaceCompetitor.id == RaceResult.competitor_id)
        .join(RaceCategory, RaceCategory.id == RaceResult.category_id)
        .where(
            RaceResult.event_id == race_event_id,
            RaceResult.deleted_at.is_(None),
        )
        .order_by(
            asc(RaceCategory.sort_order),
            asc(RaceResult.position).nulls_last(),
            asc(RaceResult.competitor_id),  # stable tie-break
        )
    )

    if category_id is not None:
        stmt = stmt.where(RaceResult.category_id == category_id)

    if club_only:
        stmt = stmt.where(RaceResult.athlete_id.is_not(None))

    if allowed_athlete_ids is not None:
        # Parent scope: only show their own children's rows.
        if not allowed_athlete_ids:
            # Empty set → no results for this parent.
            return EventResultsRead(
                race_event_id=race_event_id,
                event_name=event_row["name"],
                event_date=event_row["event_date"],
                location=event_row["location"],
                status=event_row["status"].value if hasattr(event_row["status"], "value") else str(event_row["status"]),
                categories=[],
            )
        stmt = stmt.where(RaceResult.athlete_id.in_(allowed_athlete_ids))

    rows = (await db.execute(stmt)).mappings().all()

    # 3. Group into CategoryResults.
    #    We preserve insertion order (already sorted by sort_order from SQL).
    categories_map: dict[int, dict] = {}
    for row in rows:
        cat_id = row["category_id"]
        if cat_id not in categories_map:
            categories_map[cat_id] = {
                "category_id": cat_id,
                "code": row["category_code"],
                "label": row["category_label"],
                "rows": [],
            }
        categories_map[cat_id]["rows"].append(
            ResultRow(
                position=row["position"],
                competitor_id=row["competitor_id"],
                display_name=row["display_name"],
                club_text=row["club_text"],
                athlete_id=row["athlete_id"],
                is_our_club=(row["athlete_id"] is not None),
                status=row["status"].value if hasattr(row["status"], "value") else str(row["status"]),
                race_time_ms=row["race_time_ms"],
                laps_behind=row["laps_behind"],
                points_awarded=row["points_awarded"] if row["points_awarded"] is not None else 0,
                bib_number=row["bib_number"],
            )
        )

    category_list = [CategoryResults(**v) for v in categories_map.values()]

    logger.info(
        "race_results_read event_id=%s categories=%s total_rows=%s",
        race_event_id,
        len(category_list),
        len(rows),
    )

    return EventResultsRead(
        race_event_id=race_event_id,
        event_name=event_row["name"],
        event_date=event_row["event_date"],
        location=event_row["location"],
        status=event_row["status"].value if hasattr(event_row["status"], "value") else str(event_row["status"]),
        categories=category_list,
    )
