"""Router tests for ``GET /api/athletes/{athlete_id}/growth-summary`` (feature 040 / T031).

Covers the 11 cases of ``contracts/growth-summary-api.md``:

1. coach of the athlete's club → 200, full body
2. admin → 200
3. linked parent → 200
4. unlinked parent → 403
5. unknown athlete → 404
6. no records → the ``never`` variant
7. one record → ``velocity: null``
8. interval < 30 days → ``interval_short`` true, no ``rapid_growth``
9. rapid growth (>= 0.6 cm/month, interval >= 30 days) → alert present
10. Circa-PHV stage → ``circa_phv`` alert and ``interval_days: 30``
11. privacy invariant: no ``first_name``/``last_name``/``birth_date`` key anywhere

Strategy: SQLite async in-memory with ``app.main.app`` + dependency overrides
for ``get_db``/``get_current_user`` — same pattern as
``tests/routers/test_dashboard_summary.py``. ``growth.router`` is
unconditionally mounted in ``app.main``, so no local ASGI app is needed;
``verify_athlete_access`` runs for real against the overridden session, which
is what gives us genuine 403/404 behaviour for free.

All data is fictitious (CLAUDE.md §Privacy) — no real TyR athlete data, no
minor's name or birth date anywhere in this file.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.club import ClubRole
from app.models.growth import GrowthSource
from app.models.user import UserRole

pytestmark = pytest.mark.asyncio

_TABLES = ("athletes", "anthropometric_records", "parent_athlete")

_TODAY = date.today()
_BIRTH_DATE = date(2013, 1, 1)  # atleta ficticio, ~13 años — no es un dato real


# ---------------------------------------------------------------------------
# DB fixtures — mirrors tests/routers/test_dashboard_summary.py
# ---------------------------------------------------------------------------


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
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fake users — SimpleNamespace, same convention as test_dashboard_summary.py:
# avoids lazy-loading the real ORM relationship outside of a session.
# ---------------------------------------------------------------------------


def coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


def admin_user(user_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.admin, club_memberships=[])


def parent_user(user_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.parent, club_memberships=[])


def make_client(session: AsyncSession, *, user) -> AsyncClient:
    """Bind an AsyncClient to the real ``app.main.app`` with DB/auth overrides."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def seed_athlete(
    session: AsyncSession,
    *,
    athlete_id: int = 200,
    club_id: int = 1,
    sex: Sex = Sex.M,
) -> Athlete:
    """Fictitious athlete — generic first/last name, synthetic birth date."""
    a = Athlete(
        id=athlete_id,
        user_id=athlete_id,
        first_name="Atleta",
        last_name="Prueba",
        birth_date=_BIRTH_DATE,
        sex=sex,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_record(
    session: AsyncSession,
    *,
    record_id: int,
    athlete_id: int,
    evaluation_date: date,
    standing_height_cm: float = 150.0,
    weight_kg: float = 40.0,
    maturity_offset: float = 0.0,
    age_at_phv: float = 12.5,
    maturation_status: MaturationStatus = MaturationStatus.pre_phv,
) -> AnthropometricRecord:
    bmi = round(weight_kg / (standing_height_cm / 100) ** 2, 2)
    r = AnthropometricRecord(
        id=record_id,
        athlete_id=athlete_id,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight_kg)),
        standing_height_cm=Decimal(str(standing_height_cm)),
        sitting_height_cm=Decimal("74.0"),
        leg_length_cm=Decimal("76.0"),
        leg_sitting_ratio=Decimal("1.0270"),
        maturity_offset=Decimal(str(maturity_offset)),
        age_at_phv=Decimal(str(age_at_phv)),
        maturation_status=maturation_status,
        evaluated_by=1,
        bmi=Decimal(str(bmi)),
        height_z_score=Decimal("-0.500"),
        height_percentile=Decimal("30.9"),
        bmi_z_score=Decimal("0.200"),
        bmi_percentile=Decimal("57.9"),
        growth_source=GrowthSource.WHO,
    )
    session.add(r)
    await session.flush()
    return r


async def link_parent(
    session: AsyncSession, *, parent_user_id: int, athlete_id: int
) -> ParentAthlete:
    pa = ParentAthlete(
        parent_id=parent_user_id,
        athlete_id=athlete_id,
        relationship_type=FamilyRelationship.padre,
    )
    session.add(pa)
    await session.flush()
    return pa


