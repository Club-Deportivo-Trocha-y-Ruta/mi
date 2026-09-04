"""Tests del nodo compute_metrics."""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.race.ai.nodes import compute_metrics as mod


@pytest.mark.asyncio
async def test_compute_metrics_serializes_dataframes(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    prog = pd.DataFrame([{"valida_num": 1, "position": 2}])
    podium = pd.DataFrame([{"competitor_id": 22, "gap_to_p1_ms": 1500}])

    async def _ap(db, cid):
        return prog

    async def _pg(db, cat, season):
        return podium

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)

    state = {"competitor_id": 22, "category_id": 7, "season": 2026}
    update = await mod.compute_metrics(state)
    assert update["metrics"]["progression"][0]["valida_num"] == 1
    assert update["metrics"]["podium_gap"][0]["gap_to_p1_ms"] == 1500


@pytest.mark.asyncio
async def test_compute_metrics_no_competitor(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    update = await mod.compute_metrics({"competitor_id": None, "category_id": None, "season": 2026})
    assert update["metrics"] == {}


# ---------------------------------------------------------------------------
# progression_groups (feature 039 — season comparison groups, T030)
#
# contracts/ai-context.md: "metrics.progression_groups | compute_metrics |
# NEW {'cups': {'<series_id>': [rows]}, 'championships': [rows]}" — built
# from metrics.progression via comparison_groups.split_progression.
# metrics.progression itself stays flat and unchanged.
# ---------------------------------------------------------------------------

_PROGRESSION_ROWS_039 = [
    {
        "event_id": 11,
        "series_id": 1,
        "series_kind": "cup",
        "series_level": "departmental",
        "series_name": "Copa Valle",
        "season_year": 2026,
        "event_date": "2026-03-01",
        "valida_num": 1,
        "position": 5,
    },
    {
        "event_id": 12,
        "series_id": 1,
        "series_kind": "cup",
        "series_level": "departmental",
        "series_name": "Copa Valle",
        "season_year": 2026,
        "event_date": "2026-04-01",
        "valida_num": 2,
        "position": 3,
    },
    {
        "event_id": 90,
        "series_id": 2,
        "series_kind": "championship",
        "series_level": "departmental",
        "series_name": "Cto. Departamental Valle",
        "season_year": 2026,
        "event_date": "2026-05-01",
        "valida_num": 1,
        "position": 1,
    },
]


@pytest.mark.asyncio
async def test_compute_metrics_emits_progression_groups(
    monkeypatch, configure_db_factory, fake_session
):
    """metrics.progression stays flat (compat) and metrics.progression_groups
    splits it into cups (by series_id) / championships (research.md D9)."""
    configure_db_factory(fake_session)
    prog = pd.DataFrame(_PROGRESSION_ROWS_039)

    async def _ap(db, cid):
        return prog

    async def _pg(db, cat, season):
        return pd.DataFrame()

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)

    update = await mod.compute_metrics({"competitor_id": 22, "category_id": 7, "season": 2026})

    # metrics.progression: flat, unchanged, same row order.
    assert [r["event_id"] for r in update["metrics"]["progression"]] == [11, 12, 90]

    progression_groups = update["metrics"].get("progression_groups")
    assert progression_groups is not None, (
        "compute_metrics no emite metrics.progression_groups todavía "
        "(pendiente T033: split_progression sobre metrics.progression)"
    )
    # F-7: las claves de "cups" son str (contracts/ai-context.md: "<series_id>").
    assert set(progression_groups["cups"].keys()) == {"1"}
    assert [r["event_id"] for r in progression_groups["cups"]["1"]] == [11, 12]
    assert [r["event_id"] for r in progression_groups["championships"]] == [90]


@pytest.mark.asyncio
async def test_season_comparative_receives_anchored_event_id(
    monkeypatch, configure_db_factory, fake_session
):
    """El event_id del lanzamiento anclado debe llegar a
    _compute_season_comparative como anchored_event_id (contracts/ai-context.md
    regla 1 — nunca resolver la carrera analizada solo por valida_num)."""
    configure_db_factory(fake_session)
    captured: dict = {}

    def _fake_compute_season_comparative(full_season_results, analyzed_valida_nums, **kwargs):
        captured["args"] = (full_season_results, analyzed_valida_nums)
        captured["kwargs"] = kwargs
        return [], "first_reference"

    async def _ap(db, cid):
        return pd.DataFrame(_PROGRESSION_ROWS_039)

    async def _pg(db, cat, season):
        return pd.DataFrame()

    monkeypatch.setattr(mod, "athlete_progression", _ap)
    monkeypatch.setattr(mod, "podium_gap", _pg)
    monkeypatch.setattr(mod, "_compute_season_comparative", _fake_compute_season_comparative)

    state = {
        "competitor_id": 22,
        "category_id": 7,
        "season": 2026,
        "event_id": 90,
        "valida_nums": [1],
        "full_season_results": [
            {
                "result_id": 1,
                "event_id": 90,
                "valida_num": 1,
                "series_id": 2,
                "series_kind": "championship",
                "series_level": "departmental",
                "event_date": "2026-05-01",
                "position": 1,
                "race_time_ms": 3_000_000,
                "gap_to_winner_ms": 0,
                "gap_pct": 0.0,
                "status": "finished",
            },
        ],
    }
    await mod.compute_metrics(state)

    assert captured.get("kwargs", {}).get("anchored_event_id") == 90
