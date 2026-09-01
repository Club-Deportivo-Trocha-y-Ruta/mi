"""Tests para ``app.services.race.ai.run_reconciliation`` (specs/036, T016/T018).

Cobertura exigida por T018 (mitad backend):
- Un run huérfano (``running`` o ``awaiting_hitl``) más viejo que el umbral
  se reconcilia: pasa a ``failed`` con un ``error_message`` explicativo en
  español y queda con ``finished_at`` poblado.
- Un run reciente (dentro del umbral) NO se toca, sin importar su estado.
- Runs en estado terminal (``completed``/``rejected``/``failed``/``cancelled``)
  NUNCA se tocan, aunque sean viejos — ni su status ni su ``error_message``
  original cambian.
- Un fallo de DB durante la reconciliación no se propaga: ni la función de
  servicio ni la integración real en ``main.py::lifespan`` deben lanzar.

Convención de fixtures: se usa una tabla ``agent_runs`` mínima creada por
SQL crudo (no ``Base.metadata``) porque el modelo ORM
``app.models.agent_run.AgentRun`` sólo mapea un subconjunto de columnas y
deliberadamente NO incluye ``error_message`` (ver docstring de ese módulo);
crear la tabla desde ``Base.metadata`` la dejaría sin esa columna, que es
exactamente la que este servicio necesita escribir.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.agent_run import AgentRunStatus
from app.services.race.ai.db import set_db_factory
from app.services.race.ai.run_reconciliation import (
    ORPHAN_AWAITING_HITL_ERROR_MESSAGE,
    ORPHAN_RUNNING_ERROR_MESSAGE,
    reconcile_orphan_runs,
)

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
_THRESHOLD_MINUTES = 30

_CREATE_TABLE_SQL = text(
    """
    CREATE TABLE agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_run_id VARCHAR(64) NOT NULL,
        graph_name VARCHAR(64) NOT NULL DEFAULT 'race-analyst',
        prompt_version VARCHAR(32) NOT NULL DEFAULT 'race_analyst_v2',
        started_at DATETIME NOT NULL,
        finished_at DATETIME,
        status VARCHAR(32) NOT NULL,
        error_message TEXT,
        requested_by_user_id INTEGER NOT NULL DEFAULT 1,
        checkpoint_thread_id VARCHAR(64) NOT NULL DEFAULT 'thread',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.execute(_CREATE_TABLE_SQL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _reset_db_factory():
    """Evita fugas de estado global entre tests — mismo patrón que
    ``tests/services/race/ai/conftest.py::configure_db_factory``."""
    yield
    set_db_factory(None)


async def _seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    external_run_id: str,
    status: str,
    started_at: datetime,
    error_message: str | None = None,
) -> None:
    async with session_factory() as s:
        await s.execute(
            text(
                """
                INSERT INTO agent_runs
                    (external_run_id, status, started_at, error_message)
                VALUES (:rid, :status, :started_at, :em)
                """
            ),
            {
                "rid": external_run_id,
                "status": status,
                "started_at": started_at,
                "em": error_message,
            },
        )
        await s.commit()


async def _fetch_run(
    session_factory: async_sessionmaker[AsyncSession], external_run_id: str
) -> dict:
    async with session_factory() as s:
        result = await s.execute(
            text(
                "SELECT status, error_message, finished_at FROM agent_runs "
                "WHERE external_run_id = :rid"
            ),
            {"rid": external_run_id},
        )
        row = result.first()
        assert row is not None, f"run {external_run_id} no existe"
        return dict(row._mapping)


# ---------------------------------------------------------------------------
# Runs huérfanos viejos → reconciliados
# ---------------------------------------------------------------------------


async def test_old_running_run_is_marked_failed(session_factory):
    old_started = _NOW - timedelta(minutes=60)
    await _seed_run(
        session_factory,
        external_run_id="run-old-running",
        status=AgentRunStatus.running.value,
        started_at=old_started,
    )
    set_db_factory(lambda: session_factory())

    count = await reconcile_orphan_runs(
        threshold_minutes=_THRESHOLD_MINUTES, now=_NOW
    )

    assert count == 1
    row = await _fetch_run(session_factory, "run-old-running")
    assert row["status"] == "failed"
    assert row["error_message"] == ORPHAN_RUNNING_ERROR_MESSAGE
    assert row["finished_at"] is not None


async def test_old_awaiting_hitl_run_is_marked_failed_with_honest_message(
    session_factory,
):
    """R2: el checkpoint de LangGraph no sobrevive un redeploy en Render free
    tier — el mensaje para ``awaiting_hitl`` debe ser honesto sobre eso, y
    distinto del genérico usado para ``running``."""
    old_started = _NOW - timedelta(minutes=45)
    await _seed_run(
        session_factory,
        external_run_id="run-old-hitl",
        status=AgentRunStatus.awaiting_hitl.value,
        started_at=old_started,
    )
    set_db_factory(lambda: session_factory())

    count = await reconcile_orphan_runs(
        threshold_minutes=_THRESHOLD_MINUTES, now=_NOW
    )

    assert count == 1
    row = await _fetch_run(session_factory, "run-old-hitl")
    assert row["status"] == "failed"
    assert row["error_message"] == ORPHAN_AWAITING_HITL_ERROR_MESSAGE
    assert row["error_message"] != ORPHAN_RUNNING_ERROR_MESSAGE
    assert row["finished_at"] is not None


