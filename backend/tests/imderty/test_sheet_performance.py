"""T053 (specs/047-imderty-attendance-sheet/tasks.md, Phase 7 — Polish):
``backend/tests/imderty/test_sheet_performance.py``.

Two independent concerns for ``POST /api/clubs/{club_id}/imderty-sheet``:

- **Query count (no N+1)**: the number of SQL ``SELECT`` statements the
  route issues for a one-month sheet must not grow with the athlete count.
  ``attendance_grid.py::active_athletes_in_range`` and
  ``rows.py::load_authorized_sensitive_data`` both batch-load with
  ``selectinload``/``IN`` clauses instead of looping per athlete, so a
  40-athlete club and a 5-athlete club must issue the exact same query
  count for the same month range — a real N+1 would make the 40-athlete
  count grow.
- **Timing (SC-007)**: a 40-athlete month builds in under 10 s and a
  5-month range (same 40 athletes) in under 30 s, on aiosqlite in-memory —
  a generous ceiling for a real regression, not a tight benchmark.

Self-contained engine per scenario (own ``asyncio.run``-free async helper,
not the shared ``imderty_scenario`` fixture): each scenario needs a
different, larger athlete count than the shared conftest fixtures seed, and
two scenarios must never share a DB so the query count of one cannot be
inflated by the other's rows. Reuses ``conftest.py``'s
``seed_imderty_scenario`` (club, admin, coach) instead of duplicating it,
then adds N synthetic, unnamed athletes on top.

Every name here is fictitious (CLAUDE.md, Ley 1581); IDs are namespaced away
from every other 047 test module (base 479000) so nothing collides if
engines were ever shared.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import date
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.user import User, UserRole
from tests.fixtures.race_history_fixtures import create_athlete, create_user
from tests.helpers.query_counting import count_selects
from tests.imderty.conftest import ADMIN_USER_ID, CLUB_ID, seed_imderty_scenario

_ATHLETE_ID_BASE = 479000
_USER_ID_BASE = 579000

_SHEET_URL = f"/api/clubs/{CLUB_ID}/imderty-sheet"
_ONE_MONTH_BODY = {"from": "2026-08", "to": "2026-08"}
_FIVE_MONTH_BODY = {"from": "2026-01", "to": "2026-05"}


async def _add_synthetic_athletes(
    session: AsyncSession, *, count: int, created_by: int
) -> None:
    """N unnamed athletes on the scenario's base club, each with its own
    login-less user account (``Athlete.user_id`` is a unique FK)."""
    for i in range(count):
        athlete_id = _ATHLETE_ID_BASE + i
        user_id = _USER_ID_BASE + i
        await create_user(
            session,
            user_id=user_id,
            role=UserRole.athlete,
            first_name="Deportista Ficticio",
            last_name=f"Prueba {i:03d}",
            can_login=False,
        )
        await create_athlete(
            session,
            athlete_id=athlete_id,
            first_name="Deportista Ficticio",
            last_name=f"Prueba {i:03d}",
            birth_date=date(2014, 5, 2),
            club_id=CLUB_ID,
            user_id=user_id,
            created_by=created_by,
        )
    await session.commit()


@asynccontextmanager
async def _sheet_scenario(
    athlete_count: int,
) -> AsyncGenerator[tuple[AsyncEngine, AsyncClient], None]:
    """A full-schema, self-contained engine seeded with the base 047
    scenario (club/admin/coach) plus ``athlete_count`` synthetic athletes,
    and an ``AsyncClient`` authenticated as the admin, wired the same way
    ``conftest.py::imderty_client_factory`` does."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        scenario = await seed_imderty_scenario(session)
        await _add_synthetic_athletes(
            session, count=athlete_count, created_by=scenario.coach_user_id
        )

    async with factory() as load_session:
        result = await load_session.execute(
            select(User)
            .options(selectinload(User.club_memberships))
            .where(User.id == ADMIN_USER_ID)
        )
        admin = result.scalar_one()

    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield engine, client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Query count — independent of athlete count (no N+1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_month_query_count_independent_of_athlete_count() -> None:
    async with _sheet_scenario(5) as (small_engine, small_client):
        async with count_selects(small_engine) as small_counter:
            response = await small_client.post(_SHEET_URL, json=_ONE_MONTH_BODY)
        assert response.status_code == 200

    async with _sheet_scenario(40) as (large_engine, large_client):
        async with count_selects(large_engine) as large_counter:
            response = await large_client.post(_SHEET_URL, json=_ONE_MONTH_BODY)
        assert response.status_code == 200

    # active_athletes_in_range (attendance_grid.py) and
    # load_authorized_sensitive_data (rows.py) both batch with
    # selectinload()/IN(...) — one fixed set of SELECTs regardless of how
    # many athlete rows they return. A real N+1 (one query per athlete)
    # would make the 40-athlete count 8x the 5-athlete count instead of
    # equal.
    assert large_counter[0] == small_counter[0]
    assert small_counter[0] > 0


# ---------------------------------------------------------------------------
# Timing — SC-007
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
async def test_forty_athletes_one_month_builds_under_ten_seconds() -> None:
    async with _sheet_scenario(40) as (engine, client):
        start = time.perf_counter()
        response = await client.post(_SHEET_URL, json=_ONE_MONTH_BODY)
        elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 10.0, (
        f"Building the 40-athlete August 2026 sheet took {elapsed:.2f}s, "
        "over the 10s SC-007 budget"
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_forty_athletes_five_months_builds_under_thirty_seconds() -> None:
    async with _sheet_scenario(40) as (engine, client):
        start = time.perf_counter()
        response = await client.post(_SHEET_URL, json=_FIVE_MONTH_BODY)
        elapsed = time.perf_counter() - start

    assert response.status_code == 200
    assert elapsed < 30.0, (
        f"Building the 40-athlete, 5-month (2026-01..2026-05) sheet took "
        f"{elapsed:.2f}s, over the 30s SC-007 budget"
    )
