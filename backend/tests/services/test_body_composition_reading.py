"""Tests for `build_reading` — change classifier, traffic light, family projection, copy.

Source of truth: `specs/046-body-composition-skinfolds/contracts/body-composition-reading.md`
§2–§5 (scenarios A–I of §5 are parametrised below, asserting both the coach
`band` and the `family_band`).

Strategy: `build_reading` is pure, so every input is a synthetic
`SimpleNamespace` standing in for `SkinfoldMeasurement` / `AnthropometricRecord`
(no DB, no I/O). All data is fictitious (CLAUDE.md §Privacy): no name, birth
date or note of a minor appears anywhere.
"""
from __future__ import annotations

import itertools
import re
from datetime import date, timedelta
from types import SimpleNamespace
from typing import get_args

import pytest

from app.config import Settings
from app.schemas.body_composition import BAND_REASON_CODE
from app.schemas.growth import GrowthVelocity
from app.services.body_composition import (
    COACH_REASON_COPY,
    ESCALATION_COPY,
    FAMILY_COPY,
    NEWSLETTER_NOTICE,
    SITES,
    ReadingLegs,
    build_reading,
    change_sentence,
    classify_band,
    is_reference_only_ambar,
    project_family_band,
)

D0 = date(2026, 1, 15)
D1 = D0 + timedelta(days=120)


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _set(
    sum4: float | None,
    *,
    sum6: float | None = None,
    ffm: float | None = None,
    declined: tuple[str, ...] = (),
    all_declined: bool = False,
) -> SimpleNamespace:
    """Synthetic skinfold set. Site values are placeholders; only sums matter."""
    attrs: dict[str, object] = {}
    for site in SITES:
        is_declined = all_declined or site in declined
        attrs[f"{site}_declined"] = is_declined
        attrs[f"{site}_mm"] = None if is_declined else 8.0
    attrs["sum4_mm"] = None if all_declined else sum4
    attrs["sum6_mm"] = None if all_declined else sum6
    attrs["fat_free_mass_kg"] = ffm
    return SimpleNamespace(**attrs)


def _record(
    evaluation_date: date,
    *,
    weight: float | None,
    height: float | None,
    stage: str = "Circa-PHV",
    bmi_z: float | None = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_date=evaluation_date,
        weight_kg=weight,
        standing_height_cm=height,
        maturation_status=stage,
        bmi_z_score=bmi_z,
    )


def _velocity(cm_per_year: float, expected: tuple[float, float]) -> GrowthVelocity:
    return GrowthVelocity(
        cm_per_month=round(cm_per_year / 12, 2),
        cm_per_year=cm_per_year,
        window_days=120,
        interval_short=False,
        expected_cm_per_year=expected,
    )


def _ref(triceps: str = "normal", subscapular: str = "normal") -> dict[str, dict[str, object]]:
    pct = {"low_extreme": 3.0, "low": 7.0, "normal": 50.0, "high": 90.0, "high_extreme": 97.0}
    return {
        "triceps": {"percentile": pct.get(triceps), "code": triceps},
        "subscapular": {"percentile": pct.get(subscapular), "code": subscapular},
    }


# ---------------------------------------------------------------------------
# §5 scenarios A–I
# ---------------------------------------------------------------------------


