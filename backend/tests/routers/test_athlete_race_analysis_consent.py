"""``POST /api/athletes/{id}/race-analysis/runs`` bloquea con 451 sin
consentimiento IA vigente (feature 037, T405).

Mismo contrato que ``routers/race_analysis.py::start_run`` y
``create_season_summary`` de este mismo router: sin autorización parental
vigente con ``third_party_sharing``, el endpoint responde 451 y NUNCA
lanza el run agéntico (``submit_run`` no se invoca).
"""
from __future__ import annotations

import pytest

from tests.routers.test_athlete_race_analysis import (  # noqa: F401
    _make_user,
    client_factory,
    seeded_factory,
    session_factory,
    engine,
)

pytestmark = pytest.mark.asyncio


async def _patch_no_ai_io(monkeypatch, router_mod):
    calls: list[tuple] = []

    async def _fake_submit_run(run_id, initial_state, on_complete=None):
        calls.append((run_id, initial_state, on_complete))

    async def _fake_check_budget(db):
        return None

    monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
    monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    return calls


async def test_start_athlete_run_returns_451_without_ai_consent(
    client_factory, monkeypatch  # noqa: F811
):
    from app.config import settings
    from app.models.user import UserRole
    from app.routers import athlete_race_analysis as router_mod

    monkeypatch.setattr(settings, "ai_enabled", True)
    submit_calls = await _patch_no_ai_io(monkeypatch, router_mod)

    async def _fake_no_consent(athlete_id: int, db) -> bool:
        return False

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_no_consent
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [1, 2], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )

    assert resp.status_code == 451, resp.text
    # El run NUNCA se lanza: ni submit_run ni la fila agent_runs.
    assert submit_calls == []


async def test_start_athlete_run_launches_with_ai_consent(client_factory, monkeypatch):  # noqa: F811
    from app.config import settings
    from app.models.user import UserRole
    from app.routers import athlete_race_analysis as router_mod

    monkeypatch.setattr(settings, "ai_enabled", True)
    submit_calls = await _patch_no_ai_io(monkeypatch, router_mod)

    async def _fake_consent(athlete_id: int, db) -> bool:
        return True

    monkeypatch.setattr(
        router_mod, "athlete_has_ai_processing_consent", _fake_consent
    )

    coach = _make_user(10, UserRole.coach, club_id=1)
    body = {"season": 2026, "valida_nums": [1, 2], "explain_mode": False}
    async with client_factory(user=coach) as ac:
        resp = await ac.post(
            "/api/athletes/144/race-analysis/runs",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )

    assert resp.status_code == 201, resp.text
    assert len(submit_calls) == 1
