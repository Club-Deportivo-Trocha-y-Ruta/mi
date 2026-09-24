"""Tests for R13/R14 (feature 046, T061).

Covers `app/services/ai/anthro/prechecks.py::check_r13_body_comp_numeric_leak_
to_family` and `check_r14_diet_or_weight_loss_language` against
`specs/046-body-composition-skinfolds/contracts/ai-body-composition-leaf.md`
§3 — the contract table is the source of truth for the positive/negative
cases below, not this docstring.

All text fixtures are synthetic, generic sentences — no athlete data
(CLAUDE.md / Ley 1581).
"""

from __future__ import annotations

import pytest

from app.services.ai.anthro.prechecks import (
    check_r13_body_comp_numeric_leak_to_family,
    check_r14_diet_or_weight_loss_language,
)
from app.services.ai.anthro.schemas import (
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)


def _confidence(reason: str = "Hay mediciones suficientes para esta observación.") -> Confidence:
    return Confidence(level=ConfidenceLevel.MEDIUM, reason=reason)


def _insight(*, audience: str = "family", summary_line: str) -> AnthropometryInsightV1:
    return AnthropometryInsightV1(
        audience=audience,
        summary_line=summary_line,
        changes=["El cambio fue moderado esta temporada."],
        meaning=["Esto refleja un ritmo de desarrollo dentro de lo esperado."],
        next_weeks=["Mantener la rutina habitual de entrenamiento."],
        warning_signs=[],
        confidence=_confidence(),
        data_gaps=[],
        word_count=20,
    )


# ---------------------------------------------------------------------------
# R13 — body-composition numeric leak to family (family only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["La composición corporal marcó 18 %.", "El valor fue 18,5% en la última medición.", "La suma dio 32 mm."],
)
def test_r13_blocks_family_texts_with_numeric_body_comp_figures(text):
    insight = _insight(audience="family", summary_line=text)
    violation = check_r13_body_comp_numeric_leak_to_family(insight)
    assert violation is not None
    assert violation.rule_id == "R13"
    assert violation.must_block is True
    assert violation.category == "privacy"


@pytest.mark.parametrize(
    "text",
    ["La composición corporal marcó 18 %.", "El valor fue 18,5% en la última medición.", "La suma dio 32 mm."],
)
def test_r13_passes_the_same_texts_for_coach_audience(text):
    insight = _insight(audience="coach", summary_line=text)
    assert check_r13_body_comp_numeric_leak_to_family(insight) is None


def test_r13_passes_family_texts_without_any_number():
    insight = _insight(
        audience="family", summary_line="La composición corporal se mantiene en su curva esperada."
    )
    assert check_r13_body_comp_numeric_leak_to_family(insight) is None


# ---------------------------------------------------------------------------
# R14 — diet / weight-loss language (both audiences)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Se recomienda hacer dieta esta temporada.",
        "El objetivo es bajar de peso antes de la siguiente carrera.",
        "Conviene generar un déficit calórico moderado.",
        "El plan busca quemar grasa en las próximas semanas.",
        "El porcentaje de grasa 18 preocupa al cuerpo técnico.",
    ],
)
@pytest.mark.parametrize("audience", ["family", "coach"])
def test_r14_blocks_diet_or_weight_loss_language_in_both_audiences(audience, text):
    insight = _insight(audience=audience, summary_line=text)
    violation = check_r14_diet_or_weight_loss_language(insight)
    assert violation is not None
    assert violation.rule_id == "R14"
    assert violation.must_block is True
    assert violation.category == "safety"


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_r14_passes_healthy_alimentation_language(audience):
    insight = _insight(
        audience=audience, summary_line="Sigue acompañando una alimentación variada y equilibrada."
    )
    assert check_r14_diet_or_weight_loss_language(insight) is None
