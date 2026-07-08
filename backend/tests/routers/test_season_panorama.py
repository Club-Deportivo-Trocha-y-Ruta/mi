"""Tests de integración para ``GET /api/race-analysis/insights/season/{year}`` (PR3).

Cubre:
- Coach ve panorama agregado de su club a través de varias válidas.
- Agregación correcta: races_count, wins, podiums, best_position, total_points.
- Ordenamiento por puntos desc.
- Resultados borrados (deleted_at) y de otra temporada NO cuentan.
- Parent → 403 (RBAC: solo coach/admin).
- Admin sin club_id → panorama global (todos los clubes).
- Coach con club_id ajeno → 403.

Estrategia: SQLite async in-memory con override de get_db / get_current_user
(idéntica a test_club_insights_by_race.py).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
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
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
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
    link_user_to_club,
)

_TABLES_NEEDED = [
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
    "athlete_ai_insights",
]


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_NEEDED]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory) -> async_sessionmaker[AsyncSession]:
    """Escenario:
    - club 1 (TyR), club 2 (otro).
    - coach_10 en club 1, coach_11 en club 2, admin_99 sin club.
    - parent_20 en club 1.
    - athlete_144 (club1), athlete_145 (club1), athlete_200 (club2).
    - Temporada 2026: serie 1 con 2 válidas (event 5 y event 6).
    - Temporada 2025: serie 2 con 1 válida (event 7) — NO debe contar para 2026.
    - athlete_144: V4 pos=1 (40pts), V5 pos=3 (20pts) → races=2, wins=1, podiums=2,
      best=1, points=60.
    - athlete_145: V4 pos=5 (10pts), V5 borrada (deleted) → races=1, wins=0,
      podiums=0, best=5, points=10.
    - athlete_200 (club2): V4 pos=2 (30pts) → solo aparece en panorama global.
    - athlete_144 también corrió en 2025 (event 7) pos=1 → NO cuenta para 2026.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_club(s, club_id=2, name="Otro Club", code="otro")

        await create_user(s, user_id=10, role=UserRole.coach, email="coach1@test.com")
        await create_user(s, user_id=11, role=UserRole.coach, email="coach2@test.com")
        await create_user(s, user_id=20, role=UserRole.parent, email="parent@test.com")
        await create_user(s, user_id=99, role=UserRole.admin, email="admin@test.com")
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_user(s, user_id=145, role=UserRole.athlete, can_login=False)
        await create_user(s, user_id=200, role=UserRole.athlete, can_login=False)

        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await link_user_to_club(s, user_id=11, club_id=2, role_in_club=ClubRole.coach)
        await link_user_to_club(s, user_id=20, club_id=1, role_in_club=ClubRole.parent)

        await create_athlete(
            s, athlete_id=144, first_name="Juan", last_name="Garcia",
            club_id=1, user_id=144,
        )
        await create_athlete(
            s, athlete_id=145, first_name="Maria", last_name="Perez",
            club_id=1, user_id=145,
        )
        await create_athlete(
            s, athlete_id=200, first_name="Pedro", last_name="Lopez",
            club_id=2, user_id=200,
        )

        # Temporada 2026
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(
            s, event_id=5, series_id=1, sequence_number=4,
            name="Válida IV", event_date=date(2026, 5, 17), location="Cali",
        )
        await create_race_event(
            s, event_id=6, series_id=1, sequence_number=5,
            name="Válida V", event_date=date(2026, 8, 1), location="Palmira",
        )

        # Temporada 2025 (no debe contar para 2026)
        await create_race_series(s, series_id=2, season_year=2025)
        await create_race_event(
            s, event_id=7, series_id=2, sequence_number=4,
            name="Válida IV 2025", event_date=date(2025, 5, 17), location="Cali",
        )

        # Competidores
        await create_race_competitor(
            s, competitor_id=501, normalized_name="juan garcia",
            display_name="Juan Garcia", athlete_id=144,
        )
        await create_race_competitor(
            s, competitor_id=502, normalized_name="maria perez",
            display_name="Maria Perez", athlete_id=145,
        )
        await create_race_competitor(
            s, competitor_id=503, normalized_name="pedro lopez",
            display_name="Pedro Lopez", athlete_id=200,
        )

        # ── athlete_144: 2026 V4 pos1 (40), V5 pos3 (20) ──
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=40,
        )
        await create_race_result(
            s, event_id=6, category_id=100, competitor_id=501, athlete_id=144,
            position=3, points_awarded=20,
        )
        # athlete_144 en 2025 (no cuenta)
        await create_race_result(
            s, event_id=7, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=40,
        )

        # ── athlete_145: 2026 V4 pos5 (10), V5 borrada ──
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=502, athlete_id=145,
            position=5, points_awarded=10,
        )
        await create_race_result(
            s, event_id=6, category_id=100, competitor_id=502, athlete_id=145,
            position=2, points_awarded=30,
            deleted_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        )

        # ── athlete_200 (club2): 2026 V4 pos2 (30) ──
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=503, athlete_id=200,
            position=2, points_awarded=30,
        )

        await s.commit()

    return session_factory


def _make_user(user_id: int, role: UserRole, email: str):
    memberships = []
    if role == UserRole.coach and user_id == 10:
        memberships = [SimpleNamespace(user_id=10, club_id=1, role_in_club=ClubRole.coach)]
    elif role == UserRole.coach and user_id == 11:
        memberships = [SimpleNamespace(user_id=11, club_id=2, role_in_club=ClubRole.coach)]
    elif role == UserRole.parent and user_id == 20:
        memberships = [SimpleNamespace(user_id=20, club_id=1, role_in_club=ClubRole.parent)]
    return SimpleNamespace(
        id=user_id, role=role, email=email,
        is_active=True, can_login=True, club_memberships=memberships,
    )


