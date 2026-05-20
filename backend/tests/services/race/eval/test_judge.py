"""Tests del :mod:`app.services.race.eval.judge` — parser + LLM-as-judge.

Sin red. Usa :class:`FakeChatLLM` para simular respuestas Gemini y
verifica:

- parse_judge_output: JSON puro, JSON envuelto en fences, malformado.
- score fuera de rango → clamp.
- Llamada al LLM falla (excepción) → neutral 0.5.
- build_judge_prompt renderiza con todas las variables.
- llm_judge_score integración: factory inyectable, no toca red.
"""
from __future__ import annotations

import pytest

from app.services.race.eval.judge import (
    JudgeResult,
    build_judge_prompt,
    llm_judge_score,
    parse_judge_output,
)
from app.services.race.schemas import AnalysisOutput
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage


def _make_output(markdown: str = "## Evolución\nok " * 30, citations: list[str] | None = None) -> AnalysisOutput:
    return AnalysisOutput(
        pseudonym="Atleta-X",
        sections={},
        citations_used=citations or [],
        recommendations=[],
        risk_flags=[],
        raw_markdown=markdown,
        word_count=60,
    )


def _sample_case() -> dict:
    return {
        "case_id": "test_001",
        "description": "caso de prueba",
        "expected_themes": ["evolución", "técnica"],
        "forbidden_terms": ["suplementos"],
        "max_words": 600,
        "ideal_output_excerpt": "## Evolución\n\nAtleta mejora.\n",
        "must_cite": True,
    }


# ---------------------------------------------------------------------------
# parse_judge_output
# ---------------------------------------------------------------------------


def test_parse_pure_json() -> None:
    raw = '{"score": 0.85, "reasoning": "buena cobertura"}'
    res = parse_judge_output(raw)
    assert isinstance(res, JudgeResult)
    assert res.score == pytest.approx(0.85)
    assert res.reasoning == "buena cobertura"
    assert res.parse_ok is True


def test_parse_json_wrapped_in_markdown_fences() -> None:
    raw = """Aquí está mi evaluación:

```json
{"score": 0.72, "reasoning": "falta una sección"}
```

Saludos.
"""
    res = parse_judge_output(raw)
    assert res.score == pytest.approx(0.72)
    assert "falta" in res.reasoning
    assert res.parse_ok is True


def test_parse_json_wrapped_in_plain_fences() -> None:
    """Sin sufijo 'json', sólo fences ```."""
    raw = "```\n{\"score\": 0.60, \"reasoning\": \"ok\"}\n```"
    res = parse_judge_output(raw)
    assert res.score == pytest.approx(0.60)
    assert res.parse_ok is True


def test_parse_malformed_output_returns_neutral() -> None:
    """Sin JSON parseable → 0.5 neutral + parse_ok=False."""
    raw = "Esto es texto plano sin estructura JSON alguna."
    res = parse_judge_output(raw)
    assert res.score == pytest.approx(0.5)
    assert res.parse_ok is False


def test_parse_empty_output_returns_neutral() -> None:
    res = parse_judge_output("")
    assert res.score == pytest.approx(0.5)
    assert res.parse_ok is False


def test_parse_score_out_of_range_is_clamped() -> None:
    """Score >1 → clamp a 1.0; score <0 → clamp a 0.0."""
    res_high = parse_judge_output('{"score": 1.5, "reasoning": "alto"}')
    assert res_high.score == pytest.approx(1.0)
    assert res_high.parse_ok is True

    res_low = parse_judge_output('{"score": -0.3, "reasoning": "bajo"}')
    assert res_low.score == pytest.approx(0.0)
    assert res_low.parse_ok is True


def test_parse_score_non_numeric_returns_neutral() -> None:
    raw = '{"score": "alto", "reasoning": "no es número"}'
    res = parse_judge_output(raw)
    assert res.score == pytest.approx(0.5)
    assert res.parse_ok is False


def test_parse_json_with_extra_keys_ignored() -> None:
    """Claves extra en el JSON no rompen el parser."""
    raw = '{"score": 0.9, "reasoning": "ok", "extra_dim": 8, "other": [1,2]}'
    res = parse_judge_output(raw)
    assert res.score == pytest.approx(0.9)
    assert res.parse_ok is True


# ---------------------------------------------------------------------------
# build_judge_prompt
# ---------------------------------------------------------------------------


def test_build_judge_prompt_renders_all_variables() -> None:
    """El prompt renderizado contiene case_id, themes, forbidden, ideal, actual."""
    actual = "## Evolución\n\nMejora sostenida."
    prompt = build_judge_prompt(_sample_case(), actual)
    assert "test_001" in prompt
    assert "evolución" in prompt
    assert "técnica" in prompt
    assert "suplementos" in prompt
    assert "Atleta mejora" in prompt
    assert "Mejora sostenida" in prompt


def test_build_judge_prompt_handles_empty_actual_output() -> None:
    prompt = build_judge_prompt(_sample_case(), "")
    assert "output vacío" in prompt


# ---------------------------------------------------------------------------
# llm_judge_score (con factory mock)
# ---------------------------------------------------------------------------


async def test_llm_judge_score_with_mock_llm() -> None:
    """Factory inyectable evita tocar Gemini real en tests."""
    fake_llm = FakeChatLLM(
        [StubAIMessage(content='{"score": 0.82, "reasoning": "calidad alta"}')]
    )
    out = _make_output()
    case = _sample_case()

    result = await llm_judge_score(out, case, llm_factory=lambda: fake_llm)

    assert isinstance(result, JudgeResult)
    assert result.score == pytest.approx(0.82)
    assert result.parse_ok is True
    # Verifica que el prompt enviado al fake LLM contiene los datos del caso.
    assert len(fake_llm.calls) == 1
    sent_prompt = fake_llm.calls[0][0].content
    assert "test_001" in sent_prompt


async def test_llm_judge_score_llm_raises_returns_neutral() -> None:
    """Si el LLM lanza excepción → neutral 0.5 + parse_ok=False."""

    class _BrokenLLM:
        async def ainvoke(self, messages, **kw):  # noqa: ARG002
            raise RuntimeError("API timeout")

    out = _make_output()
    case = _sample_case()
    result = await llm_judge_score(out, case, llm_factory=lambda: _BrokenLLM())
    assert result.score == pytest.approx(0.5)
    assert result.parse_ok is False
    assert "error" in result.reasoning.lower()


async def test_llm_judge_score_parses_wrapped_json_from_llm() -> None:
    """LLM devuelve fenced JSON → se parsea correctamente."""
    fake_llm = FakeChatLLM(
        [StubAIMessage(content='```json\n{"score": 0.55, "reasoning": "regular"}\n```')]
    )
    out = _make_output()
    case = _sample_case()
    result = await llm_judge_score(out, case, llm_factory=lambda: fake_llm)
    assert result.score == pytest.approx(0.55)
    assert result.parse_ok is True
