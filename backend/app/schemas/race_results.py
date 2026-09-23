"""Pydantic v2 read schemas for the race results and season standings endpoints.

These schemas are intentionally read-only (no mutation paths here).  All
``display_name`` / ``club_text`` fields come from ``race_competitors`` which
was populated during PDF ingestion — they are **not** athlete PII (no DOB,
medical data, or minor's full legal name appears on results pages).

Privacidad Ley 1581:
- ``athlete_id`` is only included to let the frontend apply club-highlight
  logic; it is a numeric FK, not a name or identifying string.
- Parent-scoped responses are filtered in the service layer before the schema
  is ever constructed, so no cross-athlete rows reach this layer.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Per-row metrics (feature 045, data-model.md §1 / §4)
# ---------------------------------------------------------------------------


class FamilyMetricSet(BaseModel):
    """Metrics a family (parent) may see for a result row — the typed wire
    shape of the family variant.

    *What* a family may see is decided by ``services.race.audience``
    (``FAMILY_EXCLUDED_METRIC_FIELDS``, the audience policy); this class only
    gives that decision a schema. Both must agree: this field set equals
    ``MetricSet`` minus the excluded fields, and a test pins it
    (``test_results_read_metrics.py``), so the two cannot drift apart.

    Values come from ``services.race.field_metrics.compute_category_metrics``
    (the one metrics engine); nothing is recomputed in the schema layer.
    """

    field_size: int = Field(
        ..., description="«Parrilla»: finishers (FINISHED + MINUS_LAPS) in the category."
    )
    timed_finishers: int = Field(
        ...,
        description="FINISHED riders with a time — the denominator of percentile and median gap.",
    )
    position: Optional[int] = Field(
        None, description="Official position. None for DNF/DNS/DSQ."
    )
    percentile: Optional[float] = Field(
        None,
        description=(
            "Time-based percentile (100 = fastest, 0 = slowest). None below 5 "
            "timed finishers, for non-timed results, or when all times tie."
        ),
    )
    gap_to_median_pct: Optional[float] = Field(
        None,
        description="«Brecha vs. mediana» (%). Same None rules as ``percentile``.",
    )


class CoachMetricSet(FamilyMetricSet):
    """Full metric set — coach / admin only (never serialized for parents).

    The extra fields are *required* (nullable, no default) on purpose: a
    family payload lacks them, so it can never validate as a
    ``CoachMetricSet`` when FastAPI re-validates the response through the
    ``Coach | Family`` union — which would re-introduce them as ``null``.
    """

    gap_to_winner_pct: Optional[float] = Field(
        ..., description="«Brecha vs. 1.ª posición» (%) against the official P1 time."
    )
    gap_to_winner_ms: Optional[int] = Field(
        ..., description="Milliseconds behind the official P1 time."
    )
    gap_to_podium_pct: Optional[float] = Field(
        ..., description="«Brecha vs. podio» (%) against the official P3 time."
    )
    gap_to_podium_ms: Optional[int] = Field(
        ..., description="Milliseconds behind the official P3 time."
    )


# ---------------------------------------------------------------------------
# Per-event finishing order
# ---------------------------------------------------------------------------


class ResultRow(BaseModel):
    """One competitor's result in a single event / category."""

    result_id: int = Field(..., description="PK of the race_results row.")
    position: Optional[int] = Field(
        None,
        description="Finishing position (1-based). None for DNF/DNS/DSQ.",
    )
    competitor_id: int
    display_name: str = Field(
        ...,
        description="Competitor name as it appeared in the official PDF.",
    )
    club_text: Optional[str] = Field(
        None,
        description="Club as printed in the PDF (raw, not normalized).",
    )
    athlete_id: Optional[int] = Field(
        None,
        description="FK to athletes.id when this competitor is a confirmed club athlete.",
    )
    is_our_club: bool = Field(
        ...,
        description="True when athlete_id is not None (confirmed Trocha y Ruta athlete).",
    )
    status: str = Field(..., description="Result status: finished/dnf/dns/dsq/minus_laps.")
    race_time_ms: Optional[int] = Field(
        None, description="Race time in milliseconds (only for 'finished' status)."
    )
    laps_behind: Optional[int] = Field(
        None, description="Laps behind the winner (only for 'minus_laps' status)."
    )
    points_awarded: int = Field(..., description="Points credited to the competitor.")
    bib_number: Optional[int] = Field(None, description="Race bib number.")
    category_label: str = Field(
        ...,
        description=(
            "Feature 044: etiqueta congelada de la categoría al momento de "
            "cargar este resultado (``category_label_raw``), o la etiqueta "
            "vigente del catálogo cuando el resultado es anterior a la "
            "migración de backfill. Nunca cambia si el catálogo se edita "
            "después — ver research.md R-04."
        ),
    )
    coach_note: Optional[str] = Field(
        None,
        description="Coach qualitative note for this result (max 500 chars). None if not set.",
    )
    coach_note_updated_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp of the last coach note update. None if no note set.",
    )
    distance_km: Optional[float] = Field(
        None,
        description=(
            "Distancia recorrida derivada del setup de recorrido de la "
            "categoría (feature 043). None si la categoría no tiene "
            "recorrido configurado, si la dinámica de la carrera no permite "
            "calcularla (DNF/DNS/DSQ o minus_laps sin laps_behind), o si el "
            "resultado quedó en cero/negativo vueltas completadas."
        ),
    )
    avg_speed_kmh: Optional[float] = Field(
        None,
        description="Velocidad promedio derivada. Ver distance_km para las condiciones de None.",
    )
    lap_distance_km: Optional[float] = Field(
        None,
        description="Distancia de una vuelta del recorrido asignado. None sin setup de recorrido.",
    )
    elevation_gain_m: Optional[int] = Field(
        None,
        description="Desnivel positivo acumulado de la variante de recorrido. None sin dato de altitud.",
    )
    # ``CoachMetricSet`` first: with a plain dict (FastAPI re-validates the
    # dumped response) it is the only member that accepts the 8-key coach
    # payload; the 5-key family payload cannot satisfy it and falls through
    # to ``FamilyMetricSet``.
    metrics: Optional[Union[CoachMetricSet, FamilyMetricSet]] = Field(
        None,
        description=(
            "Feature 045: per-row metrics computed over the WHOLE category "
            "(not just the rows this caller may see). Coach/admin get "
            "``CoachMetricSet``; parents get ``FamilyMetricSet`` — winner and "
            "podium gaps are omitted from their payload, not nulled."
        ),
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Coach note mutation schemas
# ---------------------------------------------------------------------------


class CoachNoteUpdate(BaseModel):
    """Request body for PUT /race-results/{result_id}/coach-note."""

    coach_note: str = Field(
        ...,
        description="Coach qualitative note for the result (1–500 characters, stripped).",
    )

    @field_validator("coach_note")
    @classmethod
    def validate_coach_note(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("coach_note must not be empty or whitespace-only.")
        if len(stripped) > 500:
            raise ValueError(
                f"coach_note exceeds 500 characters (got {len(stripped)})."
            )
        return stripped


class CategoryResults(BaseModel):
    """All result rows for one category within an event."""

    category_id: int
    code: str = Field(..., description="Category code, e.g. 'INF_M'.")
    label: str = Field(..., description="Human-readable category label.")
    laps: Optional[int] = Field(
        None,
        description="Vueltas configuradas para esta categoría en la válida (feature 043). None sin setup.",
    )
    variant_label: Optional[str] = Field(
        None,
        description="Nombre de la variante de recorrido asignada. None sin setup de recorrido.",
    )
    rows: list[ResultRow]


class EventResultsRead(BaseModel):
    """Full per-event finishing order grouped by category.

    Categories are ordered by ``RaceCategory.sort_order``; within each
    category rows are ordered by (position ASC NULLS LAST, competitor_id ASC).

    Event metadata fields allow the frontend to render a page header without
    a separate coach-only detail call (no minor PII included).
    """

    race_event_id: int
    event_name: str = Field(..., description="Official name of the race event.")
    event_date: date = Field(..., description="Date the race was held.")
    location: Optional[str] = Field(None, description="Municipality / venue of the race.")
    status: str = Field(..., description="RaceEventStatus value (scheduled/completed/cancelled).")
    has_course_data: bool = Field(
        default=False,
        description=(
            "True si la válida tiene al menos un setup de recorrido por "
            "categoría o al menos una variante de recorrido registrada "
            "(feature 043), sin importar cuántas filas de resultados "
            "existan para el parent que consulta."
        ),
    )
    categories: list[CategoryResults]


# ---------------------------------------------------------------------------
# Season standings
# ---------------------------------------------------------------------------


class StandingRow(BaseModel):
    """One competitor's cumulative standing for a series / season / category."""

    rank: int = Field(..., description="Rank within this category (1-based, by points DESC).")
    competitor_id: int
    display_name: str = Field(
        ...,
        description="Competitor name as it appeared in the official PDF.",
    )
    club_text: Optional[str] = None
    athlete_id: Optional[int] = Field(
        None,
        description="FK to athletes.id when confirmed as a club athlete.",
    )
    is_our_club: bool = Field(
        ...,
        description="True when athlete_id is not None.",
    )
    total_points: int = Field(..., description="Sum of points_awarded across all events.")
    races_run: int = Field(..., description="Number of events where this competitor finished.")
    podiums: int = Field(..., description="Number of top-3 finishes.")
    best_position: Optional[int] = Field(
        None, description="Best finishing position across the season."
    )


class CategoryStandings(BaseModel):
    """Ranked standings for one category within a series / season."""

    category_id: int
    code: str
    label: str
    rows: list[StandingRow]


class EventStandingsRead(BaseModel):
    """Season general standings scoped to the series of the given race event.

    Categories are ordered by ``RaceCategory.sort_order``; within each
    category rows are ordered by rank ASC (ties broken by podiums DESC,
    then best_position ASC).

    Event metadata fields allow the frontend to render a page header without
    a separate coach-only detail call (no minor PII included).
    """

    race_event_id: int
    event_name: str = Field(..., description="Official name of the anchor race event.")
    event_date: date = Field(..., description="Date the anchor race was held.")
    location: Optional[str] = Field(None, description="Municipality / venue of the anchor race.")
    status: str = Field(..., description="RaceEventStatus value of the anchor event.")
    series_id: int
    season_year: int
    categories: list[CategoryStandings]
    # Feature 044 (US5, T062, research R-10): siempre True — esta tabla SIEMPRE
    # es una suma de `points_awarded` calculada por la plataforma directamente
    # sobre `race_results` (ver docstring del módulo), nunca una copia de la
    # clasificación final que publica el organizador. Se hace explícito porque
    # las temporadas históricas (2024/2025) no tienen ningún esquema de puntos
    # oficial contra el cual reconciliar — la UI muestra "Clasificación
    # calculada por la plataforma" a partir de este flag.
    is_calculated: bool = Field(
        default=True,
        description="True (siempre): la tabla es una suma de puntos impresos, no la clasificación oficial del organizador.",
    )
