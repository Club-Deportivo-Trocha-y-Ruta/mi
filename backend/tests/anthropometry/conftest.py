"""Arnés compartido de las pruebas de API de la feature 048.

App real (``app.main.app``) sobre aiosqlite en memoria, con ``get_db`` y
``get_current_user`` sobreescritos por prueba para que ``verify_athlete_access``
y ``require_role`` corran de verdad (RBAC honesto), y notificaciones/dispatcher
falsos. Todo ficticio: ningún dato real de deportistas.

Datos sembrados:

- club 1: admin 900, coach 10 (evaluador), coach 11 (otro coach del club),
  padre 20 (vinculado al atleta 144).
- club 2: coach 12 (de otro club).
- atleta 144 (club 1, nace 2013-05-10), atleta 145 (club 1), atleta 200 (club 2).
- Tabla LMS OMS sintética (L=1) para que los percentiles se puedan verificar
  a mano: ``z = (valor / M - 1) / S``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
)
from app.main import app
from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Sex
from app.models.club import ClubRole
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES


# ``privacy_policies.content_html`` es LONGTEXT de MySQL: SQLite no lo compila.
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # pragma: no cover
    return "TEXT"


ADMIN_ID = 900
COACH_ID = 10  # evaluador de los registros sembrados
COACH2_ID = 11  # otro coach del mismo club
FOREIGN_COACH_ID = 12  # coach de otro club
PARENT_ID = 20

ATHLETE_ID = 144
OTHER_ATHLETE_ID = 145
FOREIGN_ATHLETE_ID = 200
HOME_CLUB_ID = 1
OTHER_CLUB_ID = 2

ATHLETE_BIRTH_DATE = date(2013, 5, 10)

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "anthropometric_records",
    "skinfold_measurements",
    "athlete_ai_explanations",
    "growth_reference_lms",
    "parental_consents",
    *AUDIT_TABLES,
)

# (M, S) por indicador; L = 1 => z = (valor / M - 1) / S
LMS_M_S = {
    GrowthIndicator.height_for_age: (150.0, 0.05),
    GrowthIndicator.weight_for_age: (40.0, 0.10),
    GrowthIndicator.bmi_for_age: (20.0, 0.10),
}

VALID_SITES = {
    "triceps": {"readings": [8.5, 9.0]},
    "biceps": {"readings": [5.0, 5.0]},
    "subscapular": {"readings": [7.0, 7.5]},
    "medial_calf": {"readings": [10.0, 10.5]},
    "iliac_crest": {"declined": True},
    "supraspinale": {"readings": [6.0, 6.5]},
}


def make_user(user_id: int, role: UserRole, club_id: int | None = HOME_CLUB_ID) -> SimpleNamespace:
    role_in_club = {
        UserRole.coach: ClubRole.coach,
        UserRole.admin: ClubRole.admin,
    }.get(role, ClubRole.parent)
    memberships = (
        [SimpleNamespace(club_id=club_id, role_in_club=role_in_club)] if club_id is not None else []
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=memberships,
    )


USERS = {
    "admin": make_user(ADMIN_ID, UserRole.admin),
    "coach": make_user(COACH_ID, UserRole.coach),
    "coach2": make_user(COACH2_ID, UserRole.coach),
    "foreign_coach": make_user(FOREIGN_COACH_ID, UserRole.coach, club_id=OTHER_CLUB_ID),
    "parent": make_user(PARENT_ID, UserRole.parent, club_id=None),
}


@pytest_asyncio.fixture
async def anthro_engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def anthro_factory(anthro_engine) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(anthro_engine, expire_on_commit=False)
    async with factory() as s:
        await create_club(s, club_id=HOME_CLUB_ID, code="club1")
        await create_club(s, club_id=OTHER_CLUB_ID, code="club2")
        await create_user(s, user_id=ADMIN_ID, role=UserRole.admin, email="admin@test.com")
        await link_user_to_club(s, user_id=ADMIN_ID, club_id=HOME_CLUB_ID, role_in_club=ClubRole.admin)
        for uid, club in ((COACH_ID, HOME_CLUB_ID), (COACH2_ID, HOME_CLUB_ID), (FOREIGN_COACH_ID, OTHER_CLUB_ID)):
            await create_user(s, user_id=uid, role=UserRole.coach, email=f"coach{uid}@test.com")
            await link_user_to_club(s, user_id=uid, club_id=club, role_in_club=ClubRole.coach)
        await create_user(s, user_id=PARENT_ID, role=UserRole.parent, email="parent@test.com")
        for aid, club, name in (
            (ATHLETE_ID, HOME_CLUB_ID, "Uno"),
            (OTHER_ATHLETE_ID, HOME_CLUB_ID, "Dos"),
            (FOREIGN_ATHLETE_ID, OTHER_CLUB_ID, "Tres"),
        ):
            await create_user(
                s, user_id=aid, role=UserRole.athlete, can_login=False,
                first_name="Deportista", last_name=f"Ficticio {name}",
            )
            await create_athlete(
                s,
                athlete_id=aid,
                club_id=club,
                user_id=aid,
                first_name="Deportista",
                last_name=f"Ficticio {name}",
                birth_date=ATHLETE_BIRTH_DATE,
                sex=Sex.M,
            )
        await link_parent_to_athlete(s, parent_user_id=PARENT_ID, athlete_id=ATHLETE_ID)
        for indicator, (m, sd) in LMS_M_S.items():
            for age_months in (60.0, 240.0):
                s.add(
                    GrowthReferenceLms(
                        source=GrowthSource.WHO, indicator=indicator, sex="M",
                        age_months=age_months, L=1.0, M=m, S=sd,
                    )
                )
        await s.commit()
    return factory


@pytest.fixture
def anthro_notifier() -> SimpleNamespace:
    """Dobles de notificación/dispatcher. Las pruebas asertan que no se usan."""
    return SimpleNamespace(service=MagicMock(send=AsyncMock()), dispatcher=MagicMock())


@pytest_asyncio.fixture
async def make_client(anthro_factory, anthro_notifier) -> AsyncGenerator[Callable[[str], AsyncClient], None]:
    """``make_client("coach")`` -> AsyncClient autenticado como ese usuario."""
    clients: list[AsyncClient] = []

    async def _override_db():
        async with anthro_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    def _build(user_key: str) -> AsyncClient:
        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: USERS[user_key]
        app.dependency_overrides[get_notification_service] = lambda: anthro_notifier.service
        app.dependency_overrides[get_task_dispatcher] = lambda: anthro_notifier.dispatcher
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield _build
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()


async def seed_record(
    factory: async_sessionmaker[AsyncSession],
    *,
    athlete_id: int = ATHLETE_ID,
    evaluation_date: date = date(2026, 5, 1),
    evaluated_by: int = COACH_ID,
    weight: str = "40.0",
    standing: str = "150.0",
    sitting: str = "76.0",
    arm_span: str | None = None,
) -> int:
    """Registro con derivados *obsoletos a propósito* (IMC 1.00, offset 0)
    para que una prueba pueda comprobar que un PUT los recalcula."""
    async with factory() as s:
        record = AnthropometricRecord(
            athlete_id=athlete_id,
            evaluation_date=evaluation_date,
            weight_kg=Decimal(weight),
            standing_height_cm=Decimal(standing),
            sitting_height_cm=Decimal(sitting),
            arm_span_cm=Decimal(arm_span) if arm_span else None,
            leg_length_cm=Decimal("1.0"),
            leg_sitting_ratio=Decimal("1.0000"),
            maturity_offset=Decimal("0.00"),
            age_at_phv=Decimal("0.00"),
            maturation_status=MaturationStatus.circa_phv,
            bmi=Decimal("1.00"),
            height_z_score=Decimal("9.000"),
            height_percentile=Decimal("99.9"),
            evaluated_by=evaluated_by,
        )
        s.add(record)
        await s.commit()
        await s.refresh(record)
        return record.id


def record_body(
    *,
    evaluation_date: str = "2026-05-01",
    weight: str = "42.0",
    standing: str = "156.0",
    sitting: str = "80.0",
    arm_span: str | None = None,
    notes: str | None = None,
) -> dict:
    body: dict = {
        "evaluation_date": evaluation_date,
        "weight_kg": weight,
        "standing_height_cm": standing,
        "sitting_height_cm": sitting,
    }
    if arm_span is not None:
        body["arm_span_cm"] = arm_span
    if notes is not None:
        body["notes"] = notes
    return body


def error_code(resp) -> str | None:
    """Código de un error 4xx sea ``{"detail": "codigo"}`` o
    ``{"detail": {"code"|"detail": "codigo", ...}}``."""
    detail = resp.json()["detail"]
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return detail.get("code") or detail.get("detail")
    return None


def error_field(resp, key: str):
    """Campo extra del cuerpo de error (top-level o dentro de ``detail``)."""
    body = resp.json()
    if key in body:
        return body[key]
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get(key)
    return None
