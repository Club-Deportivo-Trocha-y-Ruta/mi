"""US3 (feature 011): each persisted v2 row carries its own grounding + verdict.

Regression: snapshots were shared and never carried the critic verdict or the
grounding inputs used for that válida.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import persist_insight as mod
from app.services.race.schemas import CriticFeedback, CriticIssueSeverity
from tests.helpers.ai_stubs import make_v2_output


@pytest.mark.asyncio
async def test_persist_stores_per_valida_verdicts(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    state = {
        "athlete_id": 3,
        "season": 2026,
        "coach_id": 10,
        "competitor_id": 22,
        "ltad_group": "juvenil",
        "maturation_status": "Circa-PHV",
        "per_valida_drafts": {3: make_v2_output(), 4: make_v2_output()},
        "per_valida_verdicts": {
            3: CriticFeedback(approved=True, severity=CriticIssueSeverity.LOW),
            4: CriticFeedback(approved=False, severity=CriticIssueSeverity.HIGH),
        },
        "event_conditions": {
            3: {"climate": None, "temperature_c": None, "surface_condition": None,
                "altitude_msnm": None, "weather_notes": None},
            4: {"climate": "Nublado", "temperature_c": 25.0,
                "surface_condition": "humeda", "altitude_msnm": 1000,
                "weather_notes": None},
        },
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
    }

    await mod.persist_insight(state)

    rows = {r.valida_num: r for r in fake_session.added_objects}
    assert set(rows.keys()) == {3, 4}

    snap4 = rows[4].metrics_snapshot_json
    assert snap4["grounding"]["maturation_status_used"] == "Circa-PHV"
    assert snap4["grounding"]["ltad_group_used"] == "juvenil"
    assert snap4["grounding"]["event_conditions_used"]["surface_condition"] == "humeda"
    assert snap4["critic_verdict"]["approved"] is False

    snap3 = rows[3].metrics_snapshot_json
    assert snap3["critic_verdict"]["approved"] is True
    # All-None conditions still recorded (absence representable).
    assert snap3["grounding"]["event_conditions_used"]["climate"] is None
