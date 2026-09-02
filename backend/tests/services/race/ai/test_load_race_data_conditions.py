"""US1 (feature 011): load_race_data emits recorded event conditions per válida.

Regression: on unfixed code the node never emitted ``event_conditions``; the
analyst then had no real conditions and fabricated them.
"""
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
async def test_load_race_data_emits_event_conditions(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)

    rs = [
        _FakeResult(id=1, event_id=13, category_id=7, competitor_id=22,
                    athlete_id=1, position=5, race_time_ms=2_200_000),
        _FakeResult(id=2, event_id=14, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_050_000),
    ]

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return rs

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return []

    async def _fake_resolve_max(db, season, valida_nums, event_id=None):
        return None

    # Válida 4 = recorded (Cali Húmeda/Nublado); válida 3 = all-None (unrecorded).
    async def _fake_fetch_conditions(db, season, valida_nums):
        out = {}
        for vn in valida_nums:
            if vn == 4:
                out[4] = {
                    "climate": "Nublado",
                    "temperature_c": 25.0,
                    "surface_condition": "humeda",
                    "altitude_msnm": 1000,
                    "weather_notes": None,
                }
            else:
                out[vn] = {
                    "climate": None,
                    "temperature_c": None,
                    "surface_condition": None,
                    "altitude_msnm": None,
                    "weather_notes": None,
                }
        return out

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(mod, "fetch_event_conditions", _fake_fetch_conditions)
    monkeypatch.setattr(mod, "_resolve_max_launched_date", _fake_resolve_max)

    state = {"athlete_id": 1, "season": 2026, "valida_nums": [3, 4]}
    update = await mod.load_race_data(state)

    conds = update["event_conditions"]
    assert set(conds.keys()) == {3, 4}
    # Recorded válida surfaces the real values.
    assert conds[4]["climate"] == "Nublado"
    assert conds[4]["surface_condition"] == "humeda"
    assert conds[4]["temperature_c"] == 25.0
    # Unrecorded válida yields an all-None entry (absence is representable).
    assert all(v is None for v in conds[3].values())


@pytest.mark.asyncio
async def test_event_conditions_present_when_no_results(
    monkeypatch, configure_db_factory, fake_session
):
    """Even with no results the node must emit the event_conditions key."""
    configure_db_factory(fake_session)

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return []

    async def _fake_fetch_conditions(db, season, valida_nums):
        return {}

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_event_conditions", _fake_fetch_conditions)

    update = await mod.load_race_data({"athlete_id": 1, "season": 2026, "valida_nums": [4]})
    assert "event_conditions" in update
