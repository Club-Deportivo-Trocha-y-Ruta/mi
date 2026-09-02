"""Tests del :class:`RaceChatAgent` (Fase 3 race-results v2).

Cubren:
- Llamada simple sin tools — respuesta directa, sesión persiste.
- Tool calling: el LLM pide un tool, se ejecuta, segunda llamada produce
  respuesta final con citas extraídas.
- Sesión multi-turn — el segundo turn ve la historia del primero.
- TTL: si la sesión expiró, se inicializa fresca con system prompt.
- max iterations: si el LLM nunca para de pedir tools, no loop infinito.
- No nombres reales: el system prompt sólo recibe athlete_id.
"""
from __future__ import annotations

import pytest
from langchain_core.tools import tool

from app.services.race.agents.chat import (
    MAX_TOOL_ITERATIONS,
    RaceChatAgent,
    _SessionStore,
)
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage


@tool("stub_marco_teorico")
def _stub_marco_teorico(query: str, top_k: int = 3) -> str:
    """Tool stub que devuelve cita formateada con [1]."""
    return f"[1] Capítulo > Sección   (chunk_id=stub_id_1, score=0.90)\nContenido respondiendo: {query}\n---"


@tool("stub_insights")
async def _stub_insights(athlete_id: int, n: int = 5) -> str:
    """Tool stub async."""
    return f"- Insight previo del atleta {athlete_id}: cadencia OK."


@tool("stub_results")
async def _stub_results(athlete_id: int, season: int) -> str:
    """Tool stub async."""
    return f"- event_id=22, pos=5 (atleta {athlete_id}, season {season})"


@pytest.fixture
def chat_tools():
    return [_stub_marco_teorico, _stub_insights, _stub_results]


@pytest.fixture
def isolated_store():
    """Store fresco por test — evita fugas entre tests."""
    return _SessionStore(ttl_seconds=3600)


