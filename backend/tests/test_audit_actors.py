"""Tests de instrumentación de auditoría — personal y club (T021).

Cubre `contracts/audit-recording.md` §4.2 sobre `backend/app/routers/users.py`
(create/update/delete) y `backend/app/routers/clubs.py`
(create/update/add-member): acciones `create`/`update`/`deactivate`/
`activate`/`delete`, `changed_fields` vía `compute_changed_fields`, y la
corrección del defecto preexistente que anulaba `created_by` al borrar un
padre (§10).

Usa las fixtures compartidas de `tests/fixtures/two_coaches.py` (club único,
dos coaches, un coach de otro club, un admin, un padre y un atleta
ficticios — ningún dato real de un menor).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Base
from app.models.athlete import ParentAthlete
from app.models.audit_log import AuditAction, AuditLog
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole


async def _rows_for(session_factory, *, entity_type: str, entity_id: int | None = None):
    async with session_factory() as session:
        query = select(AuditLog).where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(AuditLog.entity_id == entity_id)
        result = await session.execute(query)
        return list(result.scalars().all())


class TestCreateUserAudit:
    @pytest.mark.asyncio
    async def test_admin_creates_coach_records_user_and_club_member_rows(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.post(
                "/api/users",
                json={
                    "email": "nuevo.coach@test.local",
                    "password": "unaClaveSegura1",
                    "first_name": "Nuevo",
                    "last_name": "Entrenador",
                    "role": "coach",
                    "club_id": s.club_id,
                },
            )
        assert resp.status_code == 201, resp.text
        new_user_id = resp.json()["id"]

        user_rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=new_user_id
        )
        assert len(user_rows) == 1
        row = user_rows[0]
        assert row.action == AuditAction.create
        assert row.actor_user_id == s.admin_user_id
        assert row.club_id == s.club_id
        assert set(row.changed_fields) == {
            "email", "first_name", "last_name", "phone", "role", "can_login",
        }
        # Privacidad: nunca se persiste el valor de un campo identificador.
        assert row.diff_json is None

        member_rows = await _rows_for(two_coaches_session_factory, entity_type="club_member")
        member_rows = [r for r in member_rows if r.request_id == row.request_id]
        assert len(member_rows) == 1
        assert member_rows[0].action == AuditAction.create
        assert member_rows[0].club_id == s.club_id
        # Misma request_id — una sola unidad de trabajo (FR-002).
        assert member_rows[0].request_id == row.request_id


class TestUpdateUserAudit:
    @pytest.mark.asyncio
    async def test_deactivate_without_reason_code_is_422(
        self, two_coaches_scenario, two_coaches_client_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.patch(
                f"/api/users/{s.coach_b_user_id}", json={"is_active": False}
            )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Debes seleccionar un motivo para esta acción."

    @pytest.mark.asyncio
    async def test_deactivate_with_reason_code_records_deactivate_row(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.patch(
                f"/api/users/{s.coach_b_user_id}",
                json={"is_active": False, "reason_code": "account_staff_rotation"},
            )
        assert resp.status_code == 200, resp.text

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=s.coach_b_user_id
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.action == AuditAction.deactivate
        assert row.changed_fields == ["is_active"]
        assert row.diff_json == {"is_active": {"before": True, "after": False}}
        assert row.reason_code == "account_staff_rotation"
        assert row.club_id == s.club_id

    @pytest.mark.asyncio
    async def test_reactivate_does_not_require_reason_code(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            deactivate = await client.patch(
                f"/api/users/{s.coach_b_user_id}",
                json={"is_active": False, "reason_code": "account_staff_rotation"},
            )
            assert deactivate.status_code == 200

            reactivate = await client.patch(
                f"/api/users/{s.coach_b_user_id}", json={"is_active": True}
            )
        assert reactivate.status_code == 200, reactivate.text

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=s.coach_b_user_id
        )
        actions = [r.action for r in rows]
        assert actions == [AuditAction.deactivate, AuditAction.activate]
        assert rows[1].reason_code is None

    @pytest.mark.asyncio
    async def test_plain_field_change_records_update_with_no_diff_value(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.patch(
                f"/api/users/{s.coach_b_user_id}", json={"phone": "3009999999"}
            )
        assert resp.status_code == 200, resp.text

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=s.coach_b_user_id
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.action == AuditAction.update
        assert row.changed_fields == ["phone"]
        # `phone` no está en VALUE_ALLOWLIST[user] — el nombre viaja, el valor no.
        assert row.diff_json is None

    @pytest.mark.asyncio
    async def test_no_op_patch_writes_no_row(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.patch(f"/api/users/{s.coach_b_user_id}", json={})
        assert resp.status_code == 200, resp.text

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=s.coach_b_user_id
        )
        assert rows == []


class TestDeleteUserAudit:
    @pytest.mark.asyncio
    async def test_delete_requires_reason_code_query_param(
        self, two_coaches_scenario, two_coaches_client_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.delete(f"/api/users/{s.parent_user_id}")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_parent_records_rows_and_preserves_created_by(
        self,
        two_coaches_scenario,
        two_coaches_client_factory,
        two_coaches_session_factory,
        two_coaches_engine,
    ):
        s = two_coaches_scenario

        # `parental_consents` no está en la lista fija de tablas de
        # `tests/fixtures/two_coaches.py` (fixture compartida entre tareas de
        # la oleada, fuera del alcance de T021) — se crea aquí, en el mismo
        # engine sqlite, solo para este test. `privacy_policies` no se crea
        # (su `content_html` es `LONGTEXT`, tipo MySQL que sqlite no puede
        # compilar); el router lee `ParentalConsent` por columnas sueltas
        # para no disparar el JOIN de `policy` (`lazy="joined"`).
        async with two_coaches_engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c,
                    tables=[
                        Base.metadata.tables["parental_consents"],
                        Base.metadata.tables["parent_invites"],
                    ],
                    checkfirst=True,
                )
            )

        # Sembrar el estado que el defecto preexistente destruía: otro
        # usuario cuyo `created_by` apunta al padre que vamos a borrar.
        async with two_coaches_session_factory() as session:
            created_child = User(
                id=95000,
                email="hijo-creado-por-padre@test.local",
                hashed_password="x",
                first_name="Creado",
                last_name="PorPadre",
                role=UserRole.parent,
                is_active=True,
                can_login=True,
                created_by=s.parent_user_id,
            )
            session.add(created_child)

            link = await session.execute(
                select(ParentAthlete).where(ParentAthlete.parent_id == s.parent_user_id)
            )
            assert link.scalars().first() is not None  # ya sembrado por seed_two_coaches

            consent = ParentalConsent(
                parent_user_id=s.parent_user_id,
                athlete_id=s.athlete_id,
                consent_version="v1",
                data_collection=True,
                training_tracking=True,
                anthropometry=True,
                third_party_sharing=False,
            )
            session.add(consent)
            await session.commit()

        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.delete(
                f"/api/users/{s.parent_user_id}",
                params={"reason_code": "parent_family_request"},
            )
        assert resp.status_code == 204, resp.text

        async with two_coaches_session_factory() as session:
            # El defecto preexistente (T021, §10): ya NO se anula created_by.
            still_created = await session.execute(
                select(User).where(User.id == 95000)
            )
            child = still_created.scalar_one()
            assert child.created_by == s.parent_user_id

            deleted = await session.execute(select(User).where(User.id == s.parent_user_id))
            assert deleted.scalar_one_or_none() is None

        user_rows = await _rows_for(
            two_coaches_session_factory, entity_type="user", entity_id=s.parent_user_id
        )
        assert len(user_rows) == 1
        assert user_rows[0].action == AuditAction.delete
        assert user_rows[0].reason_code == "parent_family_request"
        request_id = user_rows[0].request_id

        unlink_rows = await _rows_for(two_coaches_session_factory, entity_type="parent_athlete")
        unlink_rows = [r for r in unlink_rows if r.request_id == request_id]
        assert len(unlink_rows) == 1
        assert unlink_rows[0].action == AuditAction.unlink
        assert unlink_rows[0].athlete_id == s.athlete_id
        assert unlink_rows[0].club_id == s.club_id

        consent_rows = await _rows_for(
            two_coaches_session_factory, entity_type="parental_consent"
        )
        consent_rows = [r for r in consent_rows if r.request_id == request_id]
        assert len(consent_rows) == 1
        assert consent_rows[0].action == AuditAction.delete
        assert consent_rows[0].athlete_id == s.athlete_id


class TestClubAudit:
    @pytest.mark.asyncio
    async def test_create_club_records_row_with_own_club_id(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.post(
                "/api/clubs/",
                json={"name": "Club Nuevo Ficticio", "code": "cnf-041"},
            )
        assert resp.status_code == 201, resp.text
        new_club_id = resp.json()["id"]

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="club", entity_id=new_club_id
        )
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].club_id == new_club_id
        assert set(rows[0].changed_fields) == {"name", "code", "location"}

    @pytest.mark.asyncio
    async def test_update_club_records_changed_fields_only(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.patch(
                f"/api/clubs/{s.club_id}", json={"location": "Nueva sede ficticia"}
            )
        assert resp.status_code == 200, resp.text

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="club", entity_id=s.club_id
        )
        assert len(rows) == 1
        assert rows[0].action == AuditAction.update
        assert rows[0].changed_fields == ["location"]
        # `club` no está en VALUE_ALLOWLIST — nombres sí, valores no.
        assert rows[0].diff_json is None

    @pytest.mark.asyncio
    async def test_add_member_records_club_member_create(
        self, two_coaches_scenario, two_coaches_client_factory, two_coaches_session_factory
    ):
        s = two_coaches_scenario
        async with two_coaches_client_factory(s.admin_user_id, UserRole.admin) as client:
            resp = await client.post(
                f"/api/clubs/{s.other_club_id}/members",
                json={"user_id": s.parent_user_id, "role_in_club": "parent"},
            )
        assert resp.status_code == 201, resp.text
        member_id = resp.json()["id"]

        rows = await _rows_for(
            two_coaches_session_factory, entity_type="club_member", entity_id=member_id
        )
        assert len(rows) == 1
        assert rows[0].action == AuditAction.create
        assert rows[0].club_id == s.other_club_id
        assert set(rows[0].changed_fields) == {"club_id", "user_id", "role_in_club"}
