"""Router tests for ``activities.py`` (specs/025-strava-activity-sync, T030).

Covers link/re-link/unlink happy paths, parent/athlete RBAC (403 on the
coach-gated ``PATCH .../link``), cross-club session rejection (422),
session-suggestion ranking (same-day + attendance first, FR-008),
pagination, unlinked-first ordering (FR-010), and a query-count assertion
that guards against N+1 regressions in the ``selectinload`` eager-loading
strategy documented in ``_ACTIVITY_EAGER_OPTIONS``.

Why a standalone ASGI app instead of ``app.main.app``
------------------------------------------------------
Same reasoning as ``tests/routers/test_strava_integration.py``:
``app/main.py`` only mounts ``activities.router`` when
``settings.strava_enabled`` is ``True`` **at import time**, and by the time
this module is collected the session-scoped ``app.main`` import has already
happened with the default (``False``) value. We build a small local
``FastAPI`` app that mounts only ``activities.router`` under the same
``/api`` prefix used in production and drive it with its own
``dependency_overrides`` — the router still imports the *same*
``get_db``/``get_current_user`` function objects from ``app.dependencies``,
so overriding them here works exactly like it would on the real app.

RBAC note: ``permissions.can_view_activity`` / ``can_link_activity`` query
the ``club_members`` table directly for the coach branch (unlike
``dependencies.verify_athlete_access``, which reads the in-memory
``user.club_memberships`` stub attribute). Any test that exercises those
two helpers (session-suggestions, link, athlete-scoped list) therefore
seeds a real ``ClubMember`` row — a bare ``SimpleNamespace`` stub is not
enough. ``GET /api/activities`` (the coach review list) is the one
exception: it filters via ``current_user.club_memberships`` directly, so a
stub is sufficient there.

All data is fictitious (non-negotiable CLAUDE.md §Privacy constraint) —
names like "Atleta Ficticio", no real TyR athlete data.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.models import Base
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.club import ClubMember, ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.strava_activity import StravaActivity, StravaIngestSource
from app.models.strava_connection import StravaConnection, StravaConnectionStatus
from app.models.training_session import (
    SessionAttendance,
    SessionKind,
    TrainingSession,
)
from app.models.user import User, UserRole
from app.routers import activities

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Tables (subset — mirrors tests/routers/test_strava_integration.py)
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "strava_connections",
    "strava_activities",
    "training_sessions",
    "session_attendance",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Local ASGI app (see module docstring for why not app.main.app)
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(activities.router, prefix="/api")
    return test_app


# ---------------------------------------------------------------------------
# DB fixtures — in-memory aiosqlite, subset of tables
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
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
# Seed helpers
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_id: int, role: UserRole) -> User:
    u = User(
        id=user_id,
        email=f"{role.value}{user_id}@test.com",
        hashed_password="x",
        first_name="Test",
        last_name=f"User{user_id}",
        role=role,
        is_active=True,
        can_login=role != UserRole.athlete,
        created_at=_utc(),
    )
    session.add(u)
    await session.flush()
    return u


async def seed_club_member(
    session: AsyncSession, *, user_id: int, club_id: int, role: ClubRole = ClubRole.coach
) -> ClubMember:
    """Real ``club_members`` row — required for ``permissions.user_club_role``
    (queried by ``can_view_activity``/``can_link_activity``), unlike
    ``verify_athlete_access`` which reads the in-memory stub attribute."""
    m = ClubMember(user_id=user_id, club_id=club_id, role_in_club=role)
    session.add(m)
    await session.flush()
    return m


async def seed_athlete(
    session: AsyncSession,
    athlete_id: int,
    *,
    club_id: int = 1,
    user_id: int | None = None,
) -> Athlete:
    a = Athlete(
        id=athlete_id,
        user_id=user_id or (900 + athlete_id),
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        birth_date=date(2013, 5, 1),
        sex=Sex.M,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_connection(
    session: AsyncSession,
    *,
    athlete_id: int,
    strava_athlete_id: int,
    authorized_by_user_id: int,
    parent_user_id: int,
) -> StravaConnection:
    """Minimal consent + connection chain so ``strava_activities.connection_id``
    has a real parent row. Tokens are inert bytes — activities.py never
    decrypts them."""
    consent = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        consented_at=_utc(),
    )
    session.add(consent)
    await session.flush()

    conn = StravaConnection(
        athlete_id=athlete_id,
        strava_athlete_id=strava_athlete_id,
        status=StravaConnectionStatus.active,
        access_token_enc=b"enc-access",
        refresh_token_enc=b"enc-refresh",
        token_expires_at=_utc() + timedelta(hours=6),
        scope_granted="activity:read_all",
        authorized_by_user_id=authorized_by_user_id,
        consent_id=consent.id,
        connected_at=_utc(),
    )
    session.add(conn)
    await session.flush()
    return conn


async def seed_activity(
    session: AsyncSession,
    activity_id: int,
    *,
    strava_activity_id: int,
    athlete_id: int,
    connection_id: int,
    start_date_local: datetime,
    training_session_id: int | None = None,
    linked_by_user_id: int | None = None,
    name: str = "Salida ficticia",
) -> StravaActivity:
    # Mirrors the invariant the router's own link endpoint enforces
    # (activities.py::link_activity always sets linked_at/linked_by_user_id
    # together with training_session_id): a pre-linked seed row needs both,
    # otherwise ActivityLinkOut(linked_at=None) fails Pydantic validation
    # (linked_at is a required datetime on the response schema — see the
    # "seeded pre-linked row without linked_at" finding in the QA report).
    resolved_linked_at = _utc() if training_session_id is not None else None
    resolved_linked_by = (
        (linked_by_user_id or 10) if training_session_id is not None else None
    )
    a = StravaActivity(
        id=activity_id,
        strava_activity_id=strava_activity_id,
        athlete_id=athlete_id,
        connection_id=connection_id,
        name=name,
        sport_type="Ride",
        start_date_utc=start_date_local.astimezone(timezone.utc)
        if start_date_local.tzinfo
        else start_date_local,
        start_date_local=start_date_local.replace(tzinfo=None)
        if start_date_local.tzinfo
        else start_date_local,
        elapsed_time_s=3600,
        moving_time_s=3500,
        distance_m=25000.0,
        total_elevation_gain_m=300.0,
        average_heartrate=150.0,
        max_heartrate=175.0,
        is_trainer=False,
        ingest_source=StravaIngestSource.webhook,
        training_session_id=training_session_id,
        linked_at=resolved_linked_at,
        linked_by_user_id=resolved_linked_by,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_training_session(
    session: AsyncSession,
    session_id: int,
    *,
    club_id: int = 1,
    scheduled_date: date,
    created_by_user_id: int = 1,
    location: str = "Sede club",
    technical_focus: str = "Resistencia",
) -> TrainingSession:
    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        scheduled_date=scheduled_date,
        scheduled_start_time=time(15, 0),
        duration_min=90,
        location=location,
        technical_focus=technical_focus,
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add(ts)
    await session.flush()
    return ts


async def seed_attendance(
    session: AsyncSession, *, session_id: int, athlete_id: int
) -> SessionAttendance:
    from app.models.training_session import AttendanceStatus

    att = SessionAttendance(
        session_id=session_id,
        athlete_id=athlete_id,
        status=AttendanceStatus.PRESENTE,
    )
    session.add(att)
    await session.flush()
    return att


def coach_user_typed(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    """``list_activities`` filters via the in-memory ``club_memberships``
    stub attribute; ``can_view_activity``/``can_link_activity`` separately
    query a real ``club_members`` DB row (see ``seed_club_member``)."""
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


def admin_user_typed(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.admin, club_memberships=[])


def parent_user_typed(user_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.parent, club_memberships=[])


def athlete_user_typed(user_id: int = 900) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.athlete, club_memberships=[])


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def make_client(session: AsyncSession, *, user) -> AsyncClient:
    """Build an AsyncClient bound to a fresh local app with DB/auth overrides."""
    test_app = _build_app()

    async def _override_db():
        yield session
        await session.commit()

    async def _override_user():
        return user

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Query counter (mirrors tests/technique/test_perf_queries.py)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def count_selects(engine: AsyncEngine):
    counter: list[int] = [0]

    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if statement.strip().upper().startswith("SELECT"):
            counter[0] += 1

    sync_engine = engine.sync_engine
    sa_event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        sa_event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)


# ===========================================================================
# A. Link / re-link / unlink happy paths (FR-007)
# ===========================================================================


class TestLinkHappyPaths:
    async def _seed_base(self, session: AsyncSession, *, club_id: int = 1):
        # NOTE: link_activity does ``activity.linked_by = current_user`` as a
        # real SQLAlchemy relationship assignment — the ``current_user``
        # object returned by the dependency override MUST be an attached ORM
        # ``User`` instance (not the ``SimpleNamespace`` stub used by the
        # read-only/RBAC-rejection tests), otherwise SQLAlchemy raises
        # ``AttributeError: 'SimpleNamespace' object has no attribute
        # '_sa_instance_state'``. ``seed_user`` already returns the attached
        # instance, so we capture and reuse it here.
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=club_id)
        admin = await seed_user(session, 1, UserRole.admin)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=club_id)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity_dt = datetime(2026, 3, 10, 8, 0, 0)
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=activity_dt,
        )
        session_a = await seed_training_session(
            session, 501, club_id=club_id, scheduled_date=date(2026, 3, 10)
        )
        session_b = await seed_training_session(
            session, 502, club_id=club_id, scheduled_date=date(2026, 3, 11)
        )
        await session.commit()
        return activity, session_a, session_b, coach, admin

    async def test_link_activity_to_session(self, session):
        activity, session_a, _, coach, _ = await self._seed_base(session)

        async with make_client(session, user=coach) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": session_a.id},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["link"] is not None
        assert body["link"]["training_session_id"] == session_a.id
        assert body["link"]["linked_by"] == "Test User10"
        assert body["link"]["linked_at"] is not None

    async def test_relink_activity_to_another_session(self, session):
        activity, session_a, session_b, coach, _ = await self._seed_base(session)

        async with make_client(session, user=coach) as client:
            first = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": session_a.id},
            )
            assert first.status_code == 200, first.text

            second = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": session_b.id},
            )

        assert second.status_code == 200, second.text
        body = second.json()
        assert body["link"]["training_session_id"] == session_b.id

    async def test_unlink_activity(self, session):
        activity, session_a, _, coach, _ = await self._seed_base(session)

        async with make_client(session, user=coach) as client:
            linked = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": session_a.id},
            )
            assert linked.status_code == 200, linked.text

            unlinked = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": None},
            )

        assert unlinked.status_code == 200, unlinked.text
        body = unlinked.json()
        assert body["link"] is None

    async def test_link_admin_role_allowed(self, session):
        activity, session_a, _, _, admin = await self._seed_base(session)

        async with make_client(session, user=admin) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": session_a.id},
            )

        assert resp.status_code == 200, resp.text


# ===========================================================================
# B. RBAC — parent / athlete role 403 on link mutation (FR-007)
# ===========================================================================


class TestLinkRbac:
    async def _seed_base(self, session: AsyncSession):
        coach = await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        await session.commit()
        return activity, train_session, coach

    async def test_parent_cannot_link_gets_403(self, session):
        activity, train_session, _coach = await self._seed_base(session)

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": train_session.id},
            )

        assert resp.status_code == 403, resp.text
        assert "permiso" in resp.json()["detail"].lower()

    async def test_athlete_role_cannot_link_gets_403(self, session):
        activity, train_session, _coach = await self._seed_base(session)

        async with make_client(session, user=athlete_user_typed(user_id=900)) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": train_session.id},
            )

        assert resp.status_code == 403, resp.text

    async def test_parent_cannot_unlink_gets_403(self, session):
        """Parents are read-only end to end — not even unlink is allowed."""
        activity, train_session, coach = await self._seed_base(session)

        # First, link it as coach (real ORM User — see TestLinkHappyPaths
        # docstring note on relationship assignment) so there is something
        # to (attempt to) unlink.
        async with make_client(session, user=coach) as client:
            linked = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": train_session.id},
            )
        assert linked.status_code == 200, linked.text

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": None},
            )

        assert resp.status_code == 403, resp.text


# ===========================================================================
# C. Cross-club session rejection (422)
# ===========================================================================


class TestLinkCrossClub:
    async def test_link_to_session_of_another_club_returns_422(self, session):
        await seed_user(session, 10, UserRole.coach)
        # Coach belongs to club 1 (the athlete's club) — RBAC passes; the
        # 422 comes from the *session* belonging to a different club (2).
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        other_club_session = await seed_training_session(
            session, 900, club_id=2, scheduled_date=date(2026, 3, 10)
        )
        await session.commit()

        async with make_client(session, user=coach_user_typed(club_id=1)) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": other_club_session.id},
            )

        assert resp.status_code == 422, resp.text
        assert "no pertenece al club" in resp.json()["detail"].lower()

    async def test_link_to_nonexistent_session_returns_404(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        await session.commit()

        async with make_client(session, user=coach_user_typed(club_id=1)) as client:
            resp = await client.patch(
                f"/api/activities/{activity.id}/link",
                json={"training_session_id": 9999},
            )

        assert resp.status_code == 404, resp.text


# ===========================================================================
# D. Session-suggestion ranking (FR-008): same-day + attendance first
# ===========================================================================


class TestSessionSuggestions:
    async def test_ranking_same_day_and_attendance_first(self, session):
        await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity_date = date(2026, 3, 10)
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime.combine(activity_date, time(8, 0)),
        )

        # Best candidate: same day + attendance.
        same_day_attend = await seed_training_session(
            session, 501, club_id=1, scheduled_date=activity_date
        )
        await seed_attendance(session, session_id=same_day_attend.id, athlete_id=athlete.id)

        # Same day, no attendance.
        same_day_no_attend = await seed_training_session(
            session, 502, club_id=1, scheduled_date=activity_date
        )

        # Different day (within window), with attendance.
        other_day_attend = await seed_training_session(
            session, 503, club_id=1, scheduled_date=activity_date - timedelta(days=1)
        )
        await seed_attendance(session, session_id=other_day_attend.id, athlete_id=athlete.id)

        # Outside the ±1 day window — must be excluded entirely.
        outside_window = await seed_training_session(
            session, 504, club_id=1, scheduled_date=activity_date + timedelta(days=2)
        )

        await session.commit()

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(f"/api/activities/{activity.id}/session-suggestions")

        assert resp.status_code == 200, resp.text
        suggestions = resp.json()["suggestions"]
        returned_ids = [s["training_session_id"] for s in suggestions]

        assert outside_window.id not in returned_ids
        assert returned_ids[0] == same_day_attend.id
        assert suggestions[0]["same_day"] is True
        assert suggestions[0]["athlete_in_attendance"] is True

        # Same-day candidates rank ahead of different-day candidates,
        # regardless of attendance on the different day.
        same_day_rank = returned_ids.index(same_day_no_attend.id)
        other_day_rank = returned_ids.index(other_day_attend.id)
        assert same_day_rank < other_day_rank

    async def test_suggestions_parent_gets_403(self, session):
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=1)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        activity = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete.id,
            connection_id=conn.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
        )
        await session.commit()

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            resp = await client.get(f"/api/activities/{activity.id}/session-suggestions")

        assert resp.status_code == 403, resp.text


# ===========================================================================
# E. Pagination + unlinked-first ordering (FR-010) + query count (no N+1)
# ===========================================================================


class TestListActivitiesReview:
    async def _seed_many(
        self, session: AsyncSession, *, count: int = 12, club_id: int = 1
    ) -> tuple[list[StravaActivity], TrainingSession]:
        await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=club_id)
        await seed_user(session, 20, UserRole.parent)
        athlete = await seed_athlete(session, 100, club_id=club_id)
        conn = await seed_connection(
            session,
            athlete_id=athlete.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        train_session = await seed_training_session(
            session, 501, club_id=club_id, scheduled_date=date(2026, 3, 1)
        )

        base_dt = datetime(2026, 3, 1, 8, 0, 0)
        activities: list[StravaActivity] = []
        for i in range(count):
            # Every third activity starts out linked; the rest unlinked.
            linked_session_id = train_session.id if i % 3 == 0 else None
            act = await seed_activity(
                session,
                i + 1,
                strava_activity_id=9000 + i,
                athlete_id=athlete.id,
                connection_id=conn.id,
                start_date_local=base_dt + timedelta(hours=i),
                training_session_id=linked_session_id,
            )
            activities.append(act)

        await session.commit()
        return activities, train_session

    async def test_pagination(self, session):
        await self._seed_many(session, count=12)

        async with make_client(session, user=coach_user_typed()) as client:
            page1 = await client.get("/api/activities", params={"page": 1, "page_size": 5})
            page2 = await client.get("/api/activities", params={"page": 2, "page_size": 5})
            page3 = await client.get("/api/activities", params={"page": 3, "page_size": 5})

        assert page1.status_code == page2.status_code == page3.status_code == 200

        body1, body2, body3 = page1.json(), page2.json(), page3.json()
        assert body1["total"] == body2["total"] == body3["total"] == 12
        assert len(body1["items"]) == 5
        assert len(body2["items"]) == 5
        assert len(body3["items"]) == 2  # remainder

        ids_page1 = {item["id"] for item in body1["items"]}
        ids_page2 = {item["id"] for item in body2["items"]}
        ids_page3 = {item["id"] for item in body3["items"]}
        assert ids_page1.isdisjoint(ids_page2)
        assert ids_page1.isdisjoint(ids_page3)
        assert ids_page2.isdisjoint(ids_page3)

    async def test_unlinked_first_order_with_linked_all(self, session):
        await self._seed_many(session, count=12)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/activities", params={"linked": "all", "page_size": 20}
            )

        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 12

        linked_flags = [item["link"] is not None for item in items]
        # First unlinked-run, then linked-run: once a linked item appears,
        # every subsequent item must also be linked (no unlinked item comes
        # after a linked one).
        first_linked_index = linked_flags.index(True)
        assert all(linked_flags[first_linked_index:]), (
            "Expected all unlinked activities before any linked activity "
            f"when linked=all; got flags={linked_flags}"
        )
        assert not linked_flags[0], "First item must be unlinked (unlinked-first order)"

    async def test_linked_filter_true_only_returns_linked(self, session):
        await self._seed_many(session, count=12)

        async with make_client(session, user=coach_user_typed()) as client:
            resp = await client.get(
                "/api/activities", params={"linked": "true", "page_size": 20}
            )

        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 4  # i % 3 == 0 for i in 0..11 -> 0,3,6,9
        assert all(item["link"] is not None for item in items)

    async def test_query_count_no_n_plus_one(self, session, engine):
        activities, _ = await self._seed_many(session, count=15)

        async with count_selects(engine) as counter:
            async with make_client(session, user=coach_user_typed()) as client:
                resp = await client.get(
                    "/api/activities", params={"page_size": 50}
                )

        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 15

        observed = counter[0]
        # Documented contract: 1 count query + 1 primary select + 3
        # selectinload IN-queries (athlete, training_session, linked_by) = 5.
        # A generous ceiling absorbs driver bookkeeping while still catching
        # an O(N) regression (15 activities would blow well past this).
        assert observed <= 10, (
            f"N+1 regression detected: GET /api/activities issued {observed} "
            "SELECT statements for 15 activities (ceiling is 10). Check that "
            "_ACTIVITY_EAGER_OPTIONS selectinload options are applied in "
            "app/routers/activities.py."
        )
        assert observed >= 2, (
            f"Too few SELECTs ({observed}): expected at least the count "
            "query + primary select. The measurement harness may be broken."
        )


# ===========================================================================
# F. Parent RBAC — own-child read access vs other-family / athlete-role
#    (T037, FR-011)
# ===========================================================================


class TestActivitiesParentRbac:
    """``GET /api/athletes/{id}/activities`` RBAC surface (FR-011): parents
    may read their own children's activities but never another family's;
    the ``athlete`` role has no read access at all (``can_view_activity``
    only recognizes admin/coach/parent); and the per-item ``link`` object a
    parent receives is read-only end to end — they can see it via GET but
    ``PATCH .../link`` stays coach/admin-only (see ``TestLinkRbac`` for the
    mutation-side 403)."""

    async def _seed_two_families(self, session: AsyncSession):
        await seed_user(session, 10, UserRole.coach)
        await seed_club_member(session, user_id=10, club_id=1)
        await seed_user(session, 20, UserRole.parent)  # family A — linked
        await seed_user(session, 21, UserRole.parent)  # family B — no link

        athlete_a = await seed_athlete(session, 100, club_id=1)
        athlete_b = await seed_athlete(session, 101, club_id=1)

        session.add(
            ParentAthlete(
                parent_id=20,
                athlete_id=athlete_a.id,
                relationship_type=FamilyRelationship.padre,
            )
        )
        await session.flush()

        conn_a = await seed_connection(
            session,
            athlete_id=athlete_a.id,
            strava_athlete_id=555,
            authorized_by_user_id=20,
            parent_user_id=20,
        )
        train_session = await seed_training_session(
            session, 501, club_id=1, scheduled_date=date(2026, 3, 10)
        )
        activity_a = await seed_activity(
            session,
            1,
            strava_activity_id=9001,
            athlete_id=athlete_a.id,
            connection_id=conn_a.id,
            start_date_local=datetime(2026, 3, 10, 8, 0, 0),
            training_session_id=train_session.id,
            linked_by_user_id=10,
        )
        await session.commit()
        return athlete_a, athlete_b, activity_a, train_session

    async def test_parent_own_child_activities_200(self, session):
        athlete_a, _athlete_b, activity_a, _ts = await self._seed_two_families(session)

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            resp = await client.get(f"/api/athletes/{athlete_a.id}/activities")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == activity_a.id

    async def test_parent_other_family_athlete_gets_403(self, session):
        """Family A's parent may not read Family B's athlete, even though
        both belong to the same club — scope is per-family, not per-club."""
        _athlete_a, athlete_b, _activity_a, _ts = await self._seed_two_families(session)

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            resp = await client.get(f"/api/athletes/{athlete_b.id}/activities")

        assert resp.status_code == 403, resp.text
        assert "permiso" in resp.json()["detail"].lower()

    async def test_unrelated_parent_gets_403_on_other_child(self, session):
        """Symmetric check: Family B's parent (no ``ParentAthlete`` row at
        all) is blocked from Family A's athlete."""
        athlete_a, _athlete_b, _activity_a, _ts = await self._seed_two_families(session)

        async with make_client(session, user=parent_user_typed(user_id=21)) as client:
            resp = await client.get(f"/api/athletes/{athlete_a.id}/activities")

        assert resp.status_code == 403, resp.text

    async def test_athlete_role_gets_403(self, session):
        """The ``athlete`` role has no activities-read path at all —
        ``can_view_activity`` only recognizes admin/coach/parent, so even a
        request scoped to "their own" athlete row is rejected."""
        athlete_a, _athlete_b, _activity_a, _ts = await self._seed_two_families(session)

        async with make_client(session, user=athlete_user_typed(user_id=900)) as client:
            resp = await client.get(f"/api/athletes/{athlete_a.id}/activities")

        assert resp.status_code == 403, resp.text

    async def test_parent_sees_link_state_read_only(self, session):
        """Parent GET surfaces the full ``link`` object (read access to
        link state) but ``PATCH .../link`` stays 403 and leaves the link
        untouched — the family view is read-only end to end (FR-007 +
        FR-011)."""
        athlete_a, _athlete_b, activity_a, train_session = await self._seed_two_families(
            session
        )

        async with make_client(session, user=parent_user_typed(user_id=20)) as client:
            read_resp = await client.get(f"/api/athletes/{athlete_a.id}/activities")
            assert read_resp.status_code == 200, read_resp.text
            item = read_resp.json()["items"][0]
            assert item["link"] is not None
            assert item["link"]["training_session_id"] == train_session.id
            assert item["link"]["linked_by"]
            assert item["link"]["linked_at"] is not None

            patch_resp = await client.patch(
                f"/api/activities/{activity_a.id}/link",
                json={"training_session_id": None},
            )
            assert patch_resp.status_code == 403, patch_resp.text

            reread = await client.get(f"/api/athletes/{athlete_a.id}/activities")
            assert reread.json()["items"][0]["link"]["training_session_id"] == (
                train_session.id
            ), "Rejected PATCH must not mutate the link state"
