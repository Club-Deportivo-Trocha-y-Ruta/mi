"""Tests de integración para ``GET /api/races/{race_event_id}/club-insights`` (Sprint 3).

Cobertura:
- Coach lista todos los atletas del club + insights (200, datos completos).
- Parent solo ve su hijo con datos + otros atletas enmascarados.
- Atleta corrió sin insight → item con insight_id=None / summary_excerpt=None.
- Race event inexistente → 404.
- Caller no es miembro del club → 403.
- club_id explícito de otro club → 403 (no miembro).
- Admin debe especificar club_id → 422 si lo omite.
- Admin con club_id explícito → 200 con datos completos.

Estrategia: SQLite async in-memory con override de get_db / get_current_user.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
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
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Engine + DB override
# ---------------------------------------------------------------------------

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


def _utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def seeded_factory(session_factory) -> async_sessionmaker[AsyncSession]:
    """Escenario base:
    - club 1 (TyR) y club 2 (otro)
    - coach_10 en club 1 / coach_11 en club 2
    - admin_99 sin club membership
    - parent_20 → hijo: athlete_144 (NO athlete_145)
    - athlete_144 (club 1) y athlete_145 (club 1)
    - race_event_id=5 (Válida 4, Cali, 2026-05-17), serie season=2026
    - race_result para athlete_144 en event_5 con athlete_id vinculado
    - race_result para athlete_145 en event_5 (sin insight)
    - 1 insight aprobado + activo para athlete_144, event_id=5
    """
    async with session_factory() as s:
        # Clubs
        await create_club(s, club_id=1, name="Trocha y Ruta", code="tyr")
        await create_club(s, club_id=2, name="Otro Club", code="otro")

        # Usuarios
        await create_user(s, user_id=10, role=UserRole.coach, email="coach1@test.com")
        await create_user(s, user_id=11, role=UserRole.coach, email="coach2@test.com")
        await create_user(s, user_id=20, role=UserRole.parent, email="parent@test.com")
        await create_user(s, user_id=99, role=UserRole.admin, email="admin@test.com")
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_user(s, user_id=145, role=UserRole.athlete, can_login=False)

        # Membresías de club
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await link_user_to_club(s, user_id=11, club_id=2, role_in_club=ClubRole.coach)
        await link_user_to_club(s, user_id=20, club_id=1, role_in_club=ClubRole.parent)

        # Atletas del club 1
        await create_athlete(
            s,
            athlete_id=144,
            first_name="Juan Diego",
            last_name="Garcia",
            club_id=1,
            user_id=144,
        )
        await create_athlete(
            s,
            athlete_id=145,
            first_name="Maria",
            last_name="Perez",
            club_id=1,
            user_id=145,
        )

        # Relación parent → hijo
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=144)

        # Race data
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(
            s,
            event_id=5,
            series_id=1,
            sequence_number=4,
            name="Válida IV Copa Valle",
            event_date=date(2026, 5, 17),
            location="Cali",
        )

        # Competidores
        await create_race_competitor(
            s, competitor_id=501, normalized_name="juan diego garcia", display_name="Juan D. Garcia",
            athlete_id=144,
        )
        await create_race_competitor(
            s, competitor_id=502, normalized_name="maria perez", display_name="Maria Perez",
            athlete_id=145,
        )

        # Resultados vinculados a athlete_id
        await create_race_result(
            s,
            event_id=5,
            category_id=100,
            competitor_id=501,
            athlete_id=144,
            position=3,
            race_time_ms=1_802_000,
        )
        await create_race_result(
            s,
            event_id=5,
            category_id=100,
            competitor_id=502,
            athlete_id=145,
            position=5,
            race_time_ms=1_850_000,
        )

        # Insight aprobado + activo para athlete_144 (event_id=5)
        await create_insight(
            s,
            athlete_id=144,
            event_id=5,
            season=2026,
            valida_num=4,
            summary_text="Excelente progresión en la Válida IV. " + "x" * 300,
            coach_approved=True,
            is_active=1,
            confidence="high",
        )
        # athlete_145 NO tiene insight

        await s.commit()

    return session_factory


# ---------------------------------------------------------------------------
# Helpers de usuario fake
# ---------------------------------------------------------------------------


def _make_user(user_id: int, role: UserRole, email: str):
    from types import SimpleNamespace
    from app.models.club import ClubMember, ClubRole

    memberships = []
    if role == UserRole.coach and user_id == 10:
        cm = SimpleNamespace(user_id=user_id, club_id=1, role_in_club=ClubRole.coach)
        memberships = [cm]
    elif role == UserRole.parent and user_id == 20:
        cm = SimpleNamespace(user_id=user_id, club_id=1, role_in_club=ClubRole.parent)
        memberships = [cm]

    return SimpleNamespace(
        id=user_id,
        role=role,
        email=email,
        is_active=True,
        can_login=True,
        club_memberships=memberships,
    )


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client_factory(seeded_factory):
    """Factory de AsyncClient que permite inyectar el usuario actual."""

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
async def test_coach_lista_todos_atletas_con_insights(client_factory):
    """Coach ve todos los atletas del club + insight del que tiene + None del otro."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 200
    data = r.json()
    assert data["race_event_id"] == 5
    assert "Válida 4" in data["race_event_label"]
    assert "Cali" in data["race_event_label"]
    assert data["total_athletes"] == 2

    items = data["items"]
    assert len(items) == 2

    # Atleta 144 tiene insight
    item_144 = next((i for i in items if i["athlete_id"] == 144), None)
    assert item_144 is not None
    assert item_144["insight_id"] is not None
    assert item_144["summary_excerpt"] is not None
    assert len(item_144["summary_excerpt"]) <= 200
    assert item_144["confidence"] == "high"
    assert item_144["valida_num"] == 4

    # Atleta 145 NO tiene insight
    item_145 = next((i for i in items if i["athlete_id"] == 145), None)
    assert item_145 is not None
    assert item_145["insight_id"] is None
    assert item_145["summary_excerpt"] is None
    assert item_145["confidence"] is None  # sin insight → None


