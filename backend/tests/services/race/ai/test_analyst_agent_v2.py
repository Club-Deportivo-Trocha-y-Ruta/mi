"""Tests v2 — ``analyst_agent`` con cap 4 válidas y veto duro.

Contratos asumidos (Task #9):

- Cap 4: si ``state["valida_nums"]`` trae >4 enteros, el nodo lanza
  ``HTTPException(status_code=422)`` con detail describing the cap.

- Concurrencia: con 4 válidas el nodo invoca el agente analyst 4 veces
  en paralelo (asyncio.gather). Conteo verificado vía counter en el
  FakeLLM.

- Veto duro: si el output del LLM contiene una de las 5 frases vetadas
  ("debe ganar", "tiene que llegar al podio", "necesita más horas",
  "más intensidad", "trabajo de potencia para superar a"), el agente
  rechaza el output y reintenta 1 vez. Tras 2 intentos fallidos se
  propaga un error.

Si la implementación todavía no existe, xfail.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.race.ai.nodes.analyst_agent import analyst_agent
from app.services.race.schemas import AnalysisOutput
from tests.services.race.ai.conftest import (
    FakeAnalystAgent,
    make_analysis_output,
    make_zero_metrics,
)


class _CountingAnalystAgent:
    """Agente que cuenta invocaciones — verifica fan-out paralelo."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def invoke(self, input_):
        self.calls.append(input_)
        return make_analysis_output(
            markdown=f"## Qué pasó\nDraft para válida (call #{len(self.calls)})."
        ), make_zero_metrics("race_analyst_v2")


@pytest.mark.xfail(
    reason="v2: cap 4 válidas pendiente de implementación en analyst_agent",
    strict=False,
)
async def test_analyst_agent_v2_caps_at_4_validas_raises_422():
    """5 válidas → 422."""
    from fastapi import HTTPException

    agent = _CountingAnalystAgent()
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
        "valida_nums": [1, 2, 3, 4, 5],
        "_analyst_agent": agent,
    }

    with pytest.raises(HTTPException) as exc_info:
        await analyst_agent(state)
    assert exc_info.value.status_code == 422


@pytest.mark.xfail(
    reason="v2: fan-out paralelo per-válida pendiente en analyst_agent",
    strict=False,
)
async def test_analyst_agent_v2_fans_out_4_invocations_with_4_validas():
    """4 válidas → 4 llamadas al FakeLLM (idealmente vía asyncio.gather)."""
    agent = _CountingAnalystAgent()
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
        "valida_nums": [1, 2, 3, 4],
        "_analyst_agent": agent,
    }

    update = await analyst_agent(state)

    assert len(agent.calls) == 4, (
        f"Esperado 4 invocaciones (1 por válida), obtenido {len(agent.calls)}"
    )
    # Debería emitir per_valida_drafts en el state update.
    assert "per_valida_drafts" in update
    assert len(update["per_valida_drafts"]) == 4


@pytest.mark.xfail(
    reason="v2: veto duro pendiente de implementación con retry",
    strict=False,
)
async def test_analyst_agent_v2_veto_hard_phrase_triggers_retry():
    """Si el LLM responde con frase vetada, el agente rechaza y reintenta 1 vez."""

    class _VetoAgent:
        def __init__(self) -> None:
            self.calls = 0

        async def invoke(self, input_):
            self.calls += 1
            if self.calls == 1:
                # Primera invocación devuelve frase vetada.
                return make_analysis_output(
                    markdown=(
                        "## Qué pasó\nEl atleta debe ganar la próxima válida "
                        "para asegurar el podio."
                    )
                ), make_zero_metrics("race_analyst_v2")
            # Segunda invocación: válida.
            return make_analysis_output(
                markdown="## Qué pasó\nProgreso constante en frenada."
            ), make_zero_metrics("race_analyst_v2")

    agent = _VetoAgent()
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
        "valida_nums": [1],
        "_analyst_agent": agent,
    }

    update = await analyst_agent(state)
    # Reintentó una vez tras el veto → 2 calls.
    assert agent.calls == 2
    # El draft final NO debe contener la frase vetada.
    if update.get("per_valida_drafts"):
        for draft in update["per_valida_drafts"].values():
            assert "debe ganar" not in draft.raw_markdown.lower()


async def test_analyst_agent_v1_still_works_single_call():
    """Regresión v1: state sin ``valida_nums`` o con uno solo sigue funcionando."""
    fake = FakeAnalystAgent()
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
        "_analyst_agent": fake,
    }
    update = await analyst_agent(state)
    assert "draft_analysis" in update
    assert update["draft_analysis"].pseudonym == "AzulZorro"
