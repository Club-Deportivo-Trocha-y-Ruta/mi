"""Integration test harness for Structured Interval Training (feature 026, T009).

Mirrors ``backend/tests/strength/conftest.py`` (feature 021) exactly in shape:
a real aiosqlite DB (in-memory) with ``Base.metadata.create_all`` limited to
the tables these tests need, and an ``AsyncClient`` factory that overrides
``get_db`` and ``get_current_user`` so router tests exercise real SQL without
MySQL or a live JWT server.

Identity fixtures follow the same convention already established across every
other feature test suite in this repo (technique, strength, race-analysis,
etc.): the authenticated identity is injected via a
``get_current_user`` dependency override rather than by minting and decoding
a real JWT.

Tables included (targeted subset — avoids MySQL-dialect columns not needed by
this suite, e.g. ``strava_connections.access_token_enc``):

  Core identity / auth
    users
    clubs
    club_members

  Training calendar (IntervalStructure FK chain: structure -> training_session)
    calendar_events   (FK from training_sessions.calendar_event_id, nullable)
    event_audiences
    training_sessions

  Interval training tables (feature 026, US1/US4)
    interval_structures
    interval_structure_blocks
    interval_templates
    interval_template_blocks

Fixtures exposed (all ``pytest_asyncio.fixture`` unless noted):
  engine               — async in-memory aiosqlite engine
  session_factory      — async_sessionmaker[AsyncSession]
  session              — open AsyncSession (auto-committed on close)
  coach_user_obj       — unsaved User(role=coach) helper (plain function)
  admin_user_obj       — unsaved User(role=admin) helper (plain function)
  parent_user_obj      — unsaved User(role=parent) helper (plain function)

  seed_club            — async helper: insert Club(id=1) + flush
  seed_coach           — async helper: insert coach User(id=10) + ClubMember
  seed_admin           — async helper: insert admin User(id=20)
  seed_parent          — async helper: insert parent User(id=30)
  seed_training_session — async helper: insert a bare TrainingSession + commit

  make_client          — sync factory returning AsyncClient context-manager;
                         accepts ``user`` kwarg to control the authenticated
                         identity; defaults to the coach user.

  _clear_overrides     — autouse fixture that clears app.dependency_overrides
                         after every test (prevents inter-test bleed).

Seed data uses fictitious names ("Entrenador Ficticio") and dates — never
real TyR athlete data (non-negotiable constraint, CLAUDE.md §Privacy).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import Club, ClubMember, ClubRole
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Tables included in the aiosqlite create_all subset
# ---------------------------------------------------------------------------

_TABLES = (
    # Core identity
    "users",
    "clubs",
    "club_members",
    # Training calendar (required by TrainingSession FK chain — structures
    # are 1:1 with a training_session, never a calendar_event directly)
    "calendar_events",
    "event_audiences",
    "training_sessions",
    # Strava linkage chain (structures query strava_activities to decide whether
    # to dispatch a match recompute; US2 match tables persist laps + results)
    "athletes",
    "strava_connections",
    "strava_activities",
    "strava_activity_laps",
    "interval_match_results",
    # Interval training tables (feature 026, US1/US4)
    "interval_structures",
    "interval_structure_blocks",
    "interval_templates",
    "interval_template_blocks",
)


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """In-memory aiosqlite engine with the interval-training table subset."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Unsaved user object helpers (plain functions — not fixtures)
# ---------------------------------------------------------------------------


