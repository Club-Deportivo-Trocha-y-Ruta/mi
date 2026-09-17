"""Feature "adult athlete path": :func:`resolve_athlete_ai_context` para un
atleta adulto (≥18 años).

DB aiosqlite in-memory real (mismo patrón que
``tests/services/race/ai/test_athlete_context.py``). Datos 100% ficticios
(CLAUDE.md §Privacidad).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.club import Club
from app.models.user import User, UserRole
from app.services.race.group_launch import resolve_athlete_ai_context
from app.services.race.schemas import LTADGroup
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "parent_athlete",
    "anthropometric_records",
    *AUDIT_TABLES,
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


async def _seed_adult_athlete(session: AsyncSession, *, birth_year: int) -> Athlete:
    session.add(
        Club(
            id=1,
            name="Club Ficticio Adulto",
            code="TST001",
            location="Valle del Cauca — datos ficticios",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
    )
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
        id=201,
        email="atleta.adulto.ficticio@test.com",
        hashed_password="x",
        first_name="Atleta",
        last_name="AdultoFicticio",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(athlete_user)
    await session.flush()

    athlete = Athlete(
        id=1,
        user_id=athlete_user.id,
        first_name="Atleta",
        last_name="AdultoFicticio",
        birth_date=date(birth_year, 3, 15),
        sex=Sex.M,
        club_id=1,
        created_by=coach_user.id,
    )
    session.add(athlete)
    await session.flush()
    return athlete


async def test_resolve_athlete_ai_context_adult_gets_adulto_group_and_no_maturation(
    session: AsyncSession,
):
    """31 años → LTADGroup.ADULTO real (no JUNIOR, el bug de producción
    documentado en CLAUDE.md) y maturation_status=None (PHV no aplica)."""
    today = date.today()
    athlete = await _seed_adult_athlete(session, birth_year=today.year - 31)

    ctx = await resolve_athlete_ai_context(session, athlete)

    assert ctx.athlete_age == 31
    assert ctx.ltad_group == LTADGroup.ADULTO.value
    assert ctx.maturation_status is None


async def test_resolve_athlete_ai_context_adult_ignores_stale_anthro_record(
    session: AsyncSession,
):
    """Aunque el club tuviera (caso límite) un registro antropométrico viejo
    de cuando el atleta era menor, ``maturation_status`` sigue en ``None``
    para un análisis de adulto — nunca debe filtrarse al prompt."""
    today = date.today()
    athlete = await _seed_adult_athlete(session, birth_year=today.year - 20)
    session.add(
        AnthropometricRecord(
            athlete_id=athlete.id,
            evaluation_date=date(today.year - 6, 1, 1),
            weight_kg=Decimal("55.0"),
            standing_height_cm=Decimal("165.0"),
            sitting_height_cm=Decimal("85.0"),
            leg_length_cm=Decimal("80.0"),
            leg_sitting_ratio=Decimal("0.94"),
            maturity_offset=Decimal("0.5"),
            age_at_phv=Decimal("13.5"),
            maturation_status=MaturationStatus.post_phv,
            evaluated_by=100,
            created_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()

    ctx = await resolve_athlete_ai_context(session, athlete)

    assert ctx.athlete_age == 20
    assert ctx.ltad_group == LTADGroup.ADULTO.value
    assert ctx.maturation_status is None


async def test_resolve_athlete_ai_context_minor_still_gets_maturation_lookup(
    session: AsyncSession,
):
    """Regresión: un menor (12 años) sigue resolviendo maturation_status vía
    la consulta real (None acá porque no hay registro, pero la ruta de
    consulta se ejerció, a diferencia del adulto)."""
    today = date.today()
    athlete = await _seed_adult_athlete(session, birth_year=today.year - 12)

    ctx = await resolve_athlete_ai_context(session, athlete)

    assert ctx.athlete_age == 12
    assert ctx.ltad_group == LTADGroup.BAMBINO.value
    assert ctx.maturation_status is None
