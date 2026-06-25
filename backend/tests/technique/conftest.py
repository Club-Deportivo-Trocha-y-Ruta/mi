"""Integration test harness for the Technique & Gymkhana Library (feature 018).

Real aiosqlite DB (in-memory) with ``Base.metadata.create_all`` limited to the
tables these tests need.  An ``AsyncClient`` factory overrides ``get_db`` and
``get_current_user`` so router tests exercise real SQL without MySQL or a live
JWT server.

Tables included (targeted subset — avoids MySQL-dialect columns such as the
``LONGTEXT`` used in ``privacy_policies``):

  Core identity / auth
    users
    clubs
    club_members
    athletes
    parent_athlete (FK athletes + users — needed for verify_athlete_access)

  Training calendar (TechniqueSessionExercise FK → training_sessions)
    calendar_events   (FK from training_sessions.calendar_event_id)
    training_sessions
    session_attendance

  Technique tables (feature 018)
    technique_skills
    technique_materials
    technique_exercises
    technique_exercise_skills   (M2M)
    technique_exercise_materials (M2M)
    technique_exercise_age_bands
    technique_session_exercises
    athlete_skill_progress

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
  seed_technique_catalog — async helper: inserts a representative minimal
                           catalog (~3 skills, sin_material + real materials,
                           ~5 exercises mixing gymkhana / no-material / multi-
                           age-band) so catalog/detail/filter tests have data
                           without relying on the Alembic seed.

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
from app.models.athlete import Athlete, ParentAthlete, Sex
from app.models.club import Club, ClubMember, ClubRole
from app.models.technique_exercise import (
    AgeBand,
    AthleteSkillProgress,
    ExerciseDifficulty,
    SessionSegment,
    TechniqueExercise,
    TechniqueExerciseAgeBand,
    TechniqueSessionExercise,
    technique_exercise_materials,
    technique_exercise_skills,
)
from app.models.technique_material import TechniqueMaterial
from app.models.technique_skill import TechniqueSkill
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
    # Training calendar (required by TechniqueSessionExercise FK chain)
    "calendar_events",
    "event_audiences",
    "training_sessions",
    "session_attendance",
    # session_media required by get_session selectinload in create_session reload
    "session_media",
    "session_media_athlete",
    # Technique tables (feature 018)
    "technique_skills",
    "technique_materials",
    "technique_exercises",
    "technique_exercise_skills",
    "technique_exercise_materials",
    "technique_exercise_age_bands",
    "technique_session_exercises",
    "athlete_skill_progress",
)


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """In-memory aiosqlite engine with the technique table subset."""
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
    """Insert a Club and flush.  Fictitious data only."""
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
# Technique catalog seed helper
# ---------------------------------------------------------------------------


async def seed_technique_catalog(session: AsyncSession) -> dict:
    """Insert a small but representative technique catalog for test isolation.

    Inserts:
      Skills (3):
        A  posicion    — Posición neutra / equilibrio
        C  frenado     — Frenado modulado
        F  separacion  — Separación cuerpo-bici

      Materials (4):
        sin_material  (is_none=True  — always matches any filter)
        conos         (is_none=False)
        estacas       (is_none=False)
        llantas       (is_none=False)

      Exercises (5):
        1. "pie-abajo-test"
             difficulty=facil, is_game=True, is_gymkhana=False
             age_bands=[7-9, 10-12, 13-15]  (all three)
             skills=[posicion, frenado]
             materials=[conos]

        2. "slalom-test"
             difficulty=facil, is_game=False, is_gymkhana=True
             layout_ascii="[SLALOM]...", layout_alt="Descripción accesible"
             age_bands=[7-9, 10-12]
             skills=[posicion]
             materials=[conos]

        3. "limbo-test"
             difficulty=media, is_game=False, is_gymkhana=True
             layout_ascii="[LIMBO]...", layout_alt="Descripción accesible"
             age_bands=[10-12, 13-15]
             skills=[separacion]
             materials=[estacas, llantas]

        4. "semaforo-test"
             difficulty=facil, is_game=True, is_gymkhana=False
             age_bands=[7-9, 10-12]
             skills=[frenado]
             materials=[sin_material]   ← no-equipment exercise

        5. "trackstand-test"
             difficulty=avanzada, is_game=False, is_gymkhana=False
             age_bands=[13-15]
             skills=[posicion]
             materials=[sin_material]
             is_hidden=True             ← tests include_hidden filter

    Returns a dict with inserted ORM objects keyed by slug/role for assertions.
    Caller is responsible for committing the session.
    """
    now = datetime.now(timezone.utc)

    # --- Skills --------------------------------------------------------------
    skill_posicion = TechniqueSkill(
        code="A",
        name="Posición neutra/lista y equilibrio",
        focus="Postura atlética, peso centrado, trackstand",
        slug="posicion",
        sort_order=1,
    )
    skill_frenado = TechniqueSkill(
        code="C",
        name="Frenado modulado",
        focus="1 dedo por freno, peso atrás, dosificar",
        slug="frenado",
        sort_order=3,
    )
    skill_separacion = TechniqueSkill(
        code="F",
        name="Separación cuerpo-bici",
        focus="Levantar rueda, manual, bunny hop",
        slug="separacion",
        sort_order=6,
    )
    session.add_all([skill_posicion, skill_frenado, skill_separacion])
    await session.flush()

    # --- Materials -----------------------------------------------------------
    mat_none = TechniqueMaterial(
        slug="sin_material",
        name="Sin material",
        is_none=True,
    )
    mat_conos = TechniqueMaterial(
        slug="conos",
        name="Conos",
        is_none=False,
    )
    mat_estacas = TechniqueMaterial(
        slug="estacas",
        name="Estacas",
        is_none=False,
    )
    mat_llantas = TechniqueMaterial(
        slug="llantas",
        name="Llantas / neumáticos viejos",
        is_none=False,
    )
    session.add_all([mat_none, mat_conos, mat_estacas, mat_llantas])
    await session.flush()

    # --- Exercises -----------------------------------------------------------

    # 1. Pie abajo — all age bands, game, no gymkhana, requires conos
    ex_pie_abajo = TechniqueExercise(
        slug="pie-abajo-test",
        name="Pie abajo / Círculo de la muerte (test)",
        summary="Todos pedalean lento dentro de un círculo de conos.",
        how_to=(
            "Dilo: objetivo es mantenerse dentro del círculo sin poner el pie.\n"
            "Muéstralo: el entrenador rueda lento dentro del área.\n"
            "Háganlo: todos inician; tras cada ronda reduce el radio.\n"
            "Revísenlo: ¿qué hiciste para quedarte más tiempo?"
        ),
        difficulty=ExerciseDifficulty.FACIL,
        is_game=True,
        is_gymkhana=False,
        layout_ascii=None,
        layout_alt=None,
        confidence="🟡 [6]",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_pie_abajo)
    await session.flush()

    # 2. Slalom — gymkhana with layout, conos, 7-9 + 10-12
    _LAYOUT_SLALOM = (
        "🚩 SALIDA\n"
        " │\n"
        " ▼\n"
        " ▲   ▲   ▲   ▲   (conos en línea)\n"
        "  ╲ ╱ ╲ ╱ ╲ ╱\n"
        "   ▲   ▲   ▲\n"
    )
    ex_slalom = TechniqueExercise(
        slug="slalom-test",
        name="Slalom de conos (test)",
        summary="Zigzag entre conos; acerca los conos y sube velocidad.",
        how_to=(
            "Dilo: miramos siempre el cono SIGUIENTE.\n"
            "Muéstralo: el entrenador recorre el slalom.\n"
            "Háganlo: conos separados 3-4 m.\n"
            "Revísenlo: ¿dónde ponían los ojos al entrar?"
        ),
        difficulty=ExerciseDifficulty.FACIL,
        is_game=False,
        is_gymkhana=True,
        layout_ascii=_LAYOUT_SLALOM,
        layout_alt=(
            "Fila de conos alternados a izquierda y derecha separados 3-4 m. "
            "El ciclista recorre en zigzag."
        ),
        confidence="🟡⚪ [6][13]",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_slalom)
    await session.flush()

    # 3. Limbo — gymkhana, estacas+llantas, 10-12 + 13-15
    _LAYOUT_LIMBO = (
        "⊓  LIMBO en bici  ▮━━━━━━▮\n"
        "   (separación cuerpo-bici)\n"
    )
    ex_limbo = TechniqueExercise(
        slug="limbo-test",
        name="Limbo en bici (test)",
        summary="Pasar agachado bajo una barra sin tocarla.",
        how_to=(
            "Dilo: pasen bajo la barra sin tocarla.\n"
            "Muéstralo: el entrenador pasa lento bajando el centro de gravedad.\n"
            "Háganlo: empieza con la barra alta (hombros).\n"
            "Revísenlo: ¿qué parte del cuerpo les costó más separar?"
        ),
        difficulty=ExerciseDifficulty.MEDIA,
        is_game=False,
        is_gymkhana=True,
        layout_ascii=_LAYOUT_LIMBO,
        layout_alt=(
            "Dos estacas a ambos lados del carril, cuerda horizontal. "
            "El ciclista se agacha para separar el cuerpo de la bici."
        ),
        confidence="🟡 [6]",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_limbo)
    await session.flush()

    # 4. Semáforo — no material, game, 7-9 + 10-12
    ex_semaforo = TechniqueExercise(
        slug="semaforo-test",
        name="Semáforo (test)",
        summary="Verde avanza, rojo frena en seco.",
        how_to=(
            "Dilo: cuando digo VERDE, pedalean; ROJO, frenan.\n"
            "Muéstralo: el entrenador frena en seco al escuchar ROJO.\n"
            "Háganlo: empieza con cambios lentos.\n"
            "Revísenlo: ¿cuándo sentiste que ibas a pasarte?"
        ),
        difficulty=ExerciseDifficulty.FACIL,
        is_game=True,
        is_gymkhana=False,
        layout_ascii=None,
        layout_alt=None,
        confidence="🟡 [6]",
        is_seeded=True,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )
    session.add(ex_semaforo)
    await session.flush()

    # 5. Trackstand — advanced, hidden, 13-15 only, no material
    ex_trackstand = TechniqueExercise(
        slug="trackstand-test",
        name="Trackstand challenge (test)",
        summary="Quedarse parado en equilibrio sobre la bici.",
        how_to=(
            "Dilo: objetivo es quedarse parado en equilibrio.\n"
            "Muéstralo: el entrenador muestra el trackstand.\n"
            "Háganlo: cada uno intenta 3 veces seguidas.\n"
            "Revísenlo: ¿qué os ayudó a aguantar más?"
        ),
        difficulty=ExerciseDifficulty.AVANZADA,
        is_game=False,
        is_gymkhana=False,
        layout_ascii=None,
        layout_alt=None,
        confidence="⚪ [13]",
        is_seeded=True,
        is_hidden=True,  # soft-hidden — tests include_hidden filter
        created_at=now,
        updated_at=now,
    )
    session.add(ex_trackstand)
    await session.flush()

    # --- Age bands -----------------------------------------------------------
    # pie_abajo: all three
    for band in (AgeBand.BAND_7_9, AgeBand.BAND_10_12, AgeBand.BAND_13_15):
        session.add(TechniqueExerciseAgeBand(exercise_id=ex_pie_abajo.id, age_band=band))
    # slalom: 7-9, 10-12
    for band in (AgeBand.BAND_7_9, AgeBand.BAND_10_12):
        session.add(TechniqueExerciseAgeBand(exercise_id=ex_slalom.id, age_band=band))
    # limbo: 10-12, 13-15
    for band in (AgeBand.BAND_10_12, AgeBand.BAND_13_15):
        session.add(TechniqueExerciseAgeBand(exercise_id=ex_limbo.id, age_band=band))
    # semaforo: 7-9, 10-12
    for band in (AgeBand.BAND_7_9, AgeBand.BAND_10_12):
        session.add(TechniqueExerciseAgeBand(exercise_id=ex_semaforo.id, age_band=band))
    # trackstand: 13-15 only
    session.add(TechniqueExerciseAgeBand(exercise_id=ex_trackstand.id, age_band=AgeBand.BAND_13_15))
    await session.flush()

    # --- M2M: skills ---------------------------------------------------------
    await session.execute(
        technique_exercise_skills.insert(),
        [
            # pie_abajo → posicion, frenado
            {"exercise_id": ex_pie_abajo.id, "skill_id": skill_posicion.id},
            {"exercise_id": ex_pie_abajo.id, "skill_id": skill_frenado.id},
            # slalom → posicion
            {"exercise_id": ex_slalom.id, "skill_id": skill_posicion.id},
            # limbo → separacion
            {"exercise_id": ex_limbo.id, "skill_id": skill_separacion.id},
            # semaforo → frenado
            {"exercise_id": ex_semaforo.id, "skill_id": skill_frenado.id},
            # trackstand → posicion
            {"exercise_id": ex_trackstand.id, "skill_id": skill_posicion.id},
        ],
    )

    # --- M2M: materials -------------------------------------------------------
    await session.execute(
        technique_exercise_materials.insert(),
        [
            # pie_abajo → conos
            {"exercise_id": ex_pie_abajo.id, "material_id": mat_conos.id},
            # slalom → conos
            {"exercise_id": ex_slalom.id, "material_id": mat_conos.id},
            # limbo → estacas, llantas
            {"exercise_id": ex_limbo.id, "material_id": mat_estacas.id},
            {"exercise_id": ex_limbo.id, "material_id": mat_llantas.id},
            # semaforo → sin_material
            {"exercise_id": ex_semaforo.id, "material_id": mat_none.id},
            # trackstand → sin_material
            {"exercise_id": ex_trackstand.id, "material_id": mat_none.id},
        ],
    )
    await session.flush()

    return {
        "skills": {
            "posicion": skill_posicion,
            "frenado": skill_frenado,
            "separacion": skill_separacion,
        },
        "materials": {
            "sin_material": mat_none,
            "conos": mat_conos,
            "estacas": mat_estacas,
            "llantas": mat_llantas,
        },
        "exercises": {
            "pie_abajo": ex_pie_abajo,
            "slalom": ex_slalom,
            "limbo": ex_limbo,
            "semaforo": ex_semaforo,
            "trackstand": ex_trackstand,
        },
    }


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
