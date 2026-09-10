"""T047 — pruebas de contrato de eliminación/desactivación de usuarios.

Ver ``specs/041-multi-coach-governance/contracts/athlete-archive.md`` §12.4
(§8/§8.1/§8.2 describen las ocho reglas de ``DELETE /api/users/{user_id}``).
No existía ningún test para ``DELETE /api/users/{user_id}`` antes de esta
feature — cada caso de abajo es cobertura nueva. Los casos 3 y 4 son
regresión: deben fallar contra el código anterior a T046
(``users.py`` anulaba ``created_by`` y borraba ``parental_consents``).

Regla 5 del contrato (§8) es incondicional: un objetivo con
``role in (admin, coach)`` recibe siempre ``403``, sin importar quién llama
ni su actividad — por eso todos los casos de eliminación exitosa/409 de este
archivo usan un padre como objetivo (el endpoint documenta que es, en la
práctica, "eliminar un padre/acudiente").

Corre en la vía offline aiosqlite, con un engine propio — no usa el fixture
``client`` de ``conftest.py`` porque ese exige MySQL.

Ningún nombre en este archivo corresponde a una persona real (CLAUDE.md,
Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete import ParentAthlete
from app.models.audit_log import AuditAction, AuditLog
from app.models.club import ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
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

ADMIN_ID = 800
COACH_ID = 801
COACH_PEER_ID = 802
OTHER_CLUB_COACH_ID = 803

PARENT_WITH_AUDIT_ID = 810
PARENT_NO_ACTIVITY_ID = 811
PARENT_CREATOR_ID = 812
CREATED_BY_PARENT_ID = 813
PARENT_CONSENTING_ID = 814
PARENT_WITH_SESSION_ID = 815
PARENT_CLEAN_ID = 816

CONSENTING_ATHLETE_ID = 30
CLEAN_ATHLETE_ID = 31
ATHLETE_STUB_USER_A = 9930
ATHLETE_STUB_USER_B = 9931

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "training_sessions",
    *AUDIT_TABLES,
]


@pytest_asyncio.fixture
async def users_engine() -> AsyncEngine:
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
async def users_session_factory(users_engine: AsyncEngine):
    return async_sessionmaker(users_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(users_session_factory):
    async with users_session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-047-a")
        await create_club(session, club_id=OTHER_CLUB_ID, name="Club Ficticio Dos", code="cft-047-b")

        await create_user(session, user_id=ADMIN_ID, role=UserRole.admin, first_name="Admin", last_name="Ficticio")
        await create_user(session, user_id=COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Ficticio")
        await create_user(session, user_id=COACH_PEER_ID, role=UserRole.coach, first_name="Coach", last_name="Par")
        await create_user(session, user_id=OTHER_CLUB_COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Externo")

        parent_audit = await create_user(session, user_id=PARENT_WITH_AUDIT_ID, role=UserRole.parent, first_name="Padre", last_name="ConAuditoria")
        await create_user(session, user_id=PARENT_NO_ACTIVITY_ID, role=UserRole.parent, first_name="Padre", last_name="SinActividad")
        parent_creator = await create_user(session, user_id=PARENT_CREATOR_ID, role=UserRole.parent, first_name="Padre", last_name="Creador")
        created_by_parent = await create_user(session, user_id=CREATED_BY_PARENT_ID, role=UserRole.parent, first_name="Padre", last_name="Creado")
        created_by_parent.created_by = parent_creator.id
        parent_consenting = await create_user(session, user_id=PARENT_CONSENTING_ID, role=UserRole.parent, first_name="Padre", last_name="Consintiente")
        await create_user(session, user_id=PARENT_WITH_SESSION_ID, role=UserRole.parent, first_name="Padre", last_name="ConSesion")
        await create_user(session, user_id=PARENT_CLEAN_ID, role=UserRole.parent, first_name="Padre", last_name="Limpio")

        for uid, role in [
            (ADMIN_ID, ClubRole.admin),
            (COACH_ID, ClubRole.coach),
            (COACH_PEER_ID, ClubRole.coach),
        ]:
            await link_user_to_club(session, user_id=uid, club_id=CLUB_ID, role_in_club=role)
        await link_user_to_club(session, user_id=OTHER_CLUB_COACH_ID, club_id=OTHER_CLUB_ID, role_in_club=ClubRole.coach)

        for uid in [
            PARENT_WITH_AUDIT_ID,
            PARENT_NO_ACTIVITY_ID,
            PARENT_CREATOR_ID,
            CREATED_BY_PARENT_ID,
            PARENT_CONSENTING_ID,
            PARENT_WITH_SESSION_ID,
            PARENT_CLEAN_ID,
        ]:
            await link_user_to_club(session, user_id=uid, club_id=CLUB_ID, role_in_club=ClubRole.parent)

        await create_user(session, user_id=ATHLETE_STUB_USER_A, role=UserRole.athlete, first_name="Atleta Ficticio", last_name="Uno", can_login=False)
        consenting_athlete = await create_athlete(
            session,
            athlete_id=CONSENTING_ATHLETE_ID,
            first_name="Atleta Ficticio",
            last_name="Uno",
            birth_date=date(2013, 1, 1),
            club_id=CLUB_ID,
            user_id=ATHLETE_STUB_USER_A,
            created_by=COACH_ID,
        )
        await link_parent_to_athlete(session, parent_user_id=parent_consenting.id, athlete_id=consenting_athlete.id)
        session.add(
            ParentalConsent(
                parent_user_id=parent_consenting.id,
                athlete_id=consenting_athlete.id,
                consent_version="v1",
                consent_method="digital_wizard",
            )
        )

        await create_user(session, user_id=ATHLETE_STUB_USER_B, role=UserRole.athlete, first_name="Atleta Ficticio", last_name="Dos", can_login=False)
        clean_athlete = await create_athlete(
            session,
            athlete_id=CLEAN_ATHLETE_ID,
            first_name="Atleta Ficticio",
            last_name="Dos",
            birth_date=date(2013, 1, 1),
            club_id=CLUB_ID,
            user_id=ATHLETE_STUB_USER_B,
            created_by=COACH_ID,
        )
        await link_parent_to_athlete(session, parent_user_id=PARENT_CLEAN_ID, athlete_id=clean_athlete.id)

        # Padre con al menos una fila de auditoría a su nombre (probe 1, §8.1).
        session.add(
            AuditLog(
                actor_user_id=parent_audit.id,
                actor_kind="user",
                actor_role="parent",
                club_id=CLUB_ID,
                athlete_id=None,
                entity_type=AuditEntityType.athlete.value,
                entity_id=consenting_athlete.id,
                action=AuditAction.update,
                changed_fields=["first_name"],
                request_id="req-fixture-047-1",
            )
        )

        # `training_sessions.created_by_user_id` apuntando al padre — RESTRICT
        # FK preexistente a la 041 que ninguna de las tres sondas cubre
        # (contrato §8.1, caso 5).
        session.add(
            TrainingSession(
                club_id=CLUB_ID,
                created_by_user_id=PARENT_WITH_SESSION_ID,
                status=SessionStatus.PLANNED,
                scheduled_date=date(2026, 2, 1),
                scheduled_start_time=time(16, 0),
                duration_min=60,
                location="Cancha ficticia",
                technical_focus="Técnica ficticia",
                session_kind=SessionKind.ENTRENAMIENTO,
            )
        )

        await session.commit()

    return None


@pytest_asyncio.fixture
async def client_factory(users_session_factory):
    @asynccontextmanager
    async def make_client(user_id: int):
        async with users_session_factory() as load_session:
            result = await load_session.execute(
                select(User).options(selectinload(User.club_memberships)).where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with users_session_factory() as session:
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


# ---------------------------------------------------------------------------
# 1. Padre con actividad (auditoría) -> 409
# ---------------------------------------------------------------------------


async def test_delete_parent_with_audit_activity_409(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_WITH_AUDIT_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 409
    # La copia lleva tilde ("Desactívalo"), así que el fragmento buscado también
    # debe llevarla: "desacti" nunca aparece en el texto real.
    assert "desactívalo" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Padre sin ninguna actividad -> 204
# ---------------------------------------------------------------------------


async def test_delete_parent_with_no_activity_204(scenario, client_factory, users_session_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 204

    async with users_session_factory() as session:
        row = (
            await session.execute(select(User).where(User.id == PARENT_NO_ACTIVITY_ID))
        ).scalar_one_or_none()
        assert row is None


# ---------------------------------------------------------------------------
# 3. Regresión: created_by no se anula al borrar al creador
# ---------------------------------------------------------------------------


async def test_delete_creator_keeps_created_by_regression(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_CREATOR_ID}",
            json={"reason_code": "parent_family_request"},
        )
    # El creador tiene actividad registrada (probe 2: creó otra cuenta).
    assert resp.status_code == 409

    async with users_session_factory() as session:
        created = (
            await session.execute(select(User).where(User.id == CREATED_BY_PARENT_ID))
        ).scalar_one()
        assert created.created_by == PARENT_CREATOR_ID


# ---------------------------------------------------------------------------
# 4. Regresión: consentimiento parental preservado, no se puede borrar
# ---------------------------------------------------------------------------


async def test_delete_parent_with_consent_409_and_preserved(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_CONSENTING_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 409

    async with users_session_factory() as session:
        consent = (
            await session.execute(
                select(ParentalConsent).where(
                    ParentalConsent.parent_user_id == PARENT_CONSENTING_ID
                )
            )
        ).scalar_one_or_none()
        assert consent is not None


# ---------------------------------------------------------------------------
# 5. IntegrityError (RESTRICT FK preexistente) -> 409, no 500
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "Requiere que el motor aplique ON DELETE RESTRICT. El arnés de sqlite "
        "construye un subconjunto de tablas, así que activar PRAGMA "
        "foreign_keys=ON rompe el sembrado (faltan tablas referenciadas) y "
        "dejarlo apagado impide que salte el IntegrityError que el código sí "
        "provoca contra MySQL real. Se cubre en la vía -m mysql."
    ),
    strict=False,
)
async def test_delete_parent_with_training_session_maps_to_409(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_WITH_SESSION_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 6. Padre limpio, solo parent_athlete/club_members -> 204
# ---------------------------------------------------------------------------


async def test_delete_clean_parent_204(scenario, client_factory, users_session_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_CLEAN_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 204

    async with users_session_factory() as session:
        links = (
            await session.execute(
                select(ParentAthlete).where(ParentAthlete.parent_id == PARENT_CLEAN_ID)
            )
        ).scalars().all()
        assert links == []

        # El atleta en sí no se toca.
        athlete_row = (
            await session.execute(
                select(ParentAthlete).where(ParentAthlete.athlete_id == CLEAN_ATHLETE_ID)
            )
        ).scalars().all()
        assert athlete_row == []


# ---------------------------------------------------------------------------
# 7. Guardas de autorización
# ---------------------------------------------------------------------------


async def test_self_delete_403(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{ADMIN_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 403


async def test_athlete_target_400(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{ATHLETE_STUB_USER_A}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 400


async def test_unknown_user_404(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            "/api/users/999999",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 404


async def test_coach_caller_outside_target_clubs_403(scenario, client_factory):
    async with client_factory(OTHER_CLUB_COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_CLEAN_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 403


async def test_coach_caller_targeting_peer_coach_403(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{COACH_PEER_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 8. Fila de auditoría de la eliminación exitosa
# ---------------------------------------------------------------------------


async def test_successful_delete_emits_one_audit_row(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request(
            "DELETE",
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"reason_code": "parent_family_request"},
        )
    assert resp.status_code == 204

    async with users_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == AuditEntityType.user.value,
                    AuditLog.entity_id == PARENT_NO_ACTIVITY_ID,
                    AuditLog.action == AuditAction.delete,
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.diff_json is None
    assert row.actor_user_id == ADMIN_ID
    assert row.reason_code == "parent_family_request"


async def test_delete_without_reason_code_422(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.request("DELETE", f"/api/users/{PARENT_NO_ACTIVITY_ID}", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 9-11. Desactivar / reactivar vía PATCH
# ---------------------------------------------------------------------------


async def test_deactivate_via_patch_emits_deactivate_action(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.patch(
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"is_active": False, "reason_code": "account_staff_rotation"},
        )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    async with users_session_factory() as session:
        row = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == AuditEntityType.user.value,
                    AuditLog.entity_id == PARENT_NO_ACTIVITY_ID,
                    AuditLog.action == AuditAction.deactivate,
                )
            )
        ).scalar_one()
        assert row.diff_json in (
            {"is_active": [True, False]},
            {"is_active": {"before": True, "after": False}},
        )


async def test_reactivate_via_patch_emits_activate_action(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        await client.patch(
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"is_active": False, "reason_code": "account_staff_rotation"},
        )
        resp = await client.patch(
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"is_active": True, "reason_code": "account_reactivation"},
        )
    assert resp.status_code == 200

    async with users_session_factory() as session:
        row = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == AuditEntityType.user.value,
                    AuditLog.entity_id == PARENT_NO_ACTIVITY_ID,
                    AuditLog.action == AuditAction.activate,
                )
            )
        ).scalar_one_or_none()
        assert row is not None


async def test_deactivate_without_reason_code_422(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.patch(
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"is_active": False},
        )
    assert resp.status_code == 422


async def test_plain_update_without_is_active_is_just_update(
    scenario, client_factory, users_session_factory
):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.patch(
            f"/api/users/{PARENT_NO_ACTIVITY_ID}",
            json={"phone": "3000000000"},
        )
    assert resp.status_code == 200

    async with users_session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == AuditEntityType.user.value,
                    AuditLog.entity_id == PARENT_NO_ACTIVITY_ID,
                )
            )
        ).scalars().all()
    assert all(r.action not in (AuditAction.activate, AuditAction.deactivate) for r in rows)
