"""Body composition by skinfolds — pure calculations + persistence helpers.

Source of truth: ``specs/046-body-composition-skinfolds/data-model.md`` §1,
§4, §7 and ``specs/046-body-composition-skinfolds/contracts/skinfolds-api.md``
§1, plus ``contracts/body-composition-reading.md`` (change classifier,
traffic light, family projection and the Spanish copy tables) implemented by
``build_reading`` at the bottom of this module.

Inputs / outputs / side effects:
- ``site_value``, ``needs_third_reading``, ``compute_sums``,
  ``estimate_body_fat``, ``fat_masses``, ``plausible_range`` and
  ``classify_sum_change`` are pure numeric functions — no I/O, no ORM.
- ``apply_set`` mutates (and returns) the ``SkinfoldMeasurement`` attached to
  an ``AnthropometricRecord`` from a validated ``SkinfoldSetIn`` payload; it
  does not touch the database session (the caller flushes/commits).
- ``recompute_estimates_for_record`` mutates the existing measurement's
  estimate columns in place (weight-correction hook); no I/O.
- ``check_interval`` reads the database (previous counted sets for the
  athlete) and raises ``SkinfoldIntervalTooShortError`` — no writes.
- ``check_min_age`` is a pure guard over already-loaded objects; raises
  ``AthleteTooYoungError``.
- ``load_reading`` (T080) is the only DB-backed assembler of
  ``build_reading``'s inputs (records + skinfolds in one SELECT, ≤ 1 FUPRECOL
  SELECT); every surface (coach detail, referral note, growth summary,
  newsletter annex, AI leaf) goes through it. Read-only, no logging.
- ``build_reading`` (+ ``compute_legs``, ``classify_band``,
  ``is_reference_only_ambar``, ``project_family_band``) is pure: it reads
  already-loaded ORM objects / schemas and returns a
  ``BodyCompositionReading`` (never persisted). ``FAMILY_COPY``,
  ``NEWSLETTER_NOTICE``, ``COACH_REASON_COPY``, ``ESCALATION_COPY`` and
  ``CHANGE_COPY`` are the only Spanish sentences of the feature.

Privacy (Ley 1581 / CLAUDE.md): every error raised here carries only ids,
dates and numeric thresholds — never an athlete's name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anthropometry import AnthropometricRecord
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.schemas.body_composition import BodyCompositionReading, ReferenceContext
from app.services.ai.context_builders import DELTA_WEIGHT_SIGNIFICANT_KG

if TYPE_CHECKING:
    from app.config import Settings
    from app.models.athlete import Athlete
    from app.schemas.body_composition import SkinfoldSetIn
    from app.schemas.growth import GrowthVelocity

#: Ordered site codes — must match `SkinfoldSitesIn`/`SkinfoldSitesOut` field
#: names and the `{site}_mm` / `{site}_declined` / `{site}_readings` column
#: naming convention on `SkinfoldMeasurement`.
SITES: tuple[str, ...] = (
    "triceps",
    "biceps",
    "subscapular",
    "medial_calf",
    "iliac_crest",
    "supraspinale",
)

#: The four sites that make up Σ4 (Slaughter backbone: triceps + biceps +
#: subscapular + medial_calf).
BACKBONE_SITES: tuple[str, ...] = ("triceps", "biceps", "subscapular", "medial_calf")

#: Reading-tolerance rule (data-model.md §4): a third reading is required
#: when the first two readings differ by more than the larger of a fixed
#: floor (mm) and a percentage of their mean.
READING_TOLERANCE_MIN_MM = 1.0
READING_TOLERANCE_PCT = 0.05

#: Soft plausibility bounds per site (mm), 9-12y band; 13-17y keeps the same
#: lower bound and adds +10mm to the upper bound (data-model.md §4).
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "triceps": (4.0, 30.0),
    "biceps": (2.0, 20.0),
    "subscapular": (4.0, 30.0),
    "medial_calf": (4.0, 30.0),
    "iliac_crest": (4.0, 40.0),
    "supraspinale": (3.0, 35.0),
}
_PLAUSIBLE_RANGE_UPPER_BONUS_FROM_AGE = 13.0
_PLAUSIBLE_RANGE_UPPER_BONUS_MM = 10.0

#: Slaughter & al. (1988) triceps+calf skinfold equation — the only
#: supported equation today.
EQUATION_VERSION_SLAUGHTER_TC = "slaughter_tc_1988_v1"


class BodyCompositionError(Exception):
    """Base of the body-composition domain errors the router translates to HTTP."""


class SkinfoldIntervalTooShortError(BodyCompositionError):
    """A new (non-replacement) set falls under `BODY_COMP_MIN_INTERVAL_DAYS` (409).

    Carries only dates (no athlete identity) — safe for an HTTP error body.
    """

    def __init__(self, *, previous_set_date: date, next_allowed_date: date) -> None:
        self.previous_set_date = previous_set_date
        self.next_allowed_date = next_allowed_date
        super().__init__(
            "La siguiente toma de pliegues cutáneos está disponible desde "
            f"{next_allowed_date.isoformat()} (toma anterior: "
            f"{previous_set_date.isoformat()})"
        )


class AthleteTooYoungError(BodyCompositionError):
    """Athlete's age at `evaluation_date` is below `BODY_COMP_MIN_AGE_YEARS` (409)."""

    def __init__(self, *, age_years: float, min_age_years: int) -> None:
        self.age_years = age_years
        self.min_age_years = min_age_years
        super().__init__(
            "El/la deportista no cumple la edad mínima para pliegues cutáneos "
            f"(mínimo {min_age_years} años)"
        )


