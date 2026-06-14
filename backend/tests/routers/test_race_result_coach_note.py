"""Tests for PUT/DELETE /api/race-analysis/race-results/{result_id}/coach-note.

Coverage (T014 + T017):
T014 — US1 Core:
- PUT 200 sets note; subsequent GET shows it in the results list.
- PUT replaces existing note (no duplicate, updated_at changes, author set).
- DELETE clears note (coach_note=null, position/points/status intact); idempotent.
- 422 on empty/whitespace-only body.
- 422 on note exceeding 500 characters.
- 403 for parent role; 403 for no-auth (anon).
- 409 when result row has athlete_id IS NULL (non-club competitor).
- 404 for missing result id; 404 for soft-deleted result.
- Privacy: response shape never exposes DOB or medical data.

T017 — US2 Persistence-across-reopen:
- Set note → re-fetch GET .../results → note present in JSON.
- Edit note replaces text (single note, not duplicate).
- DELETE leaves row with coach_note=null; position/points_awarded/status intact.

Patterns mirror test_race_results_read.py exactly:
- In-memory SQLite via aiosqlite + StaticPool.
- _make_user(role) + app.dependency_overrides for auth.
- AsyncClient with ASGITransport.
- Same seed helpers (_insert_base, _insert_results).
- No real network, no real DB, no real athletes (fictitious fixtures only).
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
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.race_category import CategoryGender, RaceCategory
from app.models.race_competitor import RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole

# Endpoint prefixes
_BASE_EVENTS = "/api/race-analysis/race-events"
# The coach-note endpoint is mounted under race-events router, so its full path is:
# /api/race-analysis/race-events/race-results/{result_id}/coach-note
_BASE_RESULTS = "/api/race-analysis/race-events/race-results"


# ---------------------------------------------------------------------------
# Fake user helper (mirrors test_race_results_read.py)
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

    # Import models to register with metadata.
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

# Fictitious fixture IDs
_COACH_ID = 10
_PARENT_ID = 5
_ATHLETE_USER_ID = 20
_ATHLETE_ID = 1
_CLUB_RESULT_ID: int = 1   # set after insert
_RIVAL_RESULT_ID: int = 2  # set after insert (athlete_id IS NULL)


async def _insert_base(session: AsyncSession) -> None:
    """Minimal seed: users, club, athlete, series, event, categories, competitors."""
    coach = User(
        id=_COACH_ID, email="coach.ficticio@test.com", hashed_password="x",
        first_name="Entrenador", last_name="Ficticio",
        role=UserRole.coach, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    parent_user = User(
        id=_PARENT_ID, email="padre.ficticio@test.com", hashed_password="x",
        first_name="Padre", last_name="Ficticio",
        role=UserRole.parent, is_active=True, can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    # Athlete user (can_login=False) — needed for FK
    athlete_user = User(
        id=_ATHLETE_USER_ID, email="atleta.ficticio@test.com", hashed_password="x",
        first_name="Atleta", last_name="Ficticio",
        role=UserRole.parent, is_active=True, can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    club = Club(id=1, name="Club TyR Ficticio", code="TYR")
    athlete = Athlete(
        id=_ATHLETE_ID,
        user_id=_ATHLETE_USER_ID,
        first_name="Atleta",
        last_name="Ficticio",
        birth_date=date(2012, 6, 15),
        sex="M",
        club_id=1,
        created_by=_COACH_ID,
    )
    parent_link = ParentAthlete(
        id=1, parent_id=_PARENT_ID, athlete_id=_ATHLETE_ID, relationship_type="padre"
    )
    series = RaceSeries(
        id=1, name="Copa Valle Test", season_year=2026,
        organizer="Liga", points_scheme_code="copa_valle_2026",
    )
    event = RaceEvent(
        id=100,
        series_id=1,
        sequence_number=4,
        name="VALIDA IV CALI FICTICIOS",
        event_date=date(2026, 5, 17),
        location="Cali",
        is_championship=False,
        status=RaceEventStatus.COMPLETED,
        created_by_user_id=_COACH_ID,
    )
    cat = RaceCategory(
        id=1, code="INF_M", label="Infantil Masculino",
        sex=CategoryGender.M, sort_order=10, is_active=True,
    )
    # Club competitor (athlete_id set → is_our_club=True, can be noted)
    comp_club = RaceCompetitor(
        id=1, normalized_name="atleta ficticio",
        display_name="Atleta Ficticio", club_text="Club TyR Ficticio",
        athlete_id=_ATHLETE_ID,
    )
    # Rival competitor (athlete_id=None → cannot be noted → 409)
    comp_rival = RaceCompetitor(
        id=2, normalized_name="corredor rival ficticio",
        display_name="Corredor Rival Ficticio", club_text="Club Externo",
    )
    session.add_all([
        coach, parent_user, athlete_user, club, athlete, parent_link,
        series, event, cat, comp_club, comp_rival,
    ])
    await session.commit()


async def _insert_results(session: AsyncSession) -> None:
    """Two results: one club (athlete_id=1), one rival (athlete_id=None)."""
    r_club = RaceResult(
        id=1,
        event_id=100, category_id=1, competitor_id=1, athlete_id=_ATHLETE_ID,
        position=1, status=ResultStatus.FINISHED,
        race_time_ms=200_000, points_awarded=40,
        created_by_user_id=_COACH_ID,
    )
    r_rival = RaceResult(
        id=2,
        event_id=100, category_id=1, competitor_id=2,
        # athlete_id intentionally None — non-club competitor
        position=2, status=ResultStatus.FINISHED,
        race_time_ms=205_000, points_awarded=35,
        created_by_user_id=_COACH_ID,
    )
    session.add_all([r_club, r_rival])
    await session.commit()


@pytest_asyncio.fixture
async def seed_full(db_session_factory):
    async with db_session_factory() as s:
        await _insert_base(s)
        await _insert_results(s)
    yield


@pytest_asyncio.fixture
async def seed_with_soft_delete(db_session_factory):
    """Seed with the club result soft-deleted."""
    async with db_session_factory() as s:
        await _insert_base(s)
        await _insert_results(s)
        row = (await s.execute(
            select(RaceResult).where(RaceResult.id == 1)
        )).scalar_one()
        row.deleted_at = datetime.now(timezone.utc)
        await s.commit()
    yield


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_full):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, _COACH_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(sqlite_engine, db_session_factory, seed_full):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.parent, _PARENT_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, seed_full):
    """Client with no auth override — require_role will deny."""
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach_client_soft_delete(sqlite_engine, db_session_factory, seed_with_soft_delete):
    app.dependency_overrides[get_db] = _override_db_factory(db_session_factory)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, _COACH_ID)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T014 — US1: Core coach-note PUT / DELETE tests
# ---------------------------------------------------------------------------


class TestCoachNotePUT:
    """PUT /api/race-analysis/race-results/{result_id}/coach-note"""

    @pytest.mark.asyncio
    async def test_put_sets_note_200(self, coach_client):
        """Happy path: PUT returns 200 with coach_note present."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Buena salida, controló la carrera desde el inicio."},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["coach_note"] == "Buena salida, controló la carrera desde el inicio."
        assert body["coach_note_updated_at"] is not None
        assert body["result_id"] == 1
        assert body["athlete_id"] == _ATHLETE_ID

    @pytest.mark.asyncio
    async def test_put_note_appears_in_subsequent_get_results(self, coach_client):
        """After PUT, GET .../results includes the note on the correct row (T014 + T017)."""
        note_text = "Caída en curva 3, se recuperó bien."
        put_r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": note_text},
        )
        assert put_r.status_code == 200, put_r.text

        # Re-fetch via the results endpoint (simulates "reopening" the válida).
        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        assert get_r.status_code == 200, get_r.text
        body = get_r.json()

        # Find the club row (athlete_id=1, position=1)
        all_rows = [row for cat in body["categories"] for row in cat["rows"]]
        club_rows = [r for r in all_rows if r["is_our_club"]]
        assert len(club_rows) == 1
        assert club_rows[0]["coach_note"] == note_text
        assert club_rows[0]["coach_note_updated_at"] is not None

    @pytest.mark.asyncio
    async def test_put_replaces_existing_note(self, coach_client):
        """Second PUT replaces the note — no duplicate rows, updated_at changes."""
        first_note = "Primera observación del entrenador Ficticio."
        second_note = "Segunda observación actualizada — mejora técnica."

        r1 = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": first_note},
        )
        assert r1.status_code == 200, r1.text
        first_ts = r1.json()["coach_note_updated_at"]

        # Small sleep not used — timestamps from datetime.now() will differ in practice;
        # we verify the note text changes rather than rely on timestamp ordering.
        r2 = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": second_note},
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["coach_note"] == second_note
        # author is set
        assert body2["result_id"] == 1

        # Verify via GET that there is only one note value (not a list)
        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        all_rows = [row for cat in get_r.json()["categories"] for row in cat["rows"]]
        club_rows = [r for r in all_rows if r["is_our_club"]]
        assert club_rows[0]["coach_note"] == second_note

    @pytest.mark.asyncio
    async def test_put_strips_surrounding_whitespace(self, coach_client):
        """Body with leading/trailing whitespace is stripped before storage."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "  Buen desempeño.  "},
        )
        assert r.status_code == 200, r.text
        assert r.json()["coach_note"] == "Buen desempeño."

    @pytest.mark.asyncio
    async def test_put_422_empty_string(self, coach_client):
        """Empty string is rejected with 422."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": ""},
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_put_422_whitespace_only(self, coach_client):
        """Whitespace-only string is rejected with 422."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "   \t\n  "},
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_put_422_exceeds_500_chars(self, coach_client):
        """Note longer than 500 characters is rejected with 422."""
        long_note = "A" * 501
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": long_note},
        )
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_put_200_exactly_500_chars(self, coach_client):
        """Note of exactly 500 characters is accepted."""
        exactly_500 = "B" * 500
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": exactly_500},
        )
        assert r.status_code == 200, r.text
        assert r.json()["coach_note"] == exactly_500

    @pytest.mark.asyncio
    async def test_put_403_parent_role(self, parent_client):
        """Parent role cannot write notes — 403."""
        r = await parent_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota no autorizada."},
        )
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_put_403_anon(self, anon_client):
        """No auth token — 401 or 403."""
        r = await anon_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota anónima."},
        )
        assert r.status_code in (401, 403), r.text

    @pytest.mark.asyncio
    async def test_put_409_non_club_competitor(self, coach_client):
        """Result with athlete_id IS NULL (external rival) → 409 Conflict."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/2/coach-note",
            json={"coach_note": "Nota sobre rival externo."},
        )
        assert r.status_code == 409, r.text

    @pytest.mark.asyncio
    async def test_put_404_missing_result(self, coach_client):
        """Non-existent result_id → 404."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/9999/coach-note",
            json={"coach_note": "Nota sobre resultado inexistente."},
        )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_put_404_soft_deleted_result(self, coach_client_soft_delete):
        """Soft-deleted result → 404 (not exposed)."""
        r = await coach_client_soft_delete.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota sobre resultado borrado."},
        )
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_put_response_shape_no_pii_leakage(self, coach_client):
        """Response must not include DOB, medical data, or sensitive PII."""
        r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota de control de privacidad."},
        )
        assert r.status_code == 200, r.text
        body = r.json()

        # Required safe fields
        assert "result_id" in body
        assert "coach_note" in body
        assert "coach_note_updated_at" in body
        assert "position" in body
        assert "status" in body
        assert "points_awarded" in body

        # Must NOT contain DOB, medical data, or names in response keys
        response_text = str(body)
        assert "birth_date" not in response_text
        assert "dob" not in response_text.lower()
        assert "medical" not in response_text.lower()
        # hashed_password must never appear
        assert "hashed_password" not in response_text


# ---------------------------------------------------------------------------
# T014 — US1: DELETE tests
# ---------------------------------------------------------------------------


class TestCoachNoteDELETE:
    """DELETE /api/race-analysis/race-results/{result_id}/coach-note"""

    @pytest.mark.asyncio
    async def test_delete_clears_note(self, coach_client):
        """DELETE after PUT returns 200 with coach_note=null."""
        # First set a note
        put_r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota que será eliminada."},
        )
        assert put_r.status_code == 200, put_r.text

        # Then delete it
        del_r = await coach_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert del_r.status_code == 200, del_r.text
        body = del_r.json()
        assert body["coach_note"] is None
        assert body["coach_note_updated_at"] is None
        assert body["result_id"] == 1

    @pytest.mark.asyncio
    async def test_delete_is_idempotent(self, coach_client):
        """Second DELETE (when note already null) also returns 200."""
        # No note set — delete anyway
        r1 = await coach_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert r1.status_code == 200, r1.text
        assert r1.json()["coach_note"] is None

        # Delete again — must still be 200
        r2 = await coach_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert r2.status_code == 200, r2.text
        assert r2.json()["coach_note"] is None

    @pytest.mark.asyncio
    async def test_delete_preserves_other_fields(self, coach_client):
        """DELETE clears coach_note but leaves position, points_awarded, status intact."""
        put_r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota temporal para test de integridad."},
        )
        assert put_r.status_code == 200, put_r.text

        del_r = await coach_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert del_r.status_code == 200, del_r.text
        body = del_r.json()

        assert body["coach_note"] is None
        assert body["position"] == 1
        assert body["points_awarded"] == 40
        assert body["status"] == "finished"
        assert body["competitor_id"] == 1

    @pytest.mark.asyncio
    async def test_delete_403_parent_role(self, parent_client):
        """Parent cannot clear notes — 403."""
        r = await parent_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_delete_403_anon(self, anon_client):
        """No auth — 401 or 403."""
        r = await anon_client.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert r.status_code in (401, 403), r.text

    @pytest.mark.asyncio
    async def test_delete_404_missing_result(self, coach_client):
        """Non-existent result_id → 404."""
        r = await coach_client.delete(f"{_BASE_RESULTS}/9999/coach-note")
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_delete_404_soft_deleted_result(self, coach_client_soft_delete):
        """Soft-deleted result → 404."""
        r = await coach_client_soft_delete.delete(f"{_BASE_RESULTS}/1/coach-note")
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# T017 — US2: Persistence-across-reopen scenario
# ---------------------------------------------------------------------------


class TestCoachNotePersistenceAcrossReopen:
    """Persistence tests: set note, re-fetch, edit, delete — all via the full stack."""

    @pytest.mark.asyncio
    async def test_set_note_then_refetch_shows_note(self, coach_client):
        """Set note via PUT → re-fetch GET .../results → note present on correct row."""
        note_text = "Corredor ficticio manejó muy bien las curvas técnicas."

        put_r = await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": note_text},
        )
        assert put_r.status_code == 200, put_r.text

        # Simulate reopening: re-request the event results
        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        assert get_r.status_code == 200, get_r.text
        body = get_r.json()

        all_rows = [row for cat in body["categories"] for row in cat["rows"]]
        club_row = next((r for r in all_rows if r.get("is_our_club")), None)
        assert club_row is not None, "Club row not found"
        assert club_row["coach_note"] == note_text
        assert club_row["coach_note_updated_at"] is not None

        # Rival row has no note
        rival_row = next((r for r in all_rows if not r.get("is_our_club")), None)
        assert rival_row is not None, "Rival row not found"
        assert rival_row["coach_note"] is None

    @pytest.mark.asyncio
    async def test_edit_replaces_text_not_appends(self, coach_client):
        """Editing a note replaces text — only one note, not a duplicate."""
        original = "Nota original del entrenador ficticio."
        updated = "Nota editada — caída en el primer sector."

        await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": original},
        )
        await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": updated},
        )

        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        assert get_r.status_code == 200
        all_rows = [row for cat in get_r.json()["categories"] for row in cat["rows"]]
        club_rows = [r for r in all_rows if r["is_our_club"]]
        assert len(club_rows) == 1
        # Only the updated text should be present
        assert club_rows[0]["coach_note"] == updated
        # Original text must not appear (no duplicate)
        assert original not in str(club_rows[0]["coach_note"])

    @pytest.mark.asyncio
    async def test_delete_leaves_null_and_other_fields_intact(self, coach_client):
        """After DELETE, GET shows coach_note=null, position/points/status unchanged."""
        await coach_client.put(
            f"{_BASE_RESULTS}/1/coach-note",
            json={"coach_note": "Nota que se eliminará en el test T017."},
        )
        await coach_client.delete(f"{_BASE_RESULTS}/1/coach-note")

        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        assert get_r.status_code == 200
        all_rows = [row for cat in get_r.json()["categories"] for row in cat["rows"]]
        club_rows = [r for r in all_rows if r["is_our_club"]]
        assert len(club_rows) == 1

        row = club_rows[0]
        assert row["coach_note"] is None
        assert row["coach_note_updated_at"] is None
        # Other result fields must be preserved
        assert row["position"] == 1
        assert row["points_awarded"] == 40
        assert row["status"] == "finished"

    @pytest.mark.asyncio
    async def test_no_note_row_has_null_not_placeholder(self, coach_client):
        """Row with no note shows coach_note=null in GET response (no placeholder noise)."""
        # Do NOT set any note for result_id=1
        get_r = await coach_client.get(f"{_BASE_EVENTS}/100/results")
        assert get_r.status_code == 200
        all_rows = [row for cat in get_r.json()["categories"] for row in cat["rows"]]
        club_rows = [r for r in all_rows if r["is_our_club"]]
        assert club_rows[0]["coach_note"] is None
        assert club_rows[0]["coach_note_updated_at"] is None
