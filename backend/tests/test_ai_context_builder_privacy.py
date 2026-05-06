"""Tests bloqueantes de privacidad para `AthleteAIContextBuilder`.

Garantizan que ninguna PII de un menor sale por esta vía. Si alguno falla,
el CI debe detenerse: la falla equivale a una fuga potencial.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.anthropometry import MaturationStatus, NutritionalStatus
from app.models.athlete import Sex
from app.services.ai.context_builders import (
    ATHLETE_CONTEXT_ALLOWED_KEYS,
    AthleteAIContextBuilder,
)


def _athlete(birth_date: date = date(2014, 6, 15), sex: Sex = Sex.M):
    """Stub liviano para no necesitar la DB."""
    return SimpleNamespace(
        id=42,
        first_name="SECRETO",
        last_name="NO_DEBE_SALIR",
        birth_date=birth_date,
        sex=sex,
        user_id=99,
        club_id=1,
    )


def _record(
    evaluation_date: date = date(2026, 4, 1),
    maturity_offset: float = -1.5,
    height_cm: float = 150.0,
    weight_kg: float = 40.0,
    status: MaturationStatus = MaturationStatus.pre_phv,
):
    return SimpleNamespace(
        id=1,
        athlete_id=42,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight_kg)),
        standing_height_cm=Decimal(str(height_cm)),
        arm_span_cm=Decimal(str(height_cm + 2.0)),
        sitting_height_cm=Decimal("75.0"),
        leg_length_cm=Decimal(str(height_cm - 75.0)),
        maturity_offset=Decimal(str(maturity_offset)),
        age_at_phv=Decimal("13.5"),
        maturation_status=status,
        training_implications="Habilidades, juego.",
        height_z_score=Decimal("0.4"),
        height_percentile=Decimal("65.5"),
        bmi=Decimal("17.8"),
        bmi_z_score=Decimal("0.1"),
        bmi_percentile=Decimal("54.0"),
        weight_z_score=Decimal("0.2"),
        weight_percentile=Decimal("57.0"),
        nutritional_status=NutritionalStatus.adecuado,
        notes="Confidencial — no va al LLM",
    )


# ---------------------------------------------------------------------------
# 1. Sin PII bajo ningún supuesto
# ---------------------------------------------------------------------------


def test_context_keys_within_allowlist_with_record():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(
        _athlete(),
        _record(),
        history=[_record(), _record(date(2026, 1, 1))],
        reference_date=date(2026, 4, 1),
    )
    leaked = set(ctx.keys()) - ATHLETE_CONTEXT_ALLOWED_KEYS
    assert not leaked, f"Claves fuera de allowlist: {leaked}"


def test_context_keys_within_allowlist_without_record():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), None, reference_date=date(2026, 4, 1))
    leaked = set(ctx.keys()) - ATHLETE_CONTEXT_ALLOWED_KEYS
    assert not leaked


def test_context_never_contains_pii_keys():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), _record(), reference_date=date(2026, 4, 1))
    for forbidden in ("first_name", "last_name", "birth_date", "email", "id",
                      "user_id", "athlete_id", "evaluation_date", "notes"):
        assert forbidden not in ctx


def test_context_never_contains_pii_values():
    """Los strings sensibles del atleta no aparecen como valores tampoco."""
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), _record(), reference_date=date(2026, 4, 1))
    serialized = repr(ctx)
    assert "SECRETO" not in serialized
    assert "NO_DEBE_SALIR" not in serialized
    assert "Confidencial" not in serialized
    # birth_date exacta tampoco — solo edad decimal está permitida.
    assert "2014-06-15" not in serialized


# ---------------------------------------------------------------------------
# 2. Contenido útil presente
# ---------------------------------------------------------------------------


def test_context_includes_age_and_category():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), None, reference_date=date(2026, 4, 1))
    assert "age_decimal" in ctx
    assert ctx["age_decimal"] > 11
    assert ctx["age_group"] == "10-12"
    assert ctx["sex"] == "M"
    assert ctx["category"]


def test_context_includes_phv_data_when_record_present():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(_athlete(), _record(), reference_date=date(2026, 4, 1))
    assert ctx["maturation_status"] == "Pre-PHV"
    assert ctx["phv_offset"] == -1.5
    assert ctx["age_at_phv"] == 13.5
    assert ctx["nutritional_status"] == "adecuado"


def test_age_group_buckets():
    builder = AthleteAIContextBuilder()
    ref = date(2026, 4, 1)
    # 10-12
    ctx = builder.build(
        _athlete(birth_date=date(2015, 6, 1)), None, reference_date=ref
    )
    assert ctx["age_group"] == "10-12"
    # 13-15
    ctx = builder.build(
        _athlete(birth_date=date(2012, 6, 1)), None, reference_date=ref
    )
    assert ctx["age_group"] == "13-15"
    # 16+
    ctx = builder.build(
        _athlete(birth_date=date(2009, 6, 1)), None, reference_date=ref
    )
    assert ctx["age_group"] == "16+"


# ---------------------------------------------------------------------------
# 3. Tendencia
# ---------------------------------------------------------------------------


def test_trend_omitted_with_single_record():
    builder = AthleteAIContextBuilder()
    ctx = builder.build(
        _athlete(), _record(), history=[_record()], reference_date=date(2026, 4, 1)
    )
    assert "trend" not in ctx


def test_trend_present_with_multiple_records():
    builder = AthleteAIContextBuilder()
    history = [
        _record(date(2026, 4, 1), height_cm=152.0, weight_kg=41.0),
        _record(date(2026, 1, 1), height_cm=150.0, weight_kg=40.0),
        _record(date(2025, 10, 1), height_cm=148.5, weight_kg=39.0),
    ]
    ctx = builder.build(
        _athlete(), history[0], history=history, reference_date=date(2026, 4, 1)
    )
    assert "trend" in ctx
    assert len(ctx["trend"]) == 2
    assert ctx["trend"][0]["delta_height_cm"] == 2.0
    assert ctx["trend"][0]["weeks_ago"] >= 12
