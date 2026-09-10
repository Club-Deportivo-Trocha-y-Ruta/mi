"""Unit tests for the AUDIT_STRICT flush detector (T017).

``contracts/audit-recording.md`` §7 / `plan.md` Complexity Tracking: a
session-level `after_flush` listener, active only under
`APP_ENV=test` + `AUDIT_STRICT=true`, that fails a test when an auditable
table was mutated in a flush whose unit of work queued no matching
``AuditLog`` row. It is a DETECTOR, not the recording mechanism, and it must
be OFF by default so it never touches the rest of the suite while nothing
has been instrumented yet (§4/§7 wave 1, `AUDITED_ROUTES` is all-`Exempt`).

SQLite in-memory, `StaticPool`, no HTTP layer — the listener is registered
globally on `sqlalchemy.orm.Session` by importing `app.services.audit`, so a
plain `AsyncSession` flush is enough to exercise it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.base import Base
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User, UserRole
from app.services.audit import AuditEntityType, AuditStrictViolation
from app.services.request_context import new_request_id, request_id_scope

_TABLES = ["users", "audit_log", "password_reset_tokens"]


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    sqlite_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _make_user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        first_name="Coach",
        last_name="Uno",
        email=f"coach{user_id}@test.local",
        hashed_password="x",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
    )


def _make_audit_row(*, request_id: str, entity_id: int = 1) -> AuditLog:
    return AuditLog(
        actor_user_id=None,
        actor_kind=AuditActorKind.system,
        actor_role=None,
        club_id=None,
        athlete_id=None,
        entity_type=AuditEntityType.user.value,
        entity_id=entity_id,
        action=AuditAction.update,
        changed_fields=["role"],
        diff_json=None,
        reason_code=None,
        request_id=request_id,
        meta_json=None,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts from the detector OFF; each test opts in explicitly."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("AUDIT_STRICT", raising=False)


def _enable_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUDIT_STRICT", "true")


@pytest.mark.asyncio
async def test_off_by_default_even_under_app_env_test(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV=test alone (no AUDIT_STRICT=true) must not activate the
    detector — this is what keeps the rest of the offline suite green while
    routes are still unaudited.
    """
    monkeypatch.setenv("APP_ENV", "test")
    async with session_factory() as session:
        session.add(_make_user())
        await session.flush()  # must not raise


@pytest.mark.asyncio
async def test_off_when_audit_strict_false(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUDIT_STRICT", "false")
    async with session_factory() as session:
        session.add(_make_user())
        await session.flush()  # must not raise


@pytest.mark.asyncio
async def test_raises_when_audited_table_mutated_without_audit_row(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_strict(monkeypatch)
    async with session_factory() as session:
        session.add(_make_user())
        with pytest.raises(AuditStrictViolation):
            await session.flush()


@pytest.mark.asyncio
async def test_passes_when_matching_audit_log_row_queued_same_flush(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_strict(monkeypatch)
    async with session_factory() as session:
        with request_id_scope() as request_id:
            session.add(_make_user())
            session.add(_make_audit_row(request_id=request_id))
            await session.flush()  # must not raise


@pytest.mark.asyncio
async def test_raises_when_audit_log_row_has_a_different_request_id(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_strict(monkeypatch)
    async with session_factory() as session:
        with request_id_scope():
            session.add(_make_user())
            session.add(_make_audit_row(request_id=new_request_id()))
            with pytest.raises(AuditStrictViolation):
                await session.flush()


@pytest.mark.asyncio
async def test_passes_when_no_request_id_bound_and_any_audit_row_queued(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-HTTP callers outside any `request_id_scope()` still get credit
    for queuing *some* AuditLog row in the same flush.
    """
    _enable_strict(monkeypatch)
    async with session_factory() as session:
        session.add(_make_user())
        session.add(_make_audit_row(request_id=new_request_id()))
        await session.flush()  # must not raise


@pytest.mark.asyncio
async def test_non_audited_table_is_not_checked(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`password_reset_tokens` is not in `_AUDIT_STRICT_TABLES` (its own
    write is exempt, §4.1) — mutating it alone must not trip the detector.
    """
    async with session_factory() as session:
        session.add(_make_user())
        await session.flush()  # detector still off — sets up the FK target

        _enable_strict(monkeypatch)
        session.add(
            PasswordResetToken(
                user_id=1,
                token_hash="x" * 64,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.flush()  # must not raise — table not in _AUDIT_STRICT_TABLES


@pytest.mark.asyncio
async def test_audit_log_row_alone_does_not_self_trigger(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`audit_log` is deliberately excluded from `_AUDIT_STRICT_TABLES` —
    queuing an AuditLog row must never itself require a second AuditLog row.
    """
    async with session_factory() as session:
        session.add(_make_user())
        await session.flush()  # detector still off — sets up the FK target

        _enable_strict(monkeypatch)
        with request_id_scope() as request_id:
            session.add(_make_audit_row(request_id=request_id, entity_id=1))
            await session.flush()  # must not raise
