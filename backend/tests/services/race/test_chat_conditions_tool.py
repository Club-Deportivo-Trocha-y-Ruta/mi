"""US5 (feature 011): obtener_condiciones_evento tool grounding."""
from __future__ import annotations

import json

import pytest

from app.services.race.agents import chat as chat_mod
from app.services.race.agents.chat import _build_obtener_condiciones_evento_tool


@pytest.mark.asyncio
async def test_tool_returns_recorded_conditions(monkeypatch):
    async def _fake_fetch(db, season, valida_nums):
        return {
            4: {
                "climate": "Nublado",
                "temperature_c": 25.0,
                "surface_condition": "humeda",
                "altitude_msnm": 1000,
                "weather_notes": None,
            }
        }

    monkeypatch.setattr(chat_mod, "fetch_event_conditions", _fake_fetch)
    tool = _build_obtener_condiciones_evento_tool(db_factory=lambda: object())
    out = json.loads(await tool.ainvoke({"valida_num": 4, "season": 2026}))
    assert out["registro"] is True
    assert out["climate"] == "Nublado"
    assert out["surface_condition"] == "humeda"


@pytest.mark.asyncio
async def test_tool_returns_registro_false_for_unrecorded(monkeypatch):
    async def _fake_fetch(db, season, valida_nums):
        return {
            3: {
                "climate": None,
                "temperature_c": None,
                "surface_condition": None,
                "altitude_msnm": None,
                "weather_notes": None,
            }
        }

    monkeypatch.setattr(chat_mod, "fetch_event_conditions", _fake_fetch)
    tool = _build_obtener_condiciones_evento_tool(db_factory=lambda: object())
    out = json.loads(await tool.ainvoke({"valida_num": 3, "season": 2026}))
    assert out["registro"] is False


@pytest.mark.asyncio
async def test_tool_scrubs_forbidden_name_in_weather_notes(monkeypatch):
    async def _fake_fetch(db, season, valida_nums):
        return {
            4: {
                "climate": "Nublado",
                "temperature_c": None,
                "surface_condition": None,
                "altitude_msnm": None,
                "weather_notes": "Sara Gómez ayudó en boxes",
            }
        }

    monkeypatch.setattr(chat_mod, "fetch_event_conditions", _fake_fetch)
    tool = _build_obtener_condiciones_evento_tool(
        db_factory=lambda: object(), forbidden_names=["Sara Gómez"]
    )
    out = json.loads(await tool.ainvoke({"valida_num": 4, "season": 2026}))
    assert "Sara Gómez" not in out.get("weather_notes", "")


@pytest.mark.asyncio
async def test_tool_returns_registro_false_when_missing(monkeypatch):
    async def _fake_fetch(db, season, valida_nums):
        return {}

    monkeypatch.setattr(chat_mod, "fetch_event_conditions", _fake_fetch)
    tool = _build_obtener_condiciones_evento_tool(db_factory=lambda: object())
    out = json.loads(await tool.ainvoke({"valida_num": 9, "season": 2026}))
    assert out["registro"] is False
