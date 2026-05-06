"""Tests del PHVExplainerUseCase con FakeLLMProvider.

Estos tests son la garantía de que los componentes encajan: provider,
registry, context builder y guardrails colaboran como esperamos.
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
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase


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


def _record():
    return SimpleNamespace(
        id=1,
        athlete_id=42,
        evaluation_date=date(2026, 4, 1),
        weight_kg=Decimal("40.0"),
        standing_height_cm=Decimal("150.0"),
        arm_span_cm=Decimal("152.0"),
        sitting_height_cm=Decimal("75.0"),
        leg_length_cm=Decimal("75.0"),
        maturity_offset=Decimal("-1.5"),
        age_at_phv=Decimal("13.5"),
        maturation_status=MaturationStatus.pre_phv,
        training_implications="Habilidades, juego.",
        height_z_score=Decimal("0.4"),
        bmi=Decimal("17.8"),
        bmi_z_score=Decimal("0.1"),
        weight_z_score=Decimal("0.2"),
        height_percentile=None,
        bmi_percentile=None,
        weight_percentile=None,
        nutritional_status=None,
        notes="Confidencial",
    )


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_run_produces_text_with_fake_provider():
    fake = FakeLLMProvider(canned="Respuesta clara para padres en Pre-PHV.")
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    result = await uc.run(_athlete(), _record())
    assert "Pre-PHV" in result.text
    assert result.provider == "fake"
    assert result.age_group == "10-12"
    assert result.maturation_status == "Pre-PHV"


async def test_system_prompt_includes_principles():
    fake = FakeLLMProvider(canned="ok")
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    await uc.run(_athlete(), _record())
    sent = fake.last_request
    assert sent is not None
    assert "Diversión primero" in sent.system
    assert "Cero suplementos" in sent.system or "suplementos" in sent.system


async def test_user_message_has_no_pii():
    """El mensaje al modelo nunca lleva nombre, apellido ni fecha exacta."""
    fake = FakeLLMProvider(canned="ok")
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    await uc.run(_athlete(), _record())
    user_text = fake.last_request.messages[0].content
    assert "SECRETO" not in user_text
    assert "NO_DEBE_SALIR" not in user_text
    assert "2014-06-15" not in user_text
    assert "Confidencial" not in user_text


async def test_guardrails_clean_supplement_in_output():
    """Si el modelo sugiere creatina, el guardrail lo borra."""
    fake = FakeLLMProvider(
        canned="Tu hijo está en Pre-PHV. Recomendamos creatina para crecer."
    )
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    result = await uc.run(_athlete(), _record())
    assert "creatina" not in result.text.lower()


async def test_guardrails_reject_when_too_many_violations():
    """Salida con muchas violaciones explota — protege a los padres."""
    fake = FakeLLMProvider(
        canned=(
            "Tu hijo debe entrenar 6 días por semana, tomar creatina, "
            "y pedalear a 50 rpm para fortalecerse."
        )
    )
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    with pytest.raises(LLMSchemaError):
        await uc.run(_athlete(), _record())


async def test_run_requires_record():
    fake = FakeLLMProvider()
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    with pytest.raises(ValueError, match="medición"):
        await uc.run(_athlete(), None)


async def test_history_creates_trend_section():
    fake = FakeLLMProvider(canned="ok")
    uc = PHVExplainerUseCase(fake, PromptRegistry())
    rec_recent = _record()
    rec_old = SimpleNamespace(
        **{**vars(_record()), "evaluation_date": date(2026, 1, 1),
           "standing_height_cm": Decimal("148.0"),
           "weight_kg": Decimal("38.5")},
    )
    await uc.run(_athlete(), rec_recent, history=[rec_recent, rec_old])
    user_msg = fake.last_request.messages[0].content
    assert "Tendencia" in user_msg
