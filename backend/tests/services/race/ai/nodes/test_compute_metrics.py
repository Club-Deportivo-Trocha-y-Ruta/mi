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
