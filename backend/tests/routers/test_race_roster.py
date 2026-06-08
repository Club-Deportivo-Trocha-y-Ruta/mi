"""Tests for the race-event roster (call-up) endpoints.

Feature: 007-competitions-consolidation, Wave C (US3 FR-022/FR-023).

Endpoints covered:
    GET    /api/race-analysis/race-events/{id}/roster
    POST   /api/race-analysis/race-events/{id}/roster
    PATCH  /api/race-analysis/race-events/{id}/roster/{entry_id}
    DELETE /api/race-analysis/race-events/{id}/roster/{entry_id}

Also covers reconciliation service logic (T028):
    - called_up_no_result: roster athlete with no result.
    - result_not_called_up: result athlete not in roster.

Test matrix:
--------------------------------------------------------------
GET /roster
 1  Happy path coach — empty roster
 2  Happy path coach — with entries
 3  Reconciliation: called_up_no_result
 4  Reconciliation: result_not_called_up
 5  404 — event does not exist
 6  Parent — own child visible
 7  Parent — other child filtered out (privacy invariant)

POST /roster
 8  Happy path coach — 201
 9  Happy path admin — 201
10  409 — duplicate entry
11  422 — athlete does not exist
12  404 — event does not exist
13  403 — parent write blocked

PATCH /roster/{entry_id}
14  Happy path — update status
15  Happy path — update note
16  404 — entry not found
17  404 — entry does not belong to event
18  403 — parent write blocked

DELETE /roster/{entry_id}
19  Happy path — 204
20  404 — entry not found
21  403 — parent write blocked

Privacy invariants (T028):
22  Parent cannot see another minor's roster entry
23  Reconciliation is empty for parent scope
--------------------------------------------------------------

Strategy:
- SQLite async in-memory + StaticPool — same pattern as test_race_events_crud.py.
- No real JWT; override get_current_user with stub.
- Fictitious data only (no real athlete names in fixtures).
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
from app.models.athlete import Athlete
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_event_roster import RaceEventRoster, RaceEventRosterStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "/api/race-analysis/race-events"
_ROSTER_URL = _BASE + "/{event_id}/roster"
_ENTRY_URL = _BASE + "/{event_id}/roster/{entry_id}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite in-memory engine with the tables needed for roster tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Explicit imports to ensure metadata is registered.
    from app.models.athlete import Athlete as _A, ParentAthlete as _PA  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_category import RaceCategory as _RC  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_event_roster import RaceEventRoster as _RER  # noqa: F401
    from app.models.race_import import RaceImport as _RI  # noqa: F401
    from app.models.race_result import RaceResult as _RR  # noqa: F401
    from app.models.race_series import RaceSeries as _RS  # noqa: F401
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
            "race_event_roster",
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
# Base seed (shared by most tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_base(db_session_factory):
    """Inserts minimal data:

    Users: coach id=10, admin id=1, parent id=5.
    Club: id=1.
    Athletes: id=20 (club 1), id=21 (club 1), id=22 (club 1).
    Each athlete has a user row (can_login=False as per conventions).
    parent_athlete: parent id=5 → athlete id=20 (owns child 20, NOT 21).
    Series: id=1 (2026).
    Events: id=100 (scheduled, no results), id=101 (completed).
    """
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.local", hashed_password="x",
            first_name="Coach", last_name="Test",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.local", hashed_password="x",
            first_name="Admin", last_name="Test",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        parent_user = User(
            id=5, email="parent@test.local", hashed_password="x",
            first_name="Parent", last_name="Test",
            role=UserRole.parent, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        # Ghost users for athletes (can_login=False per data model convention)
        ath_user_20 = User(
            id=20, email="ath20@test.local", hashed_password="x",
            first_name="Atleta", last_name="Veinte",
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        ath_user_21 = User(
            id=21, email="ath21@test.local", hashed_password="x",
            first_name="Atleta", last_name="Veintiuno",
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        ath_user_22 = User(
            id=22, email="ath22@test.local", hashed_password="x",
            first_name="Atleta", last_name="Veintidos",
            role=UserRole.parent, is_active=True, can_login=False,
            created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club TyR Test", code="TYRT")
        athlete_20 = Athlete(
            id=20, user_id=20, first_name="Atleta", last_name="Veinte",
            birth_date=date(2012, 3, 1), sex="M", club_id=1,
            created_by=10, created_at=datetime.now(timezone.utc),
        )
        athlete_21 = Athlete(
            id=21, user_id=21, first_name="Atleta", last_name="Veintiuno",
            birth_date=date(2013, 5, 15), sex="F", club_id=1,
            created_by=10, created_at=datetime.now(timezone.utc),
        )
        athlete_22 = Athlete(
            id=22, user_id=22, first_name="Atleta", last_name="Veintidos",
            birth_date=date(2011, 8, 20), sex="M", club_id=1,
            created_by=10, created_at=datetime.now(timezone.utc),
        )

        from app.models.athlete import ParentAthlete, FamilyRelationship
        link = ParentAthlete(
            parent_id=5, athlete_id=20,
            relationship_type=FamilyRelationship.padre,
        )

        series = RaceSeries(
            id=1, name="Copa Valle 2026", season_year=2026,
            organizer="Liga", points_scheme_code="copa_valle_2026",
        )
        event_100 = RaceEvent(
            id=100, series_id=1, sequence_number=1,
            name="Válida I Test", event_date=date(2026, 1, 31),
            location="Sevilla", is_championship=False,
            status=RaceEventStatus.SCHEDULED,
            created_by_user_id=10,
        )
        event_101 = RaceEvent(
            id=101, series_id=1, sequence_number=2,
            name="Válida II Test", event_date=date(2026, 2, 28),
            location="Ginebra", is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        session.add_all([
            coach, admin, parent_user,
            ath_user_20, ath_user_21, ath_user_22,
            club,
            athlete_20, athlete_21, athlete_22,
            link,
            series, event_100, event_101,
        ])
        await session.commit()
    yield


# ---------------------------------------------------------------------------
# Extended seed: roster entries
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_with_roster(db_session_factory, seed_base):
    """Adds two roster entries to event 100: athletes 20 and 21."""
    async with db_session_factory() as session:
        entry_a = RaceEventRoster(
            id=1,
            race_event_id=100,
            athlete_id=20,
            status=RaceEventRosterStatus.called_up,
            note=None,
            created_by_user_id=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        entry_b = RaceEventRoster(
            id=2,
            race_event_id=100,
            athlete_id=21,
            status=RaceEventRosterStatus.confirmed,
            note="Transporte confirmado",
            created_by_user_id=10,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add_all([entry_a, entry_b])
        await session.commit()
    yield


@pytest_asyncio.fixture
async def seed_with_roster_and_result(db_session_factory, seed_with_roster):
    """Adds a race result for athlete 22 (result but not in roster)
    and keeps athletes 20+21 in the roster (20 has no result → called_up_no_result)."""
    async with db_session_factory() as session:
        category = RaceCategory(
            id=1, code="INF_M", label="Infantil Masculino",
            sex=CategoryGender.M, sort_order=1, is_active=True,
        )
        competitor = RaceCompetitor(
            id=1, normalized_name="atleta veintidos",
            display_name="Atleta Veintidos", club_text="TyR",
        )
        result = RaceResult(
            event_id=100,
            category_id=1,
            competitor_id=1,
            athlete_id=22,  # not in roster → result_not_called_up
            position=1,
            status=ResultStatus.FINISHED,
            race_time_ms=300_000,
            points_awarded=25,
            created_by_user_id=10,
        )
        session.add_all([category, competitor, result])
        await session.commit()
    yield


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_base):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(sqlite_engine, db_session_factory, seed_base):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.admin, 1)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_base):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.parent, 5)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# Clients with pre-seeded roster ---

@pytest_asyncio.fixture
async def coach_client_roster(sqlite_engine, db_session_factory, seed_with_roster):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_roster_result(
    sqlite_engine, db_session_factory, seed_with_roster_and_result
):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client_roster(sqlite_engine, db_session_factory, seed_with_roster):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.parent, 5)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client_roster(sqlite_engine, db_session_factory, seed_with_roster):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.admin, 1)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: GET /roster
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_roster_empty(coach_client):
    """Test 1: Coach gets an empty roster for an event with no entries."""
    resp = await coach_client.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    data = resp.json()
    assert data["race_event_id"] == 100
    assert data["entries"] == []
    assert data["reconciliation"]["called_up_no_result"] == []
    assert data["reconciliation"]["result_not_called_up"] == []


@pytest.mark.asyncio
async def test_get_roster_with_entries(coach_client_roster):
    """Test 2: Coach sees all entries with correct fields."""
    resp = await coach_client_roster.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    data = resp.json()
    assert data["race_event_id"] == 100
    assert len(data["entries"]) == 2
    ids = {e["athlete_id"] for e in data["entries"]}
    assert ids == {20, 21}
    # Names must be present (display only — never logged)
    for entry in data["entries"]:
        assert "athlete_name" in entry
        assert entry["athlete_name"]  # non-empty
        assert "status" in entry
        assert "id" in entry


@pytest.mark.asyncio
async def test_get_roster_reconciliation_called_up_no_result(
    coach_client_roster_result,
):
    """Test 3: Athletes 20 and 21 are in roster; only 22 has a result.
    called_up_no_result = [20, 21]; result_not_called_up = [22]."""
    resp = await coach_client_roster_result.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    recon = resp.json()["reconciliation"]
    assert sorted(recon["called_up_no_result"]) == [20, 21]
    assert recon["result_not_called_up"] == [22]


@pytest.mark.asyncio
async def test_get_roster_reconciliation_result_not_called_up(
    sqlite_engine, db_session_factory, seed_with_roster_and_result
):
    """Test 4: result_not_called_up direction — athlete 22 has result, not in roster."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(_ROSTER_URL.format(event_id=100))
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    recon = resp.json()["reconciliation"]
    assert 22 in recon["result_not_called_up"]