def _scenario(name: str) -> dict[str, object]:
    """Keyword arguments for `build_reading` for one §5 scenario."""
    if name == "A":  # girl circa→post PHV, rising Σ4 explained by growth
        return dict(
            latest_set=_set(39.0),
            previous_set=_set(32.0),
            latest_record=_record(D1, weight=42.5, height=152.5, stage="Post-PHV"),
            previous_record=_record(D0, weight=38.0, height=148.0, stage="Circa-PHV"),
            velocity=_velocity(4.5, (1.0, 4.0)),
            reference_context=_ref(),
            sex="F",
        )
    if name == "B":  # boy post PHV, Σ4 stable, weight up
        return dict(
            latest_set=_set(27.0),
            previous_set=_set(28.0),
            latest_record=_record(D1, weight=49.5, height=161.0, stage="Post-PHV"),
            previous_record=_record(D0, weight=45.0, height=158.0, stage="Post-PHV"),
            velocity=_velocity(3.0, (1.0, 4.0)),
            reference_context=_ref(),
            sex="M",
        )
    if name == "C":  # energy-availability pattern
        return dict(
            latest_set=_set(22.0),
            previous_set=_set(30.0),
            latest_record=_record(D1, weight=40.5, height=148.5),
            previous_record=_record(D0, weight=40.0, height=145.0),
            velocity=_velocity(10.0, (7.0, 9.0)),
            reference_context=_ref(),
            sex="F",
        )
    if name == "D":  # single set, triceps ≥ P95
        return dict(
            latest_set=_set(40.0),
            previous_set=None,
            latest_record=_record(D1, weight=41.0, height=150.0),
            previous_record=None,
            velocity=None,
            reference_context=_ref(triceps="high_extreme"),
            sex="F",
        )
    if name == "F":  # Σ4 down, weight flat, height leg missing
        return dict(
            latest_set=_set(22.0),
            previous_set=_set(30.0),
            latest_record=_record(D1, weight=40.2, height=148.5),
            previous_record=_record(D0, weight=40.0, height=None),
            velocity=None,
            reference_context=_ref(),
            sex="M",
        )
    if name == "I":  # rising Σ4 unexplained + triceps ≥ P95
        return dict(
            latest_set=_set(40.0),
            previous_set=_set(31.0),
            latest_record=_record(D1, weight=41.0, height=150.0, stage="Circa-PHV"),
            previous_record=_record(D0, weight=40.8, height=147.0, stage="Circa-PHV"),
            velocity=_velocity(9.0, (8.0, 10.0)),
            reference_context=_ref(triceps="high_extreme"),
            sex="M",
        )
    raise AssertionError(name)


@pytest.mark.parametrize(
    ("name", "band", "reason", "family_band"),
    [
        ("A", "verde", "expected_pubertal_gain", "verde"),
        ("B", "verde", "post_phv_lean_gain", "verde"),
        ("C", "rojo", "energy_availability_pattern", "ambar"),
        ("D", "ambar", "reference_extreme", "verde"),
        ("F", "ambar", "sum_down_unexplained", "ambar"),
        ("I", "ambar", "sum_up_unexplained", "ambar"),
    ],
)
def test_scenarios_band_and_family_band(name: str, band: str, reason: str, family_band: str) -> None:
    reading = build_reading(settings=_settings(), **_scenario(name))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.band == band
    assert reading.band_reason_code == reason
    assert reading.family_band == family_band


def test_scenario_a_legs() -> None:
    reading = build_reading(settings=_settings(), **_scenario("A"))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.sum_change_code == "up_real"
    assert reading.weight_change_code == "up"
    assert reading.height_growth_code == "growing"
    assert reading.velocity_code == "within_or_above"
    assert reading.sum4_change_mm == pytest.approx(7.0)


def test_scenario_c_is_energy_pattern_legs() -> None:
    reading = build_reading(settings=_settings(), **_scenario("C"))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.sum_change_code == "down_real"
    assert reading.weight_change_code == "flat_or_down"
    assert reading.height_growth_code == "growing"


def test_scenario_d_single_set_never_rojo() -> None:
    reading = build_reading(settings=_settings(), **_scenario("D"))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.sets_count == 1
    assert reading.band != "rojo"
    assert reading.sum_change_code == "none"
    assert reading.reference_triceps.code == "high_extreme"


@pytest.mark.parametrize(("latest_sum4", "code"), [(38.9, "within_noise"), (39.0, "up_real")])
def test_scenario_e_threshold_edge(latest_sum4: float, code: str) -> None:
    kwargs = _scenario("B")
    kwargs["previous_set"] = _set(32.0)
    kwargs["latest_set"] = _set(latest_sum4)
    reading = build_reading(settings=_settings(), **kwargs)  # type: ignore[arg-type]
    assert reading is not None
    assert reading.sum_change_code == code


def test_scenario_f_height_leg_missing() -> None:
    reading = build_reading(settings=_settings(), **_scenario("F"))  # type: ignore[arg-type]
    assert reading is not None
    assert reading.height_growth_code == "unavailable"
    assert "height" in reading.legs_missing
    assert reading.band != "rojo"


