"""Pure derivation of the growth summary shown on the decision-first coach tab.

`build_growth_summary` never touches the database: it takes the athlete and
the (already fetched) two latest `anthropometric_records` rows and derives
stage, velocity, next-measurement status and alerts — reusing the same rules
`routers/alerts.py` already applies to the dashboard, so the two surfaces
never disagree (feature 040 / T034, US2).

It never recomputes Z-scores, percentiles or bands: those are read as stored
on the record (WHO 2007 since feature 040 — see `routers/anthropometry.py`).

See `specs/040-growth-module-redesign/data-model.md` §3 and
`specs/040-growth-module-redesign/research.md` R-05.
"""

from __future__ import annotations

from datetime import date

from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.athlete import Athlete
from app.schemas.alerts import MeasurementStatus
from app.schemas.growth import (
    BandReading,
    GrowthSummaryAlert,
    GrowthSummaryOut,
    GrowthVelocity,
    LatestBands,
    MeasurementDue,
)
from app.services.category import compute_age_decimal
from app.services.growth import classify_nutritional_status_height
from app.services.measurement_alerts import (
    DEFAULT_INTERVAL,
    GROWTH_VELOCITY_THRESHOLD,
    WARNING_DAYS,
    calculate_growth_velocity,
    calculate_next_due,
    detect_approaching_circa,
    get_measurement_interval,
)

# Rango esperado de velocidad de crecimiento en talla, cm/año, por etapa PHV y
# sexo (research.md R-05). Deliberadamente amplio y orientativo — informa al
# entrenador, no diagnostica. Circa-PHV se separa por sexo porque el pico de
# velocidad femenino ocurre antes y es menor en magnitud que el masculino.
EXPECTED_VELOCITY_CM_YEAR: dict[str, tuple[float, float] | dict[str, tuple[float, float]]] = {
    "Pre-PHV": (4.0, 6.0),
    "Circa-PHV": {"M": (8.0, 10.0), "F": (7.0, 9.0)},
    "Post-PHV": (1.0, 4.0),
}


def get_expected_velocity_range(stage: str, sex: str) -> tuple[float, float]:
    """Retorna el rango (min, max) cm/año esperado para una etapa PHV y sexo."""
    ranges = EXPECTED_VELOCITY_CM_YEAR.get(stage, (1.0, 4.0))
    if isinstance(ranges, dict):
        return ranges.get(sex, (1.0, 4.0))
    return ranges


def _band_reading(
    value: object,
    z_score: object,
    percentile: object,
    band: NutritionalStatus | None,
) -> BandReading | None:
    """Construye un `BandReading` si hay z-score almacenado; `None` si no."""
    if z_score is None or band is None:
        return None
    return BandReading(
        value=float(value),  # type: ignore[arg-type]
        z_score=float(z_score),  # type: ignore[arg-type]
        percentile=float(percentile),  # type: ignore[arg-type]
        band=band,
    )


def _build_latest_bands(latest: AnthropometricRecord) -> LatestBands:
    """Lee talla/IMC/peso del registro más reciente tal como fueron guardados
    (sin recalcular). El peso reusa el vocabulario de bandas de talla porque
    la OMS no define un vocabulario propio para peso/edad (data-model.md §3).
    """
    height_band = (
        classify_nutritional_status_height(float(latest.height_z_score))
        if latest.height_z_score is not None
        else None
    )
    weight_band = (
        classify_nutritional_status_height(float(latest.weight_z_score))
        if latest.weight_z_score is not None
        else None
    )
    return LatestBands(
        record_id=latest.id,
        growth_source=latest.growth_source,
        height=_band_reading(
            latest.standing_height_cm, latest.height_z_score, latest.height_percentile, height_band
        ),
        bmi=_band_reading(latest.bmi, latest.bmi_z_score, latest.bmi_percentile, latest.nutritional_status),
        weight=_band_reading(
            latest.weight_kg, latest.weight_z_score, latest.weight_percentile, weight_band
        ),
    )


def _build_velocity(
    latest: AnthropometricRecord,
    previous: AnthropometricRecord | None,
    stage: str,
    sex: str,
) -> GrowthVelocity | None:
    """Velocidad de crecimiento entre las dos mediciones más recientes."""
    if previous is None:
        return None
    cm_per_month = calculate_growth_velocity(latest, previous)
    if cm_per_month is None:
        return None
    window_days = (latest.evaluation_date - previous.evaluation_date).days
    interval_short = window_days < 30
    return GrowthVelocity(
        cm_per_month=cm_per_month,
        cm_per_year=round(cm_per_month * 12, 1),
        window_days=window_days,
        interval_short=interval_short,
        expected_cm_per_year=get_expected_velocity_range(stage, sex),
    )


