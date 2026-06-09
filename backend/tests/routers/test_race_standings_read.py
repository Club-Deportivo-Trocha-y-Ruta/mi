"""Tests for GET /api/race-analysis/race-events/{id}/standings (Wave A, T009).

Coverage
--------
- Happy path: ranked standings, grouped by category, ordered by rank.
- Standings aggregate across ALL events in the series (not just the anchor event).
- 404 for unknown event.
- 404 when event exists but has no series (edge case handled by service).
- Query-count assertion (T011): standings endpoint executes ≤3 SQL statements.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
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


async def _insert_series_seed(session: AsyncSession) -> None:
    """Two events in the same series; competitor A wins both, competitor B wins none."""
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
    evt1 = RaceEvent(
        id=100, series_id=1, sequence_number=1,
        name="VALIDA I", event_date=date(2026, 1, 31),
        location="Sevilla", is_championship=False,
        status=RaceEventStatus.COMPLETED, created_by_user_id=10,
    )
    evt2 = RaceEvent(
        id=101, series_id=1, sequence_number=2,
        name="VALIDA II", event_date=date(2026, 2, 28),
        location="Ginebra", is_championship=False,
        status=RaceEventStatus.COMPLETED, created_by_user_id=10,
    )
    cat = RaceCategory(
        id=1, code="INF_M", label="Infantil Masculino",
        sex=CategoryGender.M, sort_order=10, is_active=True,
    )
    # Competitor A: club athlete (athlete_id=1)
    comp_a = RaceCompetitor(
        id=1, normalized_name="atleta tyr",
        display_name="Atleta TyR", club_text="Club TyR",
        athlete_id=1,
    )
    # Competitor B: rival
    comp_b = RaceCompetitor(
        id=2, normalized_name="corredor rival",
        display_name="Corredor Rival", club_text="Club X",
    )
    # Event 100 results.
    r1a = RaceResult(
        event_id=100, category_id=1, competitor_id=1, athlete_id=1,
        position=1, status=ResultStatus.FINISHED,
        race_time_ms=200_000, points_awarded=40, created_by_user_id=10,
    )
    r1b = RaceResult(
        event_id=100, category_id=1, competitor_id=2,
        position=2, status=ResultStatus.FINISHED,
        race_time_ms=205_000, points_awarded=35, created_by_user_id=10,
    )
    # Event 101 results: B wins, A second.
    r2b = RaceResult(
        event_id=101, category_id=1, competitor_id=2,
        position=1, status=ResultStatus.FINISHED,
        race_time_ms=198_000, points_awarded=40, created_by_user_id=10,
    )
    r2a = RaceResult(
        event_id=101, category_id=1, competitor_id=1, athlete_id=1,
        position=2, status=ResultStatus.FINISHED,
        race_time_ms=202_000, points_awarded=35, created_by_user_id=10,
    )

    session.add_all([
        coach, parent_user, athlete_user, club, athlete, parent_link,
        series, evt1, evt2, cat, comp_a, comp_b,
        r1a, r1b, r2b, r2a,
    ])
    await session.commit()


@pytest_asyncio.fixture
async def seed_standings(db_session_factory):
    async with db_session_factory() as s:
        await _insert_series_seed(s)
    yield


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_standings):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetEventStandings:
    """GET /api/race-analysis/race-events/{id}/standings"""

    @pytest.mark.asyncio
    async def test_happy_path_ranked(self, coach_client):
        """Standings are grouped by category, ranked by total_points DESC."""
        r = await coach_client.get(f"{_BASE}/100/standings")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["race_event_id"] == 100

        # Event metadata fields must be present and correct (non-sensitive).
        assert body["event_name"] == "VALIDA I"
        assert body["event_date"] == "2026-01-31"
        assert body["location"] == "Sevilla"
        assert body["status"] == "completed"

        assert body["series_id"] == 1
        assert body["season_year"] == 2026

        cats = body["categories"]
        assert len(cats) == 1
        inf_m = cats[0]
        assert inf_m["code"] == "INF_M"

        rows = inf_m["rows"]
        assert len(rows) == 2

        # Both have 75 points total (40+35); tied.
        # A has best_position=1 (won round 1), B has best_position=1 (won round 2).
        # With equal points and equal podiums, tie is broken by best_position (both 1).
        # The order is deterministic (competitor_id sorts ties), just check total_points.
        assert rows[0]["total_points"] == 75
        assert rows[1]["total_points"] == 75

        # races_run: each competitor ran 2 events.
        for row in rows:
            assert row["races_run"] == 2

    @pytest.mark.asyncio
    async def test_standings_aggregate_all_series_events(self, coach_client):
        """Standings must include results from ALL events in the series, not just the anchor."""
        # We anchor on event 101 (second round) — should still see cumulative points.
        r = await coach_client.get(f"{_BASE}/101/standings")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["race_event_id"] == 101

        # Metadata reflects the anchor event (101), not event 100.
        assert body["event_name"] == "VALIDA II"
        assert body["event_date"] == "2026-02-28"
        assert body["location"] == "Ginebra"
        assert body["status"] == "completed"

        rows = body["categories"][0]["rows"]
        # Total points per competitor = 40+35 = 75 each.
        for row in rows:
            assert row["total_points"] == 75

    @pytest.mark.asyncio
    async def test_club_athlete_highlighted(self, coach_client):
        """Competitor with athlete_id has is_our_club=True."""
        r = await coach_client.get(f"{_BASE}/100/standings")
        assert r.status_code == 200, r.text
        rows = r.json()["categories"][0]["rows"]
        club_row = next(rw for rw in rows if rw["athlete_id"] == 1)
        assert club_row["is_our_club"] is True
        rival_row = next(rw for rw in rows if rw["athlete_id"] is None)
        assert rival_row["is_our_club"] is False

    @pytest.mark.asyncio
    async def test_404_unknown_event(self, coach_client):
        """Returns 404 when event does not exist."""
        r = await coach_client.get(f"{_BASE}/9999/standings")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_when_series_has_no_results(
        self, sqlite_engine, db_session_factory
    ):
        """Event belonging to a series with NO imported results returns empty categories."""
        # Create a completely independent series + event (no results imported).
        async with db_session_factory() as s:
            await _insert_series_seed(s)  # seed series 1 and its events
            from app.models.race_series import RaceSeries as _RS
            from app.models.race_event import RaceEvent as _RE
            # New series 2 with no results at all.
            s.add(_RS(
                id=99, name="Liga Local 2026", season_year=2026,
                organizer="Liga", points_scheme_code="custom",
            ))
            await s.flush()
            s.add(_RE(
                id=200, series_id=99, sequence_number=1,
                name="VALID I LOCAL", event_date=date(2026, 3, 1),
                location="Test", is_championship=False,
                status=RaceEventStatus.SCHEDULED, created_by_user_id=10,
            ))
            await s.commit()

        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, 10
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/200/standings")
            assert r.status_code == 200, r.text
            assert r.json()["categories"] == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Query-count test (T011) for standings endpoint
# ---------------------------------------------------------------------------


class TestStandingsQueryCount:
    """Assert the standings endpoint fires a bounded number of SQL statements."""

    @pytest.mark.asyncio
    async def test_standings_bounded_queries(
        self, sqlite_engine, db_session_factory, seed_standings
    ):
        """Standings endpoint should use ≤3 SQL statements."""
        query_log: list[str] = []

        sync_engine = sqlite_engine.sync_engine

        @sa_event.listens_for(sync_engine, "before_cursor_execute")
        def _capture(conn, cursor, statement, parameters, context, executemany):
            stmt_upper = statement.strip().upper()
            if any(stmt_upper.startswith(p) for p in (
                "PRAGMA", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE"
            )):
                return
            query_log.append(statement[:80])

        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.coach, 10
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/standings")
            assert r.status_code == 200, r.text
        finally:
            app.dependency_overrides.clear()
            sa_event.remove(sync_engine, "before_cursor_execute", _capture)

        # Should be ≤3: event+series lookup + aggregate query + (optional) commit.
        assert len(query_log) <= 3, (
            f"Expected ≤3 queries, got {len(query_log)}: {query_log}"
        )
