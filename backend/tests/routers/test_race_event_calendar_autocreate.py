"""Tests for POST /api/race-analysis/race-events/{race_event_id}/calendar-event (T007, Feature 008).

Endpoint: POST /{race_event_id}/calendar-event
Auth: coach-only (FR-008).

Test table
----------
| #  | Scenario                                            | Expected |
|----|-----------------------------------------------------|----------|
| 1  | Happy path — coach, unlinked válida → 201           |  201     |
| 2  | Happy path — all_day=True on created CalendarEvent  |  201     |
| 3  | Happy path — title matches race_event.name          |  201     |
| 4  | Happy path — location matches race_event.location   |  201     |
| 5  | Happy path — start_at/end_at bound event_date       |  201     |
| 6  | Happy path — both FK sides set                      |  201     |
| 7  | Happy path — has_calendar_event=true in response    |  201     |
| 8  | Already-linked válida → 409, no duplicate created   |  409     |
| 9  | Admin role → 403                                    |  403     |
| 10 | Parent role → 403                                   |  403     |
| 11 | Unknown race_event_id → 404                         |  404     |

Strategy: SQLite async in-memory + httpx.AsyncClient + override of auth + get_db.
Same pattern as test_race_events_crud.py.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.calendar_event import CalendarEvent, EventStatus, EventType
from app.models.club import Club, ClubMember, ClubRole
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

_BASE_URL = "http://test"
_ENDPOINT = "/api/race-analysis/race-events/{race_event_id}/calendar-event"


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite in-memory with the minimal table set for this endpoint."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Explicit imports so SQLAlchemy registers the table metadata.
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_series import RaceSeries as _RS  # noqa: F401
    from app.models.race_event import RaceEvent as _RE  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "calendar_events",
            "event_audiences",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


def _override_db_factory(factory: async_sessionmaker[AsyncSession]):
    async def _override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override_db


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


_COACH = _make_user(UserRole.coach, user_id=10)
_ADMIN = _make_user(UserRole.admin, user_id=1)
_PARENT = _make_user(UserRole.parent, user_id=5)


# ---------------------------------------------------------------------------
# Seed fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed(db_session_factory):
    """Seeds:
    - Club id=1.
    - Users: coach id=10 (member), admin id=1 (member), parent id=5.
    - RaceSeries id=1 (2026).
    - RaceEvent id=200 — unlinked (no calendar_event_id).
    - RaceEvent id=201 — pre-linked (calendar_event_id=900).
    - CalendarEvent id=900 — linked to race_event id=201.
    """
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Test",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="Test",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent = User(
            id=5, email="parent@test.com", hashed_password="x",
            first_name="Parent", last_name="Test",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club Trocha y Ruta", code="TYR")
        coach_member = ClubMember(club_id=1, user_id=10, role_in_club=ClubRole.coach)
        admin_member = ClubMember(club_id=1, user_id=1, role_in_club=ClubRole.admin)
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        # Unlinked event.
        evt_unlinked = RaceEvent(
            id=200,
            series_id=1,
            sequence_number=1,
            name="VALIDA I SEVILLA 2026",
            event_date=date(2026, 1, 31),
            location="Sevilla, Valle del Cauca",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        # Pre-existing CalendarEvent linked to id=201.
        cal_existing = CalendarEvent(
            id=900,
            club_id=1,
            event_type=EventType.COMPETITION,
            status=EventStatus.SCHEDULED,
            title="VALIDA II GINEBRA 2026 (cal)",
            start_at=datetime(2026, 2, 28, 7, 0, 0),
            end_at=datetime(2026, 2, 28, 12, 0, 0),
            race_event_id=201,
            created_by_user_id=10,
        )
        evt_linked = RaceEvent(
            id=201,
            series_id=1,
            sequence_number=2,
            name="VALIDA II GINEBRA 2026",
            event_date=date(2026, 2, 28),
            location="Ginebra",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            calendar_event_id=900,
            created_by_user_id=10,
        )
        session.add_all([
            coach, admin, parent,
            club, coach_member, admin_member,
            series,
            evt_unlinked, cal_existing, evt_linked,
        ])
        await session.commit()
    yield


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------


def _make_client(db_session_factory, user: SimpleNamespace) -> AsyncClient:
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url=_BASE_URL)


def _url(race_event_id: int) -> str:
    return _ENDPOINT.format(race_event_id=race_event_id)


# ---------------------------------------------------------------------------
# Happy path tests (race_event id=200, unlinked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_201(db_session_factory, seed):
    """Coach POST on unlinked válida → 201."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_all_day_true_in_db(db_session_factory, seed):
    """Created CalendarEvent has all_day=True."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    cal_id = resp.json()["calendar_event_id"]

    async with db_session_factory() as session:
        cal = await session.get(CalendarEvent, cal_id)
        assert cal is not None
        assert cal.all_day is True
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_title_matches_name(db_session_factory, seed):
    """Created CalendarEvent.title equals race_event.name."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    cal_id = resp.json()["calendar_event_id"]

    async with db_session_factory() as session:
        cal = await session.get(CalendarEvent, cal_id)
        assert cal.title == "VALIDA I SEVILLA 2026"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_location_matches(db_session_factory, seed):
    """Created CalendarEvent.location equals race_event.location."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    cal_id = resp.json()["calendar_event_id"]

    async with db_session_factory() as session:
        cal = await session.get(CalendarEvent, cal_id)
        assert cal.location == "Sevilla, Valle del Cauca"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_start_end_bound_event_date(db_session_factory, seed):
    """start_at and end_at both fall on event_date (all-day bounds)."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    cal_id = resp.json()["calendar_event_id"]

    async with db_session_factory() as session:
        cal = await session.get(CalendarEvent, cal_id)
        expected = date(2026, 1, 31)
        assert cal.start_at.date() == expected
        assert cal.end_at.date() == expected
        assert cal.start_at.hour == 0
        assert cal.start_at.minute == 0
        assert cal.end_at.hour == 23
        assert cal.end_at.minute == 59
        assert cal.end_at.second == 59
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_both_fk_sides_set(db_session_factory, seed):
    """Both FK sides are set: race_events.calendar_event_id and calendar_events.race_event_id."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    body = resp.json()
    cal_id = body["calendar_event_id"]

    async with db_session_factory() as session:
        cal = await session.get(CalendarEvent, cal_id)
        race_ev = await session.get(RaceEvent, 200)
        assert cal.race_event_id == 200
        assert race_ev.calendar_event_id == cal_id
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_happy_path_has_calendar_event_true(db_session_factory, seed):
    """Response body has has_calendar_event=true."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_calendar_event"] is True
    assert body["race_event_id"] == 200
    assert isinstance(body["calendar_event_id"], int)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 409 — already linked; no duplicate created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_linked_returns_409(db_session_factory, seed):
    """Válida already linked → 409 Conflict."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(201))
    assert resp.status_code == 409
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_already_linked_no_duplicate_created(db_session_factory, seed):
    """409 path does not insert a second CalendarEvent for race_event id=201."""
    async with _make_client(db_session_factory, _COACH) as client:
        await client.post(_url(201))

    async with db_session_factory() as session:
        result = await session.execute(
            select(CalendarEvent).where(CalendarEvent.race_event_id == 201)
        )
        rows = result.scalars().all()
        # Only the pre-seeded CalendarEvent (id=900) must exist — no new one.
        assert len(rows) == 1
        assert rows[0].id == 900
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 403 — non-coach roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_role_returns_403(db_session_factory, seed):
    """Admin role → 403 (endpoint is coach-only)."""
    async with _make_client(db_session_factory, _ADMIN) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_parent_role_returns_403(db_session_factory, seed):
    """Parent role → 403."""
    async with _make_client(db_session_factory, _PARENT) as client:
        resp = await client.post(_url(200))
    assert resp.status_code == 403
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 404 — unknown race_event_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_race_event_id_returns_404(db_session_factory, seed):
    """Non-existent race_event_id → 404."""
    async with _make_client(db_session_factory, _COACH) as client:
        resp = await client.post(_url(9999))
    assert resp.status_code == 404
    app.dependency_overrides.clear()
