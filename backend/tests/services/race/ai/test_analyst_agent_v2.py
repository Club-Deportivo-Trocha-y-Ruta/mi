"""Tests v2 — ``analyst_agent`` (cap 4 válidas) y reintento por veto duro.

Nació como boceto previo a la implementación (xfail con una API supuesta:
422 en el nodo, veto dentro de un agente falso). Se reescribió sobre la API
real; lo ya cubierto en otro archivo se eliminó de aquí:

- Fan-out de 4 válidas → 4 borradores:
  ``test_analyst_agent_v2_uses_full_season.py::test_analyst_agent_v2_set_size_4_with_full_season_history``.
- Cap v3: ``nodes/test_analyst_agent_v3.py::test_v3_rejects_more_than_four_validas``.

Contratos reales cubiertos aquí:

- Cap v2: con ``prompt_version=race_analyst_v2`` y >4 válidas el nodo lanza
  ``ValueError`` (no ``HTTPException``) y no llama al agente.
- Veto duro (spec §7): ``RaceAnalystAgent`` rechaza la respuesta que trae una
  frase vetada y reintenta UNA vez; si el reintento también la trae, entrega
  el fallback determinista (nunca el texto vetado).
"""

from __future__ import annotations

import logging

import pytest

import app.services.race.agents.analyst as analyst_mod
from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V2,
    RaceAnalystAgent,
)
from app.services.race.ai.fallback import is_fallback_output
from app.services.race.ai.nodes.analyst_agent import analyst_agent
from app.services.race.schemas import AnalysisInput, LTADGroup
from tests.services.race.ai.conftest import FakeAnalystAgent

_CLEAN_OUTPUT = (
    "## Qué pasó en esta válida\n"
    "La deportista completó la prueba con frenadas estables.\n\n"
    "## Recorrido hasta acá\n"
    "Con una sola válida disputada aún no es posible establecer una "
    "tendencia de progresión.\n\n"
    "## Hacia dónde va\n"
    "- Reforzar técnica de curvas (categoría=technique, prioridad=med) [1]\n"
)

_VETOED_OUTPUT = _CLEAN_OUTPUT.replace(
    "La deportista completó la prueba",
    "La deportista debe ganar la próxima válida; completó la prueba",
)


class _FakeLLMCallResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens_in = 10
        self.tokens_out = 20
        self.latency_ms = 5
        self.cost_usd = 0.0


def _script_llm(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> list[str]:
    """Parchea ``call_llm`` para devolver ``replies`` en orden; retorna el
    registro de prompts enviados (uno por intento)."""
    prompts: list[str] = []

    async def _fake_call_llm(llm, prompt):
        prompts.append(prompt)
        return _FakeLLMCallResult(replies[len(prompts) - 1])

    monkeypatch.setattr(analyst_mod, "call_llm", _fake_call_llm)
    monkeypatch.setattr(analyst_mod, "build_chat_llm", lambda: None)
    return prompts


def _make_input() -> AnalysisInput:
    return AnalysisInput(
        athlete_pseudonym="AzulZorro",
        age=12,
        ltad_group=LTADGroup.BAMBINO,
        progression_df_records=[
            {"valida_num": 1, "position": 4, "race_time_ms": 2_100_000},
        ],
        podium_context={},
        athlete_id=1,
        season=2026,
    )


def _base_state(**over) -> dict:
    state = {
        "athlete_id": 1,
        "season": 2026,
        "athlete_age": 12,
        "ltad_group": "bambino",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {"progression": []},
        "podium_context": {},
        "principles": [],
        "memory": [],
    }
    state.update(over)
    return state


# ---------------------------------------------------------------------------
# Cap v2
# ---------------------------------------------------------------------------


async def test_analyst_agent_v2_rejects_more_than_four_validas():
    class _NeverCalled:
        async def invoke_per_valida(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("el cap debe cortar antes de invocar al agente")

    state = _base_state(
        prompt_version=PROMPT_VERSION_ANALYST_V2,
        valida_nums=[1, 2, 3, 4, 5],
        _analyst_agent=_NeverCalled(),
    )
    with pytest.raises(ValueError, match="máximo 4"):
        await analyst_agent(state)


async def test_invoke_per_valida_enforces_the_cap_itself(monkeypatch):
    """El cap también vive en el agente: un llamador que salte el nodo no
    puede lanzar 5 llamadas al LLM."""
    prompts = _script_llm(monkeypatch, [_CLEAN_OUTPUT] * 5)
    pairs = [(vn, _make_input()) for vn in range(1, 6)]
    with pytest.raises(ValueError, match="máximo 4"):
        await RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2).invoke_per_valida(
            pairs, forbidden_names=[], is_first_in_season=True
        )
    assert prompts == []


# ---------------------------------------------------------------------------
# Veto duro → reintento → fallback
# ---------------------------------------------------------------------------


async def test_veto_phrase_triggers_exactly_one_retry(monkeypatch):
    prompts = _script_llm(monkeypatch, [_VETOED_OUTPUT, _CLEAN_OUTPUT])
    agent = RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2)

    results = await agent.invoke_per_valida(
        [(1, _make_input())], forbidden_names=[], is_first_in_season=True
    )

    assert len(prompts) == 2
    output, _metrics = results[1]
    assert not is_fallback_output(output)
    assert "debe ganar" not in output.raw_markdown.lower()
    assert "frenadas estables" in output.raw_markdown


async def test_veto_on_both_attempts_returns_deterministic_fallback(monkeypatch, caplog):
    prompts = _script_llm(monkeypatch, [_VETOED_OUTPUT, _VETOED_OUTPUT])
    agent = RaceAnalystAgent(prompt_version=PROMPT_VERSION_ANALYST_V2)

    with caplog.at_level(logging.WARNING, logger=analyst_mod.logger.name):
        results = await agent.invoke_per_valida(
            [(1, _make_input())], forbidden_names=[], is_first_in_season=True
        )

    assert len(prompts) == 2, "solo se permite un reintento tras el veto"
    output, metrics = results[1]
    assert is_fallback_output(output)
    assert "debe ganar" not in output.raw_markdown.lower()
    assert metrics.cost_usd == 0.0
    assert any("veto duro" in r.getMessage() for r in caplog.records)


async def test_clean_output_needs_a_single_call(monkeypatch):
    prompts = _script_llm(monkeypatch, [_CLEAN_OUTPUT])
    results = await RaceAnalystAgent(
        prompt_version=PROMPT_VERSION_ANALYST_V2
    ).invoke_per_valida([(1, _make_input())], forbidden_names=[], is_first_in_season=True)
    assert len(prompts) == 1
    assert not is_fallback_output(results[1][0])


# ---------------------------------------------------------------------------
# Regresión v1
# ---------------------------------------------------------------------------


async def test_analyst_agent_v1_still_works_single_call():
    """Regresión v1: state sin ``valida_nums`` o con uno solo sigue funcionando."""
    fake = FakeAnalystAgent()
    update = await analyst_agent(_base_state(_analyst_agent=fake))
    assert "draft_analysis" in update
    assert update["draft_analysis"].pseudonym == "AzulZorro"
