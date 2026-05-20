"""Tests del nodo analyst_agent (con FakeAnalystAgent)."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.analyst_agent import analyst_agent
from tests.services.race.ai.conftest import FakeAnalystAgent, make_analysis_output


@pytest.mark.asyncio
async def test_analyst_agent_node_invokes_and_accumulates_metrics():
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
    assert update["draft_analysis"].pseudonym == "AzulZorro"
    aggregate = update["aggregate_metrics"]
    assert aggregate["tokens_in"] == 10
    assert aggregate["tokens_out"] == 20
    assert aggregate["cost_usd"] > 0


@pytest.mark.asyncio
async def test_analyst_agent_propagates_error():
    fake = FakeAnalystAgent(raises=RuntimeError("LLM down"))
    state = {
        "athlete_id": 1,
        "season": 2026,
        "anonymized_data": {"pseudonym": "VerdePuma"},
        "metrics": {},
        "_analyst_agent": fake,
    }
    with pytest.raises(RuntimeError):
        await analyst_agent(state)