def test_scenario_g_all_declined_has_no_reading() -> None:
    reading = build_reading(
        _set(None, all_declined=True),
        None,
        _record(D1, weight=40.0, height=150.0),
        None,
        None,
        None,
        _settings(),
        sex="F",
    )
    assert reading is None


def test_no_latest_set_has_no_reading() -> None:
    reading = build_reading(None, None, None, None, None, None, _settings(), sex="M")
    assert reading is None


def test_scenario_h_latest_attempt_declined() -> None:
    s1_record = _record(D0, weight=40.0, height=150.0)
    declined_record = _record(D0 + timedelta(days=100), weight=40.5, height=151.0)
    reading = build_reading(
        _set(30.0),
        None,
        s1_record,
        None,
        None,
        _ref(),
        _settings(),
        sex="F",
        latest_attempt=_set(None, all_declined=True),
        latest_attempt_record=declined_record,
        today=D0 + timedelta(days=101),
    )
    assert reading is not None
    assert reading.band_reason_code == "first_set"
    assert reading.band == "verde"
    assert reading.family_band == "verde"
    assert reading.latest_attempt_declined == D0 + timedelta(days=100)
    assert reading.next_due_date == D0 + timedelta(days=90)
    assert reading.days_until_due == -11


def test_latest_attempt_counted_is_not_declined() -> None:
    record = _record(D0, weight=40.0, height=150.0)
    latest = _set(30.0)
    reading = build_reading(
        latest, None, record, None, None, _ref(), _settings(),
        sex="F", latest_attempt=latest, latest_attempt_record=record,
    )
    assert reading is not None
    assert reading.latest_attempt_declined is None


def test_missing_previous_set_is_listed_in_legs_missing() -> None:
    reading = build_reading(settings=_settings(), **_scenario("D"))  # type: ignore[arg-type]
    assert reading is not None
    assert "previous_set" in reading.legs_missing
    assert reading.band_reason_code == "reference_extreme"


def test_next_due_counts_from_latest_counted_set() -> None:
    reading = build_reading(
        settings=_settings(), today=D1, **_scenario("B")  # type: ignore[arg-type]
    )
    assert reading is not None
    assert reading.next_due_date == D1 + timedelta(days=90)
    assert reading.days_until_due == 90


def test_sites_declined_count_and_reference_leg() -> None:
    kwargs = _scenario("B")
    kwargs["latest_set"] = _set(None, declined=("triceps", "biceps"))
    kwargs["reference_context"] = _ref(triceps="unavailable")
    reading = build_reading(settings=_settings(), **kwargs)  # type: ignore[arg-type]
    assert reading is not None
    assert reading.sites_declined_count == 2
    assert reading.sum_change_code == "none"
    assert "reference" in reading.legs_missing


def test_reference_plus_bmi_drop_is_not_reference_only() -> None:
    kwargs = _scenario("B")
    kwargs["reference_context"] = _ref(subscapular="low_extreme")
    kwargs["latest_record"] = _record(D1, weight=49.5, height=161.0, stage="Post-PHV", bmi_z=-1.2)
    reading = build_reading(settings=_settings(), **kwargs)  # type: ignore[arg-type]
    assert reading is not None
    assert reading.band == "ambar"
    assert reading.band_reason_code == "reference_extreme"
    assert reading.bmi_z_change_code == "drop_large"
    assert reading.family_band == "ambar"


def test_velocity_low_persistent() -> None:
    kwargs = _scenario("B")
    kwargs["velocity"] = _velocity(0.5, (1.0, 4.0))
    reading = build_reading(
        settings=_settings(),
        previous_velocity=_velocity(0.6, (1.0, 4.0)),
        **kwargs,  # type: ignore[arg-type]
    )
    assert reading is not None
    assert reading.band_reason_code == "velocity_low_persistent"
    assert reading.family_band == "ambar"


