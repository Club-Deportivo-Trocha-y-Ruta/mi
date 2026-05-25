"""Fixtures comunes para tests del router ``race_analysis``.

Tras el refactor BE-A1 el router NO usa SQL crudo: invoca el service
ORM ``app.services.race.ai.runs``. Por eso los tests usan SQLAlchemy
real contra SQLite in-memory (StaticPool) en vez del mock ad-hoc por
substrings que existía antes.

Fixture principal: :func:`fake_db` retorna un :class:`FakeRunStore` —
un wrapper sobre ``AsyncSession`` que delega ``execute``/``add``/``flush``
al engine real y además expone helpers ``await seed_run(...)``,
``await seed_event(...)``, ``await seed_insight(...)`` y propiedades
``await load_run(...)`` / ``await load_events(...)`` para asserts.

Compatibilidad: los métodos ``seed_*`` siguen retornando los mismos
dicts que el FakeSession anterior (``{"id": ..., "external_run_id":
...}``), permitiendo migración incremental sin tocar la API de los
tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventType,
    AgentRunStatus,
    AthleteAiInsight,
    Base,
    UserRole,
)
from app.routers.race_analysis import (
    _admin_only,
    _coach_or_admin,
    get_race_chat_agent,
)


# ---------------------------------------------------------------------------
# Fake users
# ---------------------------------------------------------------------------


class _FakeUser:
    """SimpleNamespace con .role/.id (pydantic-safe)."""

    def __init__(self, role: UserRole, user_id: int = 1):
        self.id = user_id
        self.first_name = "Test"
        self.last_name = "User"
        self.email = f"{role.value}@test.local"
        self.role = role
        self.can_login = True
        self.is_active = True
        self.club_memberships = []


def make_user(role: UserRole, user_id: int = 1) -> _FakeUser:
    return _FakeUser(role, user_id)


# ---------------------------------------------------------------------------
# FakeRunStore — AsyncSession wrapper con helpers seed_*
# ---------------------------------------------------------------------------


class FakeRunStore:
    """Wrapper que delega a ``AsyncSession`` real y añade helpers seed_*.

    El object actúa como ``AsyncSession`` desde la perspectiva del
    router (tiene ``execute``, ``add``, ``commit``, ``flush``,
    ``rollback``, ``close``).
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    # -- AsyncSession passthrough ---------------------------------------

    async def execute(self, stmt, *args, **kwargs):
        return await self._session.execute(stmt, *args, **kwargs)

    def add(self, instance, *args, **kwargs):
        self._session.add(instance, *args, **kwargs)

    def add_all(self, instances, *args, **kwargs):
        self._session.add_all(instances, *args, **kwargs)

    async def commit(self):
        await self._session.commit()

    async def rollback(self):
        await self._session.rollback()

    async def flush(self, *args, **kwargs):
        await self._session.flush(*args, **kwargs)

    async def close(self):
        await self._session.close()

    async def refresh(self, instance, *args, **kwargs):
        await self._session.refresh(instance, *args, **kwargs)

    async def delete(self, instance):
        await self._session.delete(instance)

    async def get(self, *args, **kwargs):
        return await self._session.get(*args, **kwargs)

    @property
    def autoflush(self):
        return self._session.autoflush

    # -- Helpers de seed ------------------------------------------------

    async def seed_run(
        self,
        external_run_id: str,
        *,
        status_: str = "running",
        requested_by_user_id: int = 1,
        explain_mode: bool = False,
        final_output_json: Any = None,
        finished_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Inserta una fila ``agent_runs`` y retorna su snapshot."""
        now = started_at or datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        run = AgentRun(
            external_run_id=external_run_id,
            graph_name="race-analyst",
            prompt_version="race_analyst_v1",
            started_at=now,
            finished_at=finished_at,
            status=AgentRunStatus(status_),
            requested_by_user_id=requested_by_user_id,
            checkpoint_thread_id=external_run_id,
            input_json={},
            final_output_json=final_output_json,
            error_message=error_message,
            explain_mode=explain_mode,
            created_at=now,
            updated_at=now,
        )
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return {
            "id": run.id,
            "external_run_id": run.external_run_id,
            "status": run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "requested_by_user_id": run.requested_by_user_id,
            "explain_mode": run.explain_mode,
            "error_message": run.error_message,
            "final_output_json": run.final_output_json,
        }

    async def seed_event(
        self,
        run_db_id: int,
        seq: int,
        event_type: str,
        node_name: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Inserta una fila ``agent_run_events``."""
        et = AgentRunEventType(event_type) if not isinstance(event_type, AgentRunEventType) else event_type
        ev = AgentRunEvent(
            run_id=run_db_id,
            seq=seq,
            event_type=et,
            node_name=node_name,
            payload_json=payload or {},
            created_at=datetime(2026, 5, 20, 12, 0, seq, tzinfo=timezone.utc),
        )
        self._session.add(ev)
        await self._session.flush()

    async def seed_insight(
        self,
        athlete_id: int = 1,
        cost_total: float = 0.001,
        latency_total: int = 1500,
        prompt_version: str = "race_analyst_v1",
        generated_at: Optional[datetime] = None,
    ) -> None:
        """Inserta una fila ``athlete_ai_insights`` con metrics_snapshot_json.

        Solo llena los campos necesarios para los tests de admin metrics
        + budget guard. Los FKs (athlete/user) no se validan en SQLite
        in-memory.
        """
        gen_at = generated_at or datetime.now(timezone.utc)
        ins = AthleteAiInsight(
            athlete_id=athlete_id,
            generated_by_user_id=1,
            season=2026,
            use_case="race_analysis",
            summary_text="test summary",
            recommendations_json=[],
            principles_cited_json=[],
            model="gemini-test",
            prompt_version=prompt_version,
            generated_at=gen_at,
            created_at=gen_at,
            updated_at=gen_at,
            metrics_snapshot_json={
                "aggregate": {
                    "cost_usd_total": cost_total,
                    "latency_ms_total": latency_total,
                }
            },
        )
        self._session.add(ins)
        await self._session.flush()

    # -- Helpers de lectura para asserts --------------------------------

    async def get_run(self, external_run_id: str) -> Optional[AgentRun]:
        result = await self._session.execute(
            select(AgentRun).where(AgentRun.external_run_id == external_run_id)
        )
        return result.scalar_one_or_none()

    async def get_run_dict(self, external_run_id: str) -> Optional[dict[str, Any]]:
        """Snapshot dict del run actual (re-leído del DB)."""
        run = await self.get_run(external_run_id)
        if run is None:
            return None
        return {
            "id": run.id,
            "external_run_id": run.external_run_id,
            "status": run.status.value if isinstance(run.status, AgentRunStatus) else str(run.status),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "requested_by_user_id": run.requested_by_user_id,
            "explain_mode": run.explain_mode,
            "error_message": run.error_message,
            "final_output_json": run.final_output_json,
        }

    async def get_events(self, run_db_id: int) -> list[dict[str, Any]]:
        """Snapshot list de eventos del run (dict-like compat)."""
        result = await self._session.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run_db_id)
            .order_by(AgentRunEvent.seq.asc())
        )
        out: list[dict[str, Any]] = []
        for ev in result.scalars().all():
            et = ev.event_type.value if isinstance(ev.event_type, AgentRunEventType) else str(ev.event_type)
            out.append(
                {
                    "id": ev.id,
                    "seq": ev.seq,
                    "event_type": et,
                    "node_name": ev.node_name,
                    "payload_json": ev.payload_json,
                    "created_at": ev.created_at,
                }
            )
        return out


