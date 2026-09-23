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
- Feature 045 (T015) attaches per-row ``metrics`` WITHOUT a further query:
  the metrics engine (``field_metrics.compute_category_metrics``) runs once
  per category over the rows this same query already loaded. Total budget
  stays at 3 statements (event check + course setups + results).
- Soft-deleted rows (``deleted_at IS NOT NULL``) are excluded at SQL level.
- ``is_our_club = RaceResult.athlete_id IS NOT NULL`` (single-club app; any
  confirmed competitor link means "our club").
- Returns ``None`` when the race event does not exist (caller raises 404).

Metrics vs. visibility (feature 045)
------------------------------------
Parrilla, Percentil and the gaps are properties of the WHOLE category, so
they must be computed over every non-deleted row of it. ``club_only`` and the
parent scope (``allowed_athlete_ids``) only decide which rows are *returned*;
they are applied in Python AFTER the metrics run (a parent's single child in
the SQL result would otherwise yield ``field_size=1`` and no percentile).
The ``category_id`` filter stays in SQL — it never splits a category.

Parent scoping: when ``allowed_athlete_ids`` is a ``set`` (not ``None``),
only rows whose ``athlete_id`` is in that set reach ``ResultRow`` /
``CategoryResults`` — rows of other competitors are dropped before any schema
object is built, and a parent's rows carry the family metric subset only
(``FamilyMetricSet``: no winner/podium gaps).

Privacy (Ley 1581)
------------------
- Logs contain only ``event_id`` and row count — no competitor names.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import Select, asc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.race_category import RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult, ResultStatus
from app.schemas.race_results import (
    CategoryResults,
    CoachMetricSet,
    EventResultsRead,
    FamilyMetricSet,
    ResultRow,
)
from app.services.race.audience import Audience, redact_for_audience
from app.services.race.course.derived import derive_figures
from app.services.race.field_metrics import MetricInput, MetricSet, compute_category_metrics

logger = logging.getLogger(__name__)

# Typed wire shape per audience. WHICH fields each audience may see is decided
# by ``audience.py`` (single policy); these classes only give it a schema.
_METRICS_SCHEMA: dict[Audience, type[FamilyMetricSet]] = {
    Audience.COACH: CoachMetricSet,
    Audience.FAMILY: FamilyMetricSet,
}


@dataclass(frozen=True)
class _MetricInput:
    """A ``RaceResult`` stand-in that satisfies the engine's ``MetricInput``.

    The results query returns column mappings, not ORM entities. This carries
    exactly the attributes ``field_metrics.MetricInput`` declares (``id`` /
    ``event_id`` / ``category_id`` / ``status`` / ``position`` /
    ``race_time_ms`` / ``deleted_at``). It satisfies the Protocol structurally
    (a frozen dataclass cannot inherit its read-only properties), and
    ``_metrics_by_result`` types its rows as ``MetricInput`` so a drift in
    either side is caught where they meet. The query already excludes
    soft-deleted rows, hence ``deleted_at`` is always ``None``.
    """

    id: int
    event_id: int
    category_id: int
    status: ResultStatus
    position: Optional[int]
    race_time_ms: Optional[int]
    deleted_at: None = None


def _enum_value(value: Any) -> str:
    """Enum member → its ``.value``; anything else → ``str(value)``."""
    return value.value if hasattr(value, "value") else str(value)


def _build_results_stmt(
    race_event_id: int, category_id: Optional[int]
) -> Select[Any]:
    """Aggregated results query: results → competitors → categories.

    ORDER BY: category sort_order then position ASC (NULLs last via the
    ``IS NULL`` flag — MySQL/MariaDB have no NULLS LAST). Deliberately NOT
    filtered by ``club_only`` / parent scope: metrics need the whole category
    (see the module docstring, "Metrics vs. visibility").
    """
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
            RaceResult.category_label_raw,
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
            asc(RaceResult.position.is_(None)),
            asc(RaceResult.position),
            asc(RaceResult.competitor_id),  # stable tie-break
        )
    )
    if category_id is not None:
        stmt = stmt.where(RaceResult.category_id == category_id)
    return stmt


def _is_visible(
    row: Mapping[str, Any],
    *,
    club_only: bool,
    allowed_athlete_ids: Optional[set[int]],
) -> bool:
    """Whether the caller may receive this row (club filter + parent scope)."""
    athlete_id = row["athlete_id"]
    if club_only and athlete_id is None:
        return False
    if allowed_athlete_ids is not None and athlete_id not in allowed_athlete_ids:
        return False
    return True


