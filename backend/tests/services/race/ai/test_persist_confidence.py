"""US4 (feature 011): persisted confidence varies with the run (not constant medium).

Regression: persist_insight stored the hardcoded ``medium`` for every row.
Now the critic node computes per-válida confidence and persist stores it.
"""
from __future__ import annotations

import pytest

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.ai.nodes import critic_agent as critic_mod
from app.services.race.ai.nodes import persist_insight as persist_mod
from tests.helpers.ai_stubs import StubCriticAgentV2, contradiction_verdict, make_v2_output


async def _run(state):
    update = await critic_mod.critic_agent(state)
    state.update(update)
    await persist_mod.persist_insight(state)


def _base_state(fake_session, critic_stub, *, conditions, maturation, season_n):
    return {
        "_critic_agent": critic_stub,
        "athlete_id": 3,
        "season": 2026,
        "coach_id": 10,
        "competitor_id": 22,
        "ltad_group": "juvenil",
        "maturation_status": maturation,
        "season_validas_count": season_n,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {4: conditions},
        "full_season_results": [
            {"valida_num": 4, "position": 2, "race_time_ms": 2_050_000,
             "gap_to_winner_ms": 30_000}
        ],
        "podium_context": {},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
    }


@pytest.mark.asyncio
async def test_confidence_varies_with_inputs(configure_db_factory, fake_session):
    # Clean run, full data → high.
    s_clean = fake_session
    configure_db_factory(s_clean)
    clean_state = _base_state(
        s_clean,
        StubCriticAgentV2(),
        conditions={"climate": "Nublado", "temperature_c": 25.0,
                    "surface_condition": "humeda", "altitude_msnm": 1000,
                    "weather_notes": None},
        maturation="Circa-PHV",
        season_n=3,
    )
    await _run(clean_state)
    clean_row = clean_state_added = [r for r in s_clean.added_objects][0]
    assert clean_row.confidence == InsightConfidence.high


@pytest.mark.asyncio
async def test_confidence_low_when_flagged(configure_db_factory):
    from tests.services.race.ai.conftest import FakeSession

    s = FakeSession()
    configure_db_factory(s)
    flagged_state = _base_state(
        s,
        StubCriticAgentV2(verdicts=[contradiction_verdict()]),  # high severity
        conditions={"climate": None, "temperature_c": None,
                    "surface_condition": None, "altitude_msnm": None,
                    "weather_notes": None},
        maturation=None,
        season_n=1,
    )
    await _run(flagged_state)
    row = s.added_objects[0]
    assert row.confidence == InsightConfidence.low
