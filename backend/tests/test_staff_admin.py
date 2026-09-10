"""T054 — pruebas de administración de personal (feature 041, US3).

Ver ``specs/041-multi-coach-governance/contracts/staff-admin.md`` §14.1.
Cubre el subconjunto explícitamente encargado a esta tarea:

- club obligatorio para crear personal (`role in {coach, admin}`) → 422,
- coherencia de rol en `POST /api/clubs/{id}/members` → 422,
- un coach que intenta crear otro coach → 403,
- filtros de `GET /api/users` (`role`, `is_active`),
- una cuenta desactivada no puede iniciar sesión (mensaje ya existente),
- las filas de auditoría correspondientes (mismo `request_id`),
- ninguna contraseña aparece en una respuesta ni en un log.

Corre en la vía offline aiosqlite, reutilizando el escenario compartido
``tests.fixtures.two_coaches`` (club único con ``coach_a``/``coach_b``, un
coach de otro club, un admin y un padre) en vez de construir usuarios/club
desde cero. Evita a propósito el fixture ``client`` de
``tests/conftest.py`` porque ese exige MySQL real.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.club import ClubMember
from app.models.user import User, UserRole
from app.services.auth import hash_password
from tests.fixtures.two_coaches import TwoCoachesScenario

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Cliente sin autenticar (para /api/auth/login) sobre la misma DB sembrada
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def anon_client(two_coaches_session_factory: async_sessionmaker[AsyncSession]):
    @asynccontextmanager
    async def make_client():
        async def _override_db():
            async with two_coaches_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    async with make_client() as ac:
        yield ac


async def _fetch_audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    entity_type: str,
    entity_id: int,
) -> list[AuditLog]:
    async with session_factory() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# POST /api/users — club obligatorio, no-403-antes-de-422, auditoría
# ---------------------------------------------------------------------------


class TestCreateStaffClubRequired:
    async def test_admin_creates_coach_without_club_id_is_422(self, admin_client):
        resp = await admin_client.post(
            "/api/users",
            json={
                "email": "coach.nuevo@example.org",
                "first_name": "Ana",
                "last_name": "Rivera Ficticia",
                "role": "coach",
            },
        )
        assert resp.status_code == 422
        assert "club" in resp.json()["detail"].lower()

    async def test_admin_creates_coach_with_club_id_succeeds(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        resp = await admin_client.post(
            "/api/users",
            json={
                "email": "coach.nueva@example.org",
                "first_name": "Laura",
                "last_name": "Méndez Ficticia",
                "role": "coach",
                "club_id": two_coaches_scenario.club_id,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "coach"
        # Ninguna contraseña viaja en la respuesta (no fue provista y no se genera una).
        assert "password" not in body
        assert "hashed_password" not in body

        new_user_id = body["id"]

        async with two_coaches_session_factory() as session:
            member_result = await session.execute(
                select(ClubMember).where(
                    ClubMember.user_id == new_user_id,
                    ClubMember.club_id == two_coaches_scenario.club_id,
                )
            )
            membership = member_result.scalar_one_or_none()
            assert membership is not None
            assert membership.role_in_club.value == "coach"

    async def test_audit_rows_share_request_id_and_carry_no_pii(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        resp = await admin_client.post(
            "/api/users",
            json={
                "email": "coach.auditada@example.org",
                "first_name": "Marta",
                "last_name": "Salinas Ficticia",
                "role": "coach",
                "club_id": two_coaches_scenario.club_id,
            },
        )
        assert resp.status_code == 201
        new_user_id = resp.json()["id"]

        user_rows = await _fetch_audit_rows(
            two_coaches_session_factory, entity_type="user", entity_id=new_user_id
        )
        assert len(user_rows) == 1
        user_row = user_rows[0]
        assert user_row.action.value == "create"

        async with two_coaches_session_factory() as session:
            member_result = await session.execute(
                select(ClubMember).where(ClubMember.user_id == new_user_id)
            )
            membership = member_result.scalar_one()

        club_member_rows = await _fetch_audit_rows(
            two_coaches_session_factory,
            entity_type="club_member",
            entity_id=membership.id,
        )
        assert len(club_member_rows) == 1
        club_member_row = club_member_rows[0]

        # Mismo request_id: ambas filas provienen de la misma operación (FR-002).
        assert user_row.request_id == club_member_row.request_id

        # Ninguna PII de nombre/correo/teléfono en diff_json/meta_json — solo
        # nombres de columna en changed_fields (contracts/staff-admin.md §1.5).
        forbidden = {
            "marta",
            "salinas",
            "coach.auditada@example.org",
        }
        for row in (user_row, club_member_row):
            blobs = [str(row.diff_json or {}), str(row.meta_json or {})]
            for blob in blobs:
                lowered = blob.lower()
                for forbidden_value in forbidden:
                    assert forbidden_value not in lowered


class TestCreateStaffCoachCannotCreateCoach:
    async def test_coach_creating_coach_is_403(self, coach_a_client):
        resp = await coach_a_client.post(
            "/api/users",
            json={
                "email": "otro.coach@example.org",
                "first_name": "Pedro",
                "last_name": "Gómez Ficticio",
                "role": "coach",
                "club_id": 1,
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/clubs/{id}/members — coherencia de rol (FR-022)
# ---------------------------------------------------------------------------


class TestClubMemberRoleCoherence:
    async def test_mismatched_role_in_club_is_422(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
    ):
        # El padre ficticio del escenario compartido tiene role=parent en su
        # cuenta; filiarlo como "coach" en el club contradice esa cuenta.
        resp = await admin_client.post(
            f"/api/clubs/{two_coaches_scenario.other_club_id}/members",
            json={
                "user_id": two_coaches_scenario.parent_user_id,
                "role_in_club": "coach",
            },
        )
        assert resp.status_code == 422
        assert "coincidir" in resp.json()["detail"].lower()

    async def test_coherent_role_in_club_succeeds(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
    ):
        resp = await admin_client.post(
            f"/api/clubs/{two_coaches_scenario.other_club_id}/members",
            json={
                "user_id": two_coaches_scenario.parent_user_id,
                "role_in_club": "parent",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["role_in_club"] == "parent"


# ---------------------------------------------------------------------------
# GET /api/users — filtros
# ---------------------------------------------------------------------------


class TestListUsersFilters:
    async def test_filter_by_role_coach(
        self, admin_client, two_coaches_scenario: TwoCoachesScenario
    ):
        resp = await admin_client.get("/api/users", params={"role": "coach"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 2
        assert all(item["role"] == "coach" for item in body["items"])

    async def test_filter_by_is_active_false_returns_only_deactivated(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        # Desactivar coach_b directamente para no depender de PATCH aquí.
        async with two_coaches_session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == two_coaches_scenario.coach_b_user_id)
            )
            target = result.scalar_one()
            target.is_active = False
            await session.commit()

        resp = await admin_client.get("/api/users", params={"is_active": "false"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert all(item["is_active"] is False for item in body["items"])
        assert any(
            item["id"] == two_coaches_scenario.coach_b_user_id for item in body["items"]
        )


# ---------------------------------------------------------------------------
# Cuenta desactivada no puede iniciar sesión
# ---------------------------------------------------------------------------


class TestDeactivatedAccountCannotLogin:
    async def test_login_after_deactivation_returns_401(
        self,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
        anon_client,
    ):
        plain_password = "Coach2026Segura!"
        async with two_coaches_session_factory() as session:
            coach = User(
                id=950,
                email="coach.desactivado@example.org",
                hashed_password=hash_password(plain_password),
                first_name="Renata",
                last_name="Ospina Ficticia",
                role=UserRole.coach,
                is_active=False,
                can_login=True,
            )
            session.add(coach)
            await session.commit()

        resp = await anon_client.post(
            "/api/auth/login",
            json={"email": "coach.desactivado@example.org", "password": plain_password},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Usuario desactivado"


# ---------------------------------------------------------------------------
# Ninguna contraseña en respuesta ni en logs
# ---------------------------------------------------------------------------


class TestNoPasswordLeakage:
    async def test_create_response_never_contains_raw_or_hashed_password(
        self,
        admin_client,
        two_coaches_scenario: TwoCoachesScenario,
        caplog: pytest.LogCaptureFixture,
    ):
        resp = await admin_client.post(
            "/api/users",
            json={
                "email": "sin.contrasena@example.org",
                "first_name": "Camila",
                "last_name": "Duarte Ficticia",
                "role": "coach",
                "club_id": two_coaches_scenario.club_id,
            },
        )
        assert resp.status_code == 201
        raw_body = resp.text
        assert "password" not in raw_body.lower()

        for record in caplog.records:
            message = record.getMessage()
            assert "sin.contrasena@example.org" not in message
            assert "password" not in message.lower() or "reset" in message.lower()


# ---------------------------------------------------------------------------
# GET /api/users — hallazgo F1: qué ve un coach de sus colegas
# (brechas A7 y A9 de checklists/integration-review.md)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _coach_client_with_membership(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    club_id: int,
):
    """Cliente de coach cuyo doble sí pertenece a un club.

    El doble compartido de ``tests/fixtures/two_coaches.py`` trae
    ``club_memberships=[]``, con lo que ``list_users`` devuelve lista vacía
    para cualquier coach: sirve para las rutas que no miran la membresía, no
    para estas. No se toca el fixture compartido —lo están usando otras
    pruebas— y se arma acá el doble mínimo que estas necesitan.
    """
    from types import SimpleNamespace

    from app.dependencies import get_current_user, get_db
    from app.models.club import ClubRole

    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _override_current_user():
        return SimpleNamespace(
            id=user_id,
            first_name="Test",
            last_name="Actor",
            display_name="Test Actor",
            email=f"actor{user_id}@test.local",
            role=UserRole.coach,
            can_login=True,
            is_active=True,
            club_memberships=[
                SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)
            ],
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


class TestCoachSeesStaffWithoutContactDetails:
    """F1 — un coach enumeraba personal con correo, teléfono y quién creó
    cada cuenta.

    La lista se conserva a propósito: el filtro "Entrenador" del historial
    (US1) y el selector de entrenadores a cargo (US4) la necesitan, y la
    atribución por nombre es de lo que trata la feature. Lo que se recorta es
    el contacto. Ver el comentario de la decisión en
    ``app/routers/users.py::list_users``.
    """

    async def test_coach_still_sees_the_other_coach_of_the_club(
        self,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        async with _coach_client_with_membership(
            two_coaches_session_factory,
            two_coaches_scenario.coach_a_user_id,
            two_coaches_scenario.club_id,
        ) as coach_a_client:
            resp = await coach_a_client.get("/api/users", params={"role": "coach"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        ids = {item["id"] for item in items}
        assert two_coaches_scenario.coach_b_user_id in ids, (
            "US1/US4 dependen de que un coach pueda listar a los coaches de su "
            "club para poblar el filtro del historial y el selector de sesión"
        )
        colega = next(
            item
            for item in items
            if item["id"] == two_coaches_scenario.coach_b_user_id
        )
        # Lo que un selector necesita sí viaja.
        assert colega["first_name"]
        assert colega["last_name"]
        assert colega["role"] == "coach"
        assert "is_active" in colega

    async def test_coach_does_not_see_contact_details_of_other_staff(
        self,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        async with _coach_client_with_membership(
            two_coaches_session_factory,
            two_coaches_scenario.coach_a_user_id,
            two_coaches_scenario.club_id,
        ) as coach_a_client:
            resp = await coach_a_client.get("/api/users")
        assert resp.status_code == 200
        items = resp.json()["items"]

        staff_ajeno = [
            item
            for item in items
            if item["role"] in ("coach", "admin")
            and item["id"] != two_coaches_scenario.coach_a_user_id
        ]
        assert staff_ajeno, "el escenario debe traer al menos un colega"
        for item in staff_ajeno:
            assert item["email"] is None, item
            assert item["phone"] is None, item
            assert item["created_by_display_name"] is None, item

    async def test_coach_still_sees_their_own_contact_details(
        self,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        async with _coach_client_with_membership(
            two_coaches_session_factory,
            two_coaches_scenario.coach_a_user_id,
            two_coaches_scenario.club_id,
        ) as coach_a_client:
            resp = await coach_a_client.get("/api/users")
        assert resp.status_code == 200
        propia = next(
            item
            for item in resp.json()["items"]
            if item["id"] == two_coaches_scenario.coach_a_user_id
        )
        assert propia["email"] is not None

    async def test_admin_keeps_the_full_payload(
        self, admin_client, two_coaches_scenario: TwoCoachesScenario
    ):
        resp = await admin_client.get("/api/users", params={"role": "coach"})
        assert resp.status_code == 200
        colega = next(
            item
            for item in resp.json()["items"]
            if item["id"] == two_coaches_scenario.coach_b_user_id
        )
        assert colega["email"] is not None, (
            "el recorte es solo para el coach: /admin/usuarios sigue "
            "necesitando el correo"
        )

    async def test_coach_keeps_full_contact_of_parents(
        self,
        two_coaches_scenario: TwoCoachesScenario,
        two_coaches_session_factory: async_sessionmaker[AsyncSession],
    ):
        """Gestionar a las familias del club es parte del trabajo del coach:
        el recorte no puede alcanzar a ``role=parent``.
        """
        # El escenario compartido no le da al padre una fila en
        # `club_members`, y la rama de coach de `list_users` hace JOIN contra
        # esa tabla: sin la membresía, la aserción no probaría nada. El engine
        # es in-memory y de alcance por prueba, así que se siembra acá en vez
        # de tocar el fixture compartido, que están usando otras pruebas.
        from app.models.club import ClubMember, ClubRole

        async with two_coaches_session_factory() as session:
            session.add(
                ClubMember(
                    user_id=two_coaches_scenario.parent_user_id,
                    club_id=two_coaches_scenario.club_id,
                    role_in_club=ClubRole.parent,
                )
            )
            await session.commit()

        async with _coach_client_with_membership(
            two_coaches_session_factory,
            two_coaches_scenario.coach_a_user_id,
            two_coaches_scenario.club_id,
        ) as coach_a_client:
            resp = await coach_a_client.get("/api/users", params={"role": "parent"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        padre = next(
            item
            for item in items
            if item["id"] == two_coaches_scenario.parent_user_id
        )
        assert padre["email"] is not None


class TestUsersDeniedPaths:
    """A9 — rutas denegadas que no tenían prueba propia."""

    async def test_parent_cannot_list_users(self, parent_client):
        resp = await parent_client.get("/api/users")
        assert resp.status_code == 403

    async def test_parent_cannot_create_staff(
        self, parent_client, two_coaches_scenario: TwoCoachesScenario
    ):
        resp = await parent_client.post(
            "/api/users",
            json={
                "email": "intruso@example.org",
                "first_name": "Persona",
                "last_name": "Ficticia",
                "role": "coach",
                "club_id": two_coaches_scenario.club_id,
            },
        )
        assert resp.status_code == 403

    async def test_coach_cannot_deactivate_another_coach(
        self, coach_a_client, two_coaches_scenario: TwoCoachesScenario
    ):
        """US3 AS5 — el coach no puede editar ni desactivar a otro coach.
        Es la mitad de F1 que sí estaba bien resuelta y no tenía prueba.
        """
        resp = await coach_a_client.patch(
            f"/api/users/{two_coaches_scenario.coach_b_user_id}",
            json={"is_active": False},
        )
        assert resp.status_code == 403

    async def test_admin_cannot_deactivate_themselves(
        self, admin_client, two_coaches_scenario: TwoCoachesScenario
    ):
        """Un admin que se autodesactiva deja al club sin quien administre."""
        resp = await admin_client.patch(
            f"/api/users/{two_coaches_scenario.admin_user_id}",
            json={"is_active": False},
        )
        assert resp.status_code in (400, 403, 409), resp.text