def _quantize(value: float | Decimal, exponent: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(exponent), rounding=ROUND_HALF_UP)


def site_value(readings: Sequence[float | Decimal]) -> Decimal:
    """Mean of 2 readings, or median of 3 — rounded to 0.1 mm (NUMERIC(4,1))."""
    values = sorted(Decimal(str(r)) for r in readings)
    if len(values) == 2:
        result = (values[0] + values[1]) / 2
    elif len(values) == 3:
        result = values[1]
    else:
        raise ValueError("Un sitio necesita 2 o 3 lecturas")
    return _quantize(result, "0.1")


def needs_third_reading(r1: float | Decimal, r2: float | Decimal) -> bool:
    """True when the first two readings exceed max(5% of the mean, 1.0 mm)."""
    v1, v2 = Decimal(str(r1)), Decimal(str(r2))
    mean = (v1 + v2) / 2
    tolerance = max(mean * Decimal(str(READING_TOLERANCE_PCT)), Decimal(str(READING_TOLERANCE_MIN_MM)))
    return abs(v1 - v2) > tolerance


def compute_sums(
    values: dict[str, Decimal | float | None],
) -> tuple[Decimal | None, Decimal | None]:
    """Σ4 (backbone sites) and Σ6 (all sites); `None` if any member is missing."""
    sum4 = _sum_if_complete(values, BACKBONE_SITES)
    sum6 = _sum_if_complete(values, SITES)
    return sum4, sum6


def _sum_if_complete(
    values: dict[str, Decimal | float | None], sites: Sequence[str]
) -> Decimal | None:
    site_values = [values.get(site) for site in sites]
    if any(v is None for v in site_values):
        return None
    total = sum(Decimal(str(v)) for v in site_values)
    return _quantize(total, "0.1")


def estimate_body_fat(
    sex: str, triceps_mm: float, calf_mm: float
) -> tuple[float, str]:
    """Slaughter TC (1988) body-fat % from the triceps+calf sum, by sex."""
    sum_tc = triceps_mm + calf_mm
    if sex == "M":
        pct = 0.735 * sum_tc + 1.0
    else:
        pct = 0.610 * sum_tc + 5.0
    return pct, EQUATION_VERSION_SLAUGHTER_TC


def fat_masses(weight_kg: float, body_fat_pct: float) -> tuple[float, float]:
    """`(fat_mass_kg, fat_free_mass_kg)` from weight and body-fat percentage."""
    fat_mass_kg = weight_kg * body_fat_pct / 100
    fat_free_mass_kg = weight_kg - fat_mass_kg
    return fat_mass_kg, fat_free_mass_kg


def plausible_range(site: str, age_years: float) -> tuple[float, float]:
    """Soft plausibility bounds (mm) for `site` at `age_years` (warning only)."""
    low, high = PLAUSIBLE_RANGES[site]
    if age_years >= _PLAUSIBLE_RANGE_UPPER_BONUS_FROM_AGE:
        high += _PLAUSIBLE_RANGE_UPPER_BONUS_MM
    return low, high


def classify_sum_change(delta: float, threshold: float) -> str:
    """`within_noise` / `up_real` / `down_real` for a Σ4 (or Σ6) delta.

    `none` (no previous set to compare against) is decided by the caller
    (`build_reading`), not here — this only classifies an actual delta.
    """
    if abs(delta) < threshold:
        return "within_noise"
    return "up_real" if delta > 0 else "down_real"


def _sex_value(sex: object) -> str:
    return sex.value if hasattr(sex, "value") else str(sex)


def _is_counted_set(measurement: SkinfoldMeasurement) -> bool:
    """A set "counts" when at least one site is not declined (has a value)."""
    return any(getattr(measurement, f"{site}_mm") is not None for site in SITES)


def apply_set(
    record: AnthropometricRecord,
    payload: "SkinfoldSetIn",
    settings: "Settings",
) -> SkinfoldMeasurement:
    """Create or replace `record.skinfolds` from a validated `SkinfoldSetIn`.

    Fills every computed column of `SkinfoldMeasurement` (per-site value /
    declined / readings, Σ4, Σ6, body-fat estimate). Does not set
    `measured_by` or the FK to `record` beyond `anthropometric_record_id` /
    `athlete_id` — the caller (router) attaches actor/session bookkeeping.
    """
    measurement = record.skinfolds or SkinfoldMeasurement()
    measurement.anthropometric_record_id = record.id
    measurement.athlete_id = record.athlete_id
    measurement.caliper_model = payload.caliper_model
    measurement.protocol_version = "v1"

    values: dict[str, Decimal | None] = {}
    for site in SITES:
        site_in = getattr(payload.sites, site)
        declined = bool(site_in.declined)
        setattr(measurement, f"{site}_declined", declined)
        if declined:
            setattr(measurement, f"{site}_mm", None)
            setattr(measurement, f"{site}_readings", None)
            values[site] = None
        else:
            value = site_value(site_in.readings)
            setattr(measurement, f"{site}_mm", value)
            setattr(measurement, f"{site}_readings", [float(r) for r in site_in.readings])
            values[site] = value

    sum4, sum6 = compute_sums(values)
    measurement.sum4_mm = sum4
    measurement.sum6_mm = sum6

    record.skinfolds = measurement
    _recompute_estimates(measurement, record)
    return measurement


