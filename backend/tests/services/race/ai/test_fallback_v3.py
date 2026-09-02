"""Tests de ``deterministic_fallback_v3`` (feature 037, T201).

El fallback v3 es el failure path del analista estructurado: debe cumplir el
esquema completo sin inventar un solo dato, y debe ser distinguible por
``is_fallback_output`` (que es lo que ``persist_insight`` propaga a la
columna ``is_fallback``).
"""
from __future__ import annotations

import pytest

from app.services.race.ai.fallback import (
    deterministic_fallback,
    deterministic_fallback_n1,
    deterministic_fallback_v3,
    is_fallback_output,
)
from app.services.race.insight_v3 import InsightV3, extract_numeric_tokens


def test_fallback_v3_is_a_valid_insight():
    fallback = deterministic_fallback_v3()
    assert isinstance(fallback, InsightV3)
    InsightV3.model_validate(fallback.model_dump())


def test_fallback_v3_headline_and_marker():
    fallback = deterministic_fallback_v3()
    assert fallback.headline == "Análisis no disponible"
    assert is_fallback_output(fallback) is True


def test_fallback_v3_declares_the_gap_and_no_field_reading():
    fallback = deterministic_fallback_v3()
    assert fallback.field_reading is None
    assert fallback.data_gaps


def test_fallback_v3_invents_no_numbers():
    """Sin cifras no hay violaciones de grounding falsas en el critic (T202)."""
    fallback = deterministic_fallback_v3()
    for observation in fallback.observations:
        for evidence in observation.evidence:
            assert extract_numeric_tokens(evidence) == set()
    assert extract_numeric_tokens(fallback.headline) == set()


def test_fallback_v3_actions_are_conservative():
    """Ante la falta de análisis, la recomendación segura es no cambiar la carga."""
    actions = deterministic_fallback_v3().actions
    assert len(actions) == 2
    assert all(a.priority.value == "low" for a in actions)
    assert "sin cambios" in actions[0].text


def test_fallback_v3_question_is_answerable_by_the_coach():
    assert deterministic_fallback_v3().coach_question.endswith("?")


@pytest.mark.parametrize(
    ("kind", "expected"), [("valida", "esta carrera"), ("season", "esta temporada")]
)
def test_fallback_v3_wording_follows_the_analysis_kind(kind, expected):
    fallback = deterministic_fallback_v3(analysis_kind=kind)
    assert expected in fallback.observations[0].claim


def test_is_fallback_output_still_discriminates_the_legacy_paths():
    """El contrato v1/v2 no cambia: solo el failure path marca."""
    assert is_fallback_output(deterministic_fallback("AzulZorro")) is True
    assert is_fallback_output(deterministic_fallback_n1("AzulZorro")) is False
    assert is_fallback_output(None) is False
