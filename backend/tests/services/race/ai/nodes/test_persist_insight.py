"""Tests del nodo persist_insight."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.persist_insight import persist_insight
from tests.services.race.ai.conftest import make_analysis_output


@pytest.mark.asyncio
async def test_persist_insight_inserts_row(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "draft_analysis": make_analysis_output(),
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)
    inserts = [s for s, _ in fake_session.executed_statements if "athlete_ai_insights" in s]
    assert len(inserts) == 1


@pytest.mark.asyncio
async def test_persist_insight_skip_when_no_draft(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    update = await persist_insight({"draft_analysis": None})
    assert update == {} or "errors" not in update
    assert all("athlete_ai_insights" not in s for s, _ in fake_session.executed_statements)


@pytest.mark.asyncio
async def test_persist_insight_rejected_decision_marks_archived(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "draft_analysis": make_analysis_output(),
        "hitl_decision": {"decision": "reject"},
        "aggregate_metrics": {},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)
    # Verificamos que el INSERT incluyó approved=0 y archived_at no nulo.
    inserts = [
        (s, p) for s, p in fake_session.executed_statements if "athlete_ai_insights" in s
    ]
    assert len(inserts) == 1
    _, params = inserts[0]
    assert params["coach_approved"] == 0
    assert params["archived_at"] is not None
