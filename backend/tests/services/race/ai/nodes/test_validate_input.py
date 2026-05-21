"""Tests del nodo validate_input."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.validate_input import validate_input


@pytest.mark.asyncio
async def test_validate_input_rejects_missing_athlete_id(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {"season": 2026}
    update = await validate_input(state)
    assert update.get("errors")
    assert any(e["error"] == "InvalidAthleteId" for e in update["errors"])


@pytest.mark.asyncio
async def test_validate_input_rejects_bad_season(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    state = {"athlete_id": 1, "season": 1900}
    update = await validate_input(state)
    assert any(e["error"] == "InvalidSeason" for e in update["errors"])


@pytest.mark.asyncio
async def test_validate_input_accepts_when_results_for_season(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)
    from app.services.race.ai.nodes import validate_input as mod

    class _R:
        athlete_id = 1

    async def _fake_fetch(db, aid, season, valida_nums=None):
        return [_R()]

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch)
    state = {"athlete_id": 1, "season": 2026}
    update = await validate_input(state)
    assert not update.get("errors")
    assert not update.get("no_data_for_season")


@pytest.mark.asyncio
async def test_validate_input_flags_no_data_for_season(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)
    from app.services.race.ai.nodes import validate_input as mod

    async def _fake_fetch(db, aid, season, valida_nums=None):
        return []

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch)
    state = {"athlete_id": 999, "season": 2026}
    update = await validate_input(state)
    assert update.get("no_data_for_season") is True
    assert "Sin carreras registradas para temporada 2026" in update["rendered_markdown"]
    assert update.get("status") == "no_data"
    assert not update.get("errors")


@pytest.mark.asyncio
async def test_validate_input_no_data_respects_valida_nums_filter(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)
    from app.services.race.ai.nodes import validate_input as mod

    received: dict = {}

    async def _fake_fetch(db, aid, season, valida_nums=None):
        received["valida_nums"] = valida_nums
        return []

    monkeypatch.setattr(mod, "fetch_results_for_athlete", _fake_fetch)
    state = {"athlete_id": 1, "season": 2026, "valida_nums": [1, 2]}
    update = await validate_input(state)
    assert received["valida_nums"] == [1, 2]
    assert update.get("no_data_for_season") is True
    assert "válidas: 1, 2" in update["rendered_markdown"]
