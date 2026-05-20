"""Tests del nodo critic_agent."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.critic_agent import critic_agent
from tests.services.race.ai.conftest import FakeCriticAgent, make_analysis_output


@pytest.mark.asyncio
async def test_critic_noop_when_flag_disabled(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "false")
    state = {"draft_analysis": make_analysis_output()}
    update = await critic_agent(state)
    # No-op: solo eventos, sin critic_feedback agregado.
    assert "critic_feedback" not in update


@pytest.mark.asyncio
async def test_critic_invokes_when_enabled(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    fake = FakeCriticAgent()
    state = {"draft_analysis": make_analysis_output(), "_critic_agent": fake}
    update = await critic_agent(state)
    assert update["critic_feedback"].approved is True


@pytest.mark.asyncio
async def test_critic_skips_when_no_draft(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    update = await critic_agent({"draft_analysis": None})
    assert "critic_feedback" not in update
