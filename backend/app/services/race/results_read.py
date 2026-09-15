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
- Feature 043 (US2) adds exactly one course-setup query
  (``RaceCourseCategorySetup`` + eager-loaded ``variant``), always run once
  per call regardless of row/category count — the hard "+1 statement"
  performance contract. Distance/speed figures are derived in Python via
  ``course.derived.derive_figures`` — never a query per row.
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
from sqlalchemy.orm import selectinload

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.schemas.race_results import CategoryResults, EventResultsRead, ResultRow
from app.services.race.course.derived import derive_figures

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

    # 1b. Course setups (feature 043, US2) — exactly one extra query, run
    #     once per call regardless of row/category count (contract:
    #     "get_event_results runs exactly one more statement than before").
    #     Keyed by category_id since a category can only have one setup per
    #     race_event_id (unique constraint). ``has_course_data`` is derived
    #     from this same query alone: a variant uploaded but not yet
    #     assigned to any category setup renders no distance/speed for any
    #     row either way, so gating the results columns on "at least one
    #     setup exists" (rather than "at least one variant exists") is both
    #     the more useful signal for this endpoint and what keeps the query
    #     count a hard, unconditional +1 — a second variant-exists fallback
    #     query would only fire in that narrow interim state and would
    #     violate the performance contract. The course tab's own
    #     ``has_course_data`` (whether a variant exists at all, independent
    #     of setups) is a deliberately different definition in
    #     ``course/service.py``, for a different UI surface.
    setup_rows = (
        await db.execute(
            select(RaceCourseCategorySetup)
            .options(selectinload(RaceCourseCategorySetup.variant))
            .where(RaceCourseCategorySetup.race_event_id == race_event_id)
        )
    ).scalars().all()
    setup_by_category: dict[int, RaceCourseCategorySetup] = {
        s.category_id: s for s in setup_rows
    }
    has_course_data = bool(setup_by_category)

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
            RaceResult.coach_note,
            RaceResult.coach_note_updated_at,
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
            # MySQL/MariaDB has no NULLS LAST: order by the IS NULL flag first
            # (False=0 sorts before True=1) so NULL positions land last.
            asc(RaceResult.position.is_(None)),
            asc(RaceResult.position),
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
                has_course_data=has_course_data,
                categories=[],
            )
        stmt = stmt.where(RaceResult.athlete_id.in_(allowed_athlete_ids))

    rows = (await db.execute(stmt)).mappings().all()

    # 3. Group into CategoryResults.
    #    We preserve insertion order (already sorted by sort_order from SQL).
    categories_map: dict[int, dict] = {}
    for row in rows:
        cat_id = row["category_id"]
        setup = setup_by_category.get(cat_id)
        if cat_id not in categories_map:
            categories_map[cat_id] = {
                "category_id": cat_id,
                "code": row["category_code"],
                "label": row["category_label"],
                "laps": setup.laps if setup is not None else None,
                "variant_label": setup.variant.label if setup is not None else None,
                "rows": [],
            }
        # FR-005 / SC-005: coach_note is coach/admin-only. When
        # allowed_athlete_ids is a set (parent scope), suppress it so
        # parents never see the coach's private qualitative note, even
        # for their own child's result row.
        is_parent_scope = allowed_athlete_ids is not None
        status_str = row["status"].value if hasattr(row["status"], "value") else str(row["status"])
        figures = derive_figures(setup, status_str, row["race_time_ms"], row["laps_behind"])
        categories_map[cat_id]["rows"].append(
            ResultRow(
                result_id=row["id"],
                position=row["position"],
                competitor_id=row["competitor_id"],
                display_name=row["display_name"],
                club_text=row["club_text"],
                athlete_id=row["athlete_id"],
                is_our_club=(row["athlete_id"] is not None),
                status=status_str,
                race_time_ms=row["race_time_ms"],
                laps_behind=row["laps_behind"],
                points_awarded=row["points_awarded"] if row["points_awarded"] is not None else 0,
                bib_number=row["bib_number"],
                coach_note=None if is_parent_scope else row["coach_note"],
                coach_note_updated_at=None if is_parent_scope else row["coach_note_updated_at"],
                distance_km=figures.distance_km,
                avg_speed_kmh=figures.avg_speed_kmh,
                lap_distance_km=figures.lap_distance_km,
                elevation_gain_m=figures.elevation_gain_m,
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
        has_course_data=has_course_data,
        categories=category_list,
    )
