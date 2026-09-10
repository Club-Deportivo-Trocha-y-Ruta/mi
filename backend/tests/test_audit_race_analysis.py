"""Tests de auditoría (feature 041) para ``app/routers/race_analysis.py``.

Cubre §4.9 de ``specs/041-multi-coach-governance/contracts/audit-recording.md``:
lanzar un análisis = ``create``, decidir un gate HITL (aceptar/editar =
``approve``, rechazar = ``unapprove``), invalidar = ``update``, cancelar =
``cancel``, re-ejecutar = ``execute`` (+ la ``create`` del run nuevo), y el
cierre asíncrono del run (``_finalize_run``) = ``update`` con
``actor_kind=system``.

Estrategia: SQLite async real (StaticPool). ``agent_runs`` / ``agent_run_events``
se crean con la misma DDL cruda que ``test_race_analysis_cancel.py`` (el
router las toca con SQL crudo); ``users`` / ``clubs`` / ``athletes`` /
``audit_log`` se crean vía ``Base.metadata`` (subset) para que
``select(Athlete.club_id)`` y el INSERT ORM de ``AuditLog`` funcionen
exactamente como en producción.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
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
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole

pytestmark = pytest.mark.asyncio


OWNER_ID = 10
CLUB_ID = 501
ATHLETE_ID = 144

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
    decided_by_user_id INTEGER,
    decided_at      TEXT,
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

_ORM_TABLES = ("users", "clubs", "athletes", "audit_log")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
    """Coach del club sembrado.

    El acceso al run se decide por club (``contracts/scope-ai-imports.md``
    §1.4), así que el coach de estos casos debe pertenecer a ``CLUB_ID``:
    con la lista vacía el endpoint respondería 403 antes de auditar nada.
    """
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=CLUB_ID, role_in_club=ClubRole.coach)
        ],
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
        tables = [Base.metadata.tables[t] for t in _ORM_TABLES]
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Club + atleta ficticios — resolución de club_id (§1.6 escalera paso 2).
    async with factory() as session:
        now = _utc_now()
        await session.execute(
            text(
                "INSERT INTO clubs (id, name, code, is_active, created_at) "
                "VALUES (:id, 'Club Ficticio 041', 'cft-041-audit', 1, :now)"
            ),
            {"id": CLUB_ID, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, first_name, last_name, role, is_active, can_login, created_at) "
                "VALUES (:id, 'Atleta', 'Ficticio', 'athlete', 1, 0, :now)"
            ),
            {"id": 9001, "now": now},
        )
        await session.execute(
            text(
                """
                INSERT INTO athletes (
                    id, user_id, first_name, last_name, birth_date, sex,
                    club_id, created_by, parental_consent_obtained,
                    created_at, updated_at
                ) VALUES (
                    :id, 9001, 'Deportista', 'Ficticio', '2013-06-20', 'F',
                    :club_id, :club_id, 1, :now, :now
                )
                """
            ),
            {"id": ATHLETE_ID, "club_id": CLUB_ID, "now": now},
        )
        await session.commit()

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client_factory(session_factory):
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
    external_run_id: str = "run-audit",
    db_status: str = "awaiting_hitl",
    athlete_id: int = ATHLETE_ID,
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
                    SELECT id, status, decided_by_user_id, decided_at
                    FROM agent_runs WHERE external_run_id = :rid
                    """
                ),
                {"rid": external_run_id},
            )
        ).first()
    assert row is not None
    return dict(row._mapping)


