"""Tests de las fábricas de tools default del ``RaceChatAgent``.

Aislados del agente — verifican las tools ``obtener_insights_atleta`` y
``fetch_results`` consumiendo un ``FakeAsyncSession`` minimal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services.race.agents.chat import (
    _build_fetch_results_tool,
    _build_obtener_insights_atleta_tool,
)


# ---------------------------------------------------------------------------
# Fake session para insights (SQL crudo)
# ---------------------------------------------------------------------------


@dataclass
class _Row:
    id: int = 1
    season: int = 2026
    valida_num: int | None = 3
    use_case: str = "post_race_analysis"
    summary_text: str = "Resumen del insight."
    confidence: str = "medium"
    generated_at: Any = None


class _FakeSQLResult:
    def __init__(self, rows: list[_Row]):
        self._rows = rows

    def fetchall(self) -> list[_Row]:
        return self._rows


class _FakeSession:
    """Sesión que registra el SQL ejecutado y devuelve filas pre-cargadas."""

    def __init__(self, rows: list[_Row]):
        self._rows = rows
        self.captured_sql: str | None = None
        self.captured_params: dict | None = None

    async def execute(self, stmt, params=None):
        # Capturamos el SQL string para sanity-check.
        self.captured_sql = str(stmt)
        self.captured_params = params
        return _FakeSQLResult(self._rows)


# ---------------------------------------------------------------------------
# Fake session para fetch_results (usa load_results de queries.py)
# ---------------------------------------------------------------------------


class _FakeRaceResult:
    """Mínimo necesario para fetch_results_for_athlete."""

    def __init__(self, athlete_id: int, event_id: int, position: int, time_ms: int):
        self.athlete_id = athlete_id
        self.event_id = event_id
        self.position = position
        self.race_time_ms = time_ms
        self.deleted_at = None


class _FakeEvent:
    def __init__(self, id_: int, series_id: int, seq: int, date):
        self.id = id_
        self.series_id = series_id
        self.sequence_number = seq
        self.event_date = date


class _FakeSeries:
    def __init__(self, id_: int, year: int):
        self.id = id_
        self.season_year = year


class _FakeQueryResult:
    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeResultsSession:
    """Mini-router de selects por modelo (al estilo conftest race)."""

    def __init__(self, results: list[Any], events: list[Any], series: list[Any]):
        self._results = results
        self._events = events
        self._series = series

    async def execute(self, stmt):
        # Inspeccionar el primer FROM para decidir qué devolver.
        s = str(stmt).lower()
        if "race_result" in s:
            return _FakeQueryResult(self._results)
        if "race_event" in s:
            return _FakeQueryResult(self._events)
        if "race_series" in s or "race_serie" in s:
            return _FakeQueryResult(self._series)
        return _FakeQueryResult([])


# ---------------------------------------------------------------------------
# Tests obtener_insights_atleta
# ---------------------------------------------------------------------------


async def test_obtener_insights_atleta_sin_db_factory():
    tool = _build_obtener_insights_atleta_tool(db_factory=None)
    out = await tool.ainvoke({"athlete_id": 1})
    assert "no configurado" in out


async def test_obtener_insights_atleta_sin_resultados():
    session = _FakeSession(rows=[])
    tool = _build_obtener_insights_atleta_tool(db_factory=lambda: session)
    out = await tool.ainvoke({"athlete_id": 42, "n": 5})
    assert "sin insights" in out
    assert session.captured_params == {"aid": 42, "n": 5}


async def test_obtener_insights_atleta_con_filas():
    rows = [
        _Row(id=1, season=2026, valida_num=3, summary_text="Cadencia OK"),
        _Row(id=2, season=2025, valida_num=None, summary_text="Sin válida"),
    ]
    session = _FakeSession(rows=rows)
    tool = _build_obtener_insights_atleta_tool(db_factory=lambda: session)
    out = await tool.ainvoke({"athlete_id": 42})
    assert "Válida 3" in out
    assert "Cadencia OK" in out
    assert "(sin válida)" in out


async def test_obtener_insights_atleta_clamps_n_to_max():
    """n se acota a [1, 10] — pedir 50 debe pasar 10 al SQL."""
    session = _FakeSession(rows=[])
    tool = _build_obtener_insights_atleta_tool(db_factory=lambda: session)
    await tool.ainvoke({"athlete_id": 1, "n": 50})
    assert session.captured_params["n"] == 10


# ---------------------------------------------------------------------------
# Tests fetch_results
# ---------------------------------------------------------------------------


async def test_fetch_results_sin_db_factory():
    tool = _build_fetch_results_tool(db_factory=None)
    out = await tool.ainvoke({"athlete_id": 1, "season": 2026})
    assert "no configurado" in out


async def test_fetch_results_sin_match():
    session = _FakeResultsSession(results=[], events=[], series=[])
    tool = _build_fetch_results_tool(db_factory=lambda: session)
    out = await tool.ainvoke({"athlete_id": 1, "season": 2026})
    assert out == "(sin resultados)"


async def test_fetch_results_con_match():
    from datetime import date

    series = [_FakeSeries(id_=1, year=2026)]
    events = [_FakeEvent(id_=10, series_id=1, seq=1, date=date(2026, 1, 31))]
    results = [_FakeRaceResult(athlete_id=42, event_id=10, position=5, time_ms=1800000)]

    session = _FakeResultsSession(results=results, events=events, series=series)
    tool = _build_fetch_results_tool(db_factory=lambda: session)
    out = await tool.ainvoke({"athlete_id": 42, "season": 2026})
    assert "event_id=10" in out
    assert "pos=5" in out
    assert "race_time=0:30:00" in out