def _metrics_by_result(
    rows: Sequence[Mapping[str, Any]], race_event_id: int
) -> dict[int, MetricSet]:
    """One engine batch per category over the already-loaded rows (no I/O)."""
    by_category: dict[int, list[MetricInput]] = defaultdict(list)
    for row in rows:
        by_category[row["category_id"]].append(
            _MetricInput(
                id=row["id"],
                event_id=race_event_id,
                category_id=row["category_id"],
                status=ResultStatus(_enum_value(row["status"])),
                position=row["position"],
                race_time_ms=row["race_time_ms"],
            )
        )

    metrics: dict[int, MetricSet] = {}
    for cat_id, category_rows in by_category.items():
        metrics.update(compute_category_metrics(category_rows, race_event_id, cat_id))
    return metrics


def _to_result_metrics(
    metric_set: MetricSet, audience: Audience
) -> FamilyMetricSet:
    """Engine ``MetricSet`` → response schema for ``audience``.

    The audience policy strips the excluded keys (winner / podium gaps for a
    family: removed, not nulled) and the audience's schema types what is left.
    """
    visible = redact_for_audience(dict(metric_set), audience)
    return _METRICS_SCHEMA[audience](**visible)


def _build_result_row(
    row: Mapping[str, Any],
    setup: Optional[RaceCourseCategorySetup],
    metric_set: MetricSet,
    *,
    audience: Audience,
) -> ResultRow:
    status_str = _enum_value(row["status"])
    figures = derive_figures(setup, status_str, row["race_time_ms"], row["laps_behind"])
    return ResultRow(
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
        # Feature 044 (R-04): etiqueta congelada al insertar, con
        # respaldo en la del catálogo para filas previas al backfill.
        category_label=row["category_label_raw"] or row["category_label"],
        # FR-005 / SC-005: coach_note is coach/admin-only — a parent never
        # sees the coach's private qualitative note, even on their own
        # child's row.
        coach_note=None if audience is Audience.FAMILY else row["coach_note"],
        coach_note_updated_at=(
            None if audience is Audience.FAMILY else row["coach_note_updated_at"]
        ),
        distance_km=figures.distance_km,
        avg_speed_kmh=figures.avg_speed_kmh,
        lap_distance_km=figures.lap_distance_km,
        elevation_gain_m=figures.elevation_gain_m,
        metrics=_to_result_metrics(metric_set, audience),
    )


def _group_by_category(
    visible_rows: Sequence[Mapping[str, Any]],
    metrics: Mapping[int, MetricSet],
    setup_by_category: Mapping[int, RaceCourseCategorySetup],
    *,
    audience: Audience,
) -> list[CategoryResults]:
    """Group visible rows into ``CategoryResults`` (SQL order preserved)."""
    categories_map: dict[int, dict[str, Any]] = {}
    for row in visible_rows:
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
        categories_map[cat_id]["rows"].append(
            _build_result_row(row, setup, metrics[row["id"]], audience=audience)
        )
    return [CategoryResults(**v) for v in categories_map.values()]


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
        Trocha y Ruta athletes) are returned. Metrics still consider the whole
        category.
    allowed_athlete_ids:
        ``None`` → no restriction (coach / admin).
        ``set``  → parent scope: only rows whose ``athlete_id`` is in this set
                   are returned, with the family metric subset. An empty set
                   returns zero rows.

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

    def _response(categories: list[CategoryResults]) -> EventResultsRead:
        return EventResultsRead(
            race_event_id=race_event_id,
            event_name=event_row["name"],
            event_date=event_row["event_date"],
            location=event_row["location"],
            status=_enum_value(event_row["status"]),
            has_course_data=has_course_data,
            categories=categories,
        )

    # Parent with no linked children: nothing to show, nothing to compute.
    if allowed_athlete_ids is not None and not allowed_athlete_ids:
        return _response([])

    # 2. Whole-category rows in one round-trip; metrics next, visibility last.
    rows = (
        await db.execute(_build_results_stmt(race_event_id, category_id))
    ).mappings().all()

    metrics = _metrics_by_result(rows, race_event_id)
    visible_rows = [
        r
        for r in rows
        if _is_visible(r, club_only=club_only, allowed_athlete_ids=allowed_athlete_ids)
    ]
    # ``allowed_athlete_ids`` is only ever set for a parent scope (see
    # ``permissions.allowed_athlete_ids_for``): that is the family audience.
    audience = Audience.COACH if allowed_athlete_ids is None else Audience.FAMILY
    category_list = _group_by_category(
        visible_rows, metrics, setup_by_category, audience=audience
    )

    logger.info(
        "race_results_read event_id=%s categories=%s total_rows=%s",
        race_event_id,
        len(category_list),
        len(visible_rows),
    )
    return _response(category_list)
