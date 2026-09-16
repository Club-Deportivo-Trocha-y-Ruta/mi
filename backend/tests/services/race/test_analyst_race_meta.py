"""US1 (feature 011): race_meta formatting + per-válida AnalysisInput grounding.

Regression: ``_build_v2_context`` used to read the never-set
``podium_context["race_meta"]`` (always ""), so conditions were never grounded.
``format_race_meta`` must return ``None`` (not "") when nothing is recorded.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.race import queries as q
from app.services.race.agents.analyst import format_race_meta


def test_format_race_meta_populated_with_recorded_conditions():
    block = format_race_meta(
        {
            "climate": "Nublado",
            "temperature_c": 25.0,
            "surface_condition": "humeda",
            "altitude_msnm": 1000,
            "weather_notes": "barro en el sector técnico",
        }
    )
    assert block is not None
    assert "Nublado" in block
    assert "25" in block
    assert "Húmeda" in block  # enum value 'humeda' rendered with display label
    assert "1000" in block
    assert "barro en el sector técnico" in block


def test_format_race_meta_none_when_unrecorded():
    """All-None conditions → None, never an empty string (kills silent bug)."""
    block = format_race_meta(
        {
            "climate": None,
            "temperature_c": None,
            "surface_condition": None,
            "altitude_msnm": None,
            "weather_notes": None,
        }
    )
    assert block is None


def test_format_race_meta_partial_only_lists_recorded():
    block = format_race_meta(
        {
            "climate": None,
            "temperature_c": None,
            "surface_condition": "seca",
            "altitude_msnm": None,
            "weather_notes": None,
        }
    )
    assert block is not None
    assert "Seca" in block
    assert "Clima" not in block
    assert "Temperatura" not in block


class _FakeEvent:
    def __init__(self, *, id, series_id, sequence_number, climate=None,
                 temperature_c=None, surface_condition=None, altitude_msnm=None,
                 weather_notes=None):
        self.id = id
        self.series_id = series_id
        self.sequence_number = sequence_number
        self.event_date = date(2026, 5, 17)
        self.climate = climate
        self.temperature_c = temperature_c
        self.surface_condition = surface_condition
        self.altitude_msnm = altitude_msnm
        self.weather_notes = weather_notes


class _FakeSeries:
    def __init__(self, *, id, season_year):
        self.id = id
        self.season_year = season_year


@pytest.mark.asyncio
async def test_fetch_event_conditions_all_none_entry_for_unrecorded(monkeypatch):
    events = [
        _FakeEvent(id=14, series_id=1, sequence_number=4, climate="Nublado",
                   temperature_c=25.0, surface_condition="humeda",
                   altitude_msnm=1000, weather_notes="barro"),
        _FakeEvent(id=13, series_id=1, sequence_number=3),  # all None
    ]
    series = [_FakeSeries(id=1, season_year=2026)]

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(q, "load_events", _fake_load_events)
    monkeypatch.setattr(q, "load_series", _fake_load_series)

    out = await q.fetch_event_conditions(None, 2026, [3, 4])
    assert set(out.keys()) == {3, 4}
    assert out[4]["climate"] == "Nublado"
    assert out[4]["surface_condition"] == "humeda"  # enum value passthrough
    assert all(v is None for v in out[3].values())


# ---------------------------------------------------------------------------
# fetch_event_conditions — series_id (hotfix identidad de válida)
#
# Dos copas de la misma temporada, ambas con V4, condiciones distintas:
# con series_id cada copa ve solo su propio dato; sin series_id la
# ambigüedad preexistente no se afirma (solo se documenta que colisiona).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_event_conditions_series_id_scopes_to_own_series(monkeypatch):
    events = [
        _FakeEvent(
            id=101, series_id=1, sequence_number=4,
            climate="Soleado", temperature_c=30.0, surface_condition="seca",
            altitude_msnm=1200, weather_notes="Copa Valle V4",
        ),
        _FakeEvent(
            id=202, series_id=2, sequence_number=4,
            climate="Lluvioso", temperature_c=18.0, surface_condition="humeda",
            altitude_msnm=1600, weather_notes="Copa Let's Go V4",
        ),
    ]
    series = [_FakeSeries(id=1, season_year=2026), _FakeSeries(id=2, season_year=2026)]

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(q, "load_events", _fake_load_events)
    monkeypatch.setattr(q, "load_series", _fake_load_series)

    out_valle = await q.fetch_event_conditions(None, 2026, [4], series_id=1)
    assert out_valle[4]["weather_notes"] == "Copa Valle V4"

    out_letsgo = await q.fetch_event_conditions(None, 2026, [4], series_id=2)
    assert out_letsgo[4]["weather_notes"] == "Copa Let's Go V4"


@pytest.mark.asyncio
async def test_fetch_event_conditions_without_series_id_behaviour_unchanged(monkeypatch):
    """Sin ``series_id`` la ambigüedad entre las dos copas en V4 preexiste:
    solo se afirma que se resuelve UNA entrada (dict con clave única 4),
    NUNCA cuál de las dos copas "gana" — eso es justamente el bug."""
    events = [
        _FakeEvent(
            id=101, series_id=1, sequence_number=4,
            climate="Soleado", temperature_c=30.0, surface_condition="seca",
            altitude_msnm=1200, weather_notes="Copa Valle V4",
        ),
        _FakeEvent(
            id=202, series_id=2, sequence_number=4,
            climate="Lluvioso", temperature_c=18.0, surface_condition="humeda",
            altitude_msnm=1600, weather_notes="Copa Let's Go V4",
        ),
    ]
    series = [_FakeSeries(id=1, season_year=2026), _FakeSeries(id=2, season_year=2026)]

    async def _fake_load_events(db):
        return events

    async def _fake_load_series(db):
        return series

    monkeypatch.setattr(q, "load_events", _fake_load_events)
    monkeypatch.setattr(q, "load_series", _fake_load_series)

    out = await q.fetch_event_conditions(None, 2026, [4])
    assert set(out.keys()) == {4}
    assert out[4]["weather_notes"] in ("Copa Valle V4", "Copa Let's Go V4")


# ---------------------------------------------------------------------------
# fetch_event_conditions_by_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_event_conditions_by_event_keys_both_events(monkeypatch):
    events = [
        _FakeEvent(
            id=101, series_id=1, sequence_number=4,
            climate="Soleado", temperature_c=30.0, surface_condition="seca",
            altitude_msnm=1200, weather_notes="Copa Valle V4",
        ),
        _FakeEvent(
            id=202, series_id=2, sequence_number=4,
            climate="Lluvioso", temperature_c=18.0, surface_condition="humeda",
            altitude_msnm=1600, weather_notes="Copa Let's Go V4",
        ),
    ]

    async def _fake_load_events(db):
        return events

    monkeypatch.setattr(q, "load_events", _fake_load_events)

    out = await q.fetch_event_conditions_by_event(None, [101, 202])
    assert set(out.keys()) == {101, 202}
    assert out[101]["weather_notes"] == "Copa Valle V4"
    assert out[202]["weather_notes"] == "Copa Let's Go V4"


@pytest.mark.asyncio
async def test_fetch_event_conditions_by_event_missing_id_all_none(monkeypatch):
    async def _fake_load_events(db):
        return []

    monkeypatch.setattr(q, "load_events", _fake_load_events)

    out = await q.fetch_event_conditions_by_event(None, [999])
    assert set(out.keys()) == {999}
    assert all(v is None for v in out[999].values())
