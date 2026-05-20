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
async def test_validate_input_accepts_when_athlete_exists(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    from app.services.race.ai.nodes import validate_input as mod

    async def _fake_exists(db, aid):
        return True

    monkeypatch.setattr(mod, "athlete_exists", _fake_exists)
    state = {"athlete_id": 1, "season": 2026}
    update = await validate_input(state)
    assert not update.get("errors")


@pytest.mark.asyncio
async def test_validate_input_rejects_athlete_not_found(monkeypatch, configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    from app.services.race.ai.nodes import validate_input as mod

    async def _fake_exists(db, aid):
        return False

    monkeypatch.setattr(mod, "athlete_exists", _fake_exists)
    state = {"athlete_id": 999, "season": 2026}
    update = await validate_input(state)
    assert any(e["error"] == "AthleteNotFound" for e in update["errors"])
