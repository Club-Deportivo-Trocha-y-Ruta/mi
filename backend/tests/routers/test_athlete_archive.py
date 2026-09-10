"""T045 — pruebas de contrato de archivado/restauración de atletas.

Ver ``specs/041-multi-coach-governance/contracts/athlete-archive.md`` §12.1.
No existía ningún test para ``DELETE /api/athletes/{id}`` ni para
``POST /api/athletes/{id}/restore`` antes de esta feature.

``archive_athlete``/``restore_athlete`` (``app/services/athlete_scope.py``)
son una única ``UPDATE`` sobre ``athletes`` — nunca tocan filas hijas — así
que los casos 3 y 4 (que en el contrato se documentan como "regresión" sobre
la cascada física que existía antes de esta feature) son, con el código
actual, una comprobación de que esa cascada de verdad desapareció: se siembra
un ``parental_consents``, un ``anthropometric_records``, un
``session_attendance`` y un ``club_members``/stub ``users`` del atleta, se
archiva, y se verifica que las cuatro filas siguen intactas.

Corre en la vía offline aiosqlite, con un engine propio (subconjunto de
tablas) construido sobre el mismo patrón que
``tests/routers/test_audit_log_api.py`` — no usa el fixture ``client`` de
``conftest.py`` porque ese exige MySQL.

Ningún nombre en este archivo corresponde a una persona real (CLAUDE.md,
Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest
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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditAction, AuditLog
from app.models.club import ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.training_session import (
    SessionAttendance,
    SessionKind,
    SessionStatus,
    TrainingSession,
)
from app.models.user import User, UserRole
from app.services.audit import AuditEntityType

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio

CLUB_ID = 1
OTHER_CLUB_ID = 2
ADMIN_ID = 900
COACH_ID = 901
OTHER_COACH_ID = 902
PARENT_ID = 903
ATHLETE_USER_ID = 950
ATHLETE_ID = 60

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "anthropometric_records",
    "training_sessions",
    "session_attendance",
    *AUDIT_TABLES,
]


@pytest_asyncio.fixture
async def archive_engine() -> AsyncEngine:
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
async def archive_session_factory(archive_engine: AsyncEngine):
    return async_sessionmaker(archive_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(archive_session_factory):
    async with archive_session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-045-a")
        await create_club(session, club_id=OTHER_CLUB_ID, name="Club Ficticio Dos", code="cft-045-b")

        await create_user(session, user_id=ADMIN_ID, role=UserRole.admin, first_name="Admin", last_name="Ficticio")
        coach = await create_user(session, user_id=COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Ficticio")
        await create_user(session, user_id=OTHER_COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Externo")
        await create_user(session, user_id=PARENT_ID, role=UserRole.parent, first_name="Padre", last_name="Ficticio")

        await link_user_to_club(session, user_id=ADMIN_ID, club_id=CLUB_ID, role_in_club=ClubRole.admin)
        await link_user_to_club(session, user_id=COACH_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach)
        await link_user_to_club(session, user_id=OTHER_COACH_ID, club_id=OTHER_CLUB_ID, role_in_club=ClubRole.coach)

        # Cuenta-espejo del atleta (sin inicio de sesión). El caso 4 de §12.1
        # comprueba que archivar no la destruye, así que el sembrado tiene que
        # crearla: sin esta fila la aserción miraba un usuario inexistente.
        await create_user(
            session,
            user_id=ATHLETE_USER_ID,
            role=UserRole.athlete,
            first_name="Atleta Ficticia",
            last_name="Uno",
            can_login=False,
        )
        athlete = await create_athlete(
            session,
            athlete_id=ATHLETE_ID,
            first_name="Mariana Ficticia",
            last_name="Restrepo",
            birth_date=date(2013, 6, 20),
            club_id=CLUB_ID,
            user_id=ATHLETE_USER_ID,
            created_by=coach.id,
        )
        await link_parent_to_athlete(session, parent_user_id=PARENT_ID, athlete_id=athlete.id)

        # Evidencia hija que la vieja cascada destruía (§12.1 casos 3-4).
        session.add(
            ParentalConsent(
                parent_user_id=PARENT_ID,
                athlete_id=athlete.id,
                consent_version="v1",
                consent_method="digital_wizard",
            )
        )
        session.add(
            AnthropometricRecord(
                athlete_id=athlete.id,
                evaluation_date=date(2026, 1, 10),
                weight_kg=Decimal("40.0"),
                standing_height_cm=Decimal("150.0"),
                sitting_height_cm=Decimal("78.0"),
                leg_length_cm=Decimal("72.0"),
                leg_sitting_ratio=Decimal("0.9231"),
                maturity_offset=Decimal("-1.0"),
                age_at_phv=Decimal("13.5"),
                maturation_status=MaturationStatus.pre_phv,
                evaluated_by=coach.id,
            )
        )
        training_session = TrainingSession(
            club_id=CLUB_ID,
            created_by_user_id=coach.id,
            status=SessionStatus.PLANNED,
            scheduled_date=date(2026, 2, 1),
            scheduled_start_time=time(16, 0),
            duration_min=60,
            location="Cancha ficticia",
            technical_focus="Técnica ficticia",
            session_kind=SessionKind.ENTRENAMIENTO,
        )
        session.add(training_session)
        await session.flush()
        session.add(
            SessionAttendance(
                session_id=training_session.id,
                athlete_id=athlete.id,
            )
        )
        await session.commit()

    return None


@pytest_asyncio.fixture
async def client_factory(archive_session_factory):
    @asynccontextmanager
    async def make_client(user_id: int):
        async with archive_session_factory() as load_session:
            result = await load_session.execute(
                select(User).options(selectinload(User.club_memberships)).where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with archive_session_factory() as session:
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


async def _get_athlete(session_factory, athlete_id: int) -> Athlete:
    async with session_factory() as session:
        result = await session.execute(select(Athlete).where(Athlete.id == athlete_id))
        return result.scalar_one()


# ---------------------------------------------------------------------------
# 1-2. Camino feliz de archivado
# ---------------------------------------------------------------------------


async def test_coach_archives_athlete(scenario, client_factory, archive_session_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
    assert resp.status_code == 204

    athlete = await _get_athlete(archive_session_factory, ATHLETE_ID)
    assert athlete.deleted_at is not None
    assert athlete.deleted_by_user_id == COACH_ID
    assert athlete.deleted_reason_code == "athlete_left_club"


async def test_admin_archives_athlete(scenario, client_factory, archive_session_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_transferred"},
        )
    assert resp.status_code == 204
    athlete = await _get_athlete(archive_session_factory, ATHLETE_ID)
    assert athlete.deleted_at is not None


# ---------------------------------------------------------------------------
# 3-4. Regresión: nada hijo se destruye — no hay cascada
# ---------------------------------------------------------------------------


async def test_archive_preserves_child_evidence(scenario, client_factory, archive_session_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
    assert resp.status_code == 204

    async with archive_session_factory() as session:
        consent = (
            await session.execute(
                select(ParentalConsent).where(ParentalConsent.athlete_id == ATHLETE_ID)
            )
        ).scalar_one_or_none()
        assert consent is not None

        record = (
            await session.execute(
                select(AnthropometricRecord).where(
                    AnthropometricRecord.athlete_id == ATHLETE_ID
                )
            )
        ).scalar_one_or_none()
        assert record is not None

        link = (
            await session.execute(
                select(ParentAthlete).where(ParentAthlete.athlete_id == ATHLETE_ID)
            )
        ).scalar_one_or_none()
        assert link is not None

        attendance = (
            await session.execute(
                select(SessionAttendance).where(SessionAttendance.athlete_id == ATHLETE_ID)
            )
        ).scalar_one_or_none()
        assert attendance is not None

        athlete_user = (
            await session.execute(select(User).where(User.id == ATHLETE_USER_ID))
        ).scalar_one_or_none()
        assert athlete_user is not None


# ---------------------------------------------------------------------------
# 5. reason_code obligatorio / catálogo cerrado
# ---------------------------------------------------------------------------


async def test_archive_without_reason_code_422(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request("DELETE", f"/api/athletes/{ATHLETE_ID}", json={})
    assert resp.status_code == 422


async def test_archive_with_restore_reason_code_422(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "restore_mistaken_archive"},
        )
    assert resp.status_code == 422


async def test_archive_with_free_text_reason_code_422(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "se fue del club"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Coach fuera del club
# ---------------------------------------------------------------------------


async def test_coach_outside_club_403(scenario, client_factory):
    async with client_factory(OTHER_COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. Ya archivado — coach 404, admin 409
# ---------------------------------------------------------------------------


async def test_archive_already_archived_coach_404(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        first = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
        assert first.status_code == 204
        second = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
    assert second.status_code == 404


async def test_archive_already_archived_admin_409(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
        assert resp.status_code == 204

    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 8-11. Restauración
# ---------------------------------------------------------------------------


async def test_admin_restores_athlete(scenario, client_factory, archive_session_factory):
    async with client_factory(COACH_ID) as client:
        await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )

    async with client_factory(ADMIN_ID) as client:
        resp = await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_mistaken_archive"},
        )
    assert resp.status_code == 200

    athlete = await _get_athlete(archive_session_factory, ATHLETE_ID)
    assert athlete.deleted_at is None
    assert athlete.deleted_by_user_id is None
    assert athlete.deleted_reason_code is None


async def test_coach_cannot_restore_403(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
        resp = await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_mistaken_archive"},
        )
    assert resp.status_code == 403


async def test_parent_cannot_restore_403(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )

    async with client_factory(PARENT_ID) as client:
        resp = await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_mistaken_archive"},
        )
    assert resp.status_code == 403


async def test_restore_non_archived_409(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_mistaken_archive"},
        )
    assert resp.status_code == 409


async def test_restore_without_reason_code_422(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )

    async with client_factory(ADMIN_ID) as client:
        resp = await client.post(f"/api/athletes/{ATHLETE_ID}/restore", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 12-13. Archivar → restaurar → archivar de nuevo, y forma de las filas
# ---------------------------------------------------------------------------


async def test_archive_restore_archive_cycle_audit_rows(
    scenario, client_factory, archive_session_factory
):
    async with client_factory(COACH_ID) as client:
        r1 = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )
        assert r1.status_code == 204

    async with client_factory(ADMIN_ID) as client:
        r2 = await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_returned_to_club"},
        )
        assert r2.status_code == 200

    async with client_factory(COACH_ID) as client:
        r3 = await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_duplicate_record"},
        )
        assert r3.status_code == 204

    async with archive_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == AuditEntityType.athlete.value,
                    AuditLog.entity_id == ATHLETE_ID,
                )
                .order_by(AuditLog.id)
            )
        ).scalars().all()

    assert [r.action for r in rows] == [
        AuditAction.archive,
        AuditAction.restore,
        AuditAction.archive,
    ]

    for row in rows:
        assert row.athlete_id == ATHLETE_ID
        assert row.club_id == CLUB_ID
        assert row.actor_role is not None
        assert row.request_id
        if row.diff_json is not None:
            assert set(row.diff_json.keys()) == {"deleted_reason_code"}

    # El atleta sigue usable tras el ciclo completo.
    athlete = await _get_athlete(archive_session_factory, ATHLETE_ID)
    assert athlete.deleted_at is not None
    assert athlete.deleted_reason_code == "athlete_duplicate_record"


# ---------------------------------------------------------------------------
# 14. Invariante de privacidad — nada narrativo de un menor en audit_log
# ---------------------------------------------------------------------------


async def test_archive_restore_audit_rows_have_no_minor_pii(
    scenario, client_factory, archive_session_factory
):
    async with client_factory(COACH_ID) as client:
        await client.request(
            "DELETE",
            f"/api/athletes/{ATHLETE_ID}",
            json={"reason_code": "athlete_left_club"},
        )

    async with client_factory(ADMIN_ID) as client:
        await client.post(
            f"/api/athletes/{ATHLETE_ID}/restore",
            json={"reason_code": "restore_mistaken_archive"},
        )

    forbidden_substrings = [
        "Mariana",
        "Restrepo",
        "2013-06-20",
        "150.0",
        "40.0",
    ]

    async with archive_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.athlete_id == ATHLETE_ID)
            )
        ).scalars().all()

    assert rows
    for row in rows:
        blob = str(row.diff_json) if row.diff_json else ""
        blob += str(row.changed_fields or "")
        for needle in forbidden_substrings:
            assert needle not in blob
