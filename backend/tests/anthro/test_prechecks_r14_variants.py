"""R14 also catches plurals/conjugations (feature 046, T069 audit finding F5).

Synthetic, generic sentences only — no athlete data (CLAUDE.md / Ley 1581).
"""
from __future__ import annotations

import pytest

from app.services.ai.anthro.prechecks import check_r14_diet_or_weight_loss_language
from app.services.ai.anthro.schemas import AnthropometryInsightV1, Confidence, ConfidenceLevel


def _insight(audience: str, summary_line: str) -> AnthropometryInsightV1:
    return AnthropometryInsightV1(
        audience=audience,
        summary_line=summary_line,
        changes=["El cambio fue moderado esta temporada."],
        meaning=["Esto refleja un ritmo de desarrollo dentro de lo esperado."],
        next_weeks=["Mantener la rutina habitual de entrenamiento."],
        warning_signs=[],
        confidence=Confidence(
            level=ConfidenceLevel.MEDIUM, reason="Hay mediciones suficientes para esta observación."
        ),
        data_gaps=[],
        word_count=20,
    )


@pytest.mark.parametrize("audience", ["family", "coach"])
@pytest.mark.parametrize(
    "text",
    [
        "No hacen falta dietas especiales.",
        "No es momento de bajar peso.",
        "No necesita perder de peso.",
        "Que no adelgace es lo esperado.",
        "No buscamos un adelgazamiento.",
    ],
)
def test_r14_blocks_plural_and_conjugated_variants(audience: str, text: str) -> None:
    violation = check_r14_diet_or_weight_loss_language(_insight(audience, text))
    assert violation is not None
    assert violation.rule_id == "R14"


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_r14_still_passes_neutral_food_first_language(audience: str) -> None:
    text = "Una alimentación variada acompaña bien su crecimiento."
    assert check_r14_diet_or_weight_loss_language(_insight(audience, text)) is None
