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


@pytest.mark.asyncio
async def test_anchored_event_id_trims_context_despite_sequence_collision(
    monkeypatch, configure_db_factory, fake_session
):
    """Regresión: ``sequence_number`` no identifica una carrera en la temporada.

    Escenario real (temporada 2026, atleta con 7 carreras): cuatro eventos
    comparten ``sequence_number=1`` — la válida 1 de copa (31 ene) y tres
    campeonatos posteriores (13 jun, 11 jul, 18 jul). Al recortar el contexto
    por número de válida, ``max()`` daba el 18 de julio y el análisis de la
    PRIMERA carrera del año narraba seis eventos posteriores, concluyendo
    "declive" al comparar enero contra julio.

    Con el ``event_id`` anclado (que los routers ya resuelven), el corte es la
    fecha de ESE evento y se recupera N=1.
    """
    configure_db_factory(fake_session)
    all_results = [
        # Sevilla XCO — copa, válida 1, la analizada.
        _FakeResult(id=1, event_id=16, category_id=7, competitor_id=22,
                    athlete_id=2, position=4, race_time_ms=2_179_000),
        _FakeResult(id=2, event_id=8, category_id=7, competitor_id=22,
                    athlete_id=2, position=4, race_time_ms=3_279_000),
        _FakeResult(id=3, event_id=10, category_id=7, competitor_id=22,
                    athlete_id=2, position=4, race_time_ms=2_103_000),
        # Ginebra y Pereira: campeonatos, TAMBIÉN sequence_number=1.
        _FakeResult(id=4, event_id=15, category_id=7, competitor_id=22,
                    athlete_id=2, position=2, race_time_ms=2_780_000),
        _FakeResult(id=5, event_id=20, category_id=7, competitor_id=22,
                    athlete_id=2, position=11, race_time_ms=3_393_000),
    ]
    events = [
        _FakeEvent(id=16, series_id=1, sequence_number=1, event_date=date(2026, 1, 31)),
        _FakeEvent(id=8, series_id=1, sequence_number=2, event_date=date(2026, 3, 1)),
        _FakeEvent(id=10, series_id=1, sequence_number=3, event_date=date(2026, 4, 19)),
        _FakeEvent(id=15, series_id=2, sequence_number=1, event_date=date(2026, 6, 13)),
        _FakeEvent(id=20, series_id=3, sequence_number=1, event_date=date(2026, 7, 18)),
    ]
    series = [
        _FakeSeries(id=1, season_year=2026),
        _FakeSeries(id=2, season_year=2026),
        _FakeSeries(id=3, season_year=2026),
    ]

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

    state = {
        "athlete_id": 2,
        "season": 2026,
        "valida_nums": [1],
        "event_id": 16,
    }
    update = await mod.load_race_data(state)

    assert len(update["raw_data"]) == 1, (
        "El set analizado debe quedarse solo con el evento anclado, no "
        "mezclar la válida 1 de copa con los campeonatos que comparten número."
    )
    assert update["raw_data"][0]["event_id"] == 16
    assert len(update["full_season_results"]) == 1, (
        "El corte cronológico debe usar la fecha del evento anclado "
        "(31 ene), no el max() del conjunto ambiguo (18 jul)."
    )
    assert update["full_season_results"][0]["event_id"] == 16
    assert update["season_validas_count"] == 1
    assert update["is_first_in_season"] is True


@pytest.mark.asyncio
async def test_full_season_results_valida_num_uses_event_sequence_number(
    monkeypatch, configure_db_factory, fake_session
):
    """Regresión (feature 037, T101): ``valida_num`` de ``full_season_results``
    debe venir de ``RaceEvent.sequence_number`` (el único lugar donde vive),
    NUNCA de un atributo homónimo inexistente en ``RaceResult``. Antes de este
    fix, ``_compacted_season_record`` leía ``getattr(r, "sequence_number",
    None)`` sobre el resultado y siempre devolvía ``None`` — este test falla
    contra esa versión y pasa contra la corregida.
    """
    configure_db_factory(fake_session)
    all_results = [
        _FakeResult(id=1, event_id=11, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_100_000),
        _FakeResult(id=2, event_id=12, category_id=7, competitor_id=22,
                    athlete_id=1, position=1, race_time_ms=2_000_000),
    ]
    events = [
        _FakeEvent(id=11, series_id=1, sequence_number=1, event_date=date(2026, 1, 31)),
        _FakeEvent(id=12, series_id=1, sequence_number=2, event_date=date(2026, 2, 28)),
    ]
    series = [_FakeSeries(id=1, season_year=2026)]

    async def _fake_fetch_results(db, aid, season, valida_nums=None):
        return all_results

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return all_results

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_podium_context", _fake_fetch_podium)
    monkeypatch.setattr(mod, "fetch_all_results_for_season", _fake_fetch_all_season)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    update = await mod.load_race_data({"athlete_id": 1, "season": 2026})

    records_by_event = {r["event_id"]: r for r in update["full_season_results"]}
    assert records_by_event[11]["valida_num"] == 1
    assert records_by_event[12]["valida_num"] == 2
    assert all(r["valida_num"] is not None for r in update["full_season_results"])
