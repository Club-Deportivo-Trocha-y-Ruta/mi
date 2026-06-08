"""Tests for GET /api/race-analysis/race-events/{id}/results (Wave A, T008).

Coverage
--------
- Happy path: grouped by category, ordered by position.
- category_id filter: only one category returned.
- club_only filter: only club-linked rows.
- Soft-deleted results excluded.
- 404 for unknown event.
- 403 for unauthenticated (no token → 403 from require_role).
- Query-count assertion (T011): results endpoint executes ≤3 SQL statements.

Fixtures follow the exact same pattern as ``test_race_events_crud.py``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
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
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole

_BASE = "/api/race-analysis/race-events"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}_{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Import all models needed to register metadata.
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _Cat  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "parent_athlete",
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_results",
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
# Seed helpers
# ---------------------------------------------------------------------------


async def _insert_base(session: AsyncSession) -> None:
    """Minimal set: users, club, series, event, categories, competitors."""
    coach = User(
        id=10, email="coach@test.com", hashed_password="x",
        first_name="Coach", last_name="Ten",
        role=UserRole.coach, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    parent_user = User(
        id=5, email="parent@test.com", hashed_password="x",
        first_name="Padre", last_name="Ficticio",
        role=UserRole.parent, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    # Athlete user (can_login=False, but we still need a user row for FK)
    athlete_user = User(
        id=20, email="athlete@test.com", hashed_password="x",
        first_name="Atleta", last_name="TyR",
        role=UserRole.parent, is_active=True, can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    club = Club(id=1, name="Club TyR", code="TYR")
    athlete = Athlete(
        id=1,
        user_id=20,
        first_name="Atleta",
        last_name="TyR",
        birth_date=date(2012, 1, 1),
        sex="M",
        club_id=1,
        created_by=10,
    )
    parent_link = ParentAthlete(
        id=1, parent_id=5, athlete_id=1, relationship_type="padre"
    )
    series = RaceSeries(
        id=1, name="Copa Valle", season_year=2026,
        organizer="Liga", points_scheme_code="copa_valle_2026",
    )
    event = RaceEvent(
        id=100,
        series_id=1,
        sequence_number=4,
        name="VALIDA IV CALI",
        event_date=date(2026, 5, 17),
        location="Cali",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=10,
    )
    cat1 = RaceCategory(
        id=1, code="INF_M", label="Infantil Masculino",
        sex=CategoryGender.M, sort_order=10, is_active=True,
    )
    cat2 = RaceCategory(
        id=2, code="INF_F", label="Infantil Femenino",
        sex=CategoryGender.F, sort_order=11, is_active=True,
    )
    # Club competitor (athlete_id set → is_our_club=True)
    comp_club = RaceCompetitor(
        id=1, normalized_name="atleta tyr",
        display_name="Atleta TyR", club_text="Club TyR",
        athlete_id=1,
    )
    # Rival competitor
    comp_rival = RaceCompetitor(
        id=2, normalized_name="corredor rival",
        display_name="Corredor Rival", club_text="Club X",
    )
    session.add_all([
        coach, parent_user, athlete_user, club, athlete, parent_link,
        series, event, cat1, cat2, comp_club, comp_rival,
    ])
    await session.commit()


async def _insert_results(session: AsyncSession) -> None:
    """Three results: 2 in INF_M (club 1st, rival 2nd) + 1 in INF_F (rival)."""
    r1 = RaceResult(
        event_id=100, category_id=1, competitor_id=1, athlete_id=1,
        position=1, status=ResultStatus.FINISHED,
        race_time_ms=200_000, points_awarded=40,
        created_by_user_id=10,
    )
    r2 = RaceResult(
        event_id=100, category_id=1, competitor_id=2,
        position=2, status=ResultStatus.FINISHED,
        race_time_ms=205_000, points_awarded=35,
        created_by_user_id=10,
    )
    r3 = RaceResult(
        event_id=100, category_id=2, competitor_id=2,
        position=1, status=ResultStatus.FINISHED,
        race_time_ms=220_000, points_awarded=40,
        created_by_user_id=10,
    )
    session.add_all([r1, r2, r3])
    await session.commit()


@pytest_asyncio.fixture
async def seed_full(db_session_factory):
    async with db_session_factory() as s:
        await _insert_base(s)
        await _insert_results(s)
    yield


@pytest_asyncio.fixture
async def seed_with_soft_delete(db_session_factory):
    """Seed with results, one of which is soft-deleted."""
    async with db_session_factory() as s:
        await _insert_base(s)
        await _insert_results(s)
        # Soft-delete the rival's INF_M result.
        row = (await s.execute(
            select(RaceResult).where(
                RaceResult.event_id == 100,
                RaceResult.category_id == 1,
                RaceResult.competitor_id == 2,
            )
        )).scalar_one()
        row.deleted_at = datetime.now(timezone.utc)
        await s.commit()
    yield


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


def _make_client(factory, role: UserRole, user_id: int = 10):
    """Return a context-manager that yields an AsyncClient for the given role."""
    # We use a factory function so each test can do:
    #   async with _make_client(...) as ac: ...
    class _Ctx:
        async def __aenter__(self):
            app.dependency_overrides[get_db] = _override_db_factory(factory)
            app.dependency_overrides[get_current_user] = lambda: _make_user(role, user_id)
            self._transport = ASGITransport(app=app)
            self._client = AsyncClient(transport=self._transport, base_url="http://test")
            return await self._client.__aenter__()

        async def __aexit__(self, *args):
            await self._client.__aexit__(*args)
            app.dependency_overrides.clear()

    return _Ctx()


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_full):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_full):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.parent, 5)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_soft_delete(sqlite_engine, db_session_factory, seed_with_soft_delete):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, seed_full):
    """Client with no auth override — HTTP 403 from require_role."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetEventResults:
    """GET /api/race-analysis/race-events/{id}/results"""

    @pytest.mark.asyncio
    async def test_happy_path_grouped_by_category(self, coach_client):
        """Results are grouped by category and ordered by position."""
        r = await coach_client.get(f"{_BASE}/100/results")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["race_event_id"] == 100
        cats = body["categories"]
        assert len(cats) == 2

        # First category must be INF_M (sort_order=10)
        inf_m = cats[0]
        assert inf_m["code"] == "INF_M"
        assert len(inf_m["rows"]) == 2

        # Rows ordered by position ASC.
        assert inf_m["rows"][0]["position"] == 1
        assert inf_m["rows"][1]["position"] == 2

        # Club athlete: is_our_club=True, athlete_id=1
        first = inf_m["rows"][0]
        assert first["athlete_id"] == 1
        assert first["is_our_club"] is True

        # Rival: is_our_club=False
        second = inf_m["rows"][1]
        assert second["athlete_id"] is None
        assert second["is_our_club"] is False

    @pytest.mark.asyncio
    async def test_category_filter(self, coach_client):
        """?category_id filters to only that category."""
        r = await coach_client.get(f"{_BASE}/100/results?category_id=2")
        assert r.status_code == 200, r.text
        body = r.json()
        cats = body["categories"]
        assert len(cats) == 1
        assert cats[0]["code"] == "INF_F"

    @pytest.mark.asyncio
    async def test_club_only_filter(self, coach_client):
        """?club_only=true returns only rows with athlete_id."""
        r = await coach_client.get(f"{_BASE}/100/results?club_only=true")
        assert r.status_code == 200, r.text
        body = r.json()
        all_rows = [row for cat in body["categories"] for row in cat["rows"]]
        assert all(row["is_our_club"] for row in all_rows)
        assert len(all_rows) == 1  # only the club competitor in INF_M

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded(self, coach_client_soft_delete):
        """Soft-deleted rows must not appear."""
        r = await coach_client_soft_delete.get(f"{_BASE}/100/results")
        assert r.status_code == 200, r.text
        body = r.json()
        # Find INF_M category — only the club competitor row remains.
        inf_m_cats = [c for c in body["categories"] if c["code"] == "INF_M"]
        assert len(inf_m_cats) == 1
        assert len(inf_m_cats[0]["rows"]) == 1
        assert inf_m_cats[0]["rows"][0]["competitor_id"] == 1

    @pytest.mark.asyncio
    async def test_404_unknown_event(self, coach_client):
        """Returns 404 when the race event does not exist."""
        r = await coach_client.get(f"{_BASE}/9999/results")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_403_unauthenticated(self, anon_client):
        """Returns 403 when no auth token is present."""
        r = await anon_client.get(f"{_BASE}/100/results")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_empty_event_no_results(
        self, sqlite_engine, db_session_factory
    ):
        """Event with no imported results returns empty categories list."""
        # Seed only the base (no results).
        async with db_session_factory() as s:
            await _insert_base(s)

        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, 10
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/results")
            assert r.status_code == 200, r.text
            assert r.json()["categories"] == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Query-count test (T011) for results endpoint
# ---------------------------------------------------------------------------


class TestResultsQueryCount:
    """Assert the results endpoint fires a bounded number of SQL statements."""

    @pytest.mark.asyncio
    async def test_results_bounded_queries(
        self, sqlite_engine, db_session_factory, seed_full
    ):
        """Results endpoint should use ≤3 SQL statements (event check + main query + commit)."""
        query_log: list[str] = []

        # SQLAlchemy sync event listener on the underlying sync engine.
        sync_engine = sqlite_engine.sync_engine

        @sa_event.listens_for(sync_engine, "before_cursor_execute")
        def _capture(conn, cursor, statement, parameters, context, executemany):
            # Ignore PRAGMA and BEGIN/COMMIT housekeeping.
            stmt_upper = statement.strip().upper()
            if any(stmt_upper.startswith(p) for p in ("PRAGMA", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")):
                return
            query_log.append(statement[:80])

        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, 10
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/results")
            assert r.status_code == 200, r.text
        finally:
            app.dependency_overrides.clear()
            sa_event.remove(sync_engine, "before_cursor_execute", _capture)

        # Should be ≤3: event-exists check + main join query + (optional) commit.
        assert len(query_log) <= 3, f"Expected ≤3 queries, got {len(query_log)}: {query_log}"