@pytest.mark.asyncio
async def test_get_roster_event_not_found(coach_client):
    """Test 5: 404 when event does not exist."""
    resp = await coach_client.get(_ROSTER_URL.format(event_id=9999))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_roster_parent_own_child_visible(parent_client_roster):
    """Test 6: Parent with child 20 in roster sees that entry."""
    resp = await parent_client_roster.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    data = resp.json()
    # Parent (user 5) is linked to athlete 20 only.
    assert len(data["entries"]) == 1
    assert data["entries"][0]["athlete_id"] == 20


@pytest.mark.asyncio
async def test_get_roster_parent_other_child_filtered(parent_client_roster):
    """Test 7 / Privacy invariant 22: Parent cannot see athlete 21's entry."""
    resp = await parent_client_roster.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    ids = {e["athlete_id"] for e in resp.json()["entries"]}
    assert 21 not in ids  # athlete 21 belongs to no parent user=5


# ---------------------------------------------------------------------------
# Test: POST /roster
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_roster_coach_happy(coach_client):
    """Test 8: Coach adds an athlete — 201 with correct fields."""
    resp = await coach_client.post(
        _ROSTER_URL.format(event_id=100),
        json={"athlete_id": 20},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["athlete_id"] == 20
    assert data["status"] == "called_up"
    assert "id" in data
    assert "athlete_name" in data


@pytest.mark.asyncio
async def test_post_roster_admin_happy(admin_client):
    """Test 9: Admin adds an athlete — 201."""
    resp = await admin_client.post(
        _ROSTER_URL.format(event_id=100),
        json={"athlete_id": 21, "status": "confirmed", "note": "Ready"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "confirmed"
    assert data["note"] == "Ready"


@pytest.mark.asyncio
async def test_post_roster_duplicate_409(coach_client_roster):
    """Test 10: 409 when athlete already in roster for same event."""
    resp = await coach_client_roster.post(
        _ROSTER_URL.format(event_id=100),
        json={"athlete_id": 20},  # already seeded with id=1
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_roster_nonexistent_athlete_422(coach_client):
    """Test 11: 422 when athlete_id does not exist."""
    resp = await coach_client.post(
        _ROSTER_URL.format(event_id=100),
        json={"athlete_id": 9999},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_roster_event_not_found_404(coach_client):
    """Test 12: 404 when event does not exist."""
    resp = await coach_client.post(
        _ROSTER_URL.format(event_id=9999),
        json={"athlete_id": 20},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_roster_parent_forbidden(parent_client):
    """Test 13: 403 when parent tries to write the roster."""
    resp = await parent_client.post(
        _ROSTER_URL.format(event_id=100),
        json={"athlete_id": 20},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: PATCH /roster/{entry_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_roster_update_status(coach_client_roster):
    """Test 14: Coach updates status from called_up to confirmed."""
    resp = await coach_client_roster.patch(
        _ENTRY_URL.format(event_id=100, entry_id=1),
        json={"status": "confirmed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_patch_roster_update_note(coach_client_roster):
    """Test 15: Coach updates the note; status unchanged."""
    resp = await coach_client_roster.patch(
        _ENTRY_URL.format(event_id=100, entry_id=1),
        json={"note": "New note text"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["note"] == "New note text"
    assert data["status"] == "called_up"  # unchanged


@pytest.mark.asyncio
async def test_patch_roster_entry_not_found(coach_client_roster):
    """Test 16: 404 when entry_id does not exist."""
    resp = await coach_client_roster.patch(
        _ENTRY_URL.format(event_id=100, entry_id=9999),
        json={"status": "confirmed"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_roster_entry_wrong_event(coach_client_roster):
    """Test 17: 404 when entry_id belongs to a different event."""
    # entry_id=1 belongs to event_id=100, not 101
    resp = await coach_client_roster.patch(
        _ENTRY_URL.format(event_id=101, entry_id=1),
        json={"status": "withdrawn"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_roster_parent_forbidden(parent_client_roster):
    """Test 18: 403 when parent tries to update a roster entry."""
    resp = await parent_client_roster.patch(
        _ENTRY_URL.format(event_id=100, entry_id=1),
        json={"status": "confirmed"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: DELETE /roster/{entry_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_roster_entry_204(admin_client_roster):
    """Test 19: Admin deletes an entry — 204 no content."""
    resp = await admin_client_roster.delete(
        _ENTRY_URL.format(event_id=100, entry_id=1)
    )
    assert resp.status_code == 204

    # Verify it's gone.
    get_resp = await admin_client_roster.get(_ROSTER_URL.format(event_id=100))
    ids = {e["athlete_id"] for e in get_resp.json()["entries"]}
    assert 20 not in ids


@pytest.mark.asyncio
async def test_delete_roster_entry_not_found(coach_client_roster):
    """Test 20: 404 when entry_id does not exist."""
    resp = await coach_client_roster.delete(
        _ENTRY_URL.format(event_id=100, entry_id=9999)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_roster_parent_forbidden(parent_client_roster):
    """Test 21: 403 when parent tries to delete a roster entry."""
    resp = await parent_client_roster.delete(
        _ENTRY_URL.format(event_id=100, entry_id=1)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Privacy invariants (T028)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_privacy_parent_cannot_see_other_minor_entry(parent_client_roster):
    """Privacy invariant 22: Parent (user=5, child=20) cannot see athlete 21's entry."""
    resp = await parent_client_roster.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    for entry in resp.json()["entries"]:
        assert entry["athlete_id"] == 20, (
            "Parent must never receive another minor's roster entry"
        )


@pytest.mark.asyncio
async def test_privacy_parent_reconciliation_empty(parent_client_roster):
    """Privacy invariant 23: Reconciliation is always empty in parent scope."""
    resp = await parent_client_roster.get(_ROSTER_URL.format(event_id=100))
    assert resp.status_code == 200
    recon = resp.json()["reconciliation"]
    assert recon["called_up_no_result"] == [], (
        "Parent scope must not expose called_up_no_result (leaks other athletes)"
    )
    assert recon["result_not_called_up"] == [], (
        "Parent scope must not expose result_not_called_up (leaks other athletes)"
    )


# ---------------------------------------------------------------------------
# Migration test (T026) — pragmatic: assert table in Base.metadata + single head
# ---------------------------------------------------------------------------


def test_race_event_roster_table_in_metadata():
    """T026: race_event_roster table is registered in SQLAlchemy metadata."""
    from app.models import Base as _Base
    from app.models.race_event_roster import RaceEventRoster as _RER  # noqa: F401

    assert "race_event_roster" in _Base.metadata.tables, (
        "race_event_roster table must be registered in Base.metadata"
    )


def test_alembic_single_head():
    """T026: alembic heads returns exactly one head after adding the migration."""
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, (
        f"Expected exactly 1 Alembic head, got {len(heads)}: {heads}"
    )
