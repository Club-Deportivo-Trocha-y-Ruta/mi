"""Tests del nodo hitl_gate_review.

Nota: ``interrupt()`` solo se puede invocar dentro del runtime de
LangGraph (necesita ``RUNTIME``). Aquí testeamos el camino de
auto-approve (que NO llama interrupt) y la lógica de
``_should_interrupt`` directamente.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import hitl_gate_review as mod
from tests.services.race.ai.conftest import make_critic_feedback


@pytest.mark.asyncio
async def test_auto_approve_when_no_block_no_explain(monkeypatch):
    monkeypatch.delenv("RACE_HITL_ALWAYS", raising=False)
    state = {"critic_feedback": make_critic_feedback(must_block=False), "explain_mode": False}
    update = await mod.hitl_gate_review(state)
    assert update["hitl_decision"]["decision"] == "auto-approve"


def test_should_interrupt_when_must_block():
    state = {"critic_feedback": make_critic_feedback(must_block=True), "explain_mode": False}
    assert mod._should_interrupt(state) is True


def test_should_interrupt_when_explain_mode():
    state = {"critic_feedback": make_critic_feedback(must_block=False), "explain_mode": True}
    assert mod._should_interrupt(state) is True


def test_should_interrupt_when_env_always(monkeypatch):
    monkeypatch.setenv("RACE_HITL_ALWAYS", "true")
    state = {"critic_feedback": make_critic_feedback(must_block=False), "explain_mode": False}
    assert mod._should_interrupt(state) is True


def test_should_not_interrupt_default(monkeypatch):
    monkeypatch.delenv("RACE_HITL_ALWAYS", raising=False)
    state = {"critic_feedback": make_critic_feedback(must_block=False), "explain_mode": False}
    assert mod._should_interrupt(state) is False