async def test_chat_simple_response_no_tools(chat_tools, isolated_store):
    """LLM responde sin pedir tools → respuesta directa."""
    llm = FakeChatLLM([
        StubAIMessage(content="Hola coach, dime cómo puedo ayudarte.")
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    resp = await agent.chat(session_id="s1", query="¿estás ahí?")

    assert resp.answer.startswith("Hola coach")
    assert resp.tools_called == []
    assert resp.citations_used == []


async def test_chat_calls_tool_and_synthesizes_response(chat_tools, isolated_store):
    """Primer turn: LLM pide stub_marco_teorico, segundo turn: respuesta con [1]."""
    llm = FakeChatLLM([
        # Turn 1: pide tool.
        StubAIMessage(
            content="",
            tool_calls=[{"name": "stub_marco_teorico", "args": {"query": "PHV"}, "id": "c1"}],
        ),
        # Turn 2: responde citando [1].
        StubAIMessage(content="Según el marco teórico [1], la ventana PHV importa."),
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    resp = await agent.chat(session_id="s2", query="¿qué es PHV?")

    assert resp.tools_called == ["stub_marco_teorico"]
    assert "[1]" in resp.answer
    assert "1" in resp.citations_used


async def test_chat_session_persists_across_turns(chat_tools, isolated_store):
    """Segunda llamada ve los mensajes del primero (no se reinicializa)."""
    llm = FakeChatLLM([
        StubAIMessage(content="Primera respuesta."),
        StubAIMessage(content="Segunda respuesta."),
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    await agent.chat(session_id="s3", query="primera pregunta")
    await agent.chat(session_id="s3", query="segunda pregunta")

    # Segunda invocación recibe historial completo: system + human1 + ai1 + human2.
    second_call_msgs = llm.calls[1]
    assert len(second_call_msgs) >= 4
    # Buscar el contenido textual de la primera pregunta.
    contents = [getattr(m, "content", "") for m in second_call_msgs]
    assert any("primera pregunta" in str(c) for c in contents)


async def test_chat_session_reset_clears_history(chat_tools, isolated_store):
    llm = FakeChatLLM([
        StubAIMessage(content="Primera."),
        StubAIMessage(content="Tercera, nuevo contexto."),
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    await agent.chat(session_id="sR", query="hola")
    await agent.reset("sR")
    await agent.chat(session_id="sR", query="re-hola")

    # Segunda invocación tras reset: system + human (sin historial previo).
    second_msgs = llm.calls[1]
    assert len(second_msgs) == 2  # SystemMessage + HumanMessage


async def test_chat_passes_athlete_id_to_system_prompt(chat_tools, isolated_store):
    llm = FakeChatLLM([StubAIMessage(content="ok")])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    await agent.chat(session_id="sA", query="¿cómo va?", athlete_id=77)

    system_msg = llm.calls[0][0]
    assert "77" in str(system_msg.content)


async def test_chat_system_prompt_does_not_leak_real_names(chat_tools, isolated_store):
    """El system prompt nunca debe mencionar nombres reales — solo athlete_id."""
    llm = FakeChatLLM([StubAIMessage(content="ok")])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    await agent.chat(session_id="sZ", query="¿cómo va?", athlete_id=12)

    system_content = str(llm.calls[0][0].content)
    # No deben aparecer marcadores típicos de nombres (placeholder Jinja, etc.).
    assert "{{" not in system_content
    assert "}}" not in system_content


async def test_chat_max_tool_iterations_caps_loop(chat_tools, isolated_store):
    """Si el LLM no para de pedir tools, cortamos en MAX_TOOL_ITERATIONS."""
    # Generamos MAX_TOOL_ITERATIONS+1 respuestas con tool_calls.
    responses = [
        StubAIMessage(
            content=f"loop {i}",
            tool_calls=[{"name": "stub_marco_teorico", "args": {"query": "x"}, "id": f"c{i}"}],
        )
        for i in range(MAX_TOOL_ITERATIONS + 1)
    ]
    llm = FakeChatLLM(responses)
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    resp = await agent.chat(session_id="loop", query="dispárate")

    # No crashea. Se llamaron tools varias veces.
    assert len(resp.tools_called) >= MAX_TOOL_ITERATIONS
    assert resp.answer  # algo se devolvió (último AI message del historial).


async def test_chat_unknown_tool_returns_fallback_string(chat_tools, isolated_store):
    """Si el LLM pide una tool que no existe, se inserta mensaje de error."""
    llm = FakeChatLLM([
        StubAIMessage(
            content="",
            tool_calls=[{"name": "tool_inexistente", "args": {}, "id": "x1"}],
        ),
        StubAIMessage(content="Lo siento, esa herramienta no existe."),
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=isolated_store)

    resp = await agent.chat(session_id="sU", query="usa tool fantasma")
    assert "Lo siento" in resp.answer
    # tools_called no incluye la inexistente.
    assert "tool_inexistente" not in resp.tools_called


async def test_chat_session_ttl_expiry_initializes_fresh(chat_tools):
    """Sesión expirada → fresh system prompt en próximo turn."""
    store = _SessionStore(ttl_seconds=0)  # expira inmediatamente.
    llm = FakeChatLLM([
        StubAIMessage(content="t1"),
        StubAIMessage(content="t2"),
    ])
    agent = RaceChatAgent(llm=llm, tools=chat_tools, session_store=store)

    await agent.chat(session_id="ttl", query="primera")
    # Segunda llamada: la sesión ya expiró → solo system + human.
    await agent.chat(session_id="ttl", query="segunda")

    second_msgs = llm.calls[1]
    # Sin historial previo: system + human nuevo.
    assert len(second_msgs) == 2


async def test_chat_resolves_llm_via_build_chat_llm_with_chat_role(
    chat_tools, isolated_store, monkeypatch
):
    """Sin ``llm`` explícito, ``chat()`` resuelve el modelo con
    ``build_chat_llm(role="chat")`` — feature 037 (T405): antes llamaba
    ``build_chat_llm()`` sin rol, así que ``RACE_AI_CHAT_MODEL`` (si algún
    día se agrega) o el resto de resolución por-rol nunca se ejercitaba
    para el chat.
    """
    import app.services.race.agents.chat as chat_mod

    captured_kwargs: dict = {}
    fake_llm = FakeChatLLM([StubAIMessage(content="Hola coach.")])

    def _fake_build_chat_llm(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_llm

    monkeypatch.setattr(chat_mod, "build_chat_llm", _fake_build_chat_llm)

    agent = RaceChatAgent(llm=None, tools=chat_tools, session_store=isolated_store)
    resp = await agent.chat(session_id="sRole", query="hola")

    assert resp.answer == "Hola coach."
    assert captured_kwargs.get("role") == "chat"