def _recompute_estimates(measurement: SkinfoldMeasurement, record: AnthropometricRecord) -> None:
    triceps = measurement.triceps_mm
    calf = measurement.medial_calf_mm
    if triceps is None or calf is None:
        measurement.body_fat_pct = None
        measurement.fat_mass_kg = None
        measurement.fat_free_mass_kg = None
        measurement.equation_version = None
        return

    sex = _sex_value(record.athlete.sex)
    pct, equation_version = estimate_body_fat(sex, float(triceps), float(calf))
    fat_mass_kg, fat_free_mass_kg = fat_masses(float(record.weight_kg), pct)
    measurement.body_fat_pct = _quantize(pct, "0.1")
    measurement.fat_mass_kg = _quantize(fat_mass_kg, "0.01")
    measurement.fat_free_mass_kg = _quantize(fat_free_mass_kg, "0.01")
    measurement.equation_version = equation_version


def recompute_estimates_for_record(record: AnthropometricRecord) -> None:
    """Weight-correction hook: recompute the estimate columns of `record.skinfolds`.

    No-op when the record has no skinfold set. `sum4_mm`/`sum6_mm` and the
    per-site values are unaffected by a weight correction — only
    `body_fat_pct`, `fat_mass_kg` and `fat_free_mass_kg` are recomputed.
    """
    measurement = record.skinfolds
    if measurement is None:
        return
    _recompute_estimates(measurement, record)


