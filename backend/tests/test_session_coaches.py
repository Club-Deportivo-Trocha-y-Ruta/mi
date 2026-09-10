"""T059/T060/T062/T064 — entrenadores de sesión, atribución de asistencia y
filtro por entrenador (feature 041, contracts/session-coaches.md).

Cubre la tabla de pruebas requeridas §12: B-01…B-07, B-10…B-12, B-15 y las
partes de B-13/B-14 que viven en `/api/training-sessions`.

Vía offline: motor sqlite in-memory propio con un subconjunto explícito de
tablas (patrón de `tests/routers/test_audit_log_api.py`, reutilizando
`tests/helpers/audit_tables.py`) y `app.dependency_overrides`. NO usa la
fixture `client` de `tests/conftest.py`, que levanta la app contra la base
real y no está disponible fuera de Docker.

Ningún dato corresponde a una persona real: el escenario es el de
`tests.fixtures.two_coaches` (club ficticio, dos entrenadores, un tercero de
otro club, un admin, un padre y un atleta sintético).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
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
from app.models.audit_log import AuditAction, AuditLog
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.user import User
from app.services.audit import AuditEntityType

from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Motor con el subconjunto de tablas que este módulo necesita
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "training_sessions",
    "session_attendance",
    "session_media",
    "session_media_athlete",
    "calendar_events",
    "event_audiences",
    "event_attendances",
    *AUDIT_TABLES,
)

FUTURE_DATE = date.today() + timedelta(days=7)


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
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
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(
    session_factory: async_sessionmaker[AsyncSession],
) -> TwoCoachesScenario:
    async with session_factory() as session:
        yield await seed_two_coaches(session)


@pytest_asyncio.fixture
async def client_factory(
    session_factory: async_sessionmaker[AsyncSession],
    scenario: TwoCoachesScenario,
):
    """Fábrica `make_client(user_id)` que monta el `User` REAL (con
    `club_memberships` precargadas, igual que `app/dependencies.py`) detrás de
    `get_current_user`, para que el RBAC de los tests sea el de producción."""

    @asynccontextmanager
    async def make_client(user_id: int):
        async with session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_payload(scenario: TwoCoachesScenario, **extra) -> dict:
    payload = {
        "scheduled_date": FUTURE_DATE.isoformat(),
        "scheduled_start_time": "08:00:00",
        "duration_min": 90,
        "location": "Pista ficticia",
        "technical_focus": "Técnica de curvas",
        "convocados_athlete_ids": [scenario.athlete_id],
        "send_notification": False,
    }
    payload.update(extra)
    return payload


async def _bridge_rows(
    session_factory: async_sessionmaker[AsyncSession], session_id: int
) -> list[TrainingSessionCoach]:
    async with session_factory() as s:
        result = await s.execute(
            select(TrainingSessionCoach)
            .where(TrainingSessionCoach.session_id == session_id)
            .order_by(
                TrainingSessionCoach.added_at.asc(),
                TrainingSessionCoach.coach_user_id.asc(),
            )
        )
        return list(result.scalars().all())


async def _audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
    entity_type: AuditEntityType,
    action: AuditAction | None = None,
) -> list[AuditLog]:
    async with session_factory() as s:
        stmt = select(AuditLog).where(AuditLog.entity_type == entity_type.value)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        result = await s.execute(stmt.order_by(AuditLog.id))
        return list(result.scalars().all())


async def _create_session(client: AsyncClient, scenario, **extra):
    return await client.post(
        "/api/training-sessions", json=_session_payload(scenario, **extra)
    )


# ---------------------------------------------------------------------------
# B-01 / B-02 / B-03 — alta y reemplazo del conjunto de entrenadores
# ---------------------------------------------------------------------------


async def test_b01_create_without_coach_user_ids_leaves_creator_as_sole_coach(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        resp = await _create_session(client, scenario)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [c["user_id"] for c in body["coaches"]] == [scenario.coach_a_user_id]
    assert body["has_active_coach"] is True

    rows = await _bridge_rows(session_factory, body["id"])
    assert len(rows) == 1
    assert rows[0].coach_user_id == scenario.coach_a_user_id
    assert rows[0].added_by_user_id == scenario.coach_a_user_id


async def test_b02_create_with_two_coaches_keeps_order_and_audits_both(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        resp = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [c["user_id"] for c in body["coaches"]] == [
        scenario.coach_a_user_id,
        scenario.coach_b_user_id,
    ]
    assert all(c["display_name"] for c in body["coaches"])

    rows = await _bridge_rows(session_factory, body["id"])
    assert [r.coach_user_id for r in rows] == [
        scenario.coach_a_user_id,
        scenario.coach_b_user_id,
    ]

    audit = await _audit_rows(
        session_factory, AuditEntityType.training_session_coach, AuditAction.create
    )
    assert len(audit) == 2
    assert len({row.request_id for row in audit}) == 1
    assert {row.diff_json["coach_user_id"]["after"] for row in audit} == {
        scenario.coach_a_user_id,
        scenario.coach_b_user_id,
    }


async def test_b03_coach_b_replaces_the_set_with_itself(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )
    session_id = created.json()["id"]

    async with client_factory(scenario.coach_b_user_id) as client:
        resp = await client.patch(
            f"/api/training-sessions/{session_id}",
            json={"coach_user_ids": [scenario.coach_b_user_id]},
        )

    assert resp.status_code == 200, resp.text
    assert [c["user_id"] for c in resp.json()["coaches"]] == [
        scenario.coach_b_user_id
    ]

    rows = await _bridge_rows(session_factory, session_id)
    assert [r.coach_user_id for r in rows] == [scenario.coach_b_user_id]

    deleted = await _audit_rows(
        session_factory, AuditEntityType.training_session_coach, AuditAction.delete
    )
    assert len(deleted) == 1
    assert deleted[0].diff_json["coach_user_id"]["before"] == scenario.coach_a_user_id
    assert deleted[0].actor_user_id == scenario.coach_b_user_id


# ---------------------------------------------------------------------------
# B-04 / B-05 / B-06 / B-07 — matriz de validación §3.3
# ---------------------------------------------------------------------------


async def test_b04_empty_coach_user_ids_is_422_on_create_and_update(
    scenario, client_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]

        create_resp = await _create_session(client, scenario, coach_user_ids=[])
        update_resp = await client.patch(
            f"/api/training-sessions/{session_id}", json={"coach_user_ids": []}
        )

    for resp in (create_resp, update_resp):
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == "Una sesión debe tener al menos un entrenador."


async def test_b05_service_level_empty_set_is_409(scenario, session_factory):
    """V6: el guard de conteo bajo `SELECT … FOR UPDATE`, alcanzable a nivel de
    servicio aunque el router ya rechace el payload vacío con 422."""
    from app.services.training import sessions as sessions_svc

    async with session_factory() as db:
        session = TrainingSession(
            club_id=scenario.club_id,
            created_by_user_id=scenario.coach_a_user_id,
            scheduled_date=FUTURE_DATE,
            scheduled_start_time=time(8, 0),
            duration_min=60,
            location="Pista ficticia",
            technical_focus="Base",
        )
        db.add(session)
        await db.flush()
        await sessions_svc._replace_session_coaches(
            db, session, [scenario.coach_a_user_id],
            added_by_user_id=scenario.coach_a_user_id,
        )
        await db.commit()

        with pytest.raises(sessions_svc.SessionCoachConflictError) as exc:
            await sessions_svc._replace_session_coaches(
                db, session, [], added_by_user_id=scenario.coach_a_user_id
            )
        assert str(exc.value) == "Una sesión debe tener al menos un entrenador."


async def test_b06_coach_of_another_club_is_rejected_and_nothing_is_written(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        resp = await _create_session(
            client,
            scenario,
            coach_user_ids=[
                scenario.coach_a_user_id,
                scenario.other_club_coach_user_id,
            ],
        )

    assert resp.status_code == 422, resp.text
    assert str(scenario.other_club_coach_user_id) in resp.json()["detail"]
    assert resp.json()["detail"].startswith(
        "Los siguientes usuarios no son entrenadores del club:"
    )

    async with session_factory() as s:
        total = await s.scalar(select(func.count()).select_from(TrainingSession))
    assert total == 0


async def test_b07_v4_rejects_a_new_inactive_coach_but_v5_keeps_an_assigned_one(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )
        session_id = created.json()["id"]

    # coach_b se desactiva DESPUÉS de haber quedado asignado
    async with session_factory() as s:
        coach_b = await s.get(User, scenario.coach_b_user_id)
        coach_b.is_active = False
        await s.commit()

    async with client_factory(scenario.coach_a_user_id) as client:
        # V5 — una edición ajena que conserva al co-entrenador inactivo pasa
        keep_resp = await client.patch(
            f"/api/training-sessions/{session_id}",
            json={
                "location": "Otra pista ficticia",
                "coach_user_ids": [
                    scenario.coach_a_user_id,
                    scenario.coach_b_user_id,
                ],
            },
        )

    async with client_factory(scenario.coach_a_user_id) as client:
        # V4 — asignar al inactivo en una sesión nueva se rechaza
        add_resp = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )

    assert keep_resp.status_code == 200, keep_resp.text
    assert add_resp.status_code == 422, add_resp.text
    assert add_resp.json()["detail"] == (
        f"No puedes asignar a un entrenador inactivo: [{scenario.coach_b_user_id}]"
    )


# ---------------------------------------------------------------------------
# B-15 — has_active_coach
# ---------------------------------------------------------------------------


async def test_b15_has_active_coach_flips_with_the_coaches_state(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]

    async with session_factory() as s:
        coach_a = await s.get(User, scenario.coach_a_user_id)
        coach_a.is_active = False
        await s.commit()

    async with client_factory(scenario.admin_user_id) as client:
        after_deactivation = await client.get(f"/api/training-sessions/{session_id}")
        # Se agrega un segundo entrenador ACTIVO al conjunto
        restored = await client.patch(
            f"/api/training-sessions/{session_id}",
            json={
                "coach_user_ids": [
                    scenario.coach_a_user_id,
                    scenario.coach_b_user_id,
                ]
            },
        )

    assert after_deactivation.status_code == 200, after_deactivation.text
    assert after_deactivation.json()["has_active_coach"] is False
    assert restored.status_code == 200, restored.text
    assert restored.json()["has_active_coach"] is True


# ---------------------------------------------------------------------------
# B-13 (mitad de sesiones) — filtro coach_user_id (§8.1)
# ---------------------------------------------------------------------------


async def test_b13_coach_user_id_filter_returns_only_that_coachs_sessions(
    scenario, client_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        only_a = await _create_session(client, scenario)
        shared = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )
        resp = await client.get(
            "/api/training-sessions",
            params={"coach_user_id": scenario.coach_b_user_id},
        )

    assert resp.status_code == 200, resp.text
    ids = {s["id"] for s in resp.json()}
    assert ids == {shared.json()["id"]}
    assert only_a.json()["id"] not in ids


async def test_b14_parent_cannot_filter_by_coach(scenario, client_factory):
    async with client_factory(scenario.parent_user_id) as client:
        resp = await client.get(
            "/api/training-sessions",
            params={"coach_user_id": scenario.coach_b_user_id},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "No tienes permisos para filtrar por entrenador."


async def test_b14_parent_payload_has_no_coaches(scenario, client_factory):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]

    async with client_factory(scenario.parent_user_id) as client:
        detail = await client.get(f"/api/training-sessions/{session_id}")
        attendance = await client.get(
            f"/api/training-sessions/{session_id}/attendance"
        )
        archived = await client.get(
            f"/api/training-sessions/{session_id}/attendance",
            params={"include_archived": True},
        )

    assert detail.status_code == 200, detail.text
    assert "coaches" not in detail.json()
    assert "has_active_coach" not in detail.json()

    assert attendance.status_code == 200, attendance.text
    for row in attendance.json():
        assert "recorded_by_display_name" not in row
        assert "last_edited_by_display_name" not in row
        assert "archived_at" not in row

    assert archived.status_code == 403
    assert archived.json()["detail"] == (
        "Solo un administrador puede ver los registros archivados."
    )


# ---------------------------------------------------------------------------
# B-10 / B-11 / B-12 — archivado, re-alta y atribución de asistencia (§6)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def two_athletes(scenario, session_factory):
    """Segundo atleta ficticio del mismo club, para probar la reducción de
    convocatoria con una fila con datos y otra con placeholder vacío."""
    from tests.fixtures.race_history_fixtures import create_athlete

    async with session_factory() as s:
        await create_athlete(
            s,
            athlete_id=scenario.athlete_id + 1,
            first_name="Atleta Ficticio",
            last_name="Dos",
            birth_date=date(2013, 2, 2),
            club_id=scenario.club_id,
            user_id=scenario.athlete_user_id + 1,
            created_by=scenario.coach_a_user_id,
        )
        await s.commit()
    return scenario.athlete_id, scenario.athlete_id + 1


async def test_b10_b11_roster_shrink_archives_then_restores(
    scenario, client_factory, session_factory, two_athletes
):
    first, second = two_athletes

    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(
            client, scenario, convocados_athlete_ids=[first, second]
        )
        session_id = created.json()["id"]
        # `first` recibe datos de rúbrica; `second` queda como placeholder vacío
        rated = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{first}",
            json={"status": "presente", "rubric_effort": 4, "rpe_omni": 6},
        )
        assert rated.status_code == 200, rated.text

        shrink = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json={"athlete_ids": [], "send_notification": False},
        )
        assert shrink.status_code == 200, shrink.text
        assert shrink.json() == []

    # B-10: la fila con datos sobrevive archivada; el placeholder se borró
    async with session_factory() as s:
        rows = list(
            (
                await s.execute(
                    select(SessionAttendance).where(
                        SessionAttendance.session_id == session_id
                    )
                )
            ).scalars()
        )
    assert [r.athlete_id for r in rows] == [first]
    assert rows[0].archived_at is not None
    assert rows[0].rubric_effort == 4
    assert rows[0].rpe_omni == 6

    archive_audit = await _audit_rows(
        session_factory, AuditEntityType.session_attendance, AuditAction.archive
    )
    delete_audit = await _audit_rows(
        session_factory, AuditEntityType.session_attendance, AuditAction.delete
    )
    assert len(archive_audit) == 1 and archive_audit[0].athlete_id == first
    assert len(delete_audit) == 1 and delete_audit[0].athlete_id == second

    # B-11: re-convocar al atleta archivado lo desarchiva, sin IntegrityError
    async with client_factory(scenario.coach_a_user_id) as client:
        re_add = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json={"athlete_ids": [first], "send_notification": False},
        )
    assert re_add.status_code == 200, re_add.text
    assert [r["athlete_id"] for r in re_add.json()] == [first]

    async with session_factory() as s:
        row = (
            await s.execute(
                select(SessionAttendance).where(
                    SessionAttendance.session_id == session_id,
                    SessionAttendance.athlete_id == first,
                )
            )
        ).scalar_one()
    assert row.archived_at is None
    assert row.rubric_effort == 4

    restore_audit = await _audit_rows(
        session_factory, AuditEntityType.session_attendance, AuditAction.restore
    )
    assert len(restore_audit) == 1
    assert restore_audit[0].diff_json["archived_at"]["after"] is None


async def test_b12_recorded_by_is_the_first_author_and_updated_by_the_last(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        first_write = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{scenario.athlete_id}",
            json={"status": "presente", "rubric_effort": 3},
        )
    assert first_write.status_code == 200, first_write.text

    async with client_factory(scenario.coach_b_user_id) as client:
        second_write = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{scenario.athlete_id}",
            json={"status": "presente", "rubric_effort": 5},
        )
    assert second_write.status_code == 200, second_write.text

    body = second_write.json()
    assert body["recorded_by_display_name"] == "Coach Ficticio A"
    assert body["last_edited_by_display_name"] == "Coach Ficticio B"

    async with session_factory() as s:
        row = (
            await s.execute(
                select(SessionAttendance).where(
                    SessionAttendance.session_id == session_id,
                    SessionAttendance.athlete_id == scenario.athlete_id,
                )
            )
        ).scalar_one()
    assert row.recorded_by_user_id == scenario.coach_a_user_id
    assert row.updated_by_user_id == scenario.coach_b_user_id


async def test_placeholder_row_has_no_attribution(
    scenario, client_factory, session_factory
):
    """§6.2 — la fila placeholder de la convocatoria no atribuye a nadie."""
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]

    async with session_factory() as s:
        row = (
            await s.execute(
                select(SessionAttendance).where(
                    SessionAttendance.session_id == session_id
                )
            )
        ).scalar_one()
    assert row.status == AttendanceStatus.AUSENTE
    assert row.recorded_by_user_id is None
    assert row.updated_by_user_id is None


async def test_admin_include_archived_returns_the_archived_row(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{scenario.athlete_id}",
            json={"status": "presente", "rubric_effort": 4},
        )
        await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json={"athlete_ids": [], "send_notification": False},
        )

    async with client_factory(scenario.admin_user_id) as client:
        active = await client.get(f"/api/training-sessions/{session_id}/attendance")
        archived = await client.get(
            f"/api/training-sessions/{session_id}/attendance",
            params={"include_archived": True},
        )

    assert active.status_code == 200 and active.json() == []
    assert archived.status_code == 200, archived.text
    assert len(archived.json()) == 1
    assert archived.json()[0]["archived_at"] is not None
    assert archived.json()[0]["rubric_effort"] == 4


# ---------------------------------------------------------------------------
# §7.1 — reason_code obligatorio en la cancelación (parte de B-16)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"reason_code": ""},
        {"reason_code": "athlete_left_club"},
        {"reason_code": "motivo libre"},
    ],
)
async def test_b16_cancel_requires_a_reason_code_from_the_cancel_group(
    scenario, client_factory, params
):
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        resp = await client.delete(
            f"/api/training-sessions/{session_id}", params=params
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Selecciona un motivo de cancelación."


async def test_b16_cancel_with_a_valid_code_audits_it(
    scenario, client_factory, session_factory
):
    async with client_factory(scenario.coach_b_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        resp = await client.delete(
            f"/api/training-sessions/{session_id}",
            params={"reason_code": "cancel_weather"},
        )

    assert resp.status_code == 204, resp.text
    rows = await _audit_rows(
        session_factory, AuditEntityType.training_session, AuditAction.cancel
    )
    assert len(rows) == 1
    assert rows[0].reason_code == "cancel_weather"
    assert rows[0].actor_user_id == scenario.coach_b_user_id
    assert rows[0].diff_json["status"]["after"] == "cancelled"


# ---------------------------------------------------------------------------
# Fix: `{fecha}` en las plantillas de §7.5 (contracts/audit-log-api.md) —
# `record_audit` debe llevar `meta_json.event_date` en cada escritura
# auditada de `training_session`, no solo cuando `scheduled_date` cambia, o
# `render_sentence` degrada al genérico de §7.4 por no poder resolver
# `{fecha}`.
# ---------------------------------------------------------------------------


async def test_update_session_audit_row_carries_event_date_and_full_sentence(
    scenario, client_factory, session_factory
):
    from app.services.audit import render_sentence
    from app.services.utils.dates_es import format_date_es

    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        # `location` no cambia `scheduled_date`: antes del fix esta fila
        # perdía `{fecha}` porque `_resolve_placeholder` solo miraba el diff
        # de `scheduled_date`/`start_at`.
        resp = await client.patch(
            f"/api/training-sessions/{session_id}",
            json={"location": "Pista nueva ficticia", "send_notification": False},
        )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(
        session_factory, AuditEntityType.training_session, AuditAction.update
    )
    assert len(rows) == 1
    assert rows[0].meta_json["event_date"] == FUTURE_DATE.isoformat()

    sentence = render_sentence(rows[0], "Coach Ficticio A")
    assert sentence == (
        "Coach Ficticio A actualizó la sesión de entrenamiento del "
        f"{format_date_es(FUTURE_DATE)}."
    )
    assert "actualizó la ficha" not in sentence  # nunca el genérico de §7.4


async def test_execute_session_audit_row_carries_event_date(
    scenario, client_factory, session_factory
):
    from app.services.audit import render_sentence
    from app.services.utils.dates_es import format_date_es

    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        resp = await client.post(f"/api/training-sessions/{session_id}/execute")
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(
        session_factory, AuditEntityType.training_session, AuditAction.execute
    )
    assert len(rows) == 1
    assert rows[0].meta_json["event_date"] == FUTURE_DATE.isoformat()

    sentence = render_sentence(rows[0], "Coach Ficticio A")
    assert sentence == (
        "Coach Ficticio A marcó como ejecutada la sesión de entrenamiento "
        f"del {format_date_es(FUTURE_DATE)}."
    )


async def test_cancel_session_audit_row_carries_event_date_and_reason(
    scenario, client_factory, session_factory
):
    """Reproduce el bug reportado: "Juan Diaz canceló la sesión de
    entrenamiento." sin fecha ni motivo — cae al genérico porque `{fecha}`
    no se podía resolver (`cancel` no cambia `scheduled_date`)."""
    from app.services.audit import render_sentence
    from app.services.utils.dates_es import format_date_es

    async with client_factory(scenario.coach_b_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        resp = await client.delete(
            f"/api/training-sessions/{session_id}",
            params={"reason_code": "cancel_weather"},
        )
    assert resp.status_code == 204, resp.text

    rows = await _audit_rows(
        session_factory, AuditEntityType.training_session, AuditAction.cancel
    )
    assert len(rows) == 1
    assert rows[0].meta_json["event_date"] == FUTURE_DATE.isoformat()

    sentence = render_sentence(rows[0], "Coach Ficticio B")
    assert sentence == (
        "Coach Ficticio B canceló la sesión de entrenamiento del "
        f"{format_date_es(FUTURE_DATE)} (Clima adverso)."
    )
    assert sentence != "Coach Ficticio B canceló la sesión de entrenamiento."


async def test_cancel_calendar_event_audit_row_carries_event_date(
    scenario, client_factory, session_factory
):
    """Mismo fix que las pruebas de arriba, pero para `calendar_event`·
    `cancel`: "Juan Diaz canceló el evento del calendario." sin fecha."""
    from app.services.audit import render_sentence
    from app.services.utils.dates_es import format_date_es

    event_start = f"{FUTURE_DATE.isoformat()}T09:00:00Z"
    event_end = f"{FUTURE_DATE.isoformat()}T11:00:00Z"

    async with client_factory(scenario.coach_a_user_id) as client:
        created = await client.post(
            "/api/calendar/events",
            json={
                "event_type": "club_event",
                "title": "Reunión ficticia de club",
                "start_at": event_start,
                "end_at": event_end,
                "audiences": [],
            },
        )
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]

        resp = await client.request(
            "DELETE",
            f"/api/calendar/events/{event_id}",
            json={"reason_code": "cancel_weather"},
        )
    assert resp.status_code == 204, resp.text

    rows = await _audit_rows(
        session_factory, AuditEntityType.calendar_event, AuditAction.cancel
    )
    assert len(rows) == 1
    assert rows[0].meta_json["event_date"] == FUTURE_DATE.isoformat()

    sentence = render_sentence(rows[0], "Coach Ficticio A")
    assert sentence == (
        "Coach Ficticio A canceló el evento del calendario del "
        f"{format_date_es(FUTURE_DATE)} (Clima adverso)."
    )
    assert sentence != "Coach Ficticio A canceló el evento del calendario."


# ---------------------------------------------------------------------------
# B-18 — privacidad de las filas de auditoría de este dominio
# ---------------------------------------------------------------------------


async def test_b18_audit_rows_never_carry_feedback_or_a_minors_name(
    scenario, client_factory, session_factory
):
    from tests.fixtures.two_coaches import ATHLETE_FIRST_NAME, ATHLETE_LAST_NAME

    feedback = "Texto libre del entrenador que jamás debe llegar a audit_log"
    async with client_factory(scenario.coach_a_user_id) as client:
        created = await _create_session(client, scenario)
        session_id = created.json()["id"]
        await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{scenario.athlete_id}",
            json={
                "status": "presente",
                "individual_feedback": feedback,
                "rubric_effort": 4,
            },
        )

    async with session_factory() as s:
        rows = list((await s.execute(select(AuditLog))).scalars())

    assert rows
    for row in rows:
        blob = f"{row.diff_json} {row.meta_json} {row.changed_fields}"
        assert feedback not in blob
        assert ATHLETE_FIRST_NAME not in blob
        assert ATHLETE_LAST_NAME not in blob

    updates = [
        r
        for r in rows
        if r.entity_type == AuditEntityType.session_attendance.value
        and r.action == AuditAction.update
    ]
    assert updates
    assert "individual_feedback" in updates[0].changed_fields


# ---------------------------------------------------------------------------
# B-08 / B-09 — el email nombra a QUIEN ACTUÓ, no al creador (bug de US4)
# ---------------------------------------------------------------------------


class _CapturingNotificationService:
    """Doble de `NotificationService` que solo guarda los `NotificationRequest`."""

    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, request, dispatcher=None):  # noqa: ANN001
        self.sent.append(request)
        return None


@pytest_asyncio.fixture
async def notifications(client_factory):
    """Monta el doble de notificaciones y limpia el throttle en memoria, que
    es estado global del módulo de servicios."""
    from app.dependencies import get_notification_service
    from app.services.training import sessions as sessions_svc

    sessions_svc._recent_dispatches.clear()
    fake = _CapturingNotificationService()
    app.dependency_overrides[get_notification_service] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_notification_service, None)
        sessions_svc._recent_dispatches.clear()


def _context_of(fake, template_value: str) -> dict:
    for request in fake.sent:
        if request.template.value == template_value:
            return request.context
    raise AssertionError(f"No se despachó ningún email {template_value}")


async def test_b08_cancel_email_names_the_canceller_not_the_creator(
    scenario, client_factory, notifications
):
    from app.dependencies import get_notification_service

    async with client_factory(scenario.coach_a_user_id) as client:
        app.dependency_overrides[get_notification_service] = lambda: notifications
        created = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
            send_notification=True,
        )
        session_id = created.json()["id"]

    invite_ctx = _context_of(notifications, "training_session_invite")
    assert invite_ctx["acting_coach_name"] == "Coach Ficticio A"
    assert invite_ctx["coaches_text"] == "Coach Ficticio A y Coach Ficticio B"
    assert invite_ctx["coach_names"] == ["Coach Ficticio A", "Coach Ficticio B"]

    notifications.sent.clear()
    async with client_factory(scenario.coach_b_user_id) as client:
        app.dependency_overrides[get_notification_service] = lambda: notifications
        resp = await client.delete(
            f"/api/training-sessions/{session_id}",
            params={"notify": True, "reason_code": "cancel_weather"},
        )
    assert resp.status_code == 204, resp.text

    cancel_ctx = _context_of(notifications, "training_session_cancelled")
    # El bug de US4: hoy `_load_session_coach` devolvía al CREADOR (coach A).
    assert cancel_ctx["acting_coach_name"] == "Coach Ficticio B"
    assert cancel_ctx["coaches_text"] == "Coach Ficticio A y Coach Ficticio B"
    # La razón viaja como etiqueta en español, nunca como código ni texto libre.
    assert cancel_ctx["reason"] == "Clima adverso"
    assert "coach_name" not in cancel_ctx


async def test_b09_update_email_names_the_editor(
    scenario, client_factory, notifications
):
    from app.dependencies import get_notification_service

    async with client_factory(scenario.coach_a_user_id) as client:
        app.dependency_overrides[get_notification_service] = lambda: notifications
        created = await _create_session(
            client,
            scenario,
            coach_user_ids=[scenario.coach_a_user_id, scenario.coach_b_user_id],
        )
        session_id = created.json()["id"]

    async with client_factory(scenario.coach_b_user_id) as client:
        app.dependency_overrides[get_notification_service] = lambda: notifications
        resp = await client.patch(
            f"/api/training-sessions/{session_id}",
            json={"location": "Pista ficticia dos", "send_notification": True},
        )
    assert resp.status_code == 200, resp.text

    ctx = _context_of(notifications, "training_session_updated")
    assert ctx["acting_coach_name"] == "Coach Ficticio B"
    assert ctx["coaches_text"] == "Coach Ficticio A y Coach Ficticio B"


def test_join_names_es_pluralisation():
    from app.services.training.sessions import _join_names_es

    assert _join_names_es([]) == ""
    assert _join_names_es(["Ana"]) == "Ana"
    assert _join_names_es(["Ana", "Bruno"]) == "Ana y Bruno"
    assert _join_names_es(["Ana", "Bruno", "Carla"]) == "Ana, Bruno y Carla"
