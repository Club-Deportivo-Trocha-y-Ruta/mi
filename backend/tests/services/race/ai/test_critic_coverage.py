"""US3 (feature 011): the critic reviews ALL drafts of a batch, not just one.

Regression: the critic node only read singular ``draft_analysis`` → in a
group run of N válidas, N-1 drafts went unreviewed.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import critic_agent as mod
from tests.helpers.ai_stubs import StubCriticAgentV2, contradiction_verdict, make_v2_output


@pytest.mark.asyncio
async def test_critic_reviews_all_drafts():
    stub = StubCriticAgentV2()
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {
            3: make_v2_output(),
            4: make_v2_output(),
            5: make_v2_output(),
        },
        "event_conditions": {3: {}, 4: {}, 5: {}},
        "full_season_results": [],
        "podium_context": {},
    }
    update = await mod.critic_agent(state)
    verdicts = update["per_valida_verdicts"]
    assert set(verdicts.keys()) == {3, 4, 5}
    assert stub.invoke_v2_calls == 3
    # Compat: singular critic_feedback kept (first válida).
    assert "critic_feedback" in update


@pytest.mark.asyncio
async def test_critic_flags_contradiction_with_ground_truth():
    stub = StubCriticAgentV2(verdicts=[contradiction_verdict()])
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {
            4: {
                "climate": "Nublado",
                "temperature_c": 25.0,
                "surface_condition": "humeda",
                "altitude_msnm": 1000,
                "weather_notes": None,
            }
        },
        "full_season_results": [
            {"valida_num": 4, "position": 2, "race_time_ms": 2_050_000,
             "gap_to_winner_ms": 30_000}
        ],
        "podium_context": {"podium": [{"position": 1, "race_time_ms": 2_020_000}]},
    }
    update = await mod.critic_agent(state)
    verdict = update["per_valida_verdicts"][4]
    assert verdict.approved is False
    # The ground truth threaded to the critic includes the recorded surface.
    gt = stub.captured_ground_truth[0]
    assert "Húmeda" in gt
    assert "Posición: 2" in gt


@pytest.mark.asyncio
async def test_critic_caps_at_four_drafts():
    stub = StubCriticAgentV2()
    state = {
        "_critic_agent": stub,
        "per_valida_drafts": {1: make_v2_output(), 2: make_v2_output(),
                              3: make_v2_output(), 4: make_v2_output(),
                              5: make_v2_output()},
        "event_conditions": {},
        "full_season_results": [],
        "podium_context": {},
    }
    await mod.critic_agent(state)
    assert stub.invoke_v2_calls == 4