_URL = "/api/athletes/{athlete_id}/growth-summary"


# ---------------------------------------------------------------------------
# 1-2. RBAC happy paths: coach and admin
# ---------------------------------------------------------------------------


async def test_coach_of_the_club_gets_full_body(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=201)
    await seed_record(
        session, record_id=1, athlete_id=athlete.id, evaluation_date=_TODAY - timedelta(days=90)
    )
    await seed_record(session, record_id=2, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["athlete_id"] == athlete.id
    assert data["records_count"] == 2
    assert data["stage"] == "Pre-PHV"
    assert data["velocity"] is not None
    assert data["measurement"]["status"] in {"ok", "due_soon", "overdue"}
    assert data["latest"]["record_id"] == 2
    assert data["latest"]["growth_source"] == "WHO"
    assert data["latest"]["height"]["band"] == "talla_adecuada"


async def test_admin_gets_200(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=202)
    await seed_record(session, record_id=3, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=admin_user()) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 3-4. Parent RBAC
# ---------------------------------------------------------------------------


async def test_linked_parent_gets_200(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=203)
    await seed_record(session, record_id=4, athlete_id=athlete.id, evaluation_date=_TODAY)
    await link_parent(session, parent_user_id=30, athlete_id=athlete.id)
    await session.commit()

    async with make_client(session, user=parent_user(user_id=30)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text


async def test_unlinked_parent_gets_403(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=204)
    await seed_record(session, record_id=5, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=parent_user(user_id=31)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. Unknown athlete
# ---------------------------------------------------------------------------


async def test_unknown_athlete_gets_404(session: AsyncSession) -> None:
    async with make_client(session, user=coach_user()) as client:
        resp = await client.get(_URL.format(athlete_id=999999))

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6-7. No records / one record
# ---------------------------------------------------------------------------


async def test_no_records_returns_never_variant(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=205)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["records_count"] == 0
    assert data["stage"] is None
    assert data["velocity"] is None
    assert data["latest"] is None
    assert data["measurement"]["status"] == "never"
    assert data["alerts"] == []


async def test_one_record_has_null_velocity(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=206)
    await seed_record(session, record_id=6, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["records_count"] == 1
    assert data["velocity"] is None
    assert data["latest"] is not None


# ---------------------------------------------------------------------------
# 8-9. Velocity / interval_short / rapid_growth
# ---------------------------------------------------------------------------


async def test_short_interval_suppresses_rapid_growth(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=207)
    await seed_record(
        session,
        record_id=7,
        athlete_id=athlete.id,
        evaluation_date=_TODAY - timedelta(days=20),
        standing_height_cm=149.0,
    )
    await seed_record(
        session,
        record_id=8,
        athlete_id=athlete.id,
        evaluation_date=_TODAY,
        standing_height_cm=150.0,
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["velocity"]["interval_short"] is True
    assert "rapid_growth" not in data["alerts"]


async def test_rapid_growth_alert_over_normal_interval(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=208)
    await seed_record(
        session,
        record_id=9,
        athlete_id=athlete.id,
        evaluation_date=_TODAY - timedelta(days=62),
        standing_height_cm=147.0,
    )
    await seed_record(
        session,
        record_id=10,
        athlete_id=athlete.id,
        evaluation_date=_TODAY,
        standing_height_cm=150.0,
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["velocity"]["interval_short"] is False
    assert data["velocity"]["cm_per_month"] >= 0.6
    assert "rapid_growth" in data["alerts"]


# ---------------------------------------------------------------------------
# 10. Circa-PHV stage
# ---------------------------------------------------------------------------


async def test_circa_phv_stage_alert_and_30_day_interval(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=209)
    await seed_record(
        session,
        record_id=11,
        athlete_id=athlete.id,
        evaluation_date=_TODAY,
        maturation_status=MaturationStatus.circa_phv,
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "circa_phv" in data["alerts"]
    assert data["measurement"]["interval_days"] == 30


# ---------------------------------------------------------------------------
# 11. Privacy invariant
# ---------------------------------------------------------------------------


async def test_response_has_no_identifying_keys(session: AsyncSession) -> None:
    athlete = await seed_athlete(session, athlete_id=210)
    await seed_record(session, record_id=12, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    assert "first_name" not in resp.text
    assert "last_name" not in resp.text
    assert "birth_date" not in resp.text
