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


def test_context_omits_z_scores_for_privacy():
    """Defense in depth: z-scores nunca deben fluir al contexto del LLM.

    Aunque el registro tenga valores válidos para height_z_score y
    weight_z_score (cargados desde DB), el builder los descarta. En bases
    pequeñas un par (z-altura, z-peso, edad, sexo) puede re-identificar a un
    menor. La plantilla `phv_explainer.j2` v2 ya no los renderiza; este test
    garantiza que tampoco lleguen por la vía del context builder.
    """
    builder = AthleteAIContextBuilder()
    record = _record()
    # Confirma que el fixture sí trae los z-scores cargados (input válido)
    assert record.height_z_score == Decimal("0.4")
    assert record.weight_z_score == Decimal("0.2")

    ctx = builder.build(_athlete(), record, reference_date=date(2026, 4, 1))

    # El contexto que se entrega al LLM no debe contener ninguno
    assert "height_z_score" not in ctx
    assert "weight_z_score" not in ctx

    # Sí debe mantenerse el estado nutricional cualitativo (categoría MinSalud)
    assert ctx["nutritional_status"] == "adecuado"


def test_allowlist_excludes_z_scores():
    """La allowlist tampoco debe permitir z-scores como claves válidas."""
    from app.services.ai.context_builders import ATHLETE_CONTEXT_ALLOWED_KEYS

    assert "height_z_score" not in ATHLETE_CONTEXT_ALLOWED_KEYS
    assert "weight_z_score" not in ATHLETE_CONTEXT_ALLOWED_KEYS


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


# ---------------------------------------------------------------------------
# 4. Redondeo defensivo de phv_offset / age_at_phv (GAP-3)
# ---------------------------------------------------------------------------
#
# La precisión de 2-3 decimales en clubes pequeños (n<10) combinada con
# (sexo, age_group) permite re-identificación. El builder redondea a 1
# decimal antes de inyectar, preservando utilidad clínica (Mirwald ±1 año).


def test_phv_offset_rounded_to_one_decimal():
    builder = AthleteAIContextBuilder()
    rec = _record(maturity_offset=0.8473)
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert ctx["phv_offset"] == 0.8


def test_phv_offset_negative_value_rounded():
    builder = AthleteAIContextBuilder()
    rec = _record(maturity_offset=-1.2649)
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert ctx["phv_offset"] == -1.3


def test_age_at_phv_rounded_to_one_decimal():
    """`age_at_phv` también se redondea (mismo patrón que phv_offset)."""
    builder = AthleteAIContextBuilder()
    # Construyo manualmente para forzar valor con más decimales
    rec = _record()
    rec.age_at_phv = Decimal("13.5817")
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert ctx["age_at_phv"] == 13.6


def test_phv_offset_none_remains_none():
    """Si el dato falta, `None` debe propagarse sin error de redondeo."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.maturity_offset = None
    rec.age_at_phv = None
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert ctx["phv_offset"] is None
    assert ctx["age_at_phv"] is None


# ---------------------------------------------------------------------------
# 5. Sanitización de training_implications (GAP-4)
# ---------------------------------------------------------------------------
#
# Texto libre escrito por el coach en la BD. El builder lo sanea antes de
# inyectarlo al LLM: trunca a 300 caracteres, elimina nombres propios y
# patrones diagnósticos. Si tras saneo queda vacío, omite la clave.


def test_training_implications_strips_proper_names():
    """Nombre propio (dos palabras capitalizadas) debe eliminarse."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = "Conversar con Juan Pérez sobre la sesión."
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    val = ctx["training_implications"]
    assert "Juan Pérez" not in val
    assert "Juan" not in val and "Pérez" not in val


def test_training_implications_strips_diagnostic_terms():
    """Términos diagnósticos (RED-S, déficit) deben eliminarse."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = "Sospecha de diagnóstico de RED-S, observar."
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    val = ctx["training_implications"]
    assert "RED-S" not in val
    assert "diagnóstico" not in val.lower()
    # Lo no-clínico se mantiene
    assert "observar" in val.lower()


def test_training_implications_truncates_long_text():
    """Texto >300 chars debe truncarse con elipsis."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = "habilidades técnicas y juego dirigido. " * 20
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    val = ctx["training_implications"]
    # Con elipsis, longitud máxima 301 (300 + "…")
    assert len(val) <= 301
    assert val.endswith("…")


def test_training_implications_omitted_when_empty_after_sanitize():
    """Si tras saneo queda vacío, la clave se omite del ctx."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    # Texto que se elimina por completo: solo nombre propio + diagnóstico.
    rec.training_implications = "Juan Pérez patología."
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert "training_implications" not in ctx


def test_training_implications_omitted_when_none():
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = None
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert "training_implications" not in ctx


def test_training_implications_omitted_when_blank():
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = "   "
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert "training_implications" not in ctx


def test_training_implications_clean_text_passes_through():
    """Texto legítimo (sin nombres ni términos clínicos) debe llegar igual."""
    builder = AthleteAIContextBuilder()
    rec = _record()
    rec.training_implications = "Habilidades técnicas y juego dirigido."
    ctx = builder.build(_athlete(), rec, reference_date=date(2026, 4, 1))
    assert ctx["training_implications"] == "Habilidades técnicas y juego dirigido."