@pytest.mark.parametrize(
    ("growth_explanation_code", "velocity_code", "expected_reason"),
    [
        # Velocity `below` always leaves growth explanation `none` (contract
        # §3 note): `sum_up_velocity_low` must win, not be shadowed by
        # `sum_up_unexplained` matching first.
        ("none", "below", "sum_up_velocity_low"),
        ("none", "within_or_above", "sum_up_unexplained"),
    ],
)
def test_sum_up_ambar_rule_order(
    growth_explanation_code: str, velocity_code: str, expected_reason: str
) -> None:
    legs = ReadingLegs(
        sum_change_code="up_real",
        weight_change_code="up",
        height_growth_code="growing",
        velocity_code=velocity_code,
        previous_velocity_code="within_or_above",
        bmi_z_change_code="ok",
        reference_triceps_code="normal",
        reference_subscapular_code="normal",
        growth_explanation_code=growth_explanation_code,
    )
    band, reason = classify_band(legs, sets_count=2)
    assert band == "ambar"
    assert reason == expected_reason


# ---------------------------------------------------------------------------
# Properties over the leg-code product
# ---------------------------------------------------------------------------

_SUM = ("none", "within_noise", "up_real", "down_real")
_WEIGHT = ("up", "flat_or_down", "unavailable")
_HEIGHT = ("growing", "stalled", "unavailable")
_VELOCITY = ("within_or_above", "below", "unavailable")
_BMI = ("ok", "drop_moderate", "drop_large", "unavailable")
_REF = ("low_extreme", "normal", "high_extreme", "unavailable")
_EXPLANATION = ("expected_pubertal_gain", "pre_spurt_accumulation", "post_phv_lean_gain", "none")


def _all_legs():
    for combo in itertools.product(
        _SUM, _WEIGHT, _HEIGHT, _VELOCITY, _VELOCITY, _BMI, _REF, _REF, _EXPLANATION
    ):
        yield ReadingLegs(*combo)


def test_property_family_band_never_rojo_and_rising_or_single_never_rojo() -> None:
    reasons_seen: set[str] = set()
    for legs in _all_legs():
        for sets_count in (1, 2, 3):
            band, reason = classify_band(legs, sets_count)
            reasons_seen.add(reason)
            family = project_family_band(band, reference_only=is_reference_only_ambar(legs))
            assert family in ("verde", "ambar")
            if legs.sum_change_code == "up_real":
                assert band != "rojo"
            if sets_count == 1:
                assert band != "rojo"
            if band == "rojo":
                assert family == "ambar"
                assert reason == "energy_availability_pattern"
            if band == "verde":
                assert family == "verde"
    assert "energy_availability_pattern" in reasons_seen


def test_project_family_band_table() -> None:
    assert project_family_band("verde", reference_only=False) == "verde"
    assert project_family_band("ambar", reference_only=True) == "verde"
    assert project_family_band("ambar", reference_only=False) == "ambar"
    assert project_family_band("rojo", reference_only=False) == "ambar"


# ---------------------------------------------------------------------------
# Copy (§4)
# ---------------------------------------------------------------------------

_NUMERIC_LEAK = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm)")


def test_family_copy_has_no_rojo_and_no_professional_mention() -> None:
    assert set(FAMILY_COPY) == {"verde", "ambar"}
    for entry in FAMILY_COPY.values():
        assert set(entry) == {"family_label", "family_sentence"}
        for text in entry.values():
            assert "profesional" not in text.lower()
    assert "profesional" not in NEWSLETTER_NOTICE.lower()


def test_family_copy_has_no_numbers_with_units() -> None:
    texts = [t for entry in FAMILY_COPY.values() for t in entry.values()] + [NEWSLETTER_NOTICE]
    for text in texts:
        assert not _NUMERIC_LEAK.search(text), text


def test_every_reason_code_has_a_coach_sentence() -> None:
    assert set(COACH_REASON_COPY) == set(get_args(BAND_REASON_CODE))
    assert all(sentence.strip() for sentence in COACH_REASON_COPY.values())


def test_escalation_copy_only_for_ambar_and_rojo() -> None:
    assert set(ESCALATION_COPY) == {"ambar", "rojo"}


def test_change_sentence() -> None:
    assert change_sentence("within_noise", 6.9, 7.0) == (
        "Dentro del margen de medición (+6.9 mm; umbral 7.0 mm)"
    )
    assert change_sentence("down_real", -8.0, 7.0) == "Cambio real (-8.0 mm; umbral 7.0 mm)"
    assert change_sentence("none", None, 7.0) == "Sin toma anterior comparable"
