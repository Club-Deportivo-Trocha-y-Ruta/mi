"""Tests del `AthleteAIContextBuilder.build_record_delta` y privacy fixes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.services.ai.context_builders import (
    ATHLETE_CONTEXT_ALLOWED_KEYS,
    AthleteAIContextBuilder,
)


def _athlete():
    return SimpleNamespace(
        first_name="Pepe",
        last_name="Perez",
        birth_date=date(2014, 6, 15),
        sex=Sex.M,
    )


def _record(
    *,
    rid: int = 10,
    eval_date: date = date(2026, 4, 1),
    weight: str = "40.0",
    height: str = "150.0",
    status: MaturationStatus = MaturationStatus.pre_phv,
):
    return SimpleNamespace(
        id=rid,
        evaluation_date=eval_date,
        weight_kg=Decimal(weight),
        standing_height_cm=Decimal(height),
        arm_span_cm=Decimal("152.0"),
        sitting_height_cm=Decimal("75.0"),
        leg_length_cm=Decimal("75.0"),
        leg_sitting_ratio=Decimal("1.0"),
        maturity_offset=Decimal("-1.5"),
        age_at_phv=Decimal("13.5"),
        maturation_status=status,
        training_implications="Habilidades, juego.",
        height_z_score=Decimal("0.4"),
        bmi=Decimal("17.8"),
        bmi_z_score=Decimal("0.1"),
        weight_z_score=Decimal("0.2"),
        nutritional_status=None,
    )


def test_build_record_delta_first_measurement():
    builder = AthleteAIContextBuilder()
    target = _record()
    ctx = builder.build_record_delta(_athlete(), target, [])

    assert ctx["num_previous_measurements"] == 0
    assert "delta_height_cm" not in ctx
    assert "delta_weight_kg" not in ctx
    assert "growth_velocity_cm_per_year" not in ctx
    assert "crossed_phv_phase" not in ctx


def test_build_record_delta_with_significant_delta():
    builder = AthleteAIContextBuilder()
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0", weight="42.5")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    assert ctx["num_previous_measurements"] == 1
    assert ctx["delta_height_cm"] == 3.0
    assert ctx["delta_weight_kg"] == 2.5
    assert ctx["delta_height_significant"] is True
    assert ctx["delta_weight_significant"] is True
    assert ctx["weeks_since_prev_measurement"] >= 12
    assert "growth_velocity_cm_per_year" in ctx


def test_build_record_delta_noise_below_threshold():
    builder = AthleteAIContextBuilder()
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="150.5", weight="40.5")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    # 0.5 < 0.7 → no significativo
    assert ctx["delta_height_significant"] is False
    # 0.5 < 1.5 → no significativo
    assert ctx["delta_weight_significant"] is False


def test_build_record_delta_velocity_requires_min_weeks():
    builder = AthleteAIContextBuilder()
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="151.5")
    # Solo 4 semanas — debajo del umbral de 8
    prior = _record(rid=10, eval_date=date(2026, 3, 1), height="150.0")
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    assert "growth_velocity_cm_per_year" not in ctx


def test_build_record_delta_detects_phv_phase_crossing():
    builder = AthleteAIContextBuilder()
    target = _record(
        rid=20, eval_date=date(2026, 4, 1), status=MaturationStatus.circa_phv
    )
    prior = _record(
        rid=10, eval_date=date(2026, 1, 1), status=MaturationStatus.pre_phv
    )
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    assert ctx["crossed_phv_phase"] is True
    assert ctx["prev_maturation_status"] == "Pre-PHV"
    assert ctx["maturation_status"] == "Circa-PHV"


def test_build_record_delta_no_phase_crossing_when_same_status():
    builder = AthleteAIContextBuilder()
    target = _record(rid=20, eval_date=date(2026, 4, 1))
    prior = _record(rid=10, eval_date=date(2026, 1, 1))
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    assert ctx["crossed_phv_phase"] is False


def test_build_record_delta_picks_immediate_prior():
    """Si hay múltiples previos, solo el inmediato anterior alimenta deltas."""
    builder = AthleteAIContextBuilder()
    target = _record(rid=30, eval_date=date(2026, 4, 1), height="153.0")
    middle = _record(rid=20, eval_date=date(2026, 2, 1), height="151.5")
    oldest = _record(rid=10, eval_date=date(2026, 1, 1), height="148.0")

    ctx = builder.build_record_delta(_athlete(), target, [oldest, middle])

    # delta vs `middle` (más reciente de los priors), no vs `oldest`
    assert ctx["delta_height_cm"] == 1.5
    assert ctx["num_previous_measurements"] == 2


def test_no_pii_keys_present():
    """Ninguna clave del context cae fuera de la allowlist."""
    builder = AthleteAIContextBuilder()
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0")
    ctx = builder.build_record_delta(_athlete(), target, [prior])

    leaked = set(ctx) - ATHLETE_CONTEXT_ALLOWED_KEYS
    assert leaked == set(), f"Claves no permitidas en contexto: {leaked}"


def test_bmi_numeric_removed_from_build():
    """Privacy fix: build() ya no incluye bmi ni bmi_z_score numéricos."""
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), _record(), history=None)

    assert "bmi" not in ctx
    assert "bmi_z_score" not in ctx
    # Pero nutritional_status sigue disponible si está cargado
    nutr_record = _record()
    nutr_record.nutritional_status = SimpleNamespace(value="adecuado")
    ctx2 = builder.build(_athlete(), nutr_record, history=None)
    assert ctx2.get("nutritional_status") == "adecuado"


def test_age_decimal_rounded_to_one_decimal():
    """Privacy fix: evaluation_age_decimal redondeado a 1 decimal."""
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), _record(), history=None)

    # round(x, 1) → como máximo 1 decimal
    eval_age = ctx["evaluation_age_decimal"]
    # multiplied by 10 must be integer
    assert abs(eval_age * 10 - round(eval_age * 10)) < 1e-9
    age = ctx["age_decimal"]
    assert abs(age * 10 - round(age * 10)) < 1e-9
