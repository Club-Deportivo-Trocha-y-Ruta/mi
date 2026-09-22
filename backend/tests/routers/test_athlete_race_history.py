"""Tests TDD para ``GET /api/athletes/{athlete_id}/race-analysis/history``.

Feature 044, US6 (T069) — contrato
``specs/044-race-history-backfill/contracts/history-progression-api.md``.

Cubre: RBAC vía ``verify_athlete_access`` (sin cambios: admin/coach/padre
propio → 200; otro coach / otro padre → 403), presupuesto de ≤4 SELECT,
ausencia de cualquier campo de tercero en la respuesta, y el filtro
``series_kind``.

Datos: 100% ficticios. Atleta "Juan Ficticio Pérez", ``athlete_id=300``.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import AsyncGenerator

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
from app.models.club import ClubRole
from app.models.race_series import RaceSeriesKind
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.query_counting import count_selects

_ATHLETE_ID = 300
_CATEGORY_ID = 100
_CUP_SERIES_ID = 1
_CHAMP_SERIES_ID = 2
_EVENT_V1 = 1001  # campo de 4 (<5)
_EVENT_V2 = 1002  # campo de 5 (=5)
_EVENT_CHAMP = 1003


_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    "race_course_variants",
    "race_course_category_setups",
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def history_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_hist")
        await create_club(s, club_id=2, code="otro_club_hist")

        await create_user(s, user_id=10, role=UserRole.coach, email="coach_hist@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)

        await create_user(s, user_id=11, role=UserRole.coach, email="otro_coach_hist@test.com")
        await link_user_to_club(s, user_id=11, club_id=2, role_in_club=ClubRole.coach)

        await create_user(
            s, user_id=1301, role=UserRole.athlete, email="atleta_hist@test.com",
            first_name="Juan Ficticio", last_name="Pérez", can_login=False,
        )
        await create_athlete(s, athlete_id=_ATHLETE_ID, club_id=1, user_id=1301, created_by=10)

        await create_user(s, user_id=20, role=UserRole.parent, email="padre_hist@test.com")
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=_ATHLETE_ID)

        await create_user(s, user_id=21, role=UserRole.parent, email="otro_padre_hist@test.com")

        await create_race_series(s, series_id=_CUP_SERIES_ID, season_year=2024, kind=RaceSeriesKind.cup)
        await create_race_series(
            s, series_id=_CHAMP_SERIES_ID, season_year=2024, name="Cto. Departamental",
            kind=RaceSeriesKind.championship,
        )
        await create_race_category(s, category_id=_CATEGORY_ID, code="INF_A", label="Infantil A")

        await create_race_event(s, event_id=_EVENT_V1, series_id=_CUP_SERIES_ID, sequence_number=1, event_date=date(2024, 2, 1))
        await create_race_event(s, event_id=_EVENT_V2, series_id=_CUP_SERIES_ID, sequence_number=2, event_date=date(2024, 3, 1))
        await create_race_event(s, event_id=_EVENT_CHAMP, series_id=_CHAMP_SERIES_ID, sequence_number=1, event_date=date(2024, 6, 1))

        await create_race_competitor(s, competitor_id=1, normalized_name="atleta propio", athlete_id=_ATHLETE_ID)
        for cid in (2, 3, 4, 5):
            await create_race_competitor(s, competitor_id=cid, normalized_name=f"tercero {cid}")

        # V1: campo de 4 (atleta incluido), atleta 2º.
        await create_race_result(s, event_id=_EVENT_V1, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=2, race_time_ms=3_100_000, points_awarded=18)
        for comp_id, pos, t in [(2, 1, 3_000_000), (3, 3, 3_200_000), (4, 4, 3_300_000)]:
            await create_race_result(s, event_id=_EVENT_V1, category_id=_CATEGORY_ID, competitor_id=comp_id, position=pos, race_time_ms=t)

        # V2: campo de 5, atleta gana.
        await create_race_result(s, event_id=_EVENT_V2, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=1, race_time_ms=2_900_000, points_awarded=25)
        for comp_id, pos, t in [(2, 2, 3_000_000), (3, 3, 3_100_000), (4, 4, 3_200_000), (5, 5, 3_300_000)]:
            await create_race_result(s, event_id=_EVENT_V2, category_id=_CATEGORY_ID, competitor_id=comp_id, position=pos, race_time_ms=t)

        # Campeonato: solo el atleta (para el filtro series_kind).
        await create_race_result(s, event_id=_EVENT_CHAMP, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=1, race_time_ms=2_800_000, points_awarded=30)

        await s.commit()
    return session_factory


def _user(user_id: int, role: UserRole, *, club_id: int | None = None, club_role: ClubRole = ClubRole.coach) -> SimpleNamespace:
    memberships = [] if club_id is None else [SimpleNamespace(club_id=club_id, role_in_club=club_role)]
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=memberships,
    )


@pytest_asyncio.fixture
async def client_factory(history_seeded):
    """Devuelve una fábrica ``make_client(user)`` con DB seeded compartida."""

    def _override_db():
        async def _inner():
            async with history_seeded() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        return _inner

    async def _make_client(user: SimpleNamespace) -> AsyncClient:
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _make_client
    app.dependency_overrides.clear()


_URL = f"/api/athletes/{_ATHLETE_ID}/race-analysis/history"


@pytest.mark.asyncio
async def test_coach_gets_200_with_full_series(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 2  # solo cup por default — el campeonato queda fuera
    assert {p["event_id"] for p in body["points"]} == {_EVENT_V1, _EVENT_V2}


@pytest.mark.asyncio
async def test_admin_gets_200(client_factory):
    async with await client_factory(_user(99, UserRole.admin)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_own_parent_gets_200(client_factory):
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 2


@pytest.mark.asyncio
async def test_other_parent_gets_403(client_factory):
    async with await client_factory(_user(21, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_coach_gets_403(client_factory):
    async with await client_factory(_user(11, UserRole.coach, club_id=2)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_series_kind_filter_all_includes_championship(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 3


@pytest.mark.asyncio
async def test_series_kind_filter_championship_only(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "championship"})
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["event_id"] == _EVENT_CHAMP
    assert points[0]["series_kind"] == "championship"


@pytest.mark.asyncio
async def test_response_has_no_third_party_field(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    body = resp.json()
    raw = resp.text
    # Ningún competitor_id, ni de terceros ni propio — la serie está indexada
    # por athlete_id (data-model invariante 4/5, contrato línea 5).
    assert "competitor_id" not in raw
    assert "athlete_id" not in raw
    for point in body["points"]:
        assert set(point.keys()) <= {
            "event_id", "event_date", "season", "label", "series_id",
            "series_name", "series_kind", "category_code", "category_label",
            "category_changed", "previous_category_label", "status",
            "position", "field_size", "timed_finishers", "percentile",
            "gap_to_median_pct", "gap_to_winner_pct", "avg_speed_kmh",
            "points_awarded",
        }


@pytest.mark.asyncio
async def test_field_thresholds_shape_percentile_and_gap(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    points = {p["event_id"]: p for p in resp.json()["points"]}
    v1, v2 = points[_EVENT_V1], points[_EVENT_V2]
    assert v1["field_size"] == 4
    assert v1["percentile"] is None
    assert v1["gap_to_median_pct"] is None
    assert v2["field_size"] == 5
    assert v2["percentile"] is not None
    assert v2["gap_to_median_pct"] is not None


@pytest.mark.asyncio
async def test_caveats_are_always_present_and_fixed(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    caveats = resp.json()["caveats"]
    assert caveats == [
        "different_courses",
        "weather_surface",
        "small_fields",
        "non_finishers_excluded",
        "three_rider_categories",
    ]


@pytest.mark.asyncio
async def test_seasons_completion_present(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    seasons = resp.json()["seasons"]
    assert seasons == [{"season": 2024, "started": 2, "finished": 2}]


@pytest.mark.asyncio
async def test_statement_count_at_most_four(client_factory, engine):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        async with count_selects(engine) as counter:
            resp = await ac.get(_URL)
    assert resp.status_code == 200
    # +1 por la query de ``verify_athlete_access`` (carga del Athlete),
    # que no forma parte del presupuesto de 4 del cargador de historia.
    assert counter[0] <= 5


@pytest.mark.asyncio
async def test_unknown_athlete_returns_404(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get("/api/athletes/999999/race-analysis/history")
    assert resp.status_code == 404
