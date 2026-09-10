"""Unit tests for `record_audit` (contracts/audit-recording.md §1, §9 T1).

SQLite in-memory. `record_audit` only queues the row (`db.add`) — it never
flushes or commits, so these tests assert against `session.new` / an explicit
count-after-flush rather than a fresh query.

`request_id` is always passed explicitly here rather than via a ContextVar
scope: `app/services/request_context.py` (ContextVar, middleware) is a
sibling task (T011) and out of `record_audit`'s own contract surface — §1.1
accepts `request_id` as an explicit keyword precisely so callers (and tests)
do not need the HTTP-request machinery.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.base import Base
from app.models.user import User, UserRole
from app.services.audit import (
    META_ALLOWLIST,
    AuditContractError,
    AuditEntityType,
    AuditReasonCode,
    AuditReasonRequired,
    record_audit,
)

RID = "a" * 32


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in ("users", "clubs", "athletes", "audit_log")]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        coach = User(
            id=1,
            email="coach@test.com",
            hashed_password="x",
            first_name="Ana",
            last_name="Ruiz",
            role=UserRole.coach,
        )
        s.add(coach)
        await s.flush()
        yield s
        await s.rollback()


async def _row_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(AuditLog))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_happy_path_queues_without_flush_or_commit(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    row = await record_audit(
        session,
        action=AuditAction.create,
        entity_type=AuditEntityType.athlete,
        entity_id=42,
        actor=coach,
        club_id=7,
        athlete_id=42,
        request_id=RID,
    )
    assert row is not None
    # record_audit only queues the object — it never flushes and never
    # commits itself. `session.new` is checked directly (not via a SELECT,
    # which would trigger SQLAlchemy's autoflush and mask the assertion).
    assert row in session.new
    await session.flush()
    assert await _row_count(session) == 1


@pytest.mark.asyncio
async def test_actor_kind_user_requires_actor(session: AsyncSession) -> None:
    with pytest.raises(AuditContractError):
        await record_audit(
            session,
            action=AuditAction.create,
            entity_type=AuditEntityType.athlete,
            entity_id=1,
            actor=None,
            actor_kind=AuditActorKind.user,
            club_id=7,
            request_id=RID,
        )


@pytest.mark.asyncio
async def test_non_user_actor_kind_forbids_actor(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    with pytest.raises(AuditContractError):
        await record_audit(
            session,
            action=AuditAction.execute,
            entity_type=AuditEntityType.agent_run,
            entity_id=1,
            actor=coach,
            actor_kind=AuditActorKind.cron,
            club_id=7,
            request_id=RID,
        )


@pytest.mark.asyncio
async def test_actor_role_is_a_snapshot(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    row = await record_audit(
        session,
        action=AuditAction.create,
        entity_type=AuditEntityType.athlete,
        entity_id=1,
        actor=coach,
        club_id=7,
        request_id=RID,
    )
    assert row is not None
    assert row.actor_role == UserRole.coach

    coach.role = UserRole.admin
    assert row.actor_role == UserRole.coach


@pytest.mark.asyncio
async def test_unknown_entity_type_raises(session: AsyncSession) -> None:
    with pytest.raises(AuditContractError):
        await record_audit(
            session,
            action=AuditAction.create,
            entity_type="not_a_real_entity",  # type: ignore[arg-type]
            entity_id=1,
            actor=None,
            actor_kind=AuditActorKind.system,
            club_id=7,
            request_id=RID,
        )


@pytest.mark.asyncio
async def test_no_request_id_in_scope_and_none_passed_mints_reserve_id(
    session: AsyncSession,
) -> None:
    # No request_id_scope() active and no explicit request_id passed either.
    # record_audit degrades rather than raising (see its docstring): it
    # mints its own reserve id instead of failing a legitimate write coming
    # from a caller with no bound context (e.g. a direct service call, or a
    # router-level test harness that never registers RequestIdMiddleware).
    row = await record_audit(
        session,
        action=AuditAction.create,
        entity_type=AuditEntityType.athlete,
        entity_id=1,
        actor=None,
        actor_kind=AuditActorKind.system,
        club_id=7,
    )
    assert row is not None
    assert row.request_id is not None
    assert len(row.request_id) == 32


@pytest.mark.asyncio
async def test_explicit_request_id_works(session: AsyncSession) -> None:
    row = await record_audit(
        session,
        action=AuditAction.create,
        entity_type=AuditEntityType.athlete,
        entity_id=1,
        actor=None,
        actor_kind=AuditActorKind.system,
        club_id=7,
        request_id="b" * 32,
    )
    assert row is not None
    assert row.request_id == "b" * 32


@pytest.mark.asyncio
async def test_reason_required_pair_without_reason_code_raises(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    with pytest.raises(AuditReasonRequired):
        await record_audit(
            session,
            action=AuditAction.archive,
            entity_type=AuditEntityType.athlete,
            entity_id=1,
            actor=coach,
            club_id=7,
            athlete_id=1,
            request_id=RID,
        )


@pytest.mark.asyncio
async def test_reason_required_pair_with_reason_code_succeeds(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    row = await record_audit(
        session,
        action=AuditAction.archive,
        entity_type=AuditEntityType.athlete,
        entity_id=1,
        actor=coach,
        club_id=7,
        athlete_id=1,
        reason_code=AuditReasonCode.athlete_left_club,
        request_id=RID,
    )
    assert row is not None
    assert row.reason_code == "athlete_left_club"


@pytest.mark.asyncio
async def test_update_with_empty_changed_fields_and_diff_is_a_noop(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    row = await record_audit(
        session,
        action=AuditAction.update,
        entity_type=AuditEntityType.athlete,
        entity_id=1,
        actor=coach,
        club_id=7,
        request_id=RID,
    )
    assert row is None
    assert len(session.new) == 0


@pytest.mark.asyncio
async def test_non_allowlisted_diff_key_is_dropped_but_named(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    row = await record_audit(
        session,
        action=AuditAction.update,
        entity_type=AuditEntityType.training_session,
        entity_id=1,
        actor=coach,
        club_id=7,
        changed_fields=["status", "location"],
        diff={"status": ("planned", "executed"), "location": ("Pance", "Cerro")},
        request_id=RID,
    )
    assert row is not None
    assert row.changed_fields == ["location", "status"]
    assert row.diff_json is not None
    assert "status" in row.diff_json
    assert "location" not in row.diff_json


@pytest.mark.asyncio
async def test_unknown_meta_key_raises(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    with pytest.raises(AuditContractError):
        await record_audit(
            session,
            action=AuditAction.create,
            entity_type=AuditEntityType.athlete,
            entity_id=1,
            actor=coach,
            club_id=7,
            meta={"note": "should never be allowed"},
            request_id=RID,
        )


@pytest.mark.asyncio
async def test_occurred_at_carries_microseconds(session: AsyncSession) -> None:
    coach = await session.get(User, 1)
    micros_seen = set()
    for i in range(50):
        row = await record_audit(
            session,
            action=AuditAction.create,
            entity_type=AuditEntityType.athlete,
            entity_id=1000 + i,
            actor=coach,
            club_id=7,
            request_id=RID,
        )
        assert row is not None
        micros_seen.add(row.occurred_at.microsecond)
    # At least one of 50 constructions must carry non-zero microseconds —
    # a truncated implementation would produce all-zero values.
    assert any(m != 0 for m in micros_seen)


def test_meta_allowlist_drift_guard() -> None:
    """Every meta_json key literal referenced by the nine feature contracts
    must be a subset of META_ALLOWLIST (§9 T1.12).
    """
    import re as _re
    from pathlib import Path

    contracts_dir = (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "041-multi-coach-governance"
        / "contracts"
    )
    assert contracts_dir.is_dir(), f"contracts dir not found: {contracts_dir}"

    key_pattern = _re.compile(r"meta(?:_json)?[.\[]{1,2}[\"']?([a-z_]+)[\"']?")
    inline_pattern = _re.compile(r"meta(?:_json)?\s*=\s*\{([^}]*)\}")
    dict_key_pattern = _re.compile(r"[\"'`]([a-z_]+)[\"'`]\s*:")

    found: dict[str, set[str]] = {}
    for path in sorted(contracts_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        keys: set[str] = set()
        for m in key_pattern.finditer(text):
            keys.add(m.group(1))
        for block in inline_pattern.finditer(text):
            for m in dict_key_pattern.finditer(block.group(1)):
                keys.add(m.group(1))
        # Drop obvious non-keys the loose regex may pick up.
        keys -= {"json"}
        if keys:
            found[path.name] = keys

    offending: list[str] = []
    for fname, keys in found.items():
        for key in keys:
            if key not in META_ALLOWLIST:
                offending.append(f"{key!r} in {fname}")

    assert not offending, (
        "meta_json keys referenced by contracts but missing from META_ALLOWLIST: "
        + ", ".join(sorted(offending))
    )
