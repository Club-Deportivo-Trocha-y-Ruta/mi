"""Tests del nodo ``load_athlete_context`` (feature 037, T103).

Usa el ``FakeSession``/``configure_db_factory`` compartidos (mismo patrón que
``test_load_race_data.py``): las queries ORM (``select(Athlete.club_id)``,
``load_events``) se resuelven vía monkeypatch/fakes, y los loaders puros de
``athlete_context`` se stubean para aislar el wiring del nodo (resolución de
fecha de referencia, ventana, propagación best-effort de errores).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.race.ai.nodes import load_athlete_context as mod


class _FakeEvent:
    def __init__(self, *, id, event_date):
        self.id = id
        self.event_date = event_date


@pytest.mark.asyncio
async def test_load_athlete_context_uses_anchored_event_date(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)

    captured_dates = {}

    async def _fake_load_events(db):
        return [_FakeEvent(id=99, event_date=date(2026, 5, 17))]

    async def _fake_resolve_club_id(db, athlete_id):
        return 1

    async def _fake_anthro(db, athlete_id, reference_date):
        captured_dates["anthro"] = reference_date
        return None

    async def _fake_training_window(db, athlete_id, club_id, date_from, date_to):
        captured_dates["window"] = (date_from, date_to)
        return None

    async def _fake_catalog(db, club_id, age_band):
        captured_dates["age_band"] = age_band
        return {"interval_templates": []}

    async def _fake_forbidden(db, club_id):
        return []

    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "_resolve_club_id", _fake_resolve_club_id)
    monkeypatch.setattr(mod, "load_anthro_context", _fake_anthro)
    monkeypatch.setattr(mod, "load_training_window", _fake_training_window)
    monkeypatch.setattr(mod, "load_catalog_context", _fake_catalog)
    monkeypatch.setattr(mod, "load_club_forbidden_names", _fake_forbidden)

    state = {
        "athlete_id": 1,
        "season": 2026,
        "event_id": 99,
        "athlete_age": 11,
        "analysis_kind": "valida",
    }
    update = await mod.load_athlete_context(state)

    assert captured_dates["anthro"] == date(2026, 5, 17)
    date_from, date_to = captured_dates["window"]
    assert date_to == date(2026, 5, 17)
    assert (date_to - date_from).days == 28
    assert captured_dates["age_band"] == "10-12"
    assert "errors" not in update


@pytest.mark.asyncio
async def test_load_athlete_context_season_uses_full_year_window(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)

    async def _fake_load_events(db):
        return []

    async def _fake_resolve_club_id(db, athlete_id):
        return 1

    captured = {}

    async def _fake_training_window(db, athlete_id, club_id, date_from, date_to):
        captured["range"] = (date_from, date_to)
        return None

    async def _fake_anthro(db, athlete_id, reference_date):
        return None

    async def _fake_catalog(db, club_id, age_band):
        return {"interval_templates": []}

    async def _fake_forbidden(db, club_id):
        return []

    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "_resolve_club_id", _fake_resolve_club_id)
    monkeypatch.setattr(mod, "load_anthro_context", _fake_anthro)
    monkeypatch.setattr(mod, "load_training_window", _fake_training_window)
    monkeypatch.setattr(mod, "load_catalog_context", _fake_catalog)
    monkeypatch.setattr(mod, "load_club_forbidden_names", _fake_forbidden)

    state = {"athlete_id": 1, "season": 2026, "analysis_kind": "season"}
    await mod.load_athlete_context(state)

    date_from, date_to = captured["range"]
    assert date_from == date(2026, 1, 1)
    assert date_to == date.today()


@pytest.mark.asyncio
async def test_load_athlete_context_is_best_effort_on_loader_failure(
    monkeypatch, configure_db_factory, fake_session
):
    """Un loader que falla NUNCA rompe el run — clave None + entrada en errors."""
    configure_db_factory(fake_session)

    async def _fake_load_events(db):
        return []

    async def _fake_resolve_club_id(db, athlete_id):
        return 1

    async def _boom_anthro(db, athlete_id, reference_date):
        raise RuntimeError("DB caída")

    async def _fake_training_window(db, athlete_id, club_id, date_from, date_to):
        return None

    async def _fake_catalog(db, club_id, age_band):
        return {"interval_templates": []}

    async def _fake_forbidden(db, club_id):
        return []

    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "_resolve_club_id", _fake_resolve_club_id)
    monkeypatch.setattr(mod, "load_anthro_context", _boom_anthro)
    monkeypatch.setattr(mod, "load_training_window", _fake_training_window)
    monkeypatch.setattr(mod, "load_catalog_context", _fake_catalog)
    monkeypatch.setattr(mod, "load_club_forbidden_names", _fake_forbidden)

    state = {"athlete_id": 1, "season": 2026, "analysis_kind": "valida"}
    update = await mod.load_athlete_context(state)

    assert update["anthro_context"] is None
    assert update["errors"]
    assert update["errors"][0]["field"] == "anthro_context"
    assert update["errors"][0]["error"] == "RuntimeError"


@pytest.mark.asyncio
async def test_load_athlete_context_without_club_id_records_error(
    monkeypatch, configure_db_factory, fake_session
):
    configure_db_factory(fake_session)

    async def _fake_load_events(db):
        return []

    async def _fake_resolve_club_id(db, athlete_id):
        return None

    async def _fake_anthro(db, athlete_id, reference_date):
        return None

    monkeypatch.setattr(mod, "load_events", _fake_load_events)
    monkeypatch.setattr(mod, "_resolve_club_id", _fake_resolve_club_id)
    monkeypatch.setattr(mod, "load_anthro_context", _fake_anthro)

    state = {"athlete_id": 999, "season": 2026, "analysis_kind": "valida"}
    update = await mod.load_athlete_context(state)

    assert update["training_window"] is None
    assert update["catalog_context"] == {
        "interval_templates": [],
    }
    assert update["club_forbidden_names"] == []
    assert any(e["field"] == "club_id" for e in update["errors"])
