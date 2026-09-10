"""Fixtures compartidas de "dos entrenadores" para feature 041 (multi-coach
governance).

Construye, sobre una ``AsyncSession`` real (aiosqlite in-memory + ``StaticPool``
— mismo patrón que ``tests/fixtures/race_groups.py``), un club único con dos
coaches (``coach_a`` y ``coach_b``, ambos miembros del MISMO club), un tercer
coach en un club *distinto* (``other_club_coach``), un admin, un padre y un
atleta ficticio con datos sintéticos.

Idioma de fixtures: el idioma "SQLite-in-memory + ``app.dependency_overrides``"
descrito en ``research.md`` R-32, promovido a módulo compartido y registrado
como plugin pytest (junto a ``tests.fixtures.race_groups``) para que ningún
test de esta feature construya sus propios usuarios/club desde cero.

Ningún nombre corresponde a una persona real — atleta, coaches, padre y club
son ficticios (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

# ---------------------------------------------------------------------------
# IDs y datos ficticios del escenario
# ---------------------------------------------------------------------------

CLUB_ID = 1
OTHER_CLUB_ID = 2

ADMIN_USER_ID = 900
COACH_A_USER_ID = 901
COACH_B_USER_ID = 902
OTHER_CLUB_COACH_USER_ID = 903
PARENT_USER_ID = 904

ATHLETE_ID = 941
ATHLETE_USER_ID = 1941
ATHLETE_FIRST_NAME = "Mariana Ficticia"
ATHLETE_LAST_NAME = "Restrepo"
ATHLETE_BIRTH_DATE = date(2013, 6, 20)

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    # T051: crear personal manda el correo para definir la contraseña por la vía
    # de `password_reset`, así que el alta escribe aquí aunque la prueba solo
    # mire usuarios y membresías.
    "password_reset_tokens",
    *AUDIT_TABLES,
)


# ---------------------------------------------------------------------------
# Dataclass de salida
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TwoCoachesScenario:
    """IDs (y la sesión ya sembrada) de un escenario de dos entrenadores.

    ``session`` queda commiteada y lista para pasar a funciones de servicio o
    para montarse detrás de ``app.dependency_overrides`` en tests de router.
    """

    session: AsyncSession

    club_id: int
    other_club_id: int

    admin_user_id: int
    coach_a_user_id: int
    coach_b_user_id: int
    other_club_coach_user_id: int
    parent_user_id: int

    athlete_id: int
    athlete_user_id: int


# ---------------------------------------------------------------------------
# Helper de siembra (función plana — sin decorar como fixture, misma
# convención que tests/fixtures/race_groups.py)
# ---------------------------------------------------------------------------


async def seed_two_coaches(session: AsyncSession) -> TwoCoachesScenario:
    """Club único con dos coaches, un tercer coach en otro club, un admin, un
    padre y un atleta ficticio — el escenario base de FR-034 (R-32)."""
    await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-041-a")
    await create_club(
        session, club_id=OTHER_CLUB_ID, name="Club Ficticio Dos", code="cft-041-b"
    )

    admin = await create_user(
        session,
        user_id=ADMIN_USER_ID,
        role=UserRole.admin,
        first_name="Admin",
        last_name="Ficticio",
    )
    coach_a = await create_user(
        session,
        user_id=COACH_A_USER_ID,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Ficticio A",
    )
    coach_b = await create_user(
        session,
        user_id=COACH_B_USER_ID,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Ficticio B",
    )
    other_club_coach = await create_user(
        session,
        user_id=OTHER_CLUB_COACH_USER_ID,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Ficticio Externo",
    )
    parent = await create_user(
        session,
        user_id=PARENT_USER_ID,
        role=UserRole.parent,
        first_name="Padre",
        last_name="Ficticio",
    )

    await link_user_to_club(
        session, user_id=admin.id, club_id=CLUB_ID, role_in_club=ClubRole.admin
    )
    await link_user_to_club(
        session, user_id=coach_a.id, club_id=CLUB_ID, role_in_club=ClubRole.coach
    )
    await link_user_to_club(
        session, user_id=coach_b.id, club_id=CLUB_ID, role_in_club=ClubRole.coach
    )
    await link_user_to_club(
        session,
        user_id=other_club_coach.id,
        club_id=OTHER_CLUB_ID,
        role_in_club=ClubRole.coach,
    )

    athlete = await create_athlete(
        session,
        athlete_id=ATHLETE_ID,
        first_name=ATHLETE_FIRST_NAME,
        last_name=ATHLETE_LAST_NAME,
        birth_date=ATHLETE_BIRTH_DATE,
        club_id=CLUB_ID,
        user_id=ATHLETE_USER_ID,
        created_by=coach_a.id,
    )
    await link_parent_to_athlete(
        session, parent_user_id=parent.id, athlete_id=athlete.id
    )

    await session.commit()

    return TwoCoachesScenario(
        session=session,
        club_id=CLUB_ID,
        other_club_id=OTHER_CLUB_ID,
        admin_user_id=ADMIN_USER_ID,
        coach_a_user_id=COACH_A_USER_ID,
        coach_b_user_id=COACH_B_USER_ID,
        other_club_coach_user_id=OTHER_CLUB_COACH_USER_ID,
        parent_user_id=PARENT_USER_ID,
        athlete_id=ATHLETE_ID,
        athlete_user_id=ATHLETE_USER_ID,
    )


# ---------------------------------------------------------------------------
# Fixtures pytest — engine/session
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def two_coaches_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Engine SQLite in-memory con solo las tablas que este módulo necesita."""
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
async def two_coaches_session_factory(
    two_coaches_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(two_coaches_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def two_coaches_scenario(
    two_coaches_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[TwoCoachesScenario, None]:
    """Escenario base: club único, coach_a + coach_b, other_club_coach, admin,
    parent y un atleta ficticio."""
    async with two_coaches_session_factory() as session:
        yield await seed_two_coaches(session)


# ---------------------------------------------------------------------------
# Helpers de cliente HTTP autenticado (dependency_overrides sobre app.main)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def two_coaches_client_factory(
    two_coaches_session_factory: async_sessionmaker[AsyncSession],
    two_coaches_scenario: TwoCoachesScenario,
):
    """Devuelve una fábrica ``make_client(user_id, role)`` que monta un
    ``AsyncClient`` autenticado como ese actor, con ``get_db`` y
    ``get_current_user`` overriden sobre la misma DB sembrada por
    ``two_coaches_scenario``.

    Uso típico::

        async def test_algo(two_coaches_scenario, two_coaches_client_factory):
            s = two_coaches_scenario
            async with two_coaches_client_factory(
                s.coach_a_user_id, UserRole.coach
            ) as client:
                resp = await client.get("/api/algo")
                assert resp.status_code == 200

    Cierra y limpia ``app.dependency_overrides`` al salir del context manager.
    """
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user, get_db

    @asynccontextmanager
    async def make_client(user_id: int, role: UserRole):
        async def _override_db():
            async with two_coaches_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        def _override_current_user():
            # El doble tiene que exponer todo atributo del actor que lea el
            # código de producción. `display_name` (FR-013) se sumó a `User`
            # con esta feature y su ausencia aquí se manifestaba como un 500
            # en `POST /api/users`, no como un fallo de prueba legible.
            return SimpleNamespace(
                id=user_id,
                first_name="Test",
                last_name="Actor",
                display_name="Test Actor",
                email=f"actor{user_id}@test.local",
                role=role,
                can_login=True,
                is_active=True,
                club_memberships=[],
            )

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = _override_current_user
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


@pytest_asyncio.fixture
async def coach_a_client(two_coaches_client_factory, two_coaches_scenario):
    """Cliente HTTP autenticado como ``coach_a`` (miembro del club base)."""
    async with two_coaches_client_factory(
        two_coaches_scenario.coach_a_user_id, UserRole.coach
    ) as client:
        yield client


@pytest_asyncio.fixture
async def coach_b_client(two_coaches_client_factory, two_coaches_scenario):
    """Cliente HTTP autenticado como ``coach_b`` (mismo club que coach_a)."""
    async with two_coaches_client_factory(
        two_coaches_scenario.coach_b_user_id, UserRole.coach
    ) as client:
        yield client


@pytest_asyncio.fixture
async def other_club_coach_client(two_coaches_client_factory, two_coaches_scenario):
    """Cliente HTTP autenticado como coach de un club DISTINTO — usado para
    los negative-paths "coach de otro club → 403"."""
    async with two_coaches_client_factory(
        two_coaches_scenario.other_club_coach_user_id, UserRole.coach
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_client(two_coaches_client_factory, two_coaches_scenario):
    """Cliente HTTP autenticado como admin del club base."""
    async with two_coaches_client_factory(
        two_coaches_scenario.admin_user_id, UserRole.admin
    ) as client:
        yield client


@pytest_asyncio.fixture
async def parent_client(two_coaches_client_factory, two_coaches_scenario):
    """Cliente HTTP autenticado como el padre del atleta ficticio."""
    async with two_coaches_client_factory(
        two_coaches_scenario.parent_user_id, UserRole.parent
    ) as client:
        yield client


__all__ = [
    "TwoCoachesScenario",
    "seed_two_coaches",
    "two_coaches_engine",
    "two_coaches_session_factory",
    "two_coaches_scenario",
    "two_coaches_client_factory",
    "coach_a_client",
    "coach_b_client",
    "other_club_coach_client",
    "admin_client",
    "parent_client",
]