# ---------------------------------------------------------------------------
# Engine SQLite in-memory compartido
# ---------------------------------------------------------------------------


def _enable_sqlite_bigint_autoincrement(dialect_module):
    """Compila ``BIGINT`` PKs como ``INTEGER`` en SQLite para autoincrement.

    SQLite trata ``INTEGER PRIMARY KEY`` como alias de rowid y autoincrementa;
    ``BIGINT PRIMARY KEY`` NO recibe ese tratamiento y los inserts sin id
    fallan con ``NOT NULL constraint failed``.

    Esto es solo para tests; en MySQL ``BIGINT AUTO_INCREMENT`` ya funciona.
    """
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_to_integer(type_, compiler, **kw):  # noqa: ARG001
        return "INTEGER"


_enable_sqlite_bigint_autoincrement(None)


@pytest_asyncio.fixture
async def engine():
    """Engine SQLite in-memory con StaticPool (compartido entre conexiones).

    Solo crea las tablas necesarias para el router race-analysis. Esto
    evita errores con tipos MySQL-only (LONGTEXT en ``privacy_policies``).
    """
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Filtra tablas que usan tipos MySQL-only no soportados por SQLite.
    _UNSUPPORTED_TABLES = {"privacy_policies"}
    tables_to_create = [
        t
        for t in Base.metadata.tables.values()
        if t.name not in _UNSUPPORTED_TABLES
    ]

    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=tables_to_create, checkfirst=True
            )
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def fake_db(engine):
    """Fake DB store con ``AsyncSession`` real (SQLite)."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = session_factory()
    store = FakeRunStore(session)
    yield store
    await session.close()


# ---------------------------------------------------------------------------
# Fake graph runner
# ---------------------------------------------------------------------------


class FakeGraph:
    """Imita compiled_graph.ainvoke — no hace nada (no LLM)."""

    def __init__(self) -> None:
        self.invocations: list[tuple[Any, dict]] = []

    async def ainvoke(self, value: Any, config: Optional[dict] = None) -> dict:
        import asyncio

        self.invocations.append((value, config or {}))
        await asyncio.sleep(0)  # ceder loop
        return {"ok": True}


@pytest_asyncio.fixture
async def fake_graph() -> FakeGraph:
    return FakeGraph()


# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------


@pytest.fixture
def ai_enabled(monkeypatch):
    """Setea settings.ai_enabled=True para los tests que lo requieran."""
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    return settings


@pytest_asyncio.fixture
async def coach_client(client, fake_db, fake_graph, monkeypatch):
    """Cliente HTTP con auth=coach, DB fake y runner stub."""
    from app.services.race.ai import runner as runner_mod

    async def _graph_factory():
        return fake_graph

    runner_mod.set_graph_factory(_graph_factory)
    await runner_mod._reset_for_tests()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.coach, user_id=10)
    app.dependency_overrides[_coach_or_admin] = lambda: make_user(
        UserRole.coach, user_id=10
    )
    yield client
    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def admin_client(client, fake_db, fake_graph, monkeypatch):
    """Cliente HTTP con auth=admin."""
    from app.services.race.ai import runner as runner_mod

    async def _graph_factory():
        return fake_graph

    runner_mod.set_graph_factory(_graph_factory)
    await runner_mod._reset_for_tests()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.admin, user_id=1)
    app.dependency_overrides[_coach_or_admin] = lambda: make_user(
        UserRole.admin, user_id=1
    )
    app.dependency_overrides[_admin_only] = lambda: make_user(UserRole.admin, user_id=1)
    yield client
    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def parent_client(client, fake_db, monkeypatch):
    """Cliente HTTP con auth=parent (debe ser rechazado en endpoints coach+)."""
    from fastapi import HTTPException

    async def _override_db():
        yield fake_db

    def _forbid():
        raise HTTPException(status_code=403, detail="No tienes permisos para esta acción")

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.parent, user_id=5)
    app.dependency_overrides[_coach_or_admin] = _forbid
    app.dependency_overrides[_admin_only] = _forbid
    yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(client):
    """Cliente sin auth — debe recibir 401/403 desde el bearer scheme."""
    yield client
