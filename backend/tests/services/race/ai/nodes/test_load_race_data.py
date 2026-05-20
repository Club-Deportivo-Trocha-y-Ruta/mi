"""Tests del nodo load_race_data."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import load_race_data as mod


class _FakeResult:
    def __init__(self, *, id, event_id, category_id, competitor_id, athlete_id,
                 position=1, race_time_ms=100, points_awarded=20, status=None):
        self.id = id
        self.event_id = event_id
        self.category_id = category_id
        self.competitor_id = competitor_id
        self.athlete_id = athlete_id
        self.position = position
        self.race_time_ms = race_time_ms
        self.points_awarded = points_awarded
        self.status = status


@pytest.mark.asyncio
async def test_load_race_data_serializes_and_picks_focus_event(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    rs = [
        _FakeResult(id=1, event_id=11, category_id=7, competitor_id=22, athlete_id=1, position=2),
        _FakeResult(id=2, event_id=12, category_id=7, competitor_id=22, athlete_id=1, position=1),
    ]
    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return rs

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)

    state = {"athlete_id": 1, "season": 2026}
    update = await mod.load_race_data(state)
    assert update["competitor_id"] == 22
    assert update["category_id"] == 7
    assert update["podium_context"]["event_id"] == 12  # último evento
    assert len(update["raw_data"]) == 2


@pytest.mark.asyncio
async def test_load_race_data_handles_empty(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return []

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    update = await mod.load_race_data({"athlete_id": 1, "season": 2026})
    assert update["raw_data"] == []
    assert update["competitor_id"] is None
    assert update["category_id"] is None
