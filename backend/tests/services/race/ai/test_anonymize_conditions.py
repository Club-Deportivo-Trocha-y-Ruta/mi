"""US1 privacy gate (feature 011): weather_notes scrubbed before the prompt.

Constitution privacy gate: a forbidden name seeded in the free-text
``weather_notes`` must never survive into the assembled prompt context.
"""
from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.race.agents.analyst import format_race_meta
from app.services.race.ai.db import set_db_factory
from app.services.race.ai.nodes import anonymize as mod


@pytest.mark.asyncio
async def test_weather_notes_scrubbed_before_prompt(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    forbidden = "Valentina Restrepo"
    state = {
        "athlete_id": 1,
        "competitor_id": 22,
        "run_id": "run-x",
        "forbidden_names": [forbidden],
        "raw_data": [],
        "event_conditions": {
            4: {
                "climate": "Nublado",
                "temperature_c": 25.0,
                "surface_condition": "humeda",
                "altitude_msnm": 1000,
                "weather_notes": f"{forbidden} reportó barro en el sector técnico",
            }
        },
    }

    update = await mod.anonymize(state)
    scrubbed = update["event_conditions"][4]["weather_notes"]
    assert forbidden not in scrubbed
    assert "barro en el sector técnico" in scrubbed

    # The forbidden name must also be absent from the assembled race_meta block.
    block = format_race_meta(update["event_conditions"][4])
    assert block is not None
    assert forbidden not in block


@settings(max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    name=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll")), min_size=3, max_size=12),
)
@pytest.mark.asyncio
async def test_forbidden_name_never_survives(name):
    # anonymize's mapping persist is best-effort (try/except); no DB needed here.
    set_db_factory(None)
    state = {
        "athlete_id": 1,
        "competitor_id": 22,
        "run_id": "run-y",
        "forbidden_names": [name],
        "raw_data": [],
        "event_conditions": {
            1: {
                "climate": None,
                "temperature_c": None,
                "surface_condition": None,
                "altitude_msnm": None,
                "weather_notes": f"nota con {name} adentro",
            }
        },
    }
    update = await mod.anonymize(state)
    assert name not in update["event_conditions"][1]["weather_notes"]
