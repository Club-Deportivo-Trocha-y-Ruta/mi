"""Tests de los endpoints PR5: invalidate + re-execute de runs IA.

Cubre RBAC + 404 + happy path de invalidate. Aislamos la capa de datos
monkeypatcheando ``_load_run`` (raw SQL sobre columnas no mapeadas en el ORM)
y ``mark_run_stale`` — mismo enfoque de aislamiento que el resto de tests del
router race-analysis (que usan fake_db en vez de SQLite real).
"""
from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.routers.race_analysis as ra
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import UserRole


class _FakeSession:
    """Sesión mínima — los endpoints PR5 no la usan directamente (todo va por
    helpers monkeypatcheados)."""

    async def execute(self, *a, **k):  # pragma: no cover - no debería llamarse
        raise AssertionError("execute no debería llamarse en estos tests")


def _user(user_id: int, role: UserRole):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=user_id, role=role, email=f"u{user_id}@test.com",
        is_active=True, can_login=True, club_memberships=[],
    )


@pytest_asyncio.fixture
async def client_factory():
    async def _make(user_id: int, role: UserRole):
        async def _override_db() -> AsyncGenerator[Any, None]:
            yield _FakeSession()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _user(user_id, role)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


# Run de referencia: owner = user 10.
_RUN_ROW = {
    "id": 1,
    "external_run_id": "run-abc",
    "status": "completed",
    "started_at": None,
    "finished_at": None,
    "input_json": {"athlete_id": 144, "season": 2026, "valida_nums": [4]},
    "final_output_json": None,
    "error_message": None,
    "requested_by_user_id": 10,
    "explain_mode": 0,
}


@pytest.mark.asyncio
async def test_invalidate_marca_stale(client_factory, monkeypatch):
    marked: dict[str, int] = {}

    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW) if rid == "run-abc" else None

    async def _fake_mark_stale(db, run_db_id):
        marked["id"] = run_db_id
        return True

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)
    monkeypatch.setattr(ra, "mark_run_stale", _fake_mark_stale)

    async with await client_factory(10, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/invalidate")
    assert r.status_code == 200, r.text
    assert r.json() == {"run_id": "run-abc", "stale": True}
    assert marked["id"] == 1


@pytest.mark.asyncio
async def test_invalidate_run_inexistente_404(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return None

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    async with await client_factory(10, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/nope/invalidate")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_invalidate_run_ajeno_403(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    # coach 99 no es owner (owner = 10)
    async with await client_factory(99, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/invalidate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_puede_invalidar_run_ajeno(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    async def _fake_mark_stale(db, run_db_id):
        return True

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)
    monkeypatch.setattr(ra, "mark_run_stale", _fake_mark_stale)

    async with await client_factory(1, UserRole.admin) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/invalidate")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reexecute_run_inexistente_404(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return None

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    async with await client_factory(10, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/nope/re-execute")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reexecute_run_ajeno_403(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    async with await client_factory(99, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/re-execute")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reexecute_happy_path_delega_a_start_run(client_factory, monkeypatch):
    """re-execute reconstruye StartRunRequest desde input_json y delega."""
    captured: dict[str, Any] = {}

    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    async def _fake_start_run(*, body, db, current_user):
        captured["athlete_id"] = body.athlete_id
        captured["season"] = body.season
        captured["valida_nums"] = body.valida_nums
        from app.schemas.race_ai import StartRunResponse, RunState
        from datetime import datetime, timezone

        return StartRunResponse(
            run_id="new-run",
            status=RunState.RUNNING,
            started_at=datetime.now(timezone.utc),
            status_url="/api/race-analysis/runs/new-run/status",
            estimated_seconds=20,
        )

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)
    monkeypatch.setattr(ra, "start_run", _fake_start_run)

    async with await client_factory(10, UserRole.coach) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/re-execute")
    assert r.status_code == 200, r.text
    assert r.json()["run_id"] == "new-run"
    assert captured == {"athlete_id": 144, "season": 2026, "valida_nums": [4]}
