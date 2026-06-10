"""US6 (feature 011): re-generation replaces safely; a failed run keeps the old.

FR-014: deprecation happens only inside an approved persist. A run that errors
before/at persist never deactivates the prior active insight.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import persist_insight as mod
from tests.helpers.ai_stubs import make_v2_output


@pytest.mark.asyncio
async def test_no_analysis_does_not_deprecate(configure_db_factory, fake_session, monkeypatch):
    """Run that produced no draft (error upstream) → no deprecation, no rows."""
    configure_db_factory(fake_session)
    calls: list = []

    async def _fake_deprecate(db, **kw):
        calls.append(kw)
        return None

    monkeypatch.setattr(mod, "deprecate_previous_active", _fake_deprecate)

    update = await mod.persist_insight(
        {"athlete_id": 3, "season": 2026, "draft_analysis": None}
    )
    assert "persisted_insight_ids" not in update
    assert calls == []  # prior active insight untouched


@pytest.mark.asyncio
async def test_approved_run_deprecates_previous(configure_db_factory, fake_session, monkeypatch):
    configure_db_factory(fake_session)
    calls: list = []

    async def _fake_deprecate(db, **kw):
        calls.append(kw)
        return None

    monkeypatch.setattr(mod, "deprecate_previous_active", _fake_deprecate)

    state = {
        "athlete_id": 3,
        "season": 2026,
        "coach_id": 10,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {4: {}},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        # auto-approve (no hitl_decision) → approved path.
    }
    await mod.persist_insight(state)
    assert len(calls) == 1
    assert calls[0]["valida_num"] == 4


@pytest.mark.asyncio
async def test_failed_persist_does_not_commit(configure_db_factory, fake_session, monkeypatch):
    """If the insert flush errors, the node returns errors and never commits —
    so the prior active row (deprecated only on commit) survives."""
    configure_db_factory(fake_session)

    async def _fake_deprecate(db, **kw):
        return 999  # a prior active id existed

    monkeypatch.setattr(mod, "deprecate_previous_active", _fake_deprecate)

    commits: list = []
    orig_commit = fake_session.commit

    async def _tracking_commit():
        commits.append(1)
        await orig_commit()

    async def _boom_flush():
        raise RuntimeError("db down mid-persist")

    fake_session.commit = _tracking_commit
    fake_session.flush = _boom_flush

    state = {
        "athlete_id": 3,
        "season": 2026,
        "coach_id": 10,
        "per_valida_drafts": {4: make_v2_output()},
        "event_conditions": {4: {}},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
    }
    update = await mod.persist_insight(state)
    assert update.get("errors")  # error recorded
    assert commits == []  # never committed → prior insight stays active
