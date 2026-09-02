"""Tests del juez v2 del eval v3 (``judge.build_judge_v2_prompt`` / ``llm_judge_score_v3``).

Sin red: :class:`FakeChatLLM` inyectado por ``llm_factory``. Verifican lo que
distingue al juez v2 del v1 (feature 037, T401):

- el prompt lleva **los bloques de datos que vio el analista** (sin ellos la
  dimensión de precisión sería una opinión) y el output real como JSON;
- las 6 dimensiones de la rúbrica están declaradas;
- el parseo defensivo y el neutral 0.5 se heredan intactos de v1.

Datos 100 % ficticios.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.race.eval.judge import (
    JUDGE_V2_PROMPT_PATH,
    build_judge_v2_prompt,
    llm_judge_score_v3,
)
from app.services.race.insight_v3 import InsightV3
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage

_CASE: dict[str, Any] = {
    "case_id": "t02",
    "description": "Caso sintético para el juez v2.",
    "input": {
        "valida_num": 2,
        "analysis_kind": "valida",
        "athlete_ref": "el deportista",
        "age": 12,
        "ltad_group": "bambino",
        "season": 2026,
        "validas_count": 2,
        "valida_label": "Válida 2 · Copa Valle",
        "race_row": {
            "valida_num": 2,
            "event_date": "2026-02-28",
            "category_code": "INF_B",
            "position": 4,
            "race_time_ms": 1800000,
            "gap_to_winner_ms": 60000,
            "gap_to_winner_pct": 3.45,
        },
        "field_metrics": {
            "valida_num": 2,
            "is_championship": False,
            "field_size": 10,
            "position": 4,
            "percentile": 66.7,
            "gap_to_p1_ms": 60000,
            "gap_pct": 3.45,
            "gap_to_p3_ms": 22000,
            "expected_position": 5,
            "delta_vs_expected": 1,
        },
        "training_window": {
            "window_days": 28,
            "date_from": "2026-01-31",
            "date_to": "2026-02-28",
            "sessions_in_window": 11,
            "attended": 9,
            "attendance_pct": 81.8,
            "rpe_mean": 4.2,
        },
        "catalog_context": {
            "technique_skills": [
                {"code": "C", "name": "Frenado modulado", "focus": "Dosificar"}
            ]
        },
    },
    "expected_themes": ["asistencia"],
    "forbidden_terms": ["suplementos"],
    "expected_headline_keywords": ["asistencia"],
    "must_reference_catalog": True,
    "max_words": 450,
    "ideal_output": {
        "schema_version": "v3",
        "headline": "Terminó por encima de lo esperado sosteniendo la asistencia en 81.8%.",
        "field_reading": None,
        "trend": "improving",
        "observations": [
            {
                "claim": "La continuidad explica el avance.",
                "evidence": ["asistencia 81.8%"],
                "domain": "training",
                "confidence": "high",
            },
            {
                "claim": "El pelotón es parejo.",
                "evidence": ["gap 3.45% al líder"],
                "domain": "field",
                "confidence": "medium",
            },
        ],
        "actions": [
            {
                "text": "Sostener la frecuencia actual de sesiones.",
                "category": "volume",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": None,
                "derived_from": 0,
            },
            {
                "text": "Trabajar frenado modulado dos veces por semana.",
                "category": "technique",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": {"kind": "technique_skill", "code": "C", "label": None},
                "derived_from": 1,
            },
        ],
        "watch_signals": [],
        "coach_question": "¿Cambió algo en la rutina de la semana previa?",
        "data_gaps": [],
        "principles_cited": [],
    },
}


def _draft() -> InsightV3:
    return InsightV3.model_validate(_CASE["ideal_output"])


def test_prompt_file_exists() -> None:
    assert JUDGE_V2_PROMPT_PATH.exists(), "judge_v2.md no encontrado"


def test_prompt_includes_data_blocks_and_both_outputs() -> None:
    """El juez ve los datos del caso, el ideal y el output real."""
    prompt = build_judge_v2_prompt(_CASE, _draft())

    # Bloques de datos, en el formato que vio el analista (tiempos hh:mm:ss).
    assert "0:30:00" in prompt
    assert "81.8%" in prompt
    assert "Percentil: 66.7" in prompt
    # Ambos outputs como JSON.
    assert prompt.count('"schema_version": "v3"') >= 2
    # Metadatos del caso.
    assert "t02" in prompt and "bambino" in prompt and "suplementos" in prompt


def test_prompt_declares_the_six_rubric_dimensions() -> None:
    """AC-7.1: la rúbrica v2 suma "insight causal" y "lectura del pelotón"."""
    prompt = build_judge_v2_prompt(_CASE, _draft())
    for dimension in (
        "Precisión",
        "Alineación LTAD",
        "Accionabilidad",
        "Insight causal",
        "Lectura del pelotón",
        "Tono y privacidad",
    ):
        assert dimension in prompt, f"falta la dimensión {dimension!r}"
    assert "/ 60" in prompt, "la fórmula del score debe promediar 6 dimensiones"


def test_prompt_survives_an_incomplete_case() -> None:
    """Un caso golden incompleto no debe romper el juez (el runner ya valida schema)."""
    prompt = build_judge_v2_prompt({"case_id": "x"}, None)
    assert "(sin datos)" in prompt
    assert "null" in prompt


async def test_llm_judge_score_v3_parses_the_score() -> None:
    llm = FakeChatLLM([StubAIMessage('{"score": 0.82, "reasoning": "sólido"}')])
    result = await llm_judge_score_v3(_draft(), _CASE, llm_factory=lambda: llm)
    assert result.score == pytest.approx(0.82)
    assert result.parse_ok is True


async def test_llm_judge_score_v3_falls_back_to_neutral_on_provider_error() -> None:
    """Una caída del juez no debe hundir ni inflar el gate."""

    class _BoomLLM:
        async def ainvoke(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("proveedor caído")

    result = await llm_judge_score_v3(_draft(), _CASE, llm_factory=_BoomLLM)
    assert result.score == pytest.approx(0.5)
    assert result.parse_ok is False
