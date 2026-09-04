"""Tests for ``app.services.growth_summary.build_growth_summary`` (feature 040 / T030).

Pure-function tests: no database, no HTTP — synthetic ``Athlete`` /
``AnthropometricRecord`` ORM instances are built in-memory (never flushed)
with the numeric fields the service reads. All data is fictitious (CLAUDE.md
§Privacy): no real name, birth date or note of a minor appears anywhere.

Covers:
- Velocity: cm/month → cm/year conversion.
- A < 30-day interval marks ``interval_short`` and suppresses ``rapid_growth``
  even when the raw magnitude would otherwise qualify.
- Expected velocity ranges by PHV stage and sex (research.md R-05).
- ``months_from_phv`` sign (negative before PHV, positive after).
- ``phase_changed`` and ``approaching_circa`` alerts.
- Shapes with zero and one record.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.athlete import Athlete, Sex
from app.models.growth import GrowthSource
from app.schemas.alerts import MeasurementStatus
from app.schemas.growth import GrowthSummaryAlert
from app.services.growth_summary import (
    EXPECTED_VELOCITY_CM_YEAR,
    build_growth_summary,
    get_expected_velocity_range,
)

_TODAY = date(2026, 9, 4)


def _make_athlete(*, athlete_id: int = 1, sex: Sex = Sex.M, birth_date: date = date(2014, 1, 1)) -> Athlete:
    """Synthetic athlete — no name set, only the fields the service reads."""
    return Athlete(
        id=athlete_id,
        user_id=athlete_id,
        birth_date=birth_date,
        sex=sex,
        club_id=1,
        created_by=1,
    )


def _make_record(
    *,
    record_id: int = 1,
    athlete_id: int = 1,
    evaluation_date: date,
    standing_height_cm: float = 150.0,
    weight_kg: float = 40.0,
    maturity_offset: float = 0.0,
    age_at_phv: float = 12.5,
    maturation_status: MaturationStatus = MaturationStatus.pre_phv,
    height_z_score: float | None = None,
    height_percentile: float | None = None,
    bmi_z_score: float | None = None,
    bmi_percentile: float | None = None,
    nutritional_status: NutritionalStatus | None = None,
    weight_z_score: float | None = None,
    weight_percentile: float | None = None,
    growth_source: GrowthSource | None = GrowthSource.WHO,
) -> AnthropometricRecord:
    """Synthetic anthropometric record with the raw + derived fields the
    service reads. Derived fields default to ``None`` (not needed by most
    velocity/alert tests)."""
    bmi = round(weight_kg / (standing_height_cm / 100) ** 2, 2)
    return AnthropometricRecord(
        id=record_id,
        athlete_id=athlete_id,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight_kg)),
        standing_height_cm=Decimal(str(standing_height_cm)),
        sitting_height_cm=Decimal("74.0"),
        leg_length_cm=Decimal("76.0"),
        leg_sitting_ratio=Decimal("1.0270"),
        maturity_offset=Decimal(str(maturity_offset)),
        age_at_phv=Decimal(str(age_at_phv)),
        maturation_status=maturation_status,
        evaluated_by=1,
        bmi=Decimal(str(bmi)),
        height_z_score=Decimal(str(height_z_score)) if height_z_score is not None else None,
        height_percentile=Decimal(str(height_percentile)) if height_percentile is not None else None,
        bmi_z_score=Decimal(str(bmi_z_score)) if bmi_z_score is not None else None,
        bmi_percentile=Decimal(str(bmi_percentile)) if bmi_percentile is not None else None,
        nutritional_status=nutritional_status,
        weight_z_score=Decimal(str(weight_z_score)) if weight_z_score is not None else None,
        weight_percentile=Decimal(str(weight_percentile)) if weight_percentile is not None else None,
        growth_source=growth_source,
    )


# ---------------------------------------------------------------------------
# Velocity: cm/month → cm/year
# ---------------------------------------------------------------------------


def test_velocity_converts_cm_per_month_to_cm_per_year() -> None:
    athlete = _make_athlete()
    previous = _make_record(
        record_id=1, evaluation_date=date(2026, 6, 1), standing_height_cm=147.0
    )
    latest = _make_record(
        record_id=2, evaluation_date=date(2026, 9, 1), standing_height_cm=150.0
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert summary.velocity is not None
    assert summary.velocity.window_days == (date(2026, 9, 1) - date(2026, 6, 1)).days
    assert summary.velocity.cm_per_year == round(summary.velocity.cm_per_month * 12, 1)
    # 3 cm en ~92 días ≈ 0.99 cm/mes ≈ 11.9 cm/año
    assert summary.velocity.cm_per_month == pytest.approx(0.99, abs=0.05)


# ---------------------------------------------------------------------------
# interval_short suppresses rapid_growth
# ---------------------------------------------------------------------------


def test_short_interval_flags_interval_short_and_suppresses_rapid_growth() -> None:
    athlete = _make_athlete()
    # 1.0 cm en 20 días ≈ 1.52 cm/mes: por encima del umbral (0.6) pero la
    # ventana es < 30 días — no debe generar rapid_growth.
    previous = _make_record(
        record_id=1, evaluation_date=date(2026, 8, 12), standing_height_cm=149.0
    )
    latest = _make_record(
        record_id=2, evaluation_date=date(2026, 9, 1), standing_height_cm=150.0
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert summary.velocity is not None
    assert summary.velocity.window_days == 20
    assert summary.velocity.interval_short is True
    assert summary.velocity.cm_per_month >= 0.6
    assert GrowthSummaryAlert.rapid_growth not in summary.alerts


def test_normal_interval_with_high_velocity_raises_rapid_growth() -> None:
    athlete = _make_athlete()
    # Mismo tipo de salto pero sobre una ventana >= 30 días: sí debe alertar.
    previous = _make_record(
        record_id=1, evaluation_date=date(2026, 7, 1), standing_height_cm=147.0
    )
    latest = _make_record(
        record_id=2, evaluation_date=date(2026, 9, 1), standing_height_cm=150.0
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert summary.velocity is not None
    assert summary.velocity.interval_short is False
    assert summary.velocity.cm_per_month >= 0.6
    assert GrowthSummaryAlert.rapid_growth in summary.alerts


# ---------------------------------------------------------------------------
# Expected velocity ranges by stage and sex (research.md R-05)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "sex", "expected"),
    [
        ("Pre-PHV", "M", (4.0, 6.0)),
        ("Pre-PHV", "F", (4.0, 6.0)),
        ("Circa-PHV", "M", (8.0, 10.0)),
        ("Circa-PHV", "F", (7.0, 9.0)),
        ("Post-PHV", "M", (1.0, 4.0)),
        ("Post-PHV", "F", (1.0, 4.0)),
    ],
)
def test_expected_velocity_range_by_stage_and_sex(
    stage: str, sex: str, expected: tuple[float, float]
) -> None:
    assert get_expected_velocity_range(stage, sex) == expected


def test_expected_velocity_constants_match_research_r05() -> None:
    assert EXPECTED_VELOCITY_CM_YEAR["Pre-PHV"] == (4.0, 6.0)
    assert EXPECTED_VELOCITY_CM_YEAR["Circa-PHV"] == {"M": (8.0, 10.0), "F": (7.0, 9.0)}
    assert EXPECTED_VELOCITY_CM_YEAR["Post-PHV"] == (1.0, 4.0)


def test_velocity_carries_expected_range_for_its_stage_and_athlete_sex() -> None:
    athlete = _make_athlete(sex=Sex.F)
    previous = _make_record(
        record_id=1,
        evaluation_date=date(2026, 6, 1),
        standing_height_cm=147.0,
        maturation_status=MaturationStatus.circa_phv,
    )
    latest = _make_record(
        record_id=2,
        evaluation_date=date(2026, 9, 1),
        standing_height_cm=150.0,
        maturation_status=MaturationStatus.circa_phv,
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert summary.velocity is not None
    assert summary.velocity.expected_cm_per_year == (7.0, 9.0)


# ---------------------------------------------------------------------------
# months_from_phv sign
# ---------------------------------------------------------------------------


def test_months_from_phv_is_negative_before_peak() -> None:
    # age_at_phv (13.0) mayor que la edad actual del atleta a hoy → aún no
    # llega al pico, el signo debe ser negativo.
    athlete = _make_athlete(birth_date=date(2015, 9, 4))  # 11.0 años exactos en _TODAY
    latest = _make_record(record_id=1, evaluation_date=_TODAY, age_at_phv=13.0)

    summary = build_growth_summary(athlete, latest, None, today=_TODAY)

    assert summary.months_from_phv is not None
    assert summary.months_from_phv < 0


def test_months_from_phv_is_positive_after_peak() -> None:
    # age_at_phv (10.0) menor que la edad actual → ya pasó el pico.
    athlete = _make_athlete(birth_date=date(2013, 9, 4))  # 13.0 años exactos en _TODAY
    latest = _make_record(
        record_id=1,
        evaluation_date=_TODAY,
        age_at_phv=10.0,
        maturation_status=MaturationStatus.post_phv,
    )

    summary = build_growth_summary(athlete, latest, None, today=_TODAY)

    assert summary.months_from_phv is not None
    assert summary.months_from_phv > 0


# ---------------------------------------------------------------------------
# phase_changed
# ---------------------------------------------------------------------------


def test_phase_changed_alert_when_stage_differs_from_previous() -> None:
    athlete = _make_athlete()
    previous = _make_record(
        record_id=1,
        evaluation_date=date(2026, 6, 1),
        maturation_status=MaturationStatus.pre_phv,
    )
    latest = _make_record(
        record_id=2,
        evaluation_date=date(2026, 9, 1),
        maturation_status=MaturationStatus.circa_phv,
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert GrowthSummaryAlert.phase_changed in summary.alerts


def test_no_phase_changed_alert_when_stage_is_the_same() -> None:
    athlete = _make_athlete()
    previous = _make_record(
        record_id=1,
        evaluation_date=date(2026, 6, 1),
        maturation_status=MaturationStatus.pre_phv,
    )
    latest = _make_record(
        record_id=2,
        evaluation_date=date(2026, 9, 1),
        maturation_status=MaturationStatus.pre_phv,
    )

    summary = build_growth_summary(athlete, latest, previous, today=_TODAY)

    assert GrowthSummaryAlert.phase_changed not in summary.alerts


# ---------------------------------------------------------------------------
# approaching_circa
# ---------------------------------------------------------------------------


def test_approaching_circa_alert_in_early_warning_window() -> None:
    athlete = _make_athlete()
    latest = _make_record(
        record_id=1,
        evaluation_date=_TODAY,
        maturity_offset=-1.5,  # dentro de [-2, -1) — señal temprana
        maturation_status=MaturationStatus.pre_phv,
    )

    summary = build_growth_summary(athlete, latest, None, today=_TODAY)

    assert GrowthSummaryAlert.approaching_circa in summary.alerts


def test_no_approaching_circa_alert_far_from_peak() -> None:
    athlete = _make_athlete()
    latest = _make_record(
        record_id=1,
        evaluation_date=_TODAY,
        maturity_offset=-3.0,  # fuera de la ventana de aviso temprano
        maturation_status=MaturationStatus.pre_phv,
    )

    summary = build_growth_summary(athlete, latest, None, today=_TODAY)

    assert GrowthSummaryAlert.approaching_circa not in summary.alerts


# ---------------------------------------------------------------------------
# Shapes: no records / one record
# ---------------------------------------------------------------------------


def test_no_records_shape() -> None:
    athlete = _make_athlete()

    summary = build_growth_summary(athlete, None, None, today=_TODAY)

    assert summary.athlete_id == athlete.id
    assert summary.records_count == 0
    assert summary.latest_evaluation_date is None
    assert summary.stage is None
    assert summary.maturity_offset is None
    assert summary.age_at_phv is None
    assert summary.months_from_phv is None
    assert summary.velocity is None
    assert summary.measurement.status == MeasurementStatus.never
    assert summary.measurement.next_due_date is None
    assert summary.alerts == []
    assert summary.latest is None


def test_one_record_shape() -> None:
    athlete = _make_athlete()
    latest = _make_record(
        record_id=1,
        evaluation_date=_TODAY,
        height_z_score=-0.5,
        height_percentile=30.9,
        bmi_z_score=0.2,
        bmi_percentile=57.9,
        nutritional_status=NutritionalStatus.adecuado,
    )

    summary = build_growth_summary(athlete, latest, None, today=_TODAY)

    assert summary.records_count == 1
    assert summary.velocity is None
    assert summary.latest_evaluation_date == _TODAY
    assert summary.stage == MaturationStatus.pre_phv
    assert summary.latest is not None
    assert summary.latest.record_id == 1
    assert summary.latest.height is not None
    assert summary.latest.height.band == NutritionalStatus.talla_adecuada
    assert summary.latest.bmi is not None
    assert summary.latest.bmi.band == NutritionalStatus.adecuado
    assert summary.latest.weight is None
