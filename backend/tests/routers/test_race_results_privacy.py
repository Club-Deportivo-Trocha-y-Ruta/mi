"""Privacy invariants for race results & standings (Wave A, T010).

Ley 1581 / FR-030 requirement:
  A parent user MUST only see their own child's rows in both
  the results and standings endpoints.  Another minor's name,
  competitor_id, and athlete_id MUST NOT appear in the payload.

Test structure
--------------
- Seed: two club athletes linked to two different parents.
- Competitor A → athlete 1 → parent 5 (test parent).
- Competitor B → athlete 2 → parent 6 (other parent, decoy).
- Competitor C → no athlete_id (rival, no club link).
- Parent 5 GETs results / standings → only Competitor A rows present.
- Assert Competitor B's competitor_id and athlete_id are absent.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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


def _make_user(role: UserRole, user_id: int) -> SimpleNamespace:
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
# Seed: two athletes, two parents, one rival
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_two_athletes(db_session_factory):
    """
    Users:
      - coach (id=10)
      - parent A (id=5) → athlete 1 (competitor_id=1)
      - parent B (id=6) → athlete 2 (competitor_id=2)  ← DECOY parent
      - athlete users (id=20, 21) — can_login=False

    Competitor 3 = pure rival (no athlete_id).

    Both athletes + rival ran event 100 in INF_M.
    """
    async with db_session_factory() as s:
        coach = User(
            id=10, email="coach@priv.test", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_a = User(
            id=5, email="parent_a@priv.test", hashed_password="x",
            first_name="Padre", last_name="A",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_b = User(
            id=6, email="parent_b@priv.test", hashed_password="x",
            first_name="Padre", last_name="B",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        ath_user_1 = User(
            id=20, email="ath1@priv.test", hashed_password="x",
            first_name="Atleta", last_name="Uno",
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        ath_user_2 = User(
            id=21, email="ath2@priv.test", hashed_password="x",
            first_name="Atleta", last_name="Dos",
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club TyR", code="TYR")
        athlete1 = Athlete(
            id=1, user_id=20, first_name="Atleta", last_name="Uno",
            birth_date=date(2012, 1, 1), sex="M",
            club_id=1, created_by=10,
        )
        athlete2 = Athlete(
            id=2, user_id=21, first_name="Atleta", last_name="Dos",
            birth_date=date(2013, 3, 3), sex="F",
            club_id=1, created_by=10,
        )
        link_a = ParentAthlete(id=1, parent_id=5, athlete_id=1, relationship_type="madre")
        link_b = ParentAthlete(id=2, parent_id=6, athlete_id=2, relationship_type="padre")
        series = RaceSeries(
            id=1, name="Copa Valle", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=100, series_id=1, sequence_number=4,
            name="VALIDA IV", event_date=date(2026, 5, 17),
            location="Cali", is_championship=False,
            status=RaceEventStatus.COMPLETED, created_by_user_id=10,
        )
        cat = RaceCategory(
            id=1, code="INF_M", label="Infantil Masculino",
            sex=CategoryGender.M, sort_order=10, is_active=True,
        )
        comp1 = RaceCompetitor(
            id=1, normalized_name="atleta uno",
            display_name="Atleta Uno", club_text="Club TyR",
            athlete_id=1,
        )
        comp2 = RaceCompetitor(
            id=2, normalized_name="atleta dos",
            display_name="Atleta Dos", club_text="Club TyR",
            athlete_id=2,
        )
        comp3 = RaceCompetitor(
            id=3, normalized_name="rival externo",
            display_name="Rival Externo", club_text="Club X",
        )
        results = [
            RaceResult(
                event_id=100, category_id=1, competitor_id=1, athlete_id=1,
                position=1, status=ResultStatus.FINISHED,
                race_time_ms=200_000, points_awarded=40, created_by_user_id=10,
            ),
            RaceResult(
                event_id=100, category_id=1, competitor_id=2, athlete_id=2,
                position=2, status=ResultStatus.FINISHED,
                race_time_ms=205_000, points_awarded=35, created_by_user_id=10,
            ),
            RaceResult(
                event_id=100, category_id=1, competitor_id=3,
                position=3, status=ResultStatus.FINISHED,
                race_time_ms=210_000, points_awarded=30, created_by_user_id=10,
            ),
        ]
        s.add_all([
            coach, parent_a, parent_b, ath_user_1, ath_user_2,
            club, athlete1, athlete2, link_a, link_b,
            series, event, cat, comp1, comp2, comp3,
            *results,
        ])
        await s.commit()
    yield


# ---------------------------------------------------------------------------
# Privacy invariant tests
# ---------------------------------------------------------------------------


class TestParentScopingPrivacyResults:
    """Parent 5 (owns athlete 1 / competitor 1) must NOT see athlete 2 / competitor 2."""

    @pytest.mark.asyncio
    async def test_parent_results_only_own_child(
        self, sqlite_engine, db_session_factory, seed_two_athletes
    ):
        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.parent, 5
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/results")
            assert r.status_code == 200, r.text
            body = r.json()
        finally:
            app.dependency_overrides.clear()

        all_rows = [row for cat in body["categories"] for row in cat["rows"]]

        # Parent A's child is competitor 1 / athlete 1 → MUST appear.
        own_child_ids = {row["competitor_id"] for row in all_rows}
        assert 1 in own_child_ids, "Own child (competitor_id=1) must be in results."

        # Competitor 2 (other child) and competitor 3 (rival) MUST be absent.
        assert 2 not in own_child_ids, (
            "Competitor 2 (another minor) must NOT appear in parent-scoped results."
        )
        assert 3 not in own_child_ids, (
            "Competitor 3 (rival, no athlete link) must NOT appear in parent-scoped results."
        )

        # Athlete 2 must not be disclosed via athlete_id field.
        athlete_ids_in_response = {row["athlete_id"] for row in all_rows}
        assert 2 not in athlete_ids_in_response, (
            "athlete_id=2 (another minor) must NOT appear in parent-scoped results."
        )

    @pytest.mark.asyncio
    async def test_parent_results_display_name_of_other_child_absent(
        self, sqlite_engine, db_session_factory, seed_two_athletes
    ):
        """Serialised JSON must not contain the display_name of another minor."""
        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.parent, 5
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/results")
            assert r.status_code == 200, r.text
            raw_json = r.text
        finally:
            app.dependency_overrides.clear()

        # "Atleta Dos" is the display_name of competitor 2 — must not be in the response.
        assert "Atleta Dos" not in raw_json, (
            "display_name of another minor must NOT appear in parent-scoped response."
        )


class TestParentScopingPrivacyStandings:
    """Parent 5 must NOT see athlete 2 / competitor 2 in standings."""

    @pytest.mark.asyncio
    async def test_parent_standings_only_own_child(
        self, sqlite_engine, db_session_factory, seed_two_athletes
    ):
        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.parent, 5
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/standings")
            assert r.status_code == 200, r.text
            body = r.json()
        finally:
            app.dependency_overrides.clear()

        all_rows = [row for cat in body["categories"] for row in cat["rows"]]
        competitor_ids = {row["competitor_id"] for row in all_rows}

        assert 1 in competitor_ids, "Own child must appear in standings."
        assert 2 not in competitor_ids, (
            "Competitor 2 (another minor) must NOT appear in parent-scoped standings."
        )
        assert 3 not in competitor_ids, (
            "Rival competitor must NOT appear in parent-scoped standings."
        )

    @pytest.mark.asyncio
    async def test_parent_no_children_sees_empty(
        self, sqlite_engine, db_session_factory, seed_two_athletes
    ):
        """A parent with no linked children sees zero rows (not a 403)."""
        # Add a parent with no children.
        async with db_session_factory() as s:
            lone_parent = User(
                id=99, email="lone@priv.test", hashed_password="x",
                first_name="Lone", last_name="Parent",
                role=UserRole.parent, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
            s.add(lone_parent)
            await s.commit()

        app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
        app.dependency_overrides[get_current_user] = lambda: _make_user(
            UserRole.parent, 99
        )
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                r = await ac.get(f"{_BASE}/100/results")
            assert r.status_code == 200, r.text
            assert r.json()["categories"] == []
        finally:
            app.dependency_overrides.clear()
