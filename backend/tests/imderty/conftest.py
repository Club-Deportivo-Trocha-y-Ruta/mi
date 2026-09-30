"""Shared fixtures for feature 047 (IMDERTY monthly attendance sheet).

Self-contained aiosqlite in-memory engine (same idiom as
``tests/fixtures/two_coaches.py``): one club plus a second, unrelated club,
an admin, a coach of the first club, a coach of the second club ("foreign"
to the first), a parent with two athletes, and one athlete with two
guardians. Later story tests build on top of ``imderty_scenario`` instead of
constructing users/clubs/athletes from scratch.

The HTTP client factory loads the real ``User`` row (with
``club_memberships`` via ``selectinload``), exactly like
``app.dependencies.get_current_user`` in production, so RBAC dependencies
that read ``current_user.club_memberships`` in memory (``require_athlete_staff``
/ ``require_club_staff`` in ``app.routers.imderty``) see real data instead of
an empty-list stand-in — see ``tests/routers/test_audit_log_api.py`` for the
prior art and rationale for this pattern.

No name here corresponds to a real person — club, coaches, parent and
athletes are fictitious (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import User, UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

# ---------------------------------------------------------------------------
# IDs y datos ficticios del escenario (namespace propio, 47xx, para no
# colisionar con otros módulos de pruebas que comparten motor propio).
# ---------------------------------------------------------------------------

CLUB_ID = 4701
OTHER_CLUB_ID = 4702

ADMIN_USER_ID = 4710
COACH_USER_ID = 4711
FOREIGN_COACH_USER_ID = 4712
PARENT_USER_ID = 4713
SECOND_GUARDIAN_USER_ID = 4714

PARENT_ATHLETE_ONE_ID = 4740
PARENT_ATHLETE_TWO_ID = 4741
TWO_GUARDIANS_ATHLETE_ID = 4742

PARENT_ATHLETE_ONE_USER_ID = 4750
PARENT_ATHLETE_TWO_USER_ID = 4751
TWO_GUARDIANS_ATHLETE_USER_ID = 4752

_ATHLETE_BIRTH_DATE = date(2014, 4, 10)

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    *AUDIT_TABLES,
)


@dataclass(frozen=True)
class ImdertyScenario:
    """IDs (y la sesión ya sembrada) del escenario base de la feature 047."""

    session: AsyncSession

    club_id: int
    other_club_id: int

    admin_user_id: int
    coach_user_id: int
    foreign_coach_user_id: int
    parent_user_id: int
    second_guardian_user_id: int

    parent_athlete_one_id: int
    parent_athlete_two_id: int
    two_guardians_athlete_id: int


async def seed_imderty_scenario(session: AsyncSession) -> ImdertyScenario:
    """Club base + un segundo club, admin, coach del club base, coach de un
    club distinto ("foreign"), un padre con dos atletas, y un atleta con dos
    tutores (para probar primary-contact)."""
    await create_club(session, club_id=CLUB_ID, name="Club Ficticio 047", code="cft-047-a")
    await create_club(
        session, club_id=OTHER_CLUB_ID, name="Club Ficticio 047 Dos", code="cft-047-b"
    )

    admin = await create_user(
        session, user_id=ADMIN_USER_ID, role=UserRole.admin,
        first_name="Admin", last_name="Ficticio",
    )
    coach = await create_user(
        session, user_id=COACH_USER_ID, role=UserRole.coach,
        first_name="Coach", last_name="Ficticio",
    )
    foreign_coach = await create_user(
        session, user_id=FOREIGN_COACH_USER_ID, role=UserRole.coach,
        first_name="Coach", last_name="Ficticio Externo",
    )
    parent = await create_user(
        session, user_id=PARENT_USER_ID, role=UserRole.parent,
        first_name="Padre", last_name="Ficticio",
    )
    second_guardian = await create_user(
        session, user_id=SECOND_GUARDIAN_USER_ID, role=UserRole.parent,
        first_name="Madre", last_name="Ficticia",
    )

    await link_user_to_club(
        session, user_id=admin.id, club_id=CLUB_ID, role_in_club=ClubRole.admin
    )
    await link_user_to_club(
        session, user_id=coach.id, club_id=CLUB_ID, role_in_club=ClubRole.coach
    )
    await link_user_to_club(
        session,
        user_id=foreign_coach.id,
        club_id=OTHER_CLUB_ID,
        role_in_club=ClubRole.coach,
    )

    athlete_one = await create_athlete(
        session,
        athlete_id=PARENT_ATHLETE_ONE_ID,
        first_name="Atleta Ficticio Uno",
        last_name="Ficticio",
        birth_date=_ATHLETE_BIRTH_DATE,
        club_id=CLUB_ID,
        user_id=PARENT_ATHLETE_ONE_USER_ID,
        created_by=coach.id,
    )
    athlete_two = await create_athlete(
        session,
        athlete_id=PARENT_ATHLETE_TWO_ID,
        first_name="Atleta Ficticio Dos",
        last_name="Ficticio",
        birth_date=_ATHLETE_BIRTH_DATE,
        club_id=CLUB_ID,
        user_id=PARENT_ATHLETE_TWO_USER_ID,
        created_by=coach.id,
    )
    two_guardians_athlete = await create_athlete(
        session,
        athlete_id=TWO_GUARDIANS_ATHLETE_ID,
        first_name="Atleta Ficticio Tres",
        last_name="Ficticio",
        birth_date=_ATHLETE_BIRTH_DATE,
        club_id=CLUB_ID,
        user_id=TWO_GUARDIANS_ATHLETE_USER_ID,
        created_by=coach.id,
    )

    await link_parent_to_athlete(
        session, parent_user_id=parent.id, athlete_id=athlete_one.id
    )
    await link_parent_to_athlete(
        session, parent_user_id=parent.id, athlete_id=athlete_two.id
    )
    await link_parent_to_athlete(
        session, parent_user_id=parent.id, athlete_id=two_guardians_athlete.id
    )
    await link_parent_to_athlete(
        session,
        parent_user_id=second_guardian.id,
        athlete_id=two_guardians_athlete.id,
    )

    await session.commit()

    return ImdertyScenario(
        session=session,
        club_id=CLUB_ID,
        other_club_id=OTHER_CLUB_ID,
        admin_user_id=ADMIN_USER_ID,
        coach_user_id=COACH_USER_ID,
        foreign_coach_user_id=FOREIGN_COACH_USER_ID,
        parent_user_id=PARENT_USER_ID,
        second_guardian_user_id=SECOND_GUARDIAN_USER_ID,
        parent_athlete_one_id=PARENT_ATHLETE_ONE_ID,
        parent_athlete_two_id=PARENT_ATHLETE_TWO_ID,
        two_guardians_athlete_id=TWO_GUARDIANS_ATHLETE_ID,
    )


# ---------------------------------------------------------------------------
# Fixtures pytest — engine/session/scenario
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def imderty_engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def imderty_session_factory(
    imderty_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(imderty_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def imderty_scenario(
    imderty_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[ImdertyScenario, None]:
    """Escenario base: club + segundo club, admin, coach, foreign coach,
    un padre con dos atletas y un atleta con dos tutores."""
    async with imderty_session_factory() as session:
        yield await seed_imderty_scenario(session)


# ---------------------------------------------------------------------------
# Fábrica de cliente HTTP autenticado, con ``club_memberships`` reales
# (``selectinload``), igual que ``app.dependencies.get_current_user`` en
# producción — necesario porque ``require_athlete_staff``/``require_club_staff``
# (``app/routers/imderty.py``) leen esa lista en memoria.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def imderty_client_factory(
    imderty_session_factory: async_sessionmaker[AsyncSession],
    imderty_scenario: ImdertyScenario,
):
    """Devuelve una fábrica ``make_client(user_id)`` que monta un
    ``AsyncClient`` autenticado como ese usuario real (con
    ``club_memberships`` cargados), con ``get_db``/``get_current_user``
    overriden sobre la misma DB sembrada por ``imderty_scenario``.
    """

    @asynccontextmanager
    async def make_client(user_id: int):
        async with imderty_session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with imderty_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


@pytest_asyncio.fixture
async def admin_client(imderty_client_factory, imderty_scenario):
    """Cliente HTTP autenticado como el admin del escenario."""
    async with imderty_client_factory(imderty_scenario.admin_user_id) as client:
        yield client


@pytest_asyncio.fixture
async def coach_client(imderty_client_factory, imderty_scenario):
    """Cliente HTTP autenticado como el coach del club base."""
    async with imderty_client_factory(imderty_scenario.coach_user_id) as client:
        yield client


@pytest_asyncio.fixture
async def foreign_coach_client(imderty_client_factory, imderty_scenario):
    """Cliente HTTP autenticado como un coach de un club DISTINTO — usado
    para los negative-paths "coach de otro club → 403"."""
    async with imderty_client_factory(
        imderty_scenario.foreign_coach_user_id
    ) as client:
        yield client


@pytest_asyncio.fixture
async def parent_client(imderty_client_factory, imderty_scenario):
    """Cliente HTTP autenticado como el padre — cualquier ruta IMDERTY debe
    responder 403 (contracts/api.md §1)."""
    async with imderty_client_factory(imderty_scenario.parent_user_id) as client:
        yield client
