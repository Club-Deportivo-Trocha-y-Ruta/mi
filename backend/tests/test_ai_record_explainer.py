"""Tests del AnthropometricRecordExplainerUseCase.

Verifican: cálculo de deltas, supresión de ruido instrumental, transición de
fase PHV, primera medición sin historial, y guardrails anti-diagnóstico.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.services.ai.errors import LLMSchemaError
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.anthropometric_record_explainer import (
    AnthropometricRecordExplainerUseCase,
)


def _athlete():
    return SimpleNamespace(
        id=42,
        first_name="SECRETO",
        last_name="NO_DEBE_SALIR",
        birth_date=date(2014, 6, 15),
        sex=Sex.M,
        user_id=99,
        club_id=1,
    )


def _record(
    *,
    rid: int = 10,
    eval_date: date = date(2026, 4, 1),
    weight: str = "40.0",
    height: str = "150.0",
    sitting: str = "75.0",
    status: MaturationStatus = MaturationStatus.pre_phv,
    nutritional=None,
):
    return SimpleNamespace(
        id=rid,
        athlete_id=42,
        evaluation_date=eval_date,
        weight_kg=Decimal(weight),
        standing_height_cm=Decimal(height),
        arm_span_cm=Decimal("152.0"),
        sitting_height_cm=Decimal(sitting),
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
        height_percentile=None,
        bmi_percentile=None,
        weight_percentile=None,
        nutritional_status=nutritional,
        notes="Confidencial",
    )


async def test_first_measurement_no_history():
    """num_previous_measurements=0 → rama 'primera medición'."""
    fake = FakeLLMProvider(canned="Es la primera medición registrada.")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record()
    result = await uc.run(_athlete(), target, prior_records=[])

    assert result.num_previous_measurements == 0
    assert result.delta_height_cm is None
    assert result.delta_weight_kg is None
    assert result.record_id == target.id
    assert result.maturation_status == "Pre-PHV"
    # El prompt debe haber renderizado la rama de primera medición
    sent_user = fake.last_request.messages[0].content
    assert "primera medición" in sent_user.lower() or "primera mediciÓn" in sent_user.lower() or "primera mediciOn" in sent_user.lower()


async def test_with_prior_record_computes_deltas():
    fake = FakeLLMProvider(canned="Su hijo creció desde la última medición.")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0", weight="42.5")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")

    result = await uc.run(_athlete(), target, prior_records=[prior])

    assert result.num_previous_measurements == 1
    assert result.delta_height_cm == 3.0
    assert result.delta_weight_kg == 2.5


async def test_growth_velocity_only_when_enough_weeks():
    """Si <8 semanas, no se incluye growth_velocity en el contexto."""
    fake = FakeLLMProvider(canned="ok")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="151.5")
    prior = _record(rid=10, eval_date=date(2026, 3, 15), height="150.0")  # <8 semanas

    await uc.run(_athlete(), target, prior_records=[prior])

    user_msg = fake.last_request.messages[0].content
    assert "Velocidad estimada" not in user_msg


async def test_delta_below_significance_threshold_is_omitted():
    """Δ talla 0.5 cm (< 0.7) no debe aparecer como cambio significativo."""
    fake = FakeLLMProvider(canned="ok")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="150.5", weight="40.5")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0", weight="40.0")

    result = await uc.run(_athlete(), target, prior_records=[prior])

    user_msg = fake.last_request.messages[0].content
    # delta_height = 0.5 < 0.7 → no aparece la línea de cambio significativo
    assert "Cambio de talla desde la medición anterior: 0.5" not in user_msg
    # delta_weight = 0.5 < 1.5 → tampoco
    assert "Cambio de peso desde la medición anterior: 0.5" not in user_msg
    # Pero los valores numéricos sí están en el response para el frontend
    assert result.delta_height_cm == 0.5
    assert result.delta_weight_kg == 0.5


async def test_phv_phase_transition_detected():
    """Cambio Pre-PHV → Circa-PHV se reporta como transición."""
    fake = FakeLLMProvider(canned="Su hijo entró a la fase Circa-PHV.")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record(
        rid=20, eval_date=date(2026, 4, 1), height="156.0",
        status=MaturationStatus.circa_phv,
    )
    prior = _record(
        rid=10, eval_date=date(2026, 1, 1), height="150.0",
        status=MaturationStatus.pre_phv,
    )

    await uc.run(_athlete(), target, prior_records=[prior])

    user_msg = fake.last_request.messages[0].content
    assert "CAMBIÓ de fase de maduración" in user_msg
    assert "Pre-PHV" in user_msg
    assert "Circa-PHV" in user_msg


async def test_pii_never_reaches_llm():
    """Ni el nombre ni la fecha de nacimiento exacta pueden filtrarse."""
    fake = FakeLLMProvider(canned="ok")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record()
    await uc.run(_athlete(), target, prior_records=[])

    user_msg = fake.last_request.messages[0].content
    assert "SECRETO" not in user_msg
    assert "NO_DEBE_SALIR" not in user_msg
    assert "2014-06-15" not in user_msg
    assert "Confidencial" not in user_msg


async def test_anti_diagnostic_guardrail_scrubs_red_s():
    """Si el LLM menciona RED-S, el guardrail lo elimina del output."""
    fake = FakeLLMProvider(
        canned="Su hijo podría tener síndrome de deficiencia energética relativa."
    )
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record()
    result = await uc.run(_athlete(), target, prior_records=[])

    assert "RED-S" not in result.text
    assert "deficiencia energética" not in result.text.lower()


async def test_anti_diagnostic_rejects_excessive_violations():
    """Texto con múltiples términos diagnósticos → LLMSchemaError."""
    fake = FakeLLMProvider(
        canned=(
            "Su hijo tiene patología y posible diagnóstico de retraso puberal "
            "con déficit energético. Esto es anormal."
        )
    )
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record()
    with pytest.raises(LLMSchemaError):
        await uc.run(_athlete(), target, prior_records=[])


async def test_prior_records_after_target_are_ignored():
    """Si por error llegan registros posteriores a target, no afectan deltas."""
    fake = FakeLLMProvider(canned="ok")
    uc = AnthropometricRecordExplainerUseCase(fake, PromptRegistry())
    target = _record(rid=20, eval_date=date(2026, 4, 1), height="153.0")
    future = _record(rid=30, eval_date=date(2026, 8, 1), height="160.0")
    prior = _record(rid=10, eval_date=date(2026, 1, 1), height="150.0")

    result = await uc.run(_athlete(), target, prior_records=[future, prior])

    # Solo cuenta el `prior` (estrictamente anterior). num_previous = 1.
    assert result.num_previous_measurements == 1
    assert result.delta_height_cm == 3.0
