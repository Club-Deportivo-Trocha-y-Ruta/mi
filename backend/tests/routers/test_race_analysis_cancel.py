"""Tests de ``POST /api/race-analysis/runs/{run_id}/cancel``.

Contexto: hasta este endpoint NO existía ninguna salida operativa para un
run atascado en ``awaiting_hitl``. La reconciliación de huérfanos sólo
corre al arrancar el proceso (y filtra por ``started_at`` de más de 30
minutos), así que en una instancia viva un run pendiente de revisión no
expiraba nunca y el coach quedaba bloqueado: el guard de
``find_active_run`` rechazaba con 409 cualquier intento de relanzar.

Estrategia: SQLite async real (StaticPool) con las dos tablas que el
endpoint toca vía SQL crudo — ``agent_runs`` y ``agent_run_events`` —
igual que ``test_race_event_runs.py``. Así el test ejercita la query real
y puede afirmar el efecto que de verdad importa: tras cancelar,
``group_launch.find_active_run`` devuelve ``None``.

RBAC (caminos denegados obligatorios):
  - parent → 403 (rol no permitido, vía ``require_role`` real).
  - coach que no es dueño del run → 403.
  - run ya terminal → 409.
  - admin sobre run ajeno → 200.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import UserRole
from app.services.race.group_launch import find_active_run

pytestmark = pytest.mark.asyncio


OWNER_ID = 10

_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    input_json      TEXT,
    final_output_json TEXT,
    error_message   TEXT,
    requested_by_user_id INTEGER,
    athlete_id      INTEGER,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode    INTEGER NOT NULL DEFAULT 0,
    stale_since     TEXT,
    created_at      TEXT,
    updated_at      TEXT
)
"""

_AGENT_RUN_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS agent_run_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL,
    seq          INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    node_name    TEXT,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
)
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.execute(text(_AGENT_RUNS_DDL))
        await conn.execute(text(_AGENT_RUN_EVENTS_DDL))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client_factory(session_factory):
    """Devuelve un AsyncClient autenticado con el rol/id pedidos.

    ``get_db`` se sobreescribe replicando el commit del dependency real
    (``app.dependencies.get_db``) — sin él, el UPDATE del endpoint se
    perdería al cerrar la sesión y el test no vería el cambio.
    """

    async def _make(user_id: int, role: UserRole) -> AsyncClient:
        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _make_user(role, user_id)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    external_run_id: str = "run-hitl",
    db_status: str = "awaiting_hitl",
    athlete_id: int = 144,
    season: int = 2026,
    valida_num: int = 4,
    requested_by: int = OWNER_ID,
) -> None:
    input_json = json.dumps(
        {
            "athlete_id": athlete_id,
            "season": season,
            "valida_nums": [valida_num],
            "explain_mode": False,
        }
    )
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode, athlete_id
                ) VALUES (
                    :rid, 'race-analyst', 'race_analyst_v2', :sa, :st, :inp,
                    :uid, :rid, 0, :aid
                )
                """
            ),
            {
                "rid": external_run_id,
                "sa": _utc_now(),
                "st": db_status,
                "inp": input_json,
                "uid": requested_by,
                "aid": athlete_id,
            },
        )
        await session.commit()


async def _fetch_run(
    session_factory: async_sessionmaker[AsyncSession], external_run_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, error_message, finished_at
                    FROM agent_runs WHERE external_run_id = :rid
                    """
                ),
                {"rid": external_run_id},
            )
        ).first()
    assert row is not None
    return dict(row._mapping)


# ---------------------------------------------------------------------------
# Caminos denegados
# ---------------------------------------------------------------------------


async def test_parent_no_puede_cancelar_403(client_factory, session_factory):
    await _seed_run(session_factory)

    async with await client_factory(77, UserRole.parent) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 403
    # El run sigue vivo: un parent no puede tocarlo.
    assert (await _fetch_run(session_factory, "run-hitl"))["status"] == "awaiting_hitl"