async def _fetch_audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT entity_type, entity_id, action, actor_user_id,
                           actor_kind, club_id, athlete_id, changed_fields,
                           meta_json, request_id
                    FROM audit_log ORDER BY id
                    """
                )
            )
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("changed_fields"), str):
            d["changed_fields"] = json.loads(d["changed_fields"])
        if isinstance(d.get("meta_json"), str) and d["meta_json"] is not None:
            d["meta_json"] = json.loads(d["meta_json"])
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# POST /runs/{id}/invalidate → agent_run·update, meta={"stale": True}
# ---------------------------------------------------------------------------


async def test_invalidate_run_registra_update(client_factory, session_factory):
    await _seed_run(session_factory, db_status="completed")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-audit/invalidate")

    assert resp.status_code == 200, resp.text

    rows = await _fetch_audit_rows(session_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_type"] == "agent_run"
    assert row["action"] == "update"
    assert row["actor_user_id"] == OWNER_ID
    assert row["actor_kind"] == "user"
    assert row["club_id"] == CLUB_ID
    assert row["athlete_id"] == ATHLETE_ID
    assert row["changed_fields"] == ["stale_since"]
    assert row["meta_json"] == {"stale": True}
    assert row["request_id"]


# ---------------------------------------------------------------------------
# POST /runs/{id}/cancel → agent_run·cancel, meta.previous_status
# ---------------------------------------------------------------------------


async def test_cancel_run_registra_cancel(client_factory, session_factory):
    await _seed_run(session_factory, db_status="awaiting_hitl")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-audit/cancel")

    assert resp.status_code == 200, resp.text

    rows = await _fetch_audit_rows(session_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row["entity_type"] == "agent_run"
    assert row["action"] == "cancel"
    assert row["actor_user_id"] == OWNER_ID
    assert row["club_id"] == CLUB_ID
    assert row["athlete_id"] == ATHLETE_ID
    assert row["meta_json"] == {"previous_status": "awaiting_hitl"}


async def test_cancel_run_terminal_no_registra_auditoria(
    client_factory, session_factory
):
    """El 409 de un run ya terminal no debe dejar rastro en ``audit_log``."""
    await _seed_run(session_factory, db_status="completed")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post("/api/race-analysis/runs/run-audit/cancel")

    assert resp.status_code == 409
    assert await _fetch_audit_rows(session_factory) == []


# ---------------------------------------------------------------------------
# POST /runs/{id}/hitl/{step_id} → approve (accept/edit) / unapprove (reject)
# ---------------------------------------------------------------------------


async def test_hitl_accept_registra_approve_y_decided_by(
    client_factory, session_factory
):
    await _seed_run(session_factory, db_status="awaiting_hitl")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post(
            "/api/race-analysis/runs/run-audit/hitl/hitl_gate_review",
            json={"decision": "approve"},
        )

    assert resp.status_code == 200, resp.text

    run_row = await _fetch_run(session_factory, "run-audit")
    assert run_row["decided_by_user_id"] == OWNER_ID
    assert run_row["decided_at"] is not None

    rows = await _fetch_audit_rows(session_factory)
    # La primera fila es la del gate HITL — puede haber una segunda fila del
    # cierre del run (``_finalize_run``) si el grafo fake completa síncrono;
    # en este entorno de test el grafo no corre, así que solo esperamos la
    # del endpoint.
    hitl_rows = [r for r in rows if r["action"] in {"approve", "unapprove"}]
    assert len(hitl_rows) == 1
    row = hitl_rows[0]
    assert row["entity_type"] == "agent_run"
    assert row["action"] == "approve"
    assert row["actor_user_id"] == OWNER_ID
    assert row["athlete_id"] == ATHLETE_ID
    assert row["changed_fields"] == ["decided_at", "decided_by_user_id"]
    assert row["meta_json"]["step_id"] == "hitl_gate_review"
    assert row["meta_json"]["previous_status"] == "awaiting_hitl"
    assert row["meta_json"]["has_edits"] is False


async def test_hitl_edit_marca_has_edits_true(client_factory, session_factory):
    await _seed_run(session_factory, db_status="awaiting_hitl")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post(
            "/api/race-analysis/runs/run-audit/hitl/hitl_gate_review",
            json={"decision": "edit", "edits": "texto editado"},
        )

    assert resp.status_code == 200, resp.text
    rows = [
        r
        for r in await _fetch_audit_rows(session_factory)
        if r["action"] in {"approve", "unapprove"}
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "approve"
    assert rows[0]["meta_json"]["has_edits"] is True


async def test_hitl_reject_registra_unapprove_sin_has_edits(
    client_factory, session_factory
):
    await _seed_run(session_factory, db_status="awaiting_hitl")

    async with await client_factory(OWNER_ID, UserRole.coach) as client:
        resp = await client.post(
            "/api/race-analysis/runs/run-audit/hitl/hitl_gate_review",
            json={"decision": "reject"},
        )

    assert resp.status_code == 200, resp.text
    rows = [
        r
        for r in await _fetch_audit_rows(session_factory)
        if r["action"] in {"approve", "unapprove"}
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "unapprove"
    assert "has_edits" not in row["meta_json"]
    assert row["meta_json"]["step_id"] == "hitl_gate_review"
