"""Schemas for the growth summary endpoint (feature 040 / T033).

`GrowthSummaryOut` is the payload of `GET /athletes/{athlete_id}/growth-summary`
(``routers/growth.py``). It is a pure read model built from the two latest
`anthropometric_records` rows: every Z-score, percentile and band is copied
from what `POST /athletes/{id}/anthropometry` already computed and stored
against WHO 2007 (feature 040) — this endpoint never recomputes them.

Privacy (Ley 1581 / CLAUDE.md): the payload carries only ids, dates and
numbers — no athlete name, birth date or notes.

See `specs/040-growth-module-redesign/data-model.md` §3 and
`specs/040-growth-module-redesign/contracts/growth-summary-api.md`.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.models.anthropometry import MaturationStatus, NutritionalStatus
from app.models.growth import GrowthSource
from app.schemas.alerts import MeasurementStatus
from app.schemas.body_composition import BodyCompositionFamilySummary, BodyCompositionSummary


class GrowthSummaryAlert(str, enum.Enum):
    """Alert vocabulary shown on the decision-first coach tab (US2).

    Distinct from ``app.schemas.alerts.GrowthAlert`` (dashboard-wide alerts
    summary, feature 003): this one also covers the p3 and Circa-PHV signals
    that the growth tab needs and the dashboard endpoint does not.
    """

    circa_phv = "circa_phv"
    height_p3 = "height_p3"
    bmi_p3 = "bmi_p3"
    rapid_growth = "rapid_growth"
    approaching_circa = "approaching_circa"
    phase_changed = "phase_changed"


class GrowthVelocity(BaseModel):
    """Height-velocity window between the two latest measurements."""

    cm_per_month: float
    cm_per_year: float
    window_days: int
    interval_short: bool  # window_days < 30 — suppresses `rapid_growth` and its caveat
    expected_cm_per_year: tuple[float, float]  # (min, max), by stage and sex — research.md R-05


class MeasurementDue(BaseModel):
    """Next-measurement scheduling state — same rules as `routers/alerts.py`."""

    status: MeasurementStatus
    interval_days: int
    next_due_date: date | None = None
    days_overdue: int | None = None  # positive int when overdue; None otherwise


class BandReading(BaseModel):
    """One indicator reading with its stored WHO/CDC Z-score, percentile and band."""

    value: float
    z_score: float
    percentile: float
    band: NutritionalStatus


class LatestBands(BaseModel):
    """Height/BMI/weight readings of the latest record, read as stored."""

    record_id: int
    growth_source: GrowthSource | None = None
    height: BandReading | None = None
    bmi: BandReading | None = None
    weight: BandReading | None = None


class LatestAiAnalysis(BaseModel):
    """Resumen del análisis de IA (feature 042) más reciente, para la pestaña
    de crecimiento — coach y familia comparten la misma línea (FR-027).

    Siempre proyectado desde la fila **familiar** (`RECORD_USE_CASE`),
    nunca de la variante `coach`, precisamente porque su `summary_line` está
    libre de cifras (cm/año, meses a PHV) por construcción del prompt — lo
    que la hace segura de mostrar también en modo entrenador. `critic_verdict`
    solo se puebla para el visor coach/admin (compuerta familiar, FR-016) —
    ver `contracts/growth-summary-latest-analysis.md` §0/§2.
    """

    record_id: int
    generated_at: datetime
    schema_version: Literal["v2"] = "v2"
    summary_line: str
    has_warning_signs: bool
    critic_verdict: (
        Literal["approved", "revised", "flagged", "fallback", "skipped"] | None
    ) = None
    is_stale: bool


class GrowthSummaryOut(BaseModel):
    """Decision-first growth summary for one athlete (coach tab, US2)."""

    athlete_id: int
    computed_at: date
    records_count: int
    latest_evaluation_date: date | None = None
    stage: MaturationStatus | None = None
    maturity_offset: float | None = None
    age_at_phv: float | None = None
    months_from_phv: float | None = None  # (age today − age_at_phv) × 12, 1 decimal; negative = before PHV
    velocity: GrowthVelocity | None = None  # None when < 2 records
    measurement: MeasurementDue
    alerts: list[GrowthSummaryAlert] = []
    latest: LatestBands | None = None
    latest_ai_analysis: LatestAiAnalysis | None = None  # feature 042 (T066) — null conditions §4
    # Feature 046 — coach/admin get BodyCompositionSummary, parents get the
    # 5-key BodyCompositionFamilySummary (router picks the variant per role).
    body_composition: BodyCompositionSummary | BodyCompositionFamilySummary | None = None