@pytest.mark.asyncio
async def test_parent_ve_hijo_completo_y_otros_enmascarados(client_factory):
    """Parent: datos completos para su hijo (144); enmascarado para athlete_145."""
    async with await client_factory(20, UserRole.parent, "parent@test.com") as client:
        r = await client.get("/api/races/5/club-insights")

    assert r.status_code == 200
    data = r.json()
    items = data["items"]
    assert len(items) == 2

    # Hijo propio (athlete_id=144)
    hijo = next((i for i in items if i["athlete_id"] == 144), None)
    assert hijo is not None
    assert hijo["athlete_display_name"] == "Juan Diego Garcia"
    assert hijo["insight_id"] is not None
    assert hijo["summary_excerpt"] is not None
    assert hijo["confidence"] is None  # NUNCA para parent

    # Atleta ajeno → enmascarado
    enmascarado = next((i for i in items if i["athlete_id"] == 0), None)
    assert enmascarado is not None
    assert enmascarado["athlete_display_name"] == "[Atleta del club]"
    assert enmascarado["insight_id"] is None
    assert enmascarado["summary_excerpt"] is None
    assert enmascarado["confidence"] is None


@pytest.mark.asyncio
async def test_parent_confidence_nunca_expuesta(client_factory):
    """Invariante de privacidad: confidence=None para TODOS los items del parent."""
    async with await client_factory(20, UserRole.parent, "parent@test.com") as client:
        r = await client.get("/api/races/5/club-insights")

    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["confidence"] is None, (
            f"confidence debe ser None para parent, pero fue {item['confidence']} "
            f"en item {item['athlete_id']}"
        )


@pytest.mark.asyncio
async def test_race_event_inexistente_retorna_404(client_factory):
    """race_event_id que no existe → 404."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/9999/club-insights?club_id=1")

    assert r.status_code == 404
    assert "no encontrada" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_caller_no_miembro_del_club_retorna_403(client_factory):
    """Coach del club 2 no puede ver insights del club 1 → 403."""
    async with await client_factory(11, UserRole.coach, "coach2@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_club_id_explicito_distinto_no_miembro_retorna_403(client_factory):
    """Coach del club 1 que pide club_id=2 (no es miembro) → 403."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=2")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_sin_club_id_retorna_422(client_factory):
    """Admin que no especifica club_id → 422 (debe ser explícito)."""
    async with await client_factory(99, UserRole.admin, "admin@test.com") as client:
        r = await client.get("/api/races/5/club-insights")

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_con_club_id_ve_todos(client_factory):
    """Admin con club_id explícito → 200 con todos los atletas."""
    async with await client_factory(99, UserRole.admin, "admin@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 200
    data = r.json()
    assert data["total_athletes"] == 2
    items = data["items"]
    # Admin ve nombres reales y confidence
    item_144 = next((i for i in items if i["athlete_id"] == 144), None)
    assert item_144 is not None
    assert item_144["confidence"] == "high"
    assert item_144["athlete_display_name"] == "Juan Diego Garcia"


@pytest.mark.asyncio
async def test_atleta_sin_insight_item_con_nones(client_factory):
    """Atleta que corrió sin insight → insight_id=None, summary_excerpt=None."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 200
    item_145 = next(
        (i for i in r.json()["items"] if i["athlete_id"] == 145),
        None,
    )
    assert item_145 is not None
    assert item_145["insight_id"] is None
    assert item_145["summary_excerpt"] is None
    assert item_145["generated_at"] is None


@pytest.mark.asyncio
async def test_race_event_label_formato(client_factory):
    """Verifica que race_event_label siga el formato 'Válida N — Location DD mmm YYYY'."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 200
    label = r.json()["race_event_label"]
    # Debe contener sequence_number=4, location=Cali, mes=may, año=2026
    assert "4" in label
    assert "Cali" in label
    assert "may" in label
    assert "2026" in label


@pytest.mark.asyncio
async def test_summary_excerpt_max_200_chars(client_factory):
    """summary_excerpt nunca supera 200 caracteres."""
    async with await client_factory(10, UserRole.coach, "coach1@test.com") as client:
        r = await client.get("/api/races/5/club-insights?club_id=1")

    assert r.status_code == 200
    for item in r.json()["items"]:
        if item.get("summary_excerpt") is not None:
            assert len(item["summary_excerpt"]) <= 200