def _build_measurement_due(latest: AnthropometricRecord | None, today: date) -> MeasurementDue:
    """Estado de próxima medición — mismas reglas que `routers/alerts.py`."""
    if latest is None:
        return MeasurementDue(
            status=MeasurementStatus.never,
            interval_days=DEFAULT_INTERVAL,
            next_due_date=None,
            days_overdue=None,
        )

    stage_value = latest.maturation_status.value
    interval = get_measurement_interval(stage_value)
    next_due = calculate_next_due(latest.evaluation_date, stage_value)
    days_diff = (today - next_due).days  # positivo = atrasado

    if days_diff > 0:
        m_status = MeasurementStatus.overdue
    elif days_diff >= -WARNING_DAYS:
        m_status = MeasurementStatus.due_soon
    else:
        m_status = MeasurementStatus.ok

    return MeasurementDue(
        status=m_status,
        interval_days=interval,
        next_due_date=next_due,
        days_overdue=days_diff if days_diff > 0 else None,
    )


def _build_alerts(
    stage: str,
    latest: AnthropometricRecord,
    previous: AnthropometricRecord | None,
    velocity: GrowthVelocity | None,
) -> list[GrowthSummaryAlert]:
    """Alertas de crecimiento, mismos umbrales que el dashboard (`alerts.py`)
    más las señales p3 propias de la pestaña de crecimiento."""
    alerts: list[GrowthSummaryAlert] = []

    if stage == MaturationStatus.circa_phv.value:
        alerts.append(GrowthSummaryAlert.circa_phv)

    if latest.height_percentile is not None and float(latest.height_percentile) < 3:
        alerts.append(GrowthSummaryAlert.height_p3)

    if latest.bmi_percentile is not None and float(latest.bmi_percentile) < 3:
        alerts.append(GrowthSummaryAlert.bmi_p3)

    if (
        velocity is not None
        and not velocity.interval_short
        and velocity.cm_per_month >= GROWTH_VELOCITY_THRESHOLD
    ):
        alerts.append(GrowthSummaryAlert.rapid_growth)

    if detect_approaching_circa(float(latest.maturity_offset)):
        alerts.append(GrowthSummaryAlert.approaching_circa)

    if previous is not None and latest.maturation_status != previous.maturation_status:
        alerts.append(GrowthSummaryAlert.phase_changed)

    return alerts


def build_growth_summary(
    athlete: Athlete,
    latest: AnthropometricRecord | None,
    previous: AnthropometricRecord | None,
    today: date | None = None,
) -> GrowthSummaryOut:
    """Deriva el `GrowthSummaryOut` de un atleta a partir de sus dos
    mediciones antropométricas más recientes (ya cargadas por el router con
    una sola consulta `ORDER BY evaluation_date DESC LIMIT 2`).

    No consulta la base de datos ni recalcula Z-scores/percentiles/bandas:
    es una función pura sobre los objetos recibidos.
    """
    today = today or date.today()
    records_count = sum(1 for r in (latest, previous) if r is not None)

    if latest is None:
        return GrowthSummaryOut(
            athlete_id=athlete.id,
            computed_at=today,
            records_count=records_count,
            latest_evaluation_date=None,
            stage=None,
            maturity_offset=None,
            age_at_phv=None,
            months_from_phv=None,
            velocity=None,
            measurement=_build_measurement_due(None, today),
            alerts=[],
            latest=None,
        )

    stage_value = latest.maturation_status.value
    maturity_offset = float(latest.maturity_offset)
    age_at_phv = float(latest.age_at_phv)
    age_today = compute_age_decimal(athlete.birth_date, today)
    months_from_phv = round((age_today - age_at_phv) * 12, 1)

    velocity = _build_velocity(latest, previous, stage_value, athlete.sex.value)
    measurement = _build_measurement_due(latest, today)
    alerts = _build_alerts(stage_value, latest, previous, velocity)

    return GrowthSummaryOut(
        athlete_id=athlete.id,
        computed_at=today,
        records_count=records_count,
        latest_evaluation_date=latest.evaluation_date,
        stage=latest.maturation_status,
        maturity_offset=maturity_offset,
        age_at_phv=age_at_phv,
        months_from_phv=months_from_phv,
        velocity=velocity,
        measurement=measurement,
        alerts=alerts,
        latest=_build_latest_bands(latest),
    )