@pytest_asyncio.fixture
async def client_factory(seeded_factory):
    async def _make(user_id: int, role: UserRole, email: str):
        fake_user = _make_user(user_id, role, email)

        async def _override_db() -> AsyncGenerator[AsyncSession, None]:
            async with seeded_factory() as s:
                yield s

        async def _override_user():
            return fake_user

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coach_panorama_agrega_a_traves_de_validas(client_factory):
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")

    assert r.status_code == 200
    data = r.json()
    assert data["season"] == 2026
    # club1 tiene athlete_144 y athlete_145 con resultados 2026 (no athlete_200, club2)
    assert data["total_athletes"] == 2

    by_id = {i["athlete_id"]: i for i in data["items"]}

    a144 = by_id[144]
    assert a144["athlete_display_name"] == "Juan Garcia"
    assert a144["races_count"] == 2
    assert a144["wins"] == 1
    assert a144["podiums"] == 2
    assert a144["best_position"] == 1
    assert a144["total_points"] == 60

    a145 = by_id[145]
    assert a145["races_count"] == 1  # V5 borrada no cuenta
    assert a145["wins"] == 0
    assert a145["podiums"] == 0
    assert a145["best_position"] == 5
    assert a145["total_points"] == 10


@pytest.mark.asyncio
async def test_orden_por_puntos_desc(client_factory):
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")
    items = r.json()["items"]
    # 144 (60pts) antes que 145 (10pts)
    assert items[0]["athlete_id"] == 144
    assert items[1]["athlete_id"] == 145


@pytest.mark.asyncio
async def test_otra_temporada_no_cuenta(client_factory):
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2025")
    data = r.json()
    # Solo athlete_144 corrió en 2025 (club1)
    assert data["total_athletes"] == 1
    assert data["items"][0]["athlete_id"] == 144
    assert data["items"][0]["races_count"] == 1


@pytest.mark.asyncio
async def test_parent_403(client_factory):
    async with await client_factory(20, UserRole.parent, "parent@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_panorama_global_incluye_todos_los_clubes(client_factory):
    async with await client_factory(99, UserRole.admin, "admin@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")
    data = r.json()
    # Sin club_id, admin ve global: 144, 145 (club1) + 200 (club2)
    ids = {i["athlete_id"] for i in data["items"]}
    assert ids == {144, 145, 200}


@pytest.mark.asyncio
async def test_admin_filtra_por_club_id(client_factory):
    async with await client_factory(99, UserRole.admin, "admin@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026?club_id=2")
    data = r.json()
    ids = {i["athlete_id"] for i in data["items"]}
    assert ids == {200}


@pytest.mark.asyncio
async def test_coach_club_ajeno_403(client_factory):
    # coach_10 (club1) pide club_id=2 → 403
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026?club_id=2")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_panorama_ignora_resultados_de_campeonato_nacional(
    seeded_factory, client_factory
):
    """Regresión (spec 023 SC-004): la exclusión de campeonatos de panorama
    de temporada usa ``race_series.kind`` (ver filtro ``rs.kind = 'cup'`` en
    ``season_panorama.py``), NO ``level``. Insertar resultados de un
    campeonato NACIONAL (Pereira 2026) para athlete_144 no debe alterar el
    panorama frente al baseline sin esos resultados.
    """
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r_before = await client.get("/api/race-analysis/insights/season/2026")
    baseline = r_before.json()

    async with seeded_factory() as s:
        await create_race_series(
            s,
            series_id=900,
            season_year=2026,
            name="Campeonato Nacional Fedeciclismo 2026",
            kind=RaceSeriesKind.championship,
            level=RaceSeriesLevel.national,
        )
        await create_race_event(
            s,
            event_id=900,
            series_id=900,
            sequence_number=1,
            name="Campeonato Nacional",
            event_date=date(2026, 7, 18),
            location="Pereira",
        )
        # athlete_144 wins the national championship — must NOT affect panorama.
        await create_race_result(
            s, event_id=900, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=100,
        )
        await s.commit()

    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r_after = await client.get("/api/race-analysis/insights/season/2026")

    assert r_after.status_code == 200
    assert r_after.json() == baseline


@pytest.mark.asyncio
async def test_coach_ignora_su_propio_club_sin_param(client_factory):
    # coach_11 es de club2 → solo ve athlete_200
    async with await client_factory(11, UserRole.coach, "coach2@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")
    data = r.json()
    ids = {i["athlete_id"] for i in data["items"]}
    assert ids == {200}


# ---------------------------------------------------------------------------
# Privacidad (PR3 audit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_privacidad_response_no_filtra_campos_internos(client_factory):
    """Invariante: el item solo contiene el contrato público.

    No debe filtrar fechas de nacimiento, datos médicos, IDs de usuario,
    competitor_id ni ninguna PII sensible más allá de nombre + agregados
    deportivos (visibles para el coach autorizado).
    """
    allowed_keys = {
        "athlete_id",
        "athlete_display_name",
        "races_count",
        "wins",
        "podiums",
        "best_position",
        "total_points",
    }
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/race-analysis/insights/season/2026")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert set(item.keys()) == allowed_keys, (
            f"El item filtró campos no permitidos: {set(item.keys()) - allowed_keys}"
        )
    # El wrapper tampoco debe tener campos extra.
    assert set(r.json().keys()) == {"season", "total_athletes", "items"}
