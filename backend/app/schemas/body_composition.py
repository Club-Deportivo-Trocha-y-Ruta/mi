"""Schemas for body composition by skinfolds (feature 046).

Source of truth: `specs/046-body-composition-skinfolds/contracts/skinfolds-api.md`
and `specs/046-body-composition-skinfolds/data-model.md` §5-§6. Nothing here
computes anything — values come from `app/services/body_composition.py`.

Privacy (Ley 1581 / CLAUDE.md): these payloads carry only ids, dates, codes
and numeric values — no athlete name, no free-text note about a minor.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SkinfoldSite = Literal[
    "triceps",
    "biceps",
    "subscapular",
    "medial_calf",
    "iliac_crest",
    "supraspinale",
]

SUM_CHANGE_CODE = Literal["none", "within_noise", "up_real", "down_real"]
WEIGHT_CHANGE_CODE = Literal["up", "flat_or_down", "unavailable"]
HEIGHT_GROWTH_CODE = Literal["growing", "stalled", "unavailable"]
VELOCITY_CODE = Literal["within_or_above", "below", "unavailable"]
BMI_Z_CHANGE_CODE = Literal["ok", "drop_moderate", "drop_large", "unavailable"]
REFERENCE_CODE = Literal["low_extreme", "low", "normal", "high", "high_extreme", "unavailable"]
FFM_TREND_CODE = Literal["up", "flat", "down", "unavailable"]
BAND = Literal["verde", "ambar", "rojo"]
FAMILY_BAND = Literal["verde", "ambar"]
LEG_MISSING = Literal["weight", "height", "velocity", "bmi_z", "reference", "previous_set"]
BAND_REASON_CODE = Literal[
    "no_real_change",
    "expected_pubertal_gain",
    "pre_spurt_accumulation",
    "post_phv_lean_gain",
    "first_set",
    "stable",
    "sum_up_unexplained",
    "sum_up_velocity_low",
    "sum_down_unexplained",
    "reference_extreme",
    "bmi_z_drop",
    "velocity_low_persistent",
    "energy_availability_pattern",
]

_READING_STEP = Decimal("0.5")
_READING_MIN = Decimal("2.0")
_READING_MAX = Decimal("60.0")


class SkinfoldSiteIn(BaseModel):
    """One site's input: either an explicit decline or 2–3 raw readings.

    Not a Pydantic tagged union (the wire shape has no shared literal
    discriminator key — `{"declined": true}` vs `{"readings": [...]}`), so
    the "exactly one of" rule is enforced in `model_validator`.
    """

    model_config = ConfigDict(extra="forbid")

    declined: bool = False
    readings: list[Decimal] | None = Field(default=None, min_length=2, max_length=3)

    @model_validator(mode="after")
    def _validate_shape(self) -> "SkinfoldSiteIn":
        if self.declined:
            if self.readings is not None:
                raise ValueError("Un sitio declinado no puede incluir lecturas")
            return self

        if self.readings is None:
            raise ValueError("Debe indicar `readings` o `declined: true`")

        for value in self.readings:
            if value < _READING_MIN or value > _READING_MAX:
                raise ValueError(
                    f"Cada lectura debe estar entre {_READING_MIN} y {_READING_MAX} mm"
                )
            if (value / _READING_STEP) % 1 != 0:
                raise ValueError("Cada lectura debe ser múltiplo de 0.5 mm")
        return self


class SkinfoldSitesIn(BaseModel):
    """All six sites of one set — all required (a site may still decline)."""

    model_config = ConfigDict(extra="forbid")

    triceps: SkinfoldSiteIn
    biceps: SkinfoldSiteIn
    subscapular: SkinfoldSiteIn
    medial_calf: SkinfoldSiteIn
    iliac_crest: SkinfoldSiteIn
    supraspinale: SkinfoldSiteIn


class SkinfoldSetIn(BaseModel):
    """Request body of `PUT .../skinfolds`."""

    model_config = ConfigDict(extra="forbid")

    caliper_model: str = "slim_guide"
    sites: SkinfoldSitesIn


class SkinfoldSiteOut(BaseModel):
    value_mm: float | None = None
    readings: list[float] | None = None
    declined: bool = False
    unconfirmed: bool = False


class SkinfoldSitesOut(BaseModel):
    triceps: SkinfoldSiteOut
    biceps: SkinfoldSiteOut
    subscapular: SkinfoldSiteOut
    medial_calf: SkinfoldSiteOut
    iliac_crest: SkinfoldSiteOut
    supraspinale: SkinfoldSiteOut


class SkinfoldSetOut(BaseModel):
    """Response of `PUT`/item of `GET .../anthropometry` — coach/admin only."""

    record_id: int
    athlete_id: int
    evaluation_date: date
    caliper_model: str
    protocol_version: str
    sites: SkinfoldSitesOut
    sum4_mm: float | None = None
    sum6_mm: float | None = None
    body_fat_pct: float | None = None
    fat_mass_kg: float | None = None
    fat_free_mass_kg: float | None = None
    equation_version: str | None = None
    margin_pct: int = 4
    needs_third_reading_unconfirmed: list[SkinfoldSite] = []
    measured_by: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReferenceContext(BaseModel):
    """One FUPRECOL reference lookup (`contracts/body-composition-reading.md` §2)."""

    percentile: float | None = None
    code: REFERENCE_CODE


class BodyCompositionReading(BaseModel):
    """Pure output of `services/body_composition.py::build_reading` — never persisted."""

    sets_count: int
    sum4_change_mm: float | None = None
    sum6_change_mm: float | None = None
    sum_change_code: SUM_CHANGE_CODE
    weight_change_code: WEIGHT_CHANGE_CODE
    height_growth_code: HEIGHT_GROWTH_CODE
    velocity_code: VELOCITY_CODE
    bmi_z_change_code: BMI_Z_CHANGE_CODE
    reference_triceps: ReferenceContext
    reference_subscapular: ReferenceContext
    ffm_trend_code: FFM_TREND_CODE
    sites_declined_count: int
    band: BAND
    family_band: FAMILY_BAND
    latest_attempt_declined: date | None = None
    band_reason_code: BAND_REASON_CODE
    legs_missing: list[LEG_MISSING] = []
    next_due_date: date | None = None
    days_until_due: int | None = None


class SeriesPoint(BaseModel):
    date: date
    value: float


class BodyCompositionSeries(BaseModel):
    sum4: list[SeriesPoint] = []
    sum6: list[SeriesPoint] = []
    per_site: dict[SkinfoldSite, list[SeriesPoint]] = {}


class BodyCompositionEstimates(BaseModel):
    body_fat_pct: float | None = None
    fat_mass_kg: float | None = None
    fat_free_mass_kg: float | None = None
    equation_version: str | None = None
    margin_pct: int = 4


class BodyCompositionReference(BaseModel):
    source: Literal["FUPRECOL"] = "FUPRECOL"
    population: str = "escolares de Bogotá 2016"
    side: str = "izquierdo"
    age_range: str = "9–17.9"


class BodyCompositionOut(BaseModel):
    """Response of `GET /athletes/{id}/body-composition` — coach/admin only.

    `series`, `reading`, `estimates_latest` and `reference` are `None` in the
    `has_data=false` shape (`sets=[]`), per contract §4.
    """

    athlete_id: int
    sets: list[SkinfoldSetOut] = []
    series: BodyCompositionSeries | None = None
    reading: BodyCompositionReading | None = None
    estimates_latest: BodyCompositionEstimates | None = None
    reference: BodyCompositionReference | None = None
    next_due_date: date | None = None


class BodyCompositionSummary(BaseModel):
    """`GrowthSummaryOut.body_composition` for coach/admin (`data-model.md` §6)."""

    has_data: bool
    latest_set_date: date | None = None
    band: BAND | None = None
    family_band: FAMILY_BAND | None = None
    family_label: str | None = None
    family_sentence: str | None = None
    next_due_date: date | None = None
    days_until_due: int | None = None
    latest_attempt_declined: date | None = None
    coach_reason: str | None = None
    sum4_mm: float | None = None
    sum4_change_mm: float | None = None
    sum_change_code: SUM_CHANGE_CODE | None = None
    sum6_mm: float | None = None
    body_fat_pct: float | None = None
    fat_free_mass_kg: float | None = None
    legs_missing: list[LEG_MISSING] = []


class BodyCompositionFamilySummary(BaseModel):
    """`GrowthSummaryOut.body_composition` for parents — exactly these five keys.

    `family_band` never takes the value `rojo` (contract §3c). `extra="forbid"`
    guards against ever leaking a coach-only field (band, sums, mm values) to
    a family surface.
    """

    model_config = ConfigDict(extra="forbid")

    has_data: bool
    latest_set_date: date | None = None
    family_band: FAMILY_BAND | None = None
    family_label: str | None = None
    family_sentence: str | None = None
