"""Integration test harness for the Strength Training Exercise Library (feature 021).

Mirrors ``backend/tests/technique/conftest.py`` (feature 018) exactly in shape:
a real aiosqlite DB (in-memory) with ``Base.metadata.create_all`` limited to
the tables these tests need, and an ``AsyncClient`` factory that overrides
``get_db`` and ``get_current_user`` so router tests exercise real SQL without
MySQL or a live JWT server.

Identity fixtures ("coach/admin/parent JWT token fixtures" in the task
description) follow the same convention already established across every
other feature test suite in this repo (technique, race-analysis, etc.): the authenticated identity is injected via a ``get_current_user``
dependency override rather than by minting and decoding a real JWT. This is
intentional — ``backend/tests/test_auth.py`` is the only suite that exercises
the actual login/JWT-issuance flow; every feature router suite fakes the
authenticated principal the same way ``make_client`` does here, so behavior
under test is the RBAC/router/service layer, not JWT encoding.

Tables included (targeted subset — avoids MySQL-dialect columns such as the
``LONGTEXT`` used in ``privacy_policies``):

  Core identity / auth
    users
    clubs
    club_members
    athletes
    parent_athlete (FK athletes + users — needed for club-scope checks)

  Training calendar (StrengthSessionBlock FK → training_sessions)
    calendar_events   (FK from training_sessions.calendar_event_id)
    training_sessions
    session_attendance
    session_media / session_media_athlete (FK chain reload dependencies)

  Strength tables (feature 021)
    strength_exercises
    strength_exercise_age_bands
    strength_blocks
    strength_block_entries
    strength_session_blocks
    strength_progress_notes

Fixtures exposed (all ``pytest_asyncio.fixture`` unless noted):
  engine               — async in-memory aiosqlite engine
  session_factory      — async_sessionmaker[AsyncSession]
  session              — open AsyncSession (auto-committed on close)
  coach_user_obj       — unsaved User(role=coach) helper (plain function)
  admin_user_obj       — unsaved User(role=admin) helper (plain function)
  parent_user_obj      — unsaved User(role=parent) helper (plain function)

  seed_club            — async helper: insert Club(id=1) + flush
  seed_coach           — async helper: insert coach User(id=10) + ClubMember
  seed_admin           — async helper: insert admin User(id=20)
  seed_parent          — async helper: insert parent User(id=30)
  seed_athlete_user    — async helper: insert athlete user User(id=40)
  seed_athlete_record  — async helper: insert Athlete(id=1) linked to user 40
  seed_strength_catalog — async helper: inserts a small representative test
                          catalog (a few exercises spanning both equipment
                          kinds, both age bands, and a couple of movement
                          categories) so catalog/detail/filter/block tests
                          have data without relying on the Alembic seed
                          (``app/data/strength_catalog.py``, feature T006).

  make_client          — sync factory returning AsyncClient context-manager;
                         accepts ``user`` kwarg to control the authenticated
                         identity; defaults to the coach user.

  _clear_overrides     — autouse fixture that clears app.dependency_overrides
                         after every test (prevents inter-test bleed).

Seed data uses fictitious names ("Juan Pérez Ficticio") and dates — never real
TyR athlete data (non-negotiable constraint, CLAUDE.md §Privacy).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete import Athlete, Sex
from app.models.club import Club, ClubMember, ClubRole
from app.models.technique_exercise import AgeBand
from app.models.strength import (
    EquipmentKind,
    MovementCategory,
    StrengthBlock,
    StrengthExercise,
    StrengthExerciseAgeBand,
)
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Tables included in the aiosqlite create_all subset
# ---------------------------------------------------------------------------

_TABLES = (
    # Core identity
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    # Training calendar (required by StrengthSessionBlock FK chain)
    "calendar_events",
    "event_audiences",
    "training_sessions",
    "session_attendance",
    "session_media",
    "session_media_athlete",
    # Strength tables (feature 021)
    "strength_exercises",
    "strength_exercise_age_bands",
    "strength_blocks",
    "strength_block_entries",
    "strength_session_blocks",
    "strength_progress_notes",
)


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """In-memory aiosqlite engine with the strength table subset."""
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
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Unsaved user object helpers (plain functions — not fixtures)
# ---------------------------------------------------------------------------


def coach_user_obj(user_id: int = 10) -> User:
    """Return an unsaved coach User for use as a DB fixture or auth override."""
    return User(
        id=user_id,
        email=f"entrenador.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Entrenador",
        last_name="Ficticio",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


def admin_user_obj(user_id: int = 20) -> User:
    """Return an unsaved admin User."""
    return User(
        id=user_id,
        email=f"admin.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Admin",
        last_name="Ficticio",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


def parent_user_obj(user_id: int = 30) -> User:
    """Return an unsaved parent User."""
    return User(
        id=user_id,
        email=f"padre.ficticio{user_id}@test.com",
        hashed_password="x",
        first_name="Padre",
        last_name="Ficticio",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Async seed helpers (call inside a test or fixture; callers own commit)
# ---------------------------------------------------------------------------


async def seed_club(session: AsyncSession, club_id: int = 1) -> Club:
    """Insert a Club and flush. Fictitious data only."""
    club = Club(
        id=club_id,
        name="Club Ficticio de Prueba",
        code=f"TST{club_id:03d}",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club)
    await session.flush()
    return club


async def seed_coach(
    session: AsyncSession,
    user_id: int = 10,
    club_id: int = 1,
) -> User:
    """Insert a coach User + ClubMember row and flush."""
    user = coach_user_obj(user_id)
    session.add(user)
    await session.flush()
    cm = ClubMember(
        club_id=club_id,
        user_id=user_id,
        role_in_club=ClubRole.coach,
        joined_at=datetime.now(timezone.utc),
    )
    session.add(cm)
    await session.flush()
    return user


async def seed_admin(
    session: AsyncSession,
    user_id: int = 20,
) -> User:
    """Insert an admin User (no club membership needed for global admin)."""
    user = admin_user_obj(user_id)
    session.add(user)
    await session.flush()
    return user


async def seed_parent(
    session: AsyncSession,
    user_id: int = 30,
) -> User:
    """Insert a parent User and flush."""
    user = parent_user_obj(user_id)
    session.add(user)
    await session.flush()
    return user


async def seed_athlete_user(
    session: AsyncSession,
    user_id: int = 40,
) -> User:
    """Insert a non-login athlete user row (can_login=False) and flush."""
    user = User(
        id=user_id,
        email=None,
        hashed_password=None,
        first_name="Juan",
        last_name="Pérez Ficticio",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    await session.flush()
    return user


async def seed_athlete_record(
    session: AsyncSession,
    athlete_id: int = 1,
    *,
    user_id: int = 40,
    club_id: int = 1,
    birth_date: date = date(2012, 3, 15),
    created_by: int = 10,
) -> Athlete:
    """Insert an Athlete row (fictitious DOB/name) and flush.

    Privacy constraint: fictitious birth dates and names — never real TyR data.
    birth_date default → ~14 years old in 2026.
    """
    athlete = Athlete(
        id=athlete_id,
        user_id=user_id,
        first_name="Juan",
        last_name="Pérez Ficticio",
        birth_date=birth_date,
        sex=Sex.M,
        club_id=club_id,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(athlete)
    await session.flush()
    return athlete


# ---------------------------------------------------------------------------
# Strength catalog seed helper
# ---------------------------------------------------------------------------


async def seed_strength_catalog(session: AsyncSession) -> dict:
    """Insert a small but representative strength catalog for test isolation.

    Inserts 4 exercises spanning both ``EquipmentKind`` values, both age
    bands (10-12 / 13-15), and multiple ``MovementCategory`` values:

      1. "flexiones-test"       — sin_equipo, empuje_superior, 10-12 + 13-15
      2. "remo-banda-test"      — equipo_gym,  traccion_superior, 13-15 only
      3. "sentadilla-test"      — sin_equipo, inferior_bilateral, 10-12 + 13-15
      4. "plancha-test"         — sin_equipo, core_estabilidad, 10-12 only
      5. "trackstand-oculto-test" — sin_equipo, core_estabilidad, 13-15,
         is_hidden=True (tests include_hidden filter)

    Returns a dict with inserted ORM objects keyed by slug for assertions.
    Caller is responsible for committing the session.
    """
    now = datetime.now(timezone.utc)

    ex_flexiones = StrengthExercise(
        slug="flexiones-test",
        name="Flexiones de rodillas (test)",
        summary="Empuje superior con apoyo de rodillas, cadera alineada.",
        how_to=(
            "Dilo: manos bajo los hombros, cuerpo en línea recta.\n"
            "Muéstralo: el entrenador ejecuta 3 repeticiones lentas.\n"
            "Háganlo: descenso controlado, sin dejar caer la cadera.\n"
            "Revísenlo: ¿dónde sentiste el esfuerzo principal?"
        ),
        common_errors="Cadera hundida\nCodos muy abiertos\nRango incompleto",
        illustration_ascii=(
            "  o\n"
            " /|\\  ← posición de flexión con apoyo de rodillas\n"
            " / \\\n"
        ),
        illustration_alt=(
            "Persona en posición de flexión apoyada sobre rodillas, "
            "espalda recta, manos bajo los hombros."
        ),
        equipment=EquipmentKind.SIN_EQUIPO,
        equipment_detail=None,
        movement_category=MovementCategory.EMPUJE_SUPERIOR,
        suggested_duration_min=5,
        suggested_reps="2x8-12",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_flexiones)
    await session.flush()

    ex_remo_banda = StrengthExercise(
        slug="remo-banda-test",
        name="Remo con banda elástica (test)",
        summary="Tracción superior con banda anclada, escápulas activas.",
        how_to=(
            "Dilo: tira llevando los codos atrás, junta las escápulas.\n"
            "Muéstralo: el entrenador ejecuta el remo con banda.\n"
            "Háganlo: tensión constante, sin usar impulso del tronco.\n"
            "Revísenlo: ¿lograste mantener la espalda estable?"
        ),
        common_errors="Impulso con el tronco\nCodos muy elevados\nBanda destensada",
        illustration_ascii=(
            "≈≈≈[o]───┐\n"
            "         │  ← tirón horizontal con banda anclada\n"
        ),
        illustration_alt=(
            "Persona tirando de una banda elástica anclada al frente, "
            "codos hacia atrás, escápulas juntas."
        ),
        equipment=EquipmentKind.EQUIPO_GYM,
        equipment_detail="banda elástica",
        movement_category=MovementCategory.TRACCION_SUPERIOR,
        suggested_duration_min=5,
        suggested_reps="2x10-15",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_remo_banda)
    await session.flush()

    ex_sentadilla = StrengthExercise(
        slug="sentadilla-test",
        name="Sentadilla con peso corporal (test)",
        summary="Patrón inferior bilateral, rodillas alineadas con los pies.",
        how_to=(
            "Dilo: pies al ancho de hombros, baja como si te sentaras.\n"
            "Muéstralo: el entrenador ejecuta 3 repeticiones controladas.\n"
            "Háganlo: rodillas siguen la dirección de los pies.\n"
            "Revísenlo: ¿las rodillas se fueron hacia adentro?"
        ),
        common_errors="Rodillas hacia adentro\nTalones se levantan\nEspalda encorvada",
        illustration_ascii=(
            "  o\n"
            " /=\\  ← sentadilla con peso corporal\n"
            " Λ Λ\n"
        ),
        illustration_alt=(
            "Persona en posición de sentadilla, rodillas alineadas con los "
            "pies, espalda recta."
        ),
        equipment=EquipmentKind.SIN_EQUIPO,
        equipment_detail=None,
        movement_category=MovementCategory.INFERIOR_BILATERAL,
        suggested_duration_min=5,
        suggested_reps="2x10-15",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_sentadilla)
    await session.flush()

    ex_plancha = StrengthExercise(
        slug="plancha-test",
        name="Plancha frontal (test)",
        summary="Estabilidad de core, cuerpo alineado sobre antebrazos.",
        how_to=(
            "Dilo: cuerpo en línea recta de cabeza a talones.\n"
            "Muéstralo: el entrenador sostiene la posición 10 segundos.\n"
            "Háganlo: mantener la respiración fluida.\n"
            "Revísenlo: ¿dónde sentiste el trabajo principal?"
        ),
        common_errors="Cadera elevada\nCadera hundida\nCabeza caída",
        illustration_ascii=(
            "____\n"
            "o===  ← plancha frontal sobre antebrazos\n"
        ),
        illustration_alt=(
            "Persona en posición de plancha frontal apoyada sobre "
            "antebrazos, cuerpo en línea recta."
        ),
        equipment=EquipmentKind.SIN_EQUIPO,
        equipment_detail=None,
        movement_category=MovementCategory.CORE_ESTABILIDAD,
        suggested_duration_min=3,
        suggested_reps="3x15-20 seg",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_plancha)
    await session.flush()

    ex_hidden = StrengthExercise(
        slug="trackstand-oculto-test",
        name="Ejercicio oculto de prueba",
        summary="Ejercicio de prueba oculto del catálogo por defecto.",
        how_to="Dilo.\nMuéstralo.\nHáganlo.\nRevísenlo.",
        common_errors="N/A",
        illustration_ascii="[oculto]",
        illustration_alt="Ejercicio de prueba oculto, sin ilustración real.",
        equipment=EquipmentKind.SIN_EQUIPO,
        equipment_detail=None,
        movement_category=MovementCategory.CORE_ESTABILIDAD,
        suggested_duration_min=5,
        suggested_reps="2x10",
        is_seeded=True,
        is_hidden=True,  # soft-hidden — tests include_hidden filter
        created_at=now,
        updated_at=now,
    )
    session.add(ex_hidden)
    await session.flush()

    # --- Age bands -----------------------------------------------------------
    for band in (AgeBand.BAND_10_12, AgeBand.BAND_13_15):
        session.add(StrengthExerciseAgeBand(exercise_id=ex_flexiones.id, age_band=band))
    session.add(StrengthExerciseAgeBand(exercise_id=ex_remo_banda.id, age_band=AgeBand.BAND_13_15))
    for band in (AgeBand.BAND_10_12, AgeBand.BAND_13_15):
        session.add(StrengthExerciseAgeBand(exercise_id=ex_sentadilla.id, age_band=band))
    session.add(StrengthExerciseAgeBand(exercise_id=ex_plancha.id, age_band=AgeBand.BAND_10_12))
    session.add(StrengthExerciseAgeBand(exercise_id=ex_hidden.id, age_band=AgeBand.BAND_13_15))
    await session.flush()

    return {
        "exercises": {
            "flexiones": ex_flexiones,
            "remo_banda": ex_remo_banda,
            "sentadilla": ex_sentadilla,
            "plancha": ex_plancha,
            "trackstand_oculto": ex_hidden,
        },
    }


async def seed_strength_block(
    session: AsyncSession,
    *,
    block_id: int | None = None,
    club_id: int = 1,
    created_by_user_id: int = 10,
    target_age_band: AgeBand = AgeBand.BAND_13_15,
    duration_target_min: int = 30,
    is_archived: bool = False,
) -> StrengthBlock:
    """Insert a StrengthBlock (no entries) and flush."""
    kwargs: dict = {}
    if block_id is not None:
        kwargs["id"] = block_id
    block = StrengthBlock(
        name="Bloque de fuerza de prueba",
        target_age_band=target_age_band,
        duration_target_min=duration_target_min,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        is_archived=is_archived,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        **kwargs,
    )
    session.add(block)
    await session.flush()
    return block


# ---------------------------------------------------------------------------
# AsyncClient factory
# ---------------------------------------------------------------------------


def make_client(
    session: AsyncSession,
    *,
    user: User | None = None,
    authed: bool = True,
):
    """Return an async context-manager wrapping an AsyncClient.

    The returned object is used as ``async with make_client(session) as client:``.
    It overrides ``get_db`` with the supplied session and, when ``authed=True``,
    overrides ``get_current_user`` with ``user`` (defaults to coach_user_obj()).

    App dependency_overrides are cleared by the ``_clear_overrides`` autouse
    fixture after each test.

    Args:
        session: Active AsyncSession already scoped to the test.
        user:    User object returned by ``get_current_user``; defaults to coach.
        authed:  When ``False``, removes the ``get_current_user`` override so
                 the real JWT auth fires (produces 401/403 for negative tests).
    """

    async def _override_db():
        yield session
        await session.commit()

    app.dependency_overrides[get_db] = _override_db

    if authed:
        resolved_user = user or coach_user_obj()

        async def _override_user():
            return resolved_user

        app.dependency_overrides[get_current_user] = _override_user

    @asynccontextmanager
    async def _ctx():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    return _ctx()


# ---------------------------------------------------------------------------
# Autouse fixture: clear dependency_overrides after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Prevent dependency override bleed between tests."""
    yield
    app.dependency_overrides.clear()
