"""Tests del nodo load_race_data."""
from __future__ import annotations

from datetime import date

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


class _FakeEvent:
    def __init__(self, *, id, series_id, sequence_number, event_date):
        self.id = id
        self.series_id = series_id
        self.sequence_number = sequence_number
        self.event_date = event_date


class _FakeSeries:
    def __init__(self, *, id, season_year):
        self.id = id
        self.season_year = season_year


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


@pytest.mark.asyncio
async def test_full_season_context_trimmed_to_launched_validas(
    monkeypatch, configure_db_factory, fake_session
):
    """Coach lanza solo V-I con 4 válidas disputadas en la temporada:
    el contexto histórico se recorta a V-I únicamente y se activa N=1.
    """
    configure_db_factory(fake_session)
    all_results = [
        _FakeResult(id=1, event_id=11, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_179_000),
        _FakeResult(id=2, event_id=12, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_100_000),
        _FakeResult(id=3, event_id=13, category_id=7, competitor_id=22,
                    athlete_id=1, position=5, race_time_ms=2_200_000),
        _FakeResult(id=4, event_id=14, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_050_000),
    ]
    events = [
        _FakeEvent(id=11, series_id=1, sequence_number=1, event_date=date(2026, 1, 31)),
        _FakeEvent(id=12, series_id=1, sequence_number=2, event_date=date(2026, 2, 28)),
        _FakeEvent(id=13, series_id=1, sequence_number=3, event_date=date(2026, 4, 19)),
        _FakeEvent(id=14, series_id=1, sequence_number=4, event_date=date(2026, 5, 17)),
    ]
    series = [_FakeSeries(id=1, season_year=2026)]

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        if valida_nums is None:
            return all_results
        s = set(valida_nums)
        ev_seq = {e.id: e.sequence_number for e in events}
        return [r for r in all_results if ev_seq.get(r.event_id) in s]

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        # No need for podium gap test; return [] to skip winner_map.
        return []

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    state = {"athlete_id": 1, "season": 2026, "valida_nums": [1]}
    update = await mod.load_race_data(state)

    assert len(update["raw_data"]) == 1
    assert len(update["full_season_results"]) == 1, (
        "full_season_results debe recortarse a la única válida lanzada "
        "(no contaminar con V-II, V-III, V-IV posteriores)."
    )
    assert update["full_season_results"][0]["event_id"] == 11
    assert update["season_validas_count"] == 1
    assert update["is_first_in_season"] is True, (
        "Lanzar solo la primera válida cronológica debe activar N=1, "
        "aunque existan válidas posteriores en la temporada."
    )


@pytest.mark.asyncio
async def test_full_season_context_includes_prior_validas(
    monkeypatch, configure_db_factory, fake_session
):
    """Coach lanza V-III: el contexto histórico cubre V-I, V-II y V-III
    (no incluye V-IV posterior). Se permite tendencia (N>1).
    """
    configure_db_factory(fake_session)
    all_results = [
        _FakeResult(id=1, event_id=11, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_179_000),
        _FakeResult(id=2, event_id=12, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_100_000),
        _FakeResult(id=3, event_id=13, category_id=7, competitor_id=22,
                    athlete_id=1, position=5, race_time_ms=2_200_000),
        _FakeResult(id=4, event_id=14, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_050_000),
    ]
    events = [
        _FakeEvent(id=11, series_id=1, sequence_number=1, event_date=date(2026, 1, 31)),
        _FakeEvent(id=12, series_id=1, sequence_number=2, event_date=date(2026, 2, 28)),
        _FakeEvent(id=13, series_id=1, sequence_number=3, event_date=date(2026, 4, 19)),
        _FakeEvent(id=14, series_id=1, sequence_number=4, event_date=date(2026, 5, 17)),
    ]
    series = [_FakeSeries(id=1, season_year=2026)]

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        if valida_nums is None:
            return all_results
        s = set(valida_nums)
        ev_seq = {e.id: e.sequence_number for e in events}
        return [r for r in all_results if ev_seq.get(r.event_id) in s]

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return []

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    state = {"athlete_id": 1, "season": 2026, "valida_nums": [3]}
    update = await mod.load_race_data(state)

    assert len(update["raw_data"]) == 1
    events_in_context = sorted(
        r["event_id"] for r in update["full_season_results"]
    )
    assert events_in_context == [11, 12, 13], (
        "Contexto histórico debe cubrir V-I y V-II previas + V-III lanzada, "
        "excluyendo V-IV posterior."
    )
    assert update["season_validas_count"] == 3
    assert update["is_first_in_season"] is False


@pytest.mark.asyncio
async def test_full_season_context_unfiltered_when_valida_nums_none(
    monkeypatch, configure_db_factory, fake_session
):
    """Lanzamiento global (valida_nums=None) preserva la temporada completa."""
    configure_db_factory(fake_session)
    all_results = [
        _FakeResult(id=1, event_id=11, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_179_000),
        _FakeResult(id=2, event_id=12, category_id=7, competitor_id=22,
                    athlete_id=1, position=4, race_time_ms=2_100_000),
        _FakeResult(id=3, event_id=13, category_id=7, competitor_id=22,
                    athlete_id=1, position=5, race_time_ms=2_200_000),
    ]
    events = [
        _FakeEvent(id=11, series_id=1, sequence_number=1, event_date=date(2026, 1, 31)),
        _FakeEvent(id=12, series_id=1, sequence_number=2, event_date=date(2026, 2, 28)),
        _FakeEvent(id=13, series_id=1, sequence_number=3, event_date=date(2026, 4, 19)),
    ]
    series = [_FakeSeries(id=1, season_year=2026)]

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return all_results

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return []

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    state = {"athlete_id": 1, "season": 2026}
    update = await mod.load_race_data(state)

    assert update["season_validas_count"] == 3
    assert update["is_first_in_season"] is False
    assert len(update["full_season_results"]) == 3
