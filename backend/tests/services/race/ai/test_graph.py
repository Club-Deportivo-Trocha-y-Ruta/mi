"""Tests end-to-end del grafo race-analyst.

Cubre:
- Happy path con LLM mockeado.
- Error path nodo 1 (athlete no existe) → END sin tocar agentes.
- Error path nodo 7 (analyst falla 3x) → fallback activado.
- HITL interrupt + resume (must_block del critic).
"""
from __future__ import annotations

import pytest

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.services.race.ai.graph import build_graph
from app.services.race.ai.nodes import (
    analyst_agent as analyst_node_mod,
    compute_metrics as metrics_node_mod,
    critic_agent as critic_node_mod,
    load_race_data as load_node_mod,
    rehydrate_names as rehydrate_node_mod,
    retrieve_principles as retrieve_node_mod,
    validate_input as validate_node_mod,
)
from tests.services.race.ai.conftest import (
    FakeAnalystAgent,
    FakeCriticAgent,
    make_analysis_output,
    make_critic_feedback,
)


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Patchea TODA la pipeline para evitar DB y LLM real."""

    async def _athlete_exists(db, aid):
        return True

    async def _fetch_results(db, aid, season, valida_nums=None):
        class R:
            id = 1
            event_id = 10
            category_id = 5
            competitor_id = 22
            athlete_id = aid
            position = 2
            race_time_ms = 1000
            points_awarded = 50
            status = None
        return [R()]

    async def _fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _athlete_progression(db, cid):
        import pandas as pd
        return pd.DataFrame([{"valida_num": 1, "position": 2}])

    async def _podium_gap(db, cat, season):
        import pandas as pd
        return pd.DataFrame([{"competitor_id": 22, "gap_to_p1_ms": 100}])

    def _rag(query, top_k):
        return []

    monkeypatch.setattr(validate_node_mod, "athlete_exists", _athlete_exists)
    monkeypatch.setattr(load_node_mod, "fetch_results_for_athlete", _fetch_results)
    monkeypatch.setattr(load_node_mod, "fetch_podium_context", _fetch_podium)
    monkeypatch.setattr(metrics_node_mod, "athlete_progression", _athlete_progression)
    monkeypatch.setattr(metrics_node_mod, "podium_gap", _podium_gap)
    monkeypatch.setattr(retrieve_node_mod, "rag_retrieve", _rag)

    # Patch agentes para retornar FakeAnalystAgent/FakeCriticAgent.
    monkeypatch.setattr(
        analyst_node_mod,
        "RaceAnalystAgent",
        lambda *args, **kw: FakeAnalystAgent(),
    )
    monkeypatch.setattr(
        critic_node_mod,
        "RaceCriticAgent",
        FakeCriticAgent,
    )


@pytest.mark.asyncio
async def test_graph_happy_path(
    memory_checkpointer, configure_db_factory, fake_session, patched_pipeline, monkeypatch
):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    monkeypatch.delenv("RACE_HITL_ALWAYS", raising=False)
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")

    configure_db_factory(fake_session)
    g = build_graph(checkpointer=memory_checkpointer)

    config = {"configurable": {"thread_id": "happy-1"}}
    state = await g.ainvoke(
        {
            "athlete_id": 1,
            "season": 2026,
            "coach_id": 99,
            "run_id": "happy-1",
            "explain_mode": False,
        },
        config=config,
    )
    assert state.get("rendered_markdown")
    assert state.get("final_analysis") is not None
    assert state.get("notified") is False  # SEND_EMAILS=false


@pytest.mark.asyncio
async def test_graph_validation_error_short_circuits(
    memory_checkpointer, configure_db_factory, fake_session, patched_pipeline, monkeypatch
):
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")
    monkeypatch.setattr(
        validate_node_mod, "athlete_exists", lambda db, aid: _async_false()
    )
    configure_db_factory(fake_session)
    g = build_graph(checkpointer=memory_checkpointer)

    config = {"configurable": {"thread_id": "err-1"}}
    state = await g.ainvoke(
        {"athlete_id": 999, "season": 2026, "coach_id": 1, "run_id": "err-1"},
        config=config,
    )
    assert state.get("errors")
    assert any(e["error"] == "AthleteNotFound" for e in state["errors"])
    # Pipeline NO ejecutó nodos downstream.
    assert state.get("draft_analysis") is None
    assert state.get("rendered_markdown") is None


async def _async_false():
    return False


@pytest.mark.asyncio
async def test_graph_analyst_failure_triggers_fallback(
    memory_checkpointer, configure_db_factory, fake_session, patched_pipeline, monkeypatch
):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "false")
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")
    monkeypatch.delenv("RACE_HITL_ALWAYS", raising=False)

    # Reemplaza el analyst para que SIEMPRE falle.
    monkeypatch.setattr(
        analyst_node_mod,
        "RaceAnalystAgent",
        lambda *a, **kw: FakeAnalystAgent(raises=TimeoutError("LLM down")),
    )

    configure_db_factory(fake_session)
    g = build_graph(checkpointer=memory_checkpointer)
    state = await g.ainvoke(
        {"athlete_id": 1, "season": 2026, "coach_id": 1, "run_id": "fb-1"},
        config={"configurable": {"thread_id": "fb-1"}},
    )

    # Fallback activado: draft existe pero es el determinista.
    assert state.get("draft_analysis") is not None
    assert "no disponible" in state["draft_analysis"].raw_markdown.lower()
    # Error reportado y recovery anotado.
    assert any(
        e.get("node") == "analyst_agent" and e.get("recovered_with") == "deterministic_fallback"
        for e in (state.get("errors") or [])
    )
    # Pero el pipeline llegó a render + notify.
    assert state.get("rendered_markdown")


@pytest.mark.asyncio
async def test_graph_hitl_interrupt_and_resume(
    memory_checkpointer, configure_db_factory, fake_session, patched_pipeline, monkeypatch
):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")

    # Crítico con must_block forzado → interrupt.
    class _BlockingCritic(FakeCriticAgent):
        def __init__(self, *args, **kwargs):
            super().__init__(make_critic_feedback(approved=False, must_block=True))

    monkeypatch.setattr(critic_node_mod, "RaceCriticAgent", _BlockingCritic)

    configure_db_factory(fake_session)
    g = build_graph(checkpointer=memory_checkpointer)

    config = {"configurable": {"thread_id": "hitl-1"}}
    first_result = await g.ainvoke(
        {"athlete_id": 1, "season": 2026, "coach_id": 1, "run_id": "hitl-1"},
        config=config,
    )
    # El grafo se pausó por interrupt — verificable mirando el estado del checkpoint.
    snapshot = await g.aget_state(config)
    assert snapshot.next  # quedan nodos pendientes (no terminó)
    assert "hitl_gate_review" in snapshot.next or any(
        "hitl" in n for n in snapshot.next
    )

    # Reanudar con Command(resume=...) — debe terminar el grafo.
    resumed = await g.ainvoke(
        Command(resume={"decision": "approve"}),
        config=config,
    )
    assert resumed.get("rendered_markdown")
    assert resumed.get("hitl_decision", {}).get("decision") == "approve"