# ---------------------------------------------------------------------------
# Runs recientes → nunca tocados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [AgentRunStatus.running.value, AgentRunStatus.awaiting_hitl.value]
)
async def test_fresh_run_is_not_touched(session_factory, status):
    fresh_started = _NOW - timedelta(minutes=5)
    await _seed_run(
        session_factory,
        external_run_id="run-fresh",
        status=status,
        started_at=fresh_started,
    )
    set_db_factory(lambda: session_factory())

    count = await reconcile_orphan_runs(
        threshold_minutes=_THRESHOLD_MINUTES, now=_NOW
    )

    assert count == 0
    row = await _fetch_run(session_factory, "run-fresh")
    assert row["status"] == status
    assert row["error_message"] is None
    assert row["finished_at"] is None


# ---------------------------------------------------------------------------
# Runs en estado terminal → nunca tocados, sin importar la edad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        AgentRunStatus.completed.value,
        AgentRunStatus.rejected.value,
        AgentRunStatus.failed.value,
        AgentRunStatus.cancelled.value,
    ],
)
async def test_old_terminal_status_run_is_untouched(session_factory, status):
    ancient_started = _NOW - timedelta(days=30)
    original_message = "mensaje original, no debe cambiar"
    await _seed_run(
        session_factory,
        external_run_id="run-terminal",
        status=status,
        started_at=ancient_started,
        error_message=original_message,
    )
    set_db_factory(lambda: session_factory())

    count = await reconcile_orphan_runs(
        threshold_minutes=_THRESHOLD_MINUTES, now=_NOW
    )

    assert count == 0
    row = await _fetch_run(session_factory, "run-terminal")
    assert row["status"] == status
    assert row["error_message"] == original_message


# ---------------------------------------------------------------------------
# Umbral configurable + mezcla de filas
# ---------------------------------------------------------------------------


async def test_only_rows_older_than_configured_threshold_are_reconciled(
    session_factory,
):
    """El umbral es el parámetro, no un valor fijo — con uno más chico,
    una fila que antes se consideraba "fresca" también se reconcilia."""
    started = _NOW - timedelta(minutes=10)
    await _seed_run(
        session_factory,
        external_run_id="run-10min",
        status=AgentRunStatus.running.value,
        started_at=started,
    )
    set_db_factory(lambda: session_factory())

    count_with_generous_threshold = await reconcile_orphan_runs(
        threshold_minutes=30, now=_NOW
    )
    assert count_with_generous_threshold == 0

    count_with_tight_threshold = await reconcile_orphan_runs(
        threshold_minutes=5, now=_NOW
    )
    assert count_with_tight_threshold == 1


async def test_default_threshold_comes_from_settings(session_factory, monkeypatch):
    """Sin ``threshold_minutes`` explícito, usa
    ``settings.race_ai_orphan_run_threshold_minutes``."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_orphan_run_threshold_minutes", 5)
    started = _NOW - timedelta(minutes=10)
    await _seed_run(
        session_factory,
        external_run_id="run-default-threshold",
        status=AgentRunStatus.running.value,
        started_at=started,
    )
    set_db_factory(lambda: session_factory())

    count = await reconcile_orphan_runs(now=_NOW)

    assert count == 1


# ---------------------------------------------------------------------------
# Fallo de DB → nunca se propaga (arranque no debe romperse)
# ---------------------------------------------------------------------------


class _RaisingSession:
    """Sesión async mínima cuyo ``execute`` siempre falla — simula una DB
    caída o inalcanzable en el momento del arranque."""

    async def execute(self, *args, **kwargs):
        raise ConnectionRefusedError("mysql no disponible durante el arranque")

    async def commit(self) -> None:  # pragma: no cover - no debería llegar
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass


async def test_db_error_during_reconciliation_does_not_raise():
    set_db_factory(lambda: _RaisingSession())

    count = await reconcile_orphan_runs(threshold_minutes=_THRESHOLD_MINUTES, now=_NOW)

    assert count == 0


async def test_missing_db_factory_does_not_raise():
    """``get_session()`` lanza ``RuntimeError`` si nadie llamó
    ``set_db_factory`` — tampoco debe escapar (arranque en frío sin boot
    completo, o test que olvidó configurar el factory)."""
    set_db_factory(None)

    count = await reconcile_orphan_runs(threshold_minutes=_THRESHOLD_MINUTES, now=_NOW)

    assert count == 0


async def test_lifespan_survives_reconciliation_failure(monkeypatch):
    """Integración real con ``main.py::lifespan`` (T016): incluso si
    ``reconcile_orphan_runs`` se rompiera por completo (bug futuro que
    burle su propio try/except), la doble protección en el lifespan
    tampoco debe tumbar el arranque de la app."""
    import app.services.race.ai.run_reconciliation as run_reconciliation_module
    from app.main import app as fastapi_app
    from app.main import lifespan

    async def _boom(*args, **kwargs):
        raise RuntimeError("bug hipotético que burla el try/except interno")

    monkeypatch.setattr(run_reconciliation_module, "reconcile_orphan_runs", _boom)

    async with lifespan(fastapi_app):
        pass