async def check_interval(
    db: AsyncSession,
    athlete_id: int,
    record: AnthropometricRecord,
    settings: "Settings",
) -> None:
    """Enforce `BODY_COMP_MIN_INTERVAL_DAYS` between two counted sets.

    Only applies when `record` has **no** set yet (a replace is always
    allowed, data-model.md §7). Fully-declined attempts are ignored when
    looking for the previous counted set. Raises
    `SkinfoldIntervalTooShortError` when the gap is too short.
    """
    if record.skinfolds is not None:
        return

    stmt = (
        select(AnthropometricRecord.evaluation_date, SkinfoldMeasurement)
        .join(
            SkinfoldMeasurement,
            SkinfoldMeasurement.anthropometric_record_id == AnthropometricRecord.id,
        )
        .where(
            AnthropometricRecord.athlete_id == athlete_id,
            AnthropometricRecord.id != record.id,
            AnthropometricRecord.evaluation_date <= record.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    result = await db.execute(stmt)

    previous_set_date: date | None = None
    for evaluation_date, measurement in result.all():
        if _is_counted_set(measurement):
            previous_set_date = evaluation_date
            break

    if previous_set_date is None:
        return

    gap_days = (record.evaluation_date - previous_set_date).days
    min_interval_days = settings.body_comp_min_interval_days
    if gap_days < min_interval_days:
        next_allowed_date = previous_set_date + timedelta(days=min_interval_days)
        raise SkinfoldIntervalTooShortError(
            previous_set_date=previous_set_date,
            next_allowed_date=next_allowed_date,
        )


def check_min_age(
    athlete: "Athlete",
    record: AnthropometricRecord,
    settings: "Settings",
) -> None:
    """Enforce `BODY_COMP_MIN_AGE_YEARS` at the record's `evaluation_date`."""
    from app.services.category import compute_age_decimal

    age_years = compute_age_decimal(athlete.birth_date, record.evaluation_date)
    if age_years < settings.body_comp_min_age_years:
        raise AthleteTooYoungError(
            age_years=age_years, min_age_years=settings.body_comp_min_age_years
        )


# ---------------------------------------------------------------------------
# Reading: change classifier, traffic light, family projection, copy
# (contracts/body-composition-reading.md §1–§4). Pure — nothing persisted.
# ---------------------------------------------------------------------------

#: Δweight ≥ this (kg) → weight leg `up` (reuses the anthropometry context
#: builders' "significant weight change" threshold, data-model §5).
WEIGHT_UP_KG = DELTA_WEIGHT_SIGNIFICANT_KG
#: Δheight ≥ this (cm) between the two records → height leg `growing`.
HEIGHT_GROWING_CM = 0.7
#: BMI-z drop thresholds (Δz ≤ −0.5 moderate, Δz ≤ −1.0 large).
BMI_Z_DROP_MODERATE = -0.5
BMI_Z_DROP_LARGE = -1.0
#: Δfat_free_mass (kg) thresholds for `ffm_trend_code`.
FFM_TREND_KG = 1.0

_STAGE_PRE = "Pre-PHV"
_STAGE_CIRCA = "Circa-PHV"
_STAGE_POST = "Post-PHV"

#: Ámbar rules in contract §3 order (the first match sets `band_reason_code`).
AMBAR_REASON_ORDER: tuple[str, ...] = (
    "sum_down_unexplained",
    "sum_up_unexplained",
    "sum_up_velocity_low",
    "reference_extreme",
    "bmi_z_drop",
    "velocity_low_persistent",
)


@dataclass(frozen=True)
class ReadingLegs:
    """Qualitative leg codes of one reading (contract §2) — no numbers of a minor."""

    sum_change_code: str
    weight_change_code: str
    height_growth_code: str
    velocity_code: str
    previous_velocity_code: str
    bmi_z_change_code: str
    reference_triceps_code: str
    reference_subscapular_code: str
    growth_explanation_code: str


def _dec(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _delta(latest: object, previous: object) -> Decimal | None:
    a, b = _dec(latest), _dec(previous)
    if a is None or b is None:
        return None
    return a - b


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def velocity_code(velocity: "GrowthVelocity | None") -> str:
    """`within_or_above` / `below` vs the lower bound of the expected range.

    `unavailable` when there is no velocity or its window is too short.
    """
    if velocity is None or velocity.interval_short:
        return "unavailable"
    lower_bound = velocity.expected_cm_per_year[0]
    return "below" if velocity.cm_per_year < lower_bound else "within_or_above"


def _weight_code(latest_record: object, previous_record: object | None) -> str:
    if previous_record is None:
        return "unavailable"
    delta = _delta(getattr(latest_record, "weight_kg", None), getattr(previous_record, "weight_kg", None))
    if delta is None:
        return "unavailable"
    return "up" if delta >= Decimal(str(WEIGHT_UP_KG)) else "flat_or_down"


def _height_code(latest_record: object, previous_record: object | None) -> str:
    if previous_record is None:
        return "unavailable"
    delta = _delta(
        getattr(latest_record, "standing_height_cm", None),
        getattr(previous_record, "standing_height_cm", None),
    )
    if delta is None:
        return "unavailable"
    return "growing" if delta >= Decimal(str(HEIGHT_GROWING_CM)) else "stalled"


def _bmi_z_code(latest_record: object, previous_record: object | None) -> str:
    if previous_record is None:
        return "unavailable"
    delta = _delta(getattr(latest_record, "bmi_z_score", None), getattr(previous_record, "bmi_z_score", None))
    if delta is None:
        return "unavailable"
    if delta <= Decimal(str(BMI_Z_DROP_LARGE)):
        return "drop_large"
    if delta <= Decimal(str(BMI_Z_DROP_MODERATE)):
        return "drop_moderate"
    return "ok"


def _sum_change(
    latest_set: object, previous_set: object | None, attr: str, threshold: float
) -> tuple[Decimal | None, str]:
    if previous_set is None:
        return None, "none"
    delta = _delta(getattr(latest_set, attr, None), getattr(previous_set, attr, None))
    if delta is None:
        return None, "none"
    return delta, classify_sum_change(float(delta), threshold)


def _ffm_trend(latest_set: object, previous_set: object | None) -> str:
    if previous_set is None:
        return "unavailable"
    delta = _delta(getattr(latest_set, "fat_free_mass_kg", None), getattr(previous_set, "fat_free_mass_kg", None))
    if delta is None:
        return "unavailable"
    if delta >= Decimal(str(FFM_TREND_KG)):
        return "up"
    if delta <= -Decimal(str(FFM_TREND_KG)):
        return "down"
    return "flat"


def _reference_site(reference: Mapping[str, object] | None, site: str) -> tuple[float | None, str]:
    if not reference:
        return None, "unavailable"
    entry = reference.get(site)
    if entry is None:
        return None, "unavailable"
    if isinstance(entry, Mapping):
        percentile, code = entry.get("percentile"), entry.get("code")
    else:
        percentile, code = getattr(entry, "percentile", None), getattr(entry, "code", None)
    return (float(percentile) if percentile is not None else None), (code or "unavailable")


def growth_explanation(
    *,
    sex: str,
    stage: str | None,
    sum_change_code: str,
    weight_change_code: str,
    velocity_code: str,
) -> str:
    """Growth explanation leg (contract §2) — evaluated in table order."""
    if (
        sex == "F"
        and stage in (_STAGE_CIRCA, _STAGE_POST)
        and weight_change_code == "up"
        and velocity_code == "within_or_above"
    ):
        return "expected_pubertal_gain"
    if stage == _STAGE_PRE and velocity_code == "within_or_above":
        return "pre_spurt_accumulation"
    if (
        sex == "M"
        and stage == _STAGE_POST
        and sum_change_code in ("within_noise", "down_real")
        and weight_change_code == "up"
    ):
        return "post_phv_lean_gain"
    return "none"


def compute_legs(
    latest_set: object,
    previous_set: object | None,
    latest_record: object,
    previous_record: object | None,
    velocity: "GrowthVelocity | None",
    reference_context: Mapping[str, object] | None,
    settings: "Settings",
    *,
    sex: str,
    previous_velocity: "GrowthVelocity | None" = None,
) -> ReadingLegs:
    """Every leg code of contract §2 for one pair of counted sets."""
    _, sum_code = _sum_change(latest_set, previous_set, "sum4_mm", settings.body_comp_mdc_sum4_mm)
    weight = _weight_code(latest_record, previous_record)
    vel = velocity_code(velocity)
    stage = _enum_value(getattr(latest_record, "maturation_status", None))
    _, tri_code = _reference_site(reference_context, "triceps")
    _, sub_code = _reference_site(reference_context, "subscapular")
    return ReadingLegs(
        sum_change_code=sum_code,
        weight_change_code=weight,
        height_growth_code=_height_code(latest_record, previous_record),
        velocity_code=vel,
        previous_velocity_code=velocity_code(previous_velocity),
        bmi_z_change_code=_bmi_z_code(latest_record, previous_record),
        reference_triceps_code=tri_code,
        reference_subscapular_code=sub_code,
        growth_explanation_code=growth_explanation(
            sex=_sex_value(sex),
            stage=stage,
            sum_change_code=sum_code,
            weight_change_code=weight,
            velocity_code=vel,
        ),
    )


def ambar_reasons(legs: ReadingLegs) -> list[str]:
    """Every ámbar rule of contract §3 that matches, in §3 order."""
    reasons: list[str] = []
    if (
        legs.sum_change_code == "down_real"
        and legs.weight_change_code == "flat_or_down"
        and legs.height_growth_code in ("stalled", "unavailable")
    ):
        reasons.append("sum_down_unexplained")
    # `sum_up_velocity_low` is checked before `sum_up_unexplained`: velocity
    # `below` forces `growth_explanation_code == "none"` (no explanation
    # branch matches with velocity `below`), so whenever the velocity rule
    # applies the unexplained rule would always match too and shadow it if
    # evaluated first (contract §3 note 1).
    if legs.sum_change_code == "up_real" and legs.velocity_code == "below":
        reasons.append("sum_up_velocity_low")
    if legs.sum_change_code == "up_real" and legs.growth_explanation_code == "none":
        reasons.append("sum_up_unexplained")
    if {legs.reference_triceps_code, legs.reference_subscapular_code} & {"low_extreme", "high_extreme"}:
        reasons.append("reference_extreme")
    if legs.bmi_z_change_code == "drop_large":
        reasons.append("bmi_z_drop")
    if legs.velocity_code == "below" and legs.previous_velocity_code == "below":
        reasons.append("velocity_low_persistent")
    return reasons


def is_reference_only_ambar(legs: ReadingLegs) -> bool:
    """True when `reference_extreme` is the only ámbar rule that matched (§3c).

    Evaluates the other ámbar rules without the reference rule: a
    population-reference extreme alone is context, not a change signal, so
    families see it as `verde`.
    """
    return ambar_reasons(legs) == ["reference_extreme"]


def _is_rojo(legs: ReadingLegs, sets_count: int) -> bool:
    return (
        sets_count >= 2
        and legs.sum_change_code == "down_real"
        and legs.weight_change_code == "flat_or_down"
        and legs.height_growth_code == "growing"
    )


def _verde_reason(legs: ReadingLegs, sets_count: int) -> str:
    # The growth-explanation reasons are more specific than `no_real_change`,
    # so they are checked first (contract §5 scenario B: Σ4 within noise in a
    # post-PHV boy with weight up reads `post_phv_lean_gain`).
    if legs.sum_change_code == "up_real" and legs.growth_explanation_code == "expected_pubertal_gain":
        return "expected_pubertal_gain"
    if legs.sum_change_code == "up_real" and legs.growth_explanation_code == "pre_spurt_accumulation":
        return "pre_spurt_accumulation"
    if legs.growth_explanation_code == "post_phv_lean_gain":
        return "post_phv_lean_gain"
    if sets_count == 1:
        return "first_set"
    if legs.sum_change_code == "within_noise":
        return "no_real_change"
    return "stable"


def classify_band(legs: ReadingLegs, sets_count: int) -> tuple[str, str]:
    """`(band, band_reason_code)` per contract §3 rules 2–4 (first match wins).

    Rule 1 (`sets_count == 0` → no reading) is the caller's responsibility
    (`build_reading` returns `None`).
    """
    if _is_rojo(legs, sets_count):
        return "rojo", "energy_availability_pattern"
    reasons = ambar_reasons(legs)
    if reasons:
        return "ambar", reasons[0]
    return "verde", _verde_reason(legs, sets_count)


def project_family_band(band: str, *, reference_only: bool) -> str:
    """Family projection (contract §3c) — never returns `rojo`.

    verde → verde; ámbar by reference only → verde; any other ámbar → ambar;
    rojo → ambar ("Requiere acompañamiento profesional" is said by the coach
    in person and appears on no family surface).
    """
    if band == "verde":
        return "verde"
    if band == "ambar" and reference_only:
        return "verde"
    return "ambar"


def _legs_missing(legs: ReadingLegs, previous_set: object | None) -> list[str]:
    missing: list[str] = []
    if previous_set is None:
        missing.append("previous_set")
    if legs.weight_change_code == "unavailable":
        missing.append("weight")
    if legs.height_growth_code == "unavailable":
        missing.append("height")
    if legs.velocity_code == "unavailable":
        missing.append("velocity")
    if legs.bmi_z_change_code == "unavailable":
        missing.append("bmi_z")
    if "unavailable" in (legs.reference_triceps_code, legs.reference_subscapular_code):
        missing.append("reference")
    return missing


def _latest_attempt_declined_date(
    latest_attempt: object | None,
    latest_attempt_record: object | None,
    latest_record: object,
) -> date | None:
    """Date of a fully declined attempt newer than the latest counted set (§3b)."""
    if latest_attempt is None or _is_counted_set(latest_attempt):  # type: ignore[arg-type]
        return None
    record = latest_attempt_record if latest_attempt_record is not None else getattr(
        latest_attempt, "record", None
    )
    attempt_date = getattr(record, "evaluation_date", None)
    latest_date = getattr(latest_record, "evaluation_date", None)
    if attempt_date is None or latest_date is None or attempt_date <= latest_date:
        return None
    return attempt_date


def build_reading(
    latest_set: SkinfoldMeasurement | None,
    previous_set: SkinfoldMeasurement | None,
    latest_record: AnthropometricRecord | None,
    previous_record: AnthropometricRecord | None,
    velocity: "GrowthVelocity | None",
    reference_context: Mapping[str, object] | None,
    settings: "Settings",
    *,
    sex: str,
    sets_count: int | None = None,
    previous_velocity: "GrowthVelocity | None" = None,
    latest_attempt: SkinfoldMeasurement | None = None,
    latest_attempt_record: AnthropometricRecord | None = None,
    today: date | None = None,
) -> BodyCompositionReading | None:
    """Build the coach reading of `contracts/body-composition-reading.md` §1–§3c.

    - `latest_set` / `previous_set`: the two most recent **counted** sets
      (≥ 1 non-declined site); `latest_record` / `previous_record` are their
      `AnthropometricRecord`s. Returns `None` when there is no counted set
      (rule 1, `has_data=false`), even if fully declined attempts exist.
    - `velocity` / `previous_velocity`: `GrowthVelocity` of the latest and the
      previous cycle (either may be `None`); `reference_context` is the dict
      returned by `reference_skinfolds.reference_context` (or `None`).
    - `sex`: athlete sex (`"M"`/`"F"` or the enum).
    - `sets_count`: counted sets of the athlete; defaults to 1 or 2 from
      whether `previous_set` is given.
    - `latest_attempt` (+ its record): the most recent set of any kind; when it
      is fully declined and newer than `latest_set`, `latest_attempt_declined`
      carries its date (coach only) — nothing else changes (§3b).
    """
    if latest_set is None or latest_record is None or not _is_counted_set(latest_set):
        return None
    if sets_count is None:
        sets_count = 2 if previous_set is not None else 1
    if sets_count <= 0:
        return None

    legs = compute_legs(
        latest_set,
        previous_set,
        latest_record,
        previous_record,
        velocity,
        reference_context,
        settings,
        sex=sex,
        previous_velocity=previous_velocity,
    )
    band, reason = classify_band(legs, sets_count)
    family_band = project_family_band(band, reference_only=is_reference_only_ambar(legs))

    sum4_delta, _ = _sum_change(latest_set, previous_set, "sum4_mm", settings.body_comp_mdc_sum4_mm)
    sum6_delta, _ = _sum_change(latest_set, previous_set, "sum6_mm", settings.body_comp_mdc_sum6_mm)
    tri_pct, tri_code = _reference_site(reference_context, "triceps")
    sub_pct, sub_code = _reference_site(reference_context, "subscapular")

    next_due_date = latest_record.evaluation_date + timedelta(days=settings.body_comp_min_interval_days)
    today = today or date.today()

    return BodyCompositionReading(
        sets_count=sets_count,
        sum4_change_mm=float(sum4_delta) if sum4_delta is not None else None,
        sum6_change_mm=float(sum6_delta) if sum6_delta is not None else None,
        sum_change_code=legs.sum_change_code,
        weight_change_code=legs.weight_change_code,
        height_growth_code=legs.height_growth_code,
        velocity_code=legs.velocity_code,
        bmi_z_change_code=legs.bmi_z_change_code,
        reference_triceps=ReferenceContext(percentile=tri_pct, code=tri_code),
        reference_subscapular=ReferenceContext(percentile=sub_pct, code=sub_code),
        ffm_trend_code=_ffm_trend(latest_set, previous_set),
        sites_declined_count=sum(
            1 for site in SITES if bool(getattr(latest_set, f"{site}_declined", False))
        ),
        band=band,
        family_band=family_band,
        latest_attempt_declined=_latest_attempt_declined_date(
            latest_attempt, latest_attempt_record, latest_record
        ),
        band_reason_code=reason,
        legs_missing=_legs_missing(legs, previous_set),
        next_due_date=next_due_date,
        days_until_due=(next_due_date - today).days,
    )


# ---------------------------------------------------------------------------
# Shared loader (T080, privacy-audit F6/F7): ONE place that assembles every
# input of `build_reading` from the database, so the coach detail
# (`GET …/body-composition`), the referral note, the growth-summary card, the
# newsletter annex and the anthropometry AI leaf can never disagree.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedBodyComposition:
    """Result of `load_reading` — never persisted, never logged.

    - `reading`: the `BodyCompositionReading` (or `None`: no counted set in
      scope, or the caller's `at_record_id`/`since` requirement not met).
    - `records`: the athlete's anthropometric records in scope, ascending by
      `(evaluation_date, id)`, each with `.skinfolds` loaded.
    - `latest_set_record` / `previous_set_record`: the records holding the
      two most recent **counted** sets in scope (`None` when absent).
    """

    reading: BodyCompositionReading | None
    records: tuple[AnthropometricRecord, ...] = ()
    latest_set_record: AnthropometricRecord | None = None
    previous_set_record: AnthropometricRecord | None = None

    @property
    def latest_set(self) -> SkinfoldMeasurement | None:
        return self.latest_set_record.skinfolds if self.latest_set_record is not None else None


async def load_athlete_records(
    db: AsyncSession, athlete_id: int, *, until: date | None = None
) -> list[AnthropometricRecord]:
    """The athlete's records with `.skinfolds` populated — exactly ONE SELECT.

    `LEFT OUTER JOIN skinfold_measurements` + `contains_eager`, ascending by
    `(evaluation_date, id)`; `until` (inclusive) bounds `evaluation_date`.
    """
    from sqlalchemy.orm import contains_eager

    stmt = (
        select(AnthropometricRecord)
        .outerjoin(
            SkinfoldMeasurement,
            SkinfoldMeasurement.anthropometric_record_id == AnthropometricRecord.id,
        )
        .options(contains_eager(AnthropometricRecord.skinfolds))
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.asc(), AnthropometricRecord.id.asc())
    )
    if until is not None:
        stmt = stmt.where(AnthropometricRecord.evaluation_date <= until)
    result = await db.execute(stmt)
    return list(result.unique().scalars().all())


def _velocity_at(
    records: Sequence[AnthropometricRecord], record: AnthropometricRecord | None, sex: str
) -> "GrowthVelocity | None":
    """`growth_summary._build_velocity` of `record` against the record that
    immediately precedes it in `records` (with or without skinfolds) — the
    same window the coach detail has always used."""
    if record is None or getattr(record, "maturation_status", None) is None:
        return None
    from app.services.growth_summary import _build_velocity  # circular at import time

    index = next((i for i, r in enumerate(records) if r is record), None)
    if index is None:
        return None
    before = records[index - 1] if index > 0 else None
    return _build_velocity(record, before, _enum_value(record.maturation_status) or "", sex)


async def load_reading(
    db: AsyncSession,
    athlete: "Athlete",
    *,
    records: Sequence[AnthropometricRecord] | None = None,
    until: date | None = None,
    since: date | None = None,
    at_record_id: int | None = None,
    settings: "Settings | None" = None,
    today: date | None = None,
) -> LoadedBodyComposition:
    """Assemble every `build_reading` input and build the reading (T080).

    Inputs: velocity and previous-cycle velocity (each against its
    immediately preceding record), the FUPRECOL reference context of the
    latest counted set (≤ 1 query, `reference_skinfolds.reference_context`),
    `sets_count`, and the latest attempt (§3b).

    - `records`: already-loaded records with `.skinfolds` (any order); when
      `None` they are loaded with `load_athlete_records` (one SELECT).
    - `until`: ignore records after this date (newsletter month end).
    - `at_record_id`: ignore records after that record, and build a reading
      only when that record itself holds the latest counted set (AI leaf:
      "when a measurement has a skinfold set", spec FR-029).
    - `since`: build a reading only when the latest counted set is on or
      after this date (newsletter: "only in the month of a counted set").

    Never raises for missing data; the reference lookup is skipped (no query)
    when a requirement is not met. Nothing here is logged.
    """
    if settings is None:
        from app.config import settings as app_settings

        settings = app_settings

    if records is None:
        loaded = await load_athlete_records(db, athlete.id, until=until)
    else:
        loaded = sorted(records, key=lambda r: (r.evaluation_date, r.id or 0))
        if until is not None:
            loaded = [r for r in loaded if r.evaluation_date <= until]
    if at_record_id is not None:
        cut = next((i for i, r in enumerate(loaded) if r.id == at_record_id), None)
        loaded = loaded[: cut + 1] if cut is not None else []

    scope = tuple(loaded)
    skinfold_records = [r for r in scope if r.skinfolds is not None]
    counted = [r for r in skinfold_records if _is_counted_set(r.skinfolds)]
    latest_record = counted[-1] if counted else None
    previous_record = counted[-2] if len(counted) > 1 else None
    empty = LoadedBodyComposition(
        reading=None,
        records=scope,
        latest_set_record=latest_record,
        previous_set_record=previous_record,
    )
    if latest_record is None:
        return empty
    if at_record_id is not None and latest_record.id != at_record_id:
        return empty
    if since is not None and latest_record.evaluation_date < since:
        return empty

    sex = _sex_value(athlete.sex)
    latest_set = latest_record.skinfolds
    reference_ctx = None
    if getattr(athlete, "birth_date", None) is not None:
        from app.services.category import compute_age_decimal
        from app.services.reference_skinfolds import reference_context as fetch_reference_context

        age_months = compute_age_decimal(athlete.birth_date, latest_record.evaluation_date) * 12
        reference_ctx = await fetch_reference_context(
            db,
            sex,
            age_months,
            float(latest_set.triceps_mm) if latest_set.triceps_mm is not None else None,
            float(latest_set.subscapular_mm) if latest_set.subscapular_mm is not None else None,
        )

    latest_attempt_record = skinfold_records[-1]
    reading = build_reading(
        latest_set,
        previous_record.skinfolds if previous_record is not None else None,
        latest_record,
        previous_record,
        _velocity_at(scope, latest_record, sex),
        reference_ctx,
        settings,
        sex=sex,
        sets_count=len(counted),
        previous_velocity=_velocity_at(scope, previous_record, sex),
        latest_attempt=latest_attempt_record.skinfolds,
        latest_attempt_record=latest_attempt_record,
        today=today,
    )
    return LoadedBodyComposition(
        reading=reading,
        records=scope,
        latest_set_record=latest_record,
        previous_set_record=previous_record,
    )


# ---------------------------------------------------------------------------
# Copy (contract §4) — español (Colombia). The only body-composition text a
# family ever sees is FAMILY_COPY (+ NEWSLETTER_NOTICE in the PDF newsletter).
# ---------------------------------------------------------------------------

#: Keyed by `family_band`. There is deliberately no `rojo` entry (§3c).
FAMILY_COPY: dict[str, dict[str, str]] = {
    "verde": {
        "family_label": "En su curva esperada",
        "family_sentence": (
            "La composición corporal de tu hijo/a se mantiene dentro de lo esperado "
            "para su etapa de desarrollo. Sigue acompañando el proceso: esto va de "
            "la mano de un crecimiento saludable."
        ),
    },
    "ambar": {
        "family_label": "En observación",
        "family_sentence": (
            "Notamos un cambio que vale la pena conversar. El entrenador se pondrá "
            "en contacto contigo para revisarlo juntos; no es una alarma, es una "
            "oportunidad de acompañar mejor a tu hijo/a."
        ),
    },
}

#: Newsletter (Bitácora de etapa) PDF block — deterministic, never sent to AI.
NEWSLETTER_TITLE = "Composición corporal"
NEWSLETTER_NOTICE = (
    "Este mes el entrenador tomó una medición de pliegues cutáneos (con una "
    "pinza, en sitios como el brazo, la espalda y la pantorrilla), en un espacio "
    "privado y respetando siempre el derecho de tu hijo/a a decir que no, sin "
    "ninguna consecuencia. Se usa solo para acompañar su crecimiento: nunca para "
    "comparar deportistas ni como una meta."
)

#: Coach-only card copy (card "Sin datos" line for a declined attempt, §3b).
LATEST_ATTEMPT_DECLINED_COPY = "Sin datos: el/la deportista prefirió no medirse"

#: Coach-only, one sentence per `band_reason_code`.
COACH_REASON_COPY: dict[str, str] = {
    "no_real_change": (
        "Sin cambio real en la suma de pliegues desde la última toma (dentro del "
        "margen de medición)."
    ),
    "expected_pubertal_gain": (
        "La suma de pliegues subió de forma real, con peso y talla creciendo dentro "
        "de lo esperado: patrón habitual alrededor del pico de crecimiento en niñas."
    ),
    "pre_spurt_accumulation": (
        "La suma de pliegues subió de forma real con la talla creciendo a ritmo "
        "esperado: acumulación previa al estirón, frecuente en esta etapa."
    ),
    "post_phv_lean_gain": (
        "Peso arriba con pliegues estables o a la baja después del pico de "
        "crecimiento: ganancia de masa magra esperada."
    ),
    "first_set": (
        "Primera toma de pliegues: hace falta una segunda toma (≥ 90 días) para "
        "leer una tendencia."
    ),
    "stable": "Composición corporal estable respecto a la toma anterior.",
    "sum_up_unexplained": (
        "La suma de pliegues subió más allá del margen sin un patrón de crecimiento "
        "que lo explique: vale una conversación en privado, sin cifras."
    ),
    "sum_up_velocity_low": (
        "La suma de pliegues subió de forma real mientras la velocidad de talla está "
        "por debajo de lo esperado: conversa en privado y revisa en la próxima toma."
    ),
    "sum_down_unexplained": (
        "La suma de pliegues bajó más allá del margen con el peso estancado; falta "
        "confirmar el crecimiento en talla para leer el patrón."
    ),
    "reference_extreme": (
        "Un pliegue está en el extremo de la referencia poblacional (≤ P5 o ≥ P95): "
        "es contexto, no un veredicto; observa la tendencia en la próxima toma."
    ),
    "bmi_z_drop": (
        "El índice de masa corporal para la edad cayó más de una desviación "
        "estándar: conversa con la familia y revisa alimentación con enfoque "
        "«comida primero»."
    ),
    "velocity_low_persistent": (
        "La velocidad de talla lleva dos ciclos por debajo de lo esperado: revisa "
        "junto con la composición corporal y considera consultar."
    ),
    "energy_availability_pattern": (
        "Patrón combinado: la suma de pliegues cayó más allá del margen, el peso se "
        "estancó y la talla sigue creciendo. Compatible con baja disponibilidad "
        "energética. No es un diagnóstico: conversa con la familia en lenguaje "
        "neutro y considera remitir a un profesional de salud."
    ),
}

#: Coach-only escalation prompt, keyed by coach `band` (none for verde).
ESCALATION_COPY: dict[str, str] = {
    "ambar": (
        "Sugerencia: conversa en privado con el/la deportista y la familia, sin "
        "mencionar números ni porcentajes. Si el patrón se repite en la próxima "
        "toma o aparecen otras señales (fatiga persistente, cambios de ánimo, "
        "enfermedad frecuente), pasa a seguimiento con la familia."
    ),
    "rojo": (
        "Esto NO es un diagnóstico. Conversa con la familia en lenguaje neutro "
        "(nunca calorías ni peso frente al/a la deportista) y coordina la remisión "
        "a un profesional de salud con la nota de remisión."
    ),
}

#: Coach card change line, keyed by `sum_change_code`; format with
#: `delta` (float) and `threshold` (`settings.body_comp_mdc_sum4_mm`).
CHANGE_COPY: dict[str, str] = {
    "within_noise": "Dentro del margen de medición ({delta:+.1f} mm; umbral {threshold} mm)",
    "up_real": "Cambio real ({delta:+.1f} mm; umbral {threshold} mm)",
    "down_real": "Cambio real ({delta:+.1f} mm; umbral {threshold} mm)",
    "none": "Sin toma anterior comparable",
}


def change_sentence(sum_change_code: str, delta: float | None, threshold: float) -> str:
    """Coach-only change line for the card (never a family surface)."""
    if sum_change_code == "none" or delta is None:
        return CHANGE_COPY["none"]
    return CHANGE_COPY[sum_change_code].format(delta=delta, threshold=threshold)
