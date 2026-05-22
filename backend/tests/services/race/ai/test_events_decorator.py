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

        raise GraphInterrupt((Interrupt(value={"step": "review"}),))

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
    # El evento hitl_request lleva el nombre del nodo y payload vacío.
    last = events[-1]
    assert last["node"] == "hitl_gate_review"
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