async def test_coach_no_owner_403(client_factory, session_factory):
    await _seed_run(session_factory)

    # coach 99 no es el dueño (owner = 10).
    async with await client_factory(99, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 403
    assert (await _fetch_run(session_factory, "run-hitl"))["status"] == "awaiting_hitl"


async def test_run_inexistente_404(client_factory, session_factory):
    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/no-existe/cancel")

    assert resp.status_code == 404


@pytest.mark.parametrize("terminal", ["completed", "rejected", "failed", "cancelled"])
async def test_run_terminal_409(client_factory, session_factory, terminal):
    await _seed_run(session_factory, db_status=terminal)

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 409
    assert terminal in resp.json()["detail"]
    # Estado intacto — cancelar dos veces no reescribe nada.
    assert (await _fetch_run(session_factory, "run-hitl"))["status"] == terminal


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


async def test_cancela_run_en_awaiting_hitl_y_libera_find_active_run(
    client_factory, session_factory
):
    """El caso P0: run atascado esperando revisión humana."""
    await _seed_run(session_factory)

    # Precondición: el guard de relanzamiento lo ve como activo (409).
    async with session_factory() as session:
        assert await find_active_run(session, 144, 2026, 4) == "run-hitl"

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": "run-hitl", "state": "cancelled"}

    row = await _fetch_run(session_factory, "run-hitl")
    assert row["status"] == "cancelled"
    assert row["error_message"] == "Análisis descartado por el coach."
    assert row["finished_at"] is not None

    # Efecto que desbloquea al coach: ya no hay run activo, el 409 de
    # "ya hay un análisis en curso" desaparece.
    async with session_factory() as session:
        assert await find_active_run(session, 144, 2026, 4) is None


async def test_cancela_run_running(client_factory, session_factory):
    await _seed_run(session_factory, db_status="running")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 200, resp.text
    assert (await _fetch_run(session_factory, "run-hitl"))["status"] == "cancelled"


async def test_admin_puede_cancelar_run_ajeno(client_factory, session_factory):
    await _seed_run(session_factory)

    async with await client_factory(1, UserRole.admin) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")

    assert resp.status_code == 200, resp.text
    assert (await _fetch_run(session_factory, "run-hitl"))["status"] == "cancelled"


async def test_inserta_evento_para_el_polling_del_frontend(
    client_factory, session_factory
):
    """El polling debe ver un evento nuevo (``last_seq`` avanza → no 304)."""
    await _seed_run(session_factory)

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-hitl/cancel")
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT seq, event_type, node_name, payload_json
                    FROM agent_run_events ORDER BY seq
                    """
                )
            )
        ).fetchall()

    assert len(rows) == 1
    seq, event_type, node_name, payload_raw = rows[0]
    assert seq == 1
    assert event_type == "done"
    # Sin nodo: el timeline sólo reduce eventos con nodo, y marcar el gate
    # HITL como completado sería mentirle al coach.
    assert node_name is None
    payload = json.loads(payload_raw)
    assert payload["reason"] == "cancelled_by_coach"
    assert payload["previous_status"] == "awaiting_hitl"
    assert payload["by_user_id"] == OWNER_ID


async def test_status_refleja_cancelled_tras_cancelar(client_factory, session_factory):
    """Integración con el endpoint de polling: `state=cancelled` es terminal
    para el frontend, que corta el polling solo."""
    await _seed_run(session_factory)

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        assert (
            await client.post("/api/race-analysis/runs/run-hitl/cancel")
        ).status_code == 200
        status_resp = await client.get(
            "/api/race-analysis/runs/run-hitl/status", params={"since": 0}
        )

    assert status_resp.status_code == 200, status_resp.text
    body = status_resp.json()
    assert body["state"] == "cancelled"
    assert body["progress_pct"] == 100
    assert body["last_seq"] == 1


async def test_finalize_no_revive_un_run_cancelado(session_factory):
    """Si la task del grafo termina DESPUÉS de que el coach descartó el run,
    ``_finalize_run`` no debe reescribir el estado terminal ``cancelled``."""
    import app.routers.race_analysis as ra

    await _seed_run(session_factory, db_status="cancelled")

    result_state = {
        "rendered_markdown": "# Informe que ya no interesa",
        "events": [
            {"seq": 1, "ts": _utc_now().isoformat(), "type": "node_end",
             "node": "render_outputs", "payload": {}},
        ],
    }

    async with session_factory() as session:
        await ra._finalize_run(session, "run-hitl", None, result_state)
        await session.commit()

    row = await _fetch_run(session_factory, "run-hitl")
    assert row["status"] == "cancelled"

    # Los eventos del grafo sí se drenan (audit trail intacto).
    async with session_factory() as session:
        count = (
            await session.execute(text("SELECT COUNT(*) FROM agent_run_events"))
        ).scalar()
    assert count == 1
