"""Tests aiosqlite de los loaders de ``app.services.race.ai.athlete_context``
(feature 037, T103).

Usa una DB aiosqlite in-memory real (no mocks de ORM) para verificar límites
de ventana, ausencia de asistencia, ausencia total de claves de peso/IMC/
nutrición, y el catálogo con los 8 skills A-H. Todos los nombres y fechas de
fixture son ficticios (CLAUDE.md §Privacidad).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.athlete import Athlete, ParentAthlete, Sex
from app.models.club import Club
from app.models.technique_skill import TechniqueSkill
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionKind,
    SessionStatus,
    TrainingSession,
)
from app.models.user import User, UserRole
from app.services.race.ai import athlete_context as mod

pytestmark = pytest.mark.asyncio

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "parent_athlete",
    "anthropometric_records",
    "training_sessions",
    "session_attendance",
    "technique_skills",
    "technique_materials",
    "technique_exercises",
    "technique_exercise_skills",
    "technique_exercise_materials",
    "technique_exercise_age_bands",
    "technique_session_exercises",
    "strength_exercises",
    "strength_exercise_age_bands",
    "strength_blocks",
    "strength_block_entries",
    "strength_session_blocks",
    "interval_structures",
    "interval_templates",
    "interval_template_blocks",
)


@pytest_asyncio.fixture
async def engine():
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
async def session(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_club_and_athlete(
    session: AsyncSession, *, athlete_id: int = 1, club_id: int = 1, birth_year: int = 2013
) -> Athlete:
    existing_club = await session.get(Club, club_id)
    if existing_club is None:
        session.add(
            Club(
                id=club_id,
                name="Club Ficticio de Prueba",
                code=f"TST{club_id:03d}",
                location="Valle del Cauca — datos ficticios",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
    existing_coach = await session.get(User, 100)
    coach_user = existing_coach
    if existing_coach is None:
        coach_user = User(
            id=100,
            email="entrenador.ficticio@test.com",
            hashed_password="x",
            first_name="Entrenador",
            last_name="Ficticio",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(coach_user)
    athlete_user = User(
        id=200 + athlete_id,
        email=f"atleta.ficticio{athlete_id}@test.com",
        hashed_password="x",
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(athlete_user)
    await session.flush()

    athlete = Athlete(
        id=athlete_id,
        user_id=athlete_user.id,
        first_name="Atleta",
        last_name=f"Ficticio{athlete_id}",
        birth_date=date(birth_year, 3, 15),
        sex=Sex.M,
        club_id=club_id,
        created_by=coach_user.id,
    )
    session.add(athlete)
    await session.flush()

    parent_user = User(
        id=300 + athlete_id,
        email=f"padre.ficticio{athlete_id}@test.com",
        hashed_password="x",
        first_name="Padre",
        last_name=f"Ficticio{athlete_id}",
        role=UserRole.parent,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(parent_user)
    await session.flush()
    session.add(ParentAthlete(parent_id=parent_user.id, athlete_id=athlete.id, relationship_type="madre"))
    await session.flush()

    return athlete


# ---------------------------------------------------------------------------
# load_anthro_context
# ---------------------------------------------------------------------------


async def test_load_anthro_context_none_without_records(session: AsyncSession):
    await _seed_club_and_athlete(session)
    result = await mod.load_anthro_context(session, athlete_id=1, reference_date=date(2026, 6, 1))
    assert result is None


async def test_load_anthro_context_never_exposes_weight_bmi_nutrition(session: AsyncSession):
    await _seed_club_and_athlete(session)
    session.add(
        AnthropometricRecord(
            athlete_id=1,
            evaluation_date=date(2026, 1, 1),
            weight_kg=Decimal("40.0"),
            standing_height_cm=Decimal("150.0"),
            sitting_height_cm=Decimal("78.0"),
            leg_length_cm=Decimal("72.0"),
            leg_sitting_ratio=Decimal("0.9231"),
            maturity_offset=Decimal("-1.5"),
            age_at_phv=Decimal("13.0"),
            maturation_status=MaturationStatus.pre_phv,
            evaluated_by=100,
            created_at=datetime.now(timezone.utc),
            bmi=Decimal("17.7"),
            nutritional_status=NutritionalStatus.talla_adecuada,
            height_percentile=Decimal("55.0"),
        )
    )
    await session.flush()

    result = await mod.load_anthro_context(session, athlete_id=1, reference_date=date(2026, 6, 1))
    assert result is not None

    # Recorrido recursivo: ninguna clave de peso/IMC/nutrición debe aparecer
    # en ningún nivel del dict retornado.
    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k not in {"weight_kg", "weight", "bmi", "nutritional_status", "weight_percentile", "weight_z_score", "bmi_z_score", "bmi_percentile"}
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(result)
    assert result["latest"]["maturation_status"] == "Pre-PHV"
    assert result["latest"]["height_percentile"] == 55.0
    assert result["records_count"] == 1
    assert result["previous"] is None


async def test_load_anthro_context_growth_velocity_and_flags(session: AsyncSession):
    await _seed_club_and_athlete(session)
    session.add_all(
        [
            AnthropometricRecord(
                athlete_id=1,
                evaluation_date=date(2026, 1, 1),
                weight_kg=Decimal("38.0"),
                standing_height_cm=Decimal("148.0"),
                sitting_height_cm=Decimal("77.0"),
                leg_length_cm=Decimal("71.0"),
                leg_sitting_ratio=Decimal("0.9"),
                maturity_offset=Decimal("-1.8"),
                age_at_phv=Decimal("13.0"),
                maturation_status=MaturationStatus.pre_phv,
                evaluated_by=100,
                created_at=datetime.now(timezone.utc),
            ),
            AnthropometricRecord(
                athlete_id=1,
                evaluation_date=date(2026, 4, 1),
                weight_kg=Decimal("40.0"),
                standing_height_cm=Decimal("151.0"),
                sitting_height_cm=Decimal("78.0"),
                leg_length_cm=Decimal("73.0"),
                leg_sitting_ratio=Decimal("0.9"),
                maturity_offset=Decimal("-1.4"),
                age_at_phv=Decimal("13.2"),
                maturation_status=MaturationStatus.pre_phv,
                evaluated_by=100,
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )
    await session.flush()

    # Ventana de referencia lejana → dispara stale_measurement_gt_120d.
    result = await mod.load_anthro_context(session, athlete_id=1, reference_date=date(2026, 9, 1))
    assert result["records_count"] == 2
    assert result["previous"]["evaluation_date"] == "2026-01-01"
    assert result["growth_velocity_cm_per_year"] is not None
    assert result["growth_velocity_cm_per_year"] > 0
    assert "approaching_circa_phv" in result["flags"]
    assert "stale_measurement_gt_120d" in result["flags"]


# ---------------------------------------------------------------------------
# load_training_window
# ---------------------------------------------------------------------------


async def test_load_training_window_none_without_attendance(session: AsyncSession):
    await _seed_club_and_athlete(session)
    result = await mod.load_training_window(
        session, athlete_id=1, club_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 28)
    )
    assert result is None


async def test_load_training_window_respects_boundaries_and_aggregates(session: AsyncSession):
    await _seed_club_and_athlete(session)

    # Dentro de la ventana [2026-05-01, 2026-05-28].
    in_window = TrainingSession(
        id=1,
        club_id=1,
        created_by_user_id=100,
        status=SessionStatus.EXECUTED,
        scheduled_date=date(2026, 5, 20),
        scheduled_start_time=datetime(2026, 5, 20, 16, 0).time(),
        duration_min=90,
        location="Pista ficticia",
        technical_focus="Curvas cerradas y frenado",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    # Fuera de la ventana (antes de date_from).
    out_of_window = TrainingSession(
        id=2,
        club_id=1,
        created_by_user_id=100,
        status=SessionStatus.EXECUTED,
        scheduled_date=date(2026, 4, 1),
        scheduled_start_time=datetime(2026, 4, 1, 16, 0).time(),
        duration_min=60,
        location="Pista ficticia",
        technical_focus="Cambios y cadencia",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add_all([in_window, out_of_window])
    await session.flush()

    session.add_all(
        [
            SessionAttendance(
                session_id=1,
                athlete_id=1,
                status=AttendanceStatus.PRESENTE,
                rpe_omni=6,
                rubric_effort=4,
                rubric_attitude=5,
                rubric_technique=4,
                individual_feedback="Buen manejo en curvas cerradas de la pista ficticia.",
            ),
            SessionAttendance(
                session_id=2,
                athlete_id=1,
                status=AttendanceStatus.AUSENTE,
            ),
        ]
    )
    await session.flush()

    result = await mod.load_training_window(
        session, athlete_id=1, club_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 28)
    )
    assert result is not None
    assert result["sessions_in_window"] == 1  # solo in_window: out_of_window queda fuera
    assert result["attended"] == 1
    assert result["absent"] == 0
    assert result["attendance_pct"] == 100.0
    assert result["training_hours"] == 1.5
    assert result["rpe_mean"] == 6.0
    assert result["coach_feedback"] == ["Buen manejo en curvas cerradas de la pista ficticia."]
    assert result["technical_foci"]


# ---------------------------------------------------------------------------
# load_catalog_context
# ---------------------------------------------------------------------------


async def test_load_catalog_context_has_all_eight_skills(session: AsyncSession):
    await _seed_club_and_athlete(session)
    codes = "ABCDEFGH"
    for i, code in enumerate(codes):
        session.add(
            TechniqueSkill(
                code=code,
                name=f"Habilidad {code}",
                focus=f"Foco ficticio {code}",
                slug=f"skill-{code.lower()}",
                sort_order=i,
            )
        )
    await session.flush()

    catalog = await mod.load_catalog_context(session, club_id=1, age_band="10-12")
    assert len(catalog["technique_skills"]) == 8
    assert {s["code"] for s in catalog["technique_skills"]} == set(codes)
    assert catalog["strength_blocks"] == []
    assert catalog["interval_templates"] == []


# ---------------------------------------------------------------------------
# load_club_forbidden_names
# ---------------------------------------------------------------------------


async def test_load_club_forbidden_names_includes_athletes_and_parents(session: AsyncSession):
    await _seed_club_and_athlete(session, athlete_id=1)
    await _seed_club_and_athlete(session, athlete_id=2)

    names = await mod.load_club_forbidden_names(session, club_id=1)
    assert "Atleta Ficticio1" in names
    assert "Atleta Ficticio2" in names
    assert "Padre Ficticio1" in names
    assert "Padre Ficticio2" in names


# ---------------------------------------------------------------------------
# age_band_from_age
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age,expected",
    [(7.0, "7-9"), (9.9, "7-9"), (10.0, "10-12"), (12.9, "10-12"), (13.0, "13-15"), (15.0, "13-15")],
)
def test_age_band_from_age(age, expected):
    assert mod.age_band_from_age(age) == expected
