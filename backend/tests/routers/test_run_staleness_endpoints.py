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


#: Club del atleta del run de referencia. El arnés no tiene tabla
#: ``athletes``, así que ``_FakeResult`` responde este valor por el atleta y
#: con eso ``run_club_ids`` resuelve en el paso 3 de
#: ``contracts/scope-ai-imports.md`` §1.1 — nunca por el respaldo de autoría.
RUN_CLUB_ID = 1


class _FakeResult:
    """Resultado mínimo para los SELECT que este arnés atraviesa.

    ``scalar_one_or_none`` cubre ``_resolve_athlete_club`` y el paso 3 de la
    resolución de club: devuelve ``RUN_CLUB_ID``, de modo que el run tiene
    club resoluble y el 403 de un coach ajeno prueba la regla de club (§1.4)
    y no una lista de membresías vacía. ``scalars().all()`` cubre el paso 4
    (``club_members`` del solicitante), que con el paso 3 resuelto ya no se
    consulta.
    """

    def scalar_one_or_none(self):
        return RUN_CLUB_ID

    def scalars(self):
        return self

    def all(self):
        return []


class _FakeSession:
    """Sesión mínima — los endpoints PR5 no usan la sesión para el flujo de
    negocio propiamente dicho (todo va por helpers monkeypatcheados), pero
    ``record_audit``/``_resolve_athlete_club``/``run_club_ids`` (feature 041)
    sí la tocan directamente: ``execute`` responde el SELECT de club_id y
    ``add`` encola la fila de auditoría sin persistirla — ninguna prueba de
    este archivo verifica el contenido de ``audit_log``."""

    async def execute(self, *a, **k):
        return _FakeResult()

    def add(self, *a, **k):
        return None


def _user(user_id: int, role: UserRole, club_ids: tuple[int, ...] = (RUN_CLUB_ID,)):
    """Usuario falso con membresías de coach explícitas.

    El alcance de un run es el club, no la autoría (§1.4), así que el arnés
    tiene que poder decir en qué club está cada coach.
    """
    from types import SimpleNamespace

    from app.models.club import ClubRole

    return SimpleNamespace(
        id=user_id, role=role, email=f"u{user_id}@test.com",
        is_active=True, can_login=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach)
            for cid in club_ids
        ],
    )


@pytest_asyncio.fixture
async def client_factory():
    async def _make(
        user_id: int, role: UserRole, club_ids: tuple[int, ...] = (RUN_CLUB_ID,)
    ):
        async def _override_db() -> AsyncGenerator[Any, None]:
            yield _FakeSession()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _user(
            user_id, role, club_ids
        )
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
async def test_invalidate_run_de_otro_club_403(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    # El coach 99 es coach del club 2; el run es del club 1 (§1.4).
    async with await client_factory(99, UserRole.coach, (2,)) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/invalidate")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invalidate_run_mismo_club_otro_coach_200(client_factory, monkeypatch):
    """Espejo de §1.4: cualquier coach del club opera el run, no sólo su autor."""
    marked: dict[str, int] = {}

    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    async def _fake_mark_stale(db, run_db_id):
        marked["id"] = run_db_id
        return True

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)
    monkeypatch.setattr(ra, "mark_run_stale", _fake_mark_stale)

    # El coach 99 comparte club con el run (club 1); el autor es el 10.
    async with await client_factory(99, UserRole.coach, (RUN_CLUB_ID,)) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/invalidate")
    assert r.status_code == 200, r.text
    assert marked["id"] == 1


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
async def test_reexecute_run_de_otro_club_403(client_factory, monkeypatch):
    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)

    async with await client_factory(99, UserRole.coach, (2,)) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/re-execute")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reexecute_run_mismo_club_otro_coach_200(client_factory, monkeypatch):
    """Espejo de §1.4 para re-ejecutar: basta con ser coach del club."""

    async def _fake_load_run(db, rid):
        return dict(_RUN_ROW)

    async def _fake_start_run(*, body, db, current_user):
        from datetime import datetime, timezone

        from app.schemas.race_ai import RunState, StartRunResponse

        return StartRunResponse(
            run_id="new-run",
            status=RunState.RUNNING,
            started_at=datetime.now(timezone.utc),
            status_url="/api/race-analysis/runs/new-run/status",
            estimated_seconds=20,
        )

    monkeypatch.setattr(ra, "_load_run", _fake_load_run)
    monkeypatch.setattr(ra, "start_run", _fake_start_run)

    async with await client_factory(99, UserRole.coach, (RUN_CLUB_ID,)) as client:
        r = await client.post("/api/race-analysis/runs/run-abc/re-execute")
    assert r.status_code == 200, r.text
    assert r.json()["run_id"] == "new-run"


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
