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
    # persist_insight usa ORM db.add() — verificar objetos agregados.
    assert len(fake_session.added_objects) == 1


@pytest.mark.asyncio
async def test_persist_insight_skip_when_no_draft(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    update = await persist_insight({"draft_analysis": None})
    assert update == {} or "errors" not in update
    assert len(fake_session.added_objects) == 0


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
    # persist_insight usa ORM db.add() — verificar atributos del objeto ORM.
    assert len(fake_session.added_objects) == 1
    row = fake_session.added_objects[0]
    assert row.coach_approved is False
    assert row.archived_at is not None
