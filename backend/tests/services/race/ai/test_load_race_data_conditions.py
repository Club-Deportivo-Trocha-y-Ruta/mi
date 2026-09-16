"""US1 (feature 011): load_race_data emits recorded event conditions per válida.

Regression: on unfixed code the node never emitted ``event_conditions``; the
analyst then had no real conditions and fabricated them.
"""
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

    async def _fake_fetch_results(db, aid, season, valida_nums=None, series_id=None):
        return rs

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _fake_fetch_all_season(db, cat, season):
        return []

    async def _fake_resolve_max(db, season, valida_nums, event_id=None):
        return None

    # Válida 4 = recorded (Cali Húmeda/Nublado); válida 3 = all-None (unrecorded).
    async def _fake_fetch_conditions(db, season, valida_nums, series_id=None):
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

    async def _fake_fetch_results(db, aid, season, valida_nums=None, series_id=None):
        return []

    async def _fake_fetch_conditions(db, season, valida_nums, series_id=None):
        return {}

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch_results)
    monkeypatch.setattr(mod, "fetch_event_conditions", _fake_fetch_conditions)

    update = await mod.load_race_data({"athlete_id": 1, "season": 2026, "valida_nums": [4]})
    assert "event_conditions" in update


# ---------------------------------------------------------------------------
# Multicopa (hotfix identidad de válida): sin ``series_id`` resuelto, una
# válida ambigua entre copas NUNCA debe pasar a
# ``fetch_event_conditions``/``fetch_course_context`` con ``series_id=None``
# — eso dejaría que la primera copa encontrada en memoria "gane" (el bug
# original). Se excluye de condiciones y se vacía en circuito.
# ---------------------------------------------------------------------------


class _FakeEvent:
    def __init__(self, *, id, series_id, sequence_number, event_date=date(2026, 5, 1)):
        self.id = id
        self.series_id = series_id
        self.sequence_number = sequence_number
        self.event_date = event_date


class _FakeSeries:
    def __init__(self, *, id, season_year):
        self.id = id
        self.season_year = season_year


async def _fake_conditions_mirroring_request(db, season, valida_nums, series_id=None):
    """Fake de ``fetch_event_conditions`` — devuelve una entrada por cada
    ``valida_num`` pedido (para verificar EXACTAMENTE qué se pidió)."""
    return {vn: {"climate": f"FAKE-{vn}"} for vn in valida_nums}


async def _fake_course_mirroring_request(db, season, valida_nums, category_id=None, series_id=None):
    """Fake de ``fetch_course_context`` — ídem, una entrada por válida pedida."""
    return {vn: {"terrain_type": f"FAKE-{vn}"} for vn in valida_nums}


@pytest.mark.asyncio
async def test_ambiguous_valida_without_anchor_gets_no_conditions_or_course_from_either_cup(
    monkeypatch, configure_db_factory, fake_session
):
    """Dos copas comparten "Válida 4" en la temporada; el lanzamiento no trae
    ancla (``event_id``) ni resuelve un ``series_id`` único. Ninguna de las
    dos copas debe aportar condiciones ni circuito — nunca first-match-wins."""
    configure_db_factory(fake_session)

    events = [
        _FakeEvent(id=10, series_id=1, sequence_number=4),  # Copa Valle V4
        _FakeEvent(id=43, series_id=2, sequence_number=4),  # Copa Let's Go V4
    ]
    series = [
        _FakeSeries(id=1, season_year=2026),
        _FakeSeries(id=2, season_year=2026),
    ]
    rs = [
        _FakeResult(id=1, event_id=10, category_id=7, competitor_id=22,
                    athlete_id=1, position=3, race_time_ms=2_100_000),
    ]

    async def _fake_fetch_results(db, aid, season, valida_nums=None, series_id=None):
        return rs

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
    monkeypatch.setattr(mod, "fetch_event_conditions", _fake_conditions_mirroring_request)
    monkeypatch.setattr(mod, "fetch_course_context", _fake_course_mirroring_request)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    state = {"athlete_id": 1, "season": 2026, "valida_nums": [4]}
    update = await mod.load_race_data(state)

    assert update["series_id"] is None
    assert 4 not in update["event_conditions"], (
        "válida ambigua sin series_id: NO debe pedirse condiciones a ninguna "
        "copa (first-match-wins es el bug original)."
    )
    assert update["course_context"][4] == {}, (
        "válida ambigua sin series_id: el circuito debe quedar vacío "
        "(nunca el de la primera copa encontrada)."
    )


@pytest.mark.asyncio
async def test_only_the_ambiguous_valida_is_excluded_the_others_keep_their_data(
    monkeypatch, configure_db_factory, fake_session
):
    """Lanzamiento sin ancla con dos válidas: la 3 es única en la temporada
    (conserva sus condiciones/circuito), la 4 es ambigua entre dos copas
    (se excluye/vacía). Una no debe contaminar a la otra."""
    configure_db_factory(fake_session)

    events = [
        _FakeEvent(id=9, series_id=1, sequence_number=3),   # única en la temporada
        _FakeEvent(id=10, series_id=1, sequence_number=4),  # Copa Valle V4
        _FakeEvent(id=43, series_id=2, sequence_number=4),  # Copa Let's Go V4
    ]
    series = [
        _FakeSeries(id=1, season_year=2026),
        _FakeSeries(id=2, season_year=2026),
    ]
    rs = [
        _FakeResult(id=1, event_id=9, category_id=7, competitor_id=22,
                    athlete_id=1, position=2, race_time_ms=2_050_000),
        _FakeResult(id=2, event_id=10, category_id=7, competitor_id=22,
                    athlete_id=1, position=3, race_time_ms=2_100_000),
    ]

    async def _fake_fetch_results(db, aid, season, valida_nums=None, series_id=None):
        return rs

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
    monkeypatch.setattr(mod, "fetch_event_conditions", _fake_conditions_mirroring_request)
    monkeypatch.setattr(mod, "fetch_course_context", _fake_course_mirroring_request)
    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "load_series", _fake_load_series)

    state = {"athlete_id": 1, "season": 2026, "valida_nums": [3, 4]}
    update = await mod.load_race_data(state)

    assert update["series_id"] is None
    # Válida 3 (única en la temporada) conserva sus datos.
    assert update["event_conditions"][3] == {"climate": "FAKE-3"}
    assert update["course_context"][3] == {"terrain_type": "FAKE-3"}
    # Válida 4 (ambigua) queda excluida/vacía — sin contaminar la 3.
    assert 4 not in update["event_conditions"]
    assert update["course_context"][4] == {}