def coach_user_obj(user_id: int = 10) -> User:
    """Return an unsaved coach User for use as a DB fixture or auth override."""
    return User(
        id=user_id,
        email=f"entrenador.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Entrenador",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


def admin_user_obj(user_id: int = 20) -> User:
    """Return an unsaved admin User."""
    return User(
        id=user_id,
        email=f"admin.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Admin",
        last_name="Ficticio",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


def parent_user_obj(user_id: int = 30) -> User:
    """Return an unsaved parent User."""
    return User(
        id=user_id,
        email=f"padre.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Padre",
        last_name="Ficticio",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Async seed helpers (call inside a test or fixture; callers own commit)
# ---------------------------------------------------------------------------


async def seed_club(session: AsyncSession, club_id: int = 1) -> Club:
    """Insert a Club and flush. Fictitious data only."""
    club = Club(
        id=club_id,
        name="Club Ficticio de Prueba",
        code=f"TST{club_id:03d}",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club)
    await session.flush()
    return club


async def seed_coach(
    session: AsyncSession,
    user_id: int = 10,
    club_id: int = 1,
) -> User:
    """Insert a coach User + ClubMember row and flush."""
    user = coach_user_obj(user_id)
    session.add(user)
    await session.flush()
    cm = ClubMember(
        club_id=club_id,
        user_id=user_id,
        role_in_club=ClubRole.coach,
        joined_at=datetime.now(timezone.utc),
    )
    session.add(cm)
    await session.flush()
    return user


async def seed_admin(
    session: AsyncSession,
    user_id: int = 20,
) -> User:
    """Insert an admin User (no club membership needed for global admin)."""
    user = admin_user_obj(user_id)
    session.add(user)
    await session.flush()
    return user


async def seed_parent(
    session: AsyncSession,
    user_id: int = 30,
) -> User:
    """Insert a parent User and flush."""
    user = parent_user_obj(user_id)
    session.add(user)
    await session.flush()
    return user


async def seed_training_session(
    session: AsyncSession,
    *,
    session_id: int | None = None,
    club_id: int = 1,
    created_by_user_id: int = 10,
    scheduled_date: date = date(2026, 7, 10),
) -> TrainingSession:
    """Insert a bare TrainingSession (no wizard, no calendar event) and flush.

    Mirrors ``tests/strength/test_rbac.py::_seed_training_session`` — a
    session with no ``calendar_event_id`` is a valid, common state (the
    column is nullable), and IntervalStructure only needs
    ``training_sessions.id`` + ``club_id`` to exist.
    """
    kwargs: dict = {}
    if session_id is not None:
        kwargs["id"] = session_id
    ts = TrainingSession(
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        status=SessionStatus.PLANNED,
        session_kind=SessionKind.ENTRENAMIENTO,
        scheduled_date=scheduled_date,
        scheduled_start_time=time(16, 0),
        duration_min=90,
        location="Cancha Ficticia",
        technical_focus="Intervalos (test)",
        **kwargs,
    )
    session.add(ts)
    await session.flush()
    return ts


# ---------------------------------------------------------------------------
# AsyncClient factory
# ---------------------------------------------------------------------------


def make_client(
    session: AsyncSession,
    *,
    user: User | None = None,
    authed: bool = True,
):
    """Return an async context-manager wrapping an AsyncClient.

    The returned object is used as ``async with make_client(session) as client:``.
    It overrides ``get_db`` with the supplied session and, when ``authed=True``,
    overrides ``get_current_user`` with ``user`` (defaults to coach_user_obj()).

    App dependency_overrides are cleared by the ``_clear_overrides`` autouse
    fixture after each test.

    Args:
        session: Active AsyncSession already scoped to the test.
        user:    User object returned by ``get_current_user``; defaults to coach.
        authed:  When ``False``, removes the ``get_current_user`` override so
                 the real JWT auth fires (produces 401/403 for negative tests).
    """

    async def _override_db():
        yield session
        await session.commit()

    app.dependency_overrides[get_db] = _override_db

    if authed:
        resolved_user = user or coach_user_obj()

        async def _override_user():
            return resolved_user

        app.dependency_overrides[get_current_user] = _override_user

    @asynccontextmanager
    async def _ctx():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    return _ctx()


# ---------------------------------------------------------------------------
# Autouse fixture: clear dependency_overrides after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Prevent dependency override bleed between tests."""
    yield
    app.dependency_overrides.clear()
