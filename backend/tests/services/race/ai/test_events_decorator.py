"""Tests del decorador :func:`with_events` — manejo de eventos por nodo.

Casos clave:
- ``GraphInterrupt`` (HITL via ``interrupt()``) NO debe emitir ``node_error``.
  En su lugar emite ``hitl_request`` y re-raise para que LangGraph suspenda.
- Excepciones reales (``ValueError``, etc.) siguen emitiendo ``node_error``.
- Camino feliz emite ``node_start`` + ``node_end``.
"""
from __future__ import annotations

import pytest
from langgraph.errors import GraphInterrupt

from app.services.race.ai.events import with_events


@pytest.mark.asyncio
async def test_happy_path_emits_start_and_end():
    @with_events("node_x")
    async def node(state: dict) -> dict:
        return {"foo": "bar"}

    state: dict = {}
    update = await node(state)

    events = state["events"]
    assert [e["type"] for e in events] == ["node_start", "node_end"]
    assert all(e["node"] == "node_x" for e in events)
    # El update propaga events para LangGraph checkpointing.
    assert "events" in update


@pytest.mark.asyncio
async def test_graph_interrupt_emits_hitl_request_not_node_error():
    """Regresión bug HITL UX: interrupt() lanza GraphInterrupt y el decorador
    no debe tratarlo como error."""

    @with_events("hitl_gate_review")
    async def node(state: dict) -> dict:
        # GraphInterrupt requiere una lista de Interrupt en su constructor.
        # Simulamos lo que LangGraph hace al llamar interrupt().
        from langgraph.types import Interrupt

        raise GraphInterrupt(
            (
                Interrupt(
                    value={
                        "step": "review",
                        "draft_markdown": "# Análisis\nContenido del draft",
                        "pseudonym": "Atleta A",
                    }
                ),
            )
        )

    state: dict = {}
    with pytest.raises(GraphInterrupt):
        await node(state)

    events = state["events"]
    types = [e["type"] for e in events]
    assert types == ["node_start", "hitl_request"], (
        f"esperado [node_start, hitl_request], obtenido {types}"
    )
    # No debe haber node_error ni errores acumulados.
    assert "node_error" not in types
    assert state.get("errors", []) == []
    # El evento hitl_request lleva el nombre del nodo + payload del interrupt
    # (necesario para que la UI renderice el draft_markdown).
    last = events[-1]
    assert last["node"] == "hitl_gate_review"
    assert last["payload"]["step"] == "review"
    assert last["payload"]["draft_markdown"].startswith("# Análisis")
    assert last["payload"]["pseudonym"] == "Atleta A"


@pytest.mark.asyncio
async def test_graph_interrupt_with_empty_payload_is_resilient():
    """Si GraphInterrupt llega sin payload o con estructura inesperada,
    emitimos hitl_request con payload vacío (no crashea)."""

    @with_events("hitl_gate_review")
    async def node(state: dict) -> dict:
        raise GraphInterrupt(())  # tupla vacía

    state: dict = {}
    with pytest.raises(GraphInterrupt):
        await node(state)

    last = state["events"][-1]
    assert last["type"] == "hitl_request"
    assert last["payload"] == {}


@pytest.mark.asyncio
async def test_real_exception_still_emits_node_error():
    """Regresión guard: errores reales siguen emitiendo node_error."""

    @with_events("flaky_node")
    async def node(state: dict) -> dict:
        raise ValueError("bug real")

    state: dict = {}
    with pytest.raises(ValueError):
        await node(state)

    events = state["events"]
    types = [e["type"] for e in events]
    assert types == ["node_start", "node_error"]
    # Errores reales sí se acumulan en state["errors"].
    errors = state["errors"]
    assert len(errors) == 1
    assert errors[0]["error"] == "ValueError"
    assert errors[0]["node"] == "flaky_node"
    # Y el payload del evento lleva exc + msg truncado.
    err_ev = events[-1]
    assert err_ev["payload"]["exc"] == "ValueError"
    assert "bug real" in err_ev["payload"]["msg"]


# ---------------------------------------------------------------------------
# EVENT_SAFE_MESSAGE_ATTR — sustitución del mensaje publicado (feature 044)
#
# El mensaje del evento ``node_error`` se persiste en ``agent_run_events`` y
# se sirve por ``GET /race-analysis/runs/{run_id}/status``. Una excepción
# cuyo ``str()`` lleve datos que no deban publicarse puede declarar un
# sustituto; ``events.py`` no importa ninguna excepción concreta, así que la
# convención sirve para cualquier nodo, presente o futuro.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_with_event_safe_message_publishes_the_substitute():
    """El ``str()`` con el dato sensible no llega al evento; el sustituto sí."""

    class _Sensitive(RuntimeError):
        event_safe_message = "acceso denegado"

    @with_events("guarded_node")
    async def node(state: dict) -> dict:
        raise _Sensitive("dato que no debe publicarse id=4242")

    state: dict = {}
    with pytest.raises(_Sensitive):
        await node(state)

    err_ev = state["events"][-1]
    assert err_ev["type"] == "node_error"
    assert err_ev["payload"]["exc"] == "_Sensitive"
    assert err_ev["payload"]["msg"] == "acceso denegado"
    assert "4242" not in err_ev["payload"]["msg"]
    # state["errors"] es la otra copia persistida — misma sustitución.
    assert state["errors"][0]["message"] == "acceso denegado"


@pytest.mark.asyncio
async def test_event_safe_message_is_ignored_when_empty_or_not_a_string():
    """Un atributo vacío o de tipo raro NO debe silenciar el mensaje real:
    se cae al ``str(exc)`` de siempre en vez de publicar un evento mudo."""

    class _EmptySafe(RuntimeError):
        event_safe_message = "   "

    class _WrongType(RuntimeError):
        event_safe_message = 42

    for exc_cls in (_EmptySafe, _WrongType):

        @with_events("node_y")
        async def node(state: dict, _cls=exc_cls) -> dict:
            raise _cls("mensaje real")

        state: dict = {}
        with pytest.raises(exc_cls):
            await node(state)
        assert state["events"][-1]["payload"]["msg"] == "mensaje real"


@pytest.mark.asyncio
async def test_event_safe_message_is_truncated_to_200_chars():
    """El sustituto pasa por el mismo truncado que el mensaje normal."""

    class _LongSafe(RuntimeError):
        event_safe_message = "x" * 500

    @with_events("node_z")
    async def node(state: dict) -> dict:
        raise _LongSafe("corto")

    state: dict = {}
    with pytest.raises(_LongSafe):
        await node(state)

    assert len(state["events"][-1]["payload"]["msg"]) == 200
