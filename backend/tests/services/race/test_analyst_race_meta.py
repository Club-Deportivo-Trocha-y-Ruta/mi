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
