"""Tests del router de calendario.

Patrón idéntico a test_ai_router.py: usa app.dependency_overrides para
evitar dependencia de MySQL. No requiere base de datos.

Cubre:
- Sin token → 403 (HTTPBearer)
- Parámetros inválidos → 422
- from > to → 400
- RBAC: parent no puede crear (403)
- Responses: 404 evento inexistente, 403 sin permiso
- allDay alias para FullCalendar
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db, get_notification_service, get_task_dispatcher
from app.main import app
from app.models.calendar_event import EventStatus, EventType
from app.models.club import ClubMember, ClubRole
from app.models.user import UserRole
from app.services.audit import AuditAction, AuditEntityType


# ---------------------------------------------------------------------------
# Helpers de usuarios mock
# ---------------------------------------------------------------------------


def _make_club_membership(club_id: int = 1, role: ClubRole = ClubRole.coach):
    m = SimpleNamespace(club_id=club_id, role_in_club=role)
    return m


def _coach_user():
    return SimpleNamespace(
        id=1,
        first_name="Entrenador",
        last_name="Test",
        email="coach@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[_make_club_membership(1, ClubRole.coach)],
    )


def _admin_user():
    return SimpleNamespace(
        id=2,
        first_name="Admin",
        last_name="Test",
        email="admin@test.com",
        role=UserRole.admin,
        can_login=True,
        is_active=True,
        club_memberships=[_make_club_membership(1, ClubRole.athlete)],
    )


def _parent_user():
    return SimpleNamespace(
        id=3,
        first_name="Padre",
        last_name="Test",
        email="padre@test.com",
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _make_event_mock(event_id: int = 1) -> MagicMock:
    ev = MagicMock()
    ev.id = event_id
    ev.club_id = 1
    ev.event_type = EventType.CLUB_EVENT
    ev.status = EventStatus.SCHEDULED
    ev.title = "Asamblea anual"
    ev.description = None
    ev.location = "Sede del club"
    ev.start_at = datetime(2030, 9, 1, 18, 0, tzinfo=timezone.utc)
    ev.end_at = datetime(2030, 9, 1, 20, 0, tzinfo=timezone.utc)
    ev.all_day = False
    ev.timezone = "America/Bogota"
    ev.event_data = {"kind": "meeting"}
    ev.color_hex = None
    ev.created_by_user_id = 1
    ev.created_at = datetime.now(timezone.utc)
    ev.updated_at = datetime.now(timezone.utc)
    ev.audiences = []
    ev.attendances = []
    return ev


def _club_event_payload(**kwargs) -> dict:
    defaults = {
        "event_type": "club_event",
        "title": "Asamblea anual",
        "start_at": "2030-09-01T18:00:00",
        "end_at": "2030-09-01T20:00:00",
        "event_data": {"kind": "meeting"},
        "audiences": [{"audience_type": "all_club", "audience_value": {}}],
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Fixture — client y setup/teardown de overrides
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # Limpiar siempre después del test
    app.dependency_overrides.clear()


def _override_db():
    """DB fake que no hace nada (para tests que no necesitan DB)."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    async def _yield_db():
        yield db

    return _yield_db


def _override_notification_service():
    return MagicMock()


def _override_dispatcher():
    return MagicMock()


# ---------------------------------------------------------------------------
# Sin token — 403
# ---------------------------------------------------------------------------


class TestNoAuth:
    async def test_sin_token_list_requiere_auth(self, client: AsyncClient):
        """Sin token → 401 o 403 (depende de si HTTPBearer rechaza o requiere permisos)."""
        resp = await client.get(
            "/api/calendar/events",
            params={"from": "2030-09-01", "to": "2030-09-30"},
        )
        assert resp.status_code in (401, 403)

    async def test_sin_token_create_requiere_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/calendar/events",
            json=_club_event_payload(),
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Validación de parámetros
# ---------------------------------------------------------------------------


class TestListParams:
    async def test_sin_from_to_retorna_422(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        resp = await client.get(
            "/api/calendar/events",
            headers={"Authorization": "Bearer fake"},
        )

        assert resp.status_code == 422

    async def test_lista_vacia_con_params_validos(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        with patch(
            "app.services.calendar.events.list_events_in_range",
            AsyncMock(return_value=[]),
        ):
            resp = await client.get(
                "/api/calendar/events",
                params={"from": "2030-09-01", "to": "2030-09-30"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_from_mayor_que_to_retorna_400(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        resp = await client.get(
            "/api/calendar/events",
            params={"from": "2030-12-01", "to": "2030-01-01"},
            headers={"Authorization": "Bearer fake"},
        )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/calendar/events — RBAC
# ---------------------------------------------------------------------------


class TestCreateEventRBAC:
    async def test_parent_no_puede_crear_403(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service

        resp = await client.post(
            "/api/calendar/events",
            json=_club_event_payload(),
            headers={"Authorization": "Bearer fake"},
        )

        assert resp.status_code == 403

    async def test_payload_invalido_retorna_422(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service

        resp = await client.post(
            "/api/calendar/events",
            json={"campo_invalido": "test"},
            headers={"Authorization": "Bearer fake"},
        )

        assert resp.status_code == 422

    async def test_coach_crea_evento_201(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service
        app.dependency_overrides[get_task_dispatcher] = _override_dispatcher

        event_mock = _make_event_mock(event_id=999)

        with patch(
            "app.routers.calendar._get_club_id_for_user",
            AsyncMock(return_value=1),
        ):
            with patch(
                "app.services.calendar.events.create_event",
                AsyncMock(return_value=event_mock),
            ):
                resp = await client.post(
                    "/api/calendar/events",
                    json=_club_event_payload(),
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# GET /api/calendar/events/{id}
# ---------------------------------------------------------------------------


class TestGetEventById:
    async def test_evento_inexistente_retorna_404(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=None),
        ):
            resp = await client.get(
                "/api/calendar/events/99999",
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 404

    async def test_sin_permiso_retorna_403(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_view_calendar_event",
                AsyncMock(return_value=False),
            ):
                resp = await client.get(
                    "/api/calendar/events/1",
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 403

    async def test_coach_con_permiso_retorna_200(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_view_calendar_event",
                AsyncMock(return_value=True),
            ):
                resp = await client.get(
                    "/api/calendar/events/1",
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/calendar/events/{id}
# ---------------------------------------------------------------------------


class TestPatchEvent:
    async def test_sin_permiso_retorna_403(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service
        app.dependency_overrides[get_task_dispatcher] = _override_dispatcher

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=False),
            ):
                resp = await client.patch(
                    "/api/calendar/events/1",
                    json={"title": "Intento"},
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 403

    async def test_coach_puede_editar_200(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service
        app.dependency_overrides[get_task_dispatcher] = _override_dispatcher

        event_mock = _make_event_mock()
        updated_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.calendar.events.update_event",
                    AsyncMock(return_value=updated_mock),
                ):
                    resp = await client.patch(
                        "/api/calendar/events/1",
                        json={"title": "Nuevo título"},
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/calendar/events/{id}
# ---------------------------------------------------------------------------


class TestDeleteEvent:
    async def test_sin_permiso_retorna_403(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=False),
            ):
                resp = await client.delete(
                    "/api/calendar/events/1",
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 403

    async def test_coach_puede_cancelar_204(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_notification_service] = _override_notification_service
        app.dependency_overrides[get_task_dispatcher] = _override_dispatcher

        event_mock = _make_event_mock()
        cancelled = _make_event_mock()
        cancelled.status = EventStatus.CANCELLED

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.calendar.events.cancel_event",
                    AsyncMock(return_value=cancelled),
                ):
                    resp = await client.delete(
                        "/api/calendar/events/1?reason=Lluvia",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# POST /api/calendar/events/{id}/rsvp
# ---------------------------------------------------------------------------


class TestRSVP:
    async def test_sin_permiso_retorna_403(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.services.permissions.can_rsvp_event",
                AsyncMock(return_value=False),
            ):
                resp = await client.post(
                    "/api/calendar/events/1/rsvp",
                    json={"athlete_id": 1, "rsvp_status": "accepted"},
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 403

    async def test_con_permiso_retorna_200(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()
        att_mock = MagicMock()
        att_mock.id = 1
        att_mock.event_id = 1
        att_mock.athlete_id = 1
        att_mock.rsvp_status = "accepted"
        att_mock.rsvp_at = datetime.now(timezone.utc)
        att_mock.rsvp_by_user_id = 3
        att_mock.actual_status = "unknown"
        att_mock.notes = None
        att_mock.created_at = datetime.now(timezone.utc)
        att_mock.updated_at = datetime.now(timezone.utc)

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_rsvp_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.calendar.attendances.rsvp",
                    AsyncMock(return_value=att_mock),
                ):
                    resp = await client.post(
                        "/api/calendar/events/1/rsvp",
                        json={"athlete_id": 1, "rsvp_status": "accepted"},
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# allDay alias — FullCalendar compatibility
# ---------------------------------------------------------------------------


class TestAllDayAlias:
    async def test_lista_retorna_allDay_alias(self, client: AsyncClient):
        """FullCalendar espera 'allDay' (camelCase). Verificamos la serialización."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.list_events_in_range",
            AsyncMock(return_value=[event_mock]),
        ):
            resp = await client.get(
                "/api/calendar/events",
                params={"from": "2030-09-01", "to": "2030-09-30"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        first = items[0]
        assert first.get("id") == 1
        # La respuesta debe incluir el alias 'allDay'
        assert "allDay" in first, f"'allDay' no encontrado en respuesta: {list(first.keys())}"

    async def test_lista_vacia_retorna_array_vacio(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        with patch(
            "app.services.calendar.events.list_events_in_range",
            AsyncMock(return_value=[]),
        ):
            resp = await client.get(
                "/api/calendar/events",
                params={"from": "2030-09-01", "to": "2030-09-30"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_all_day_no_aparece_como_snake_case(self, client: AsyncClient):
        """La clave 'all_day' (snake_case) no debe aparecer — solo 'allDay'."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.list_events_in_range",
            AsyncMock(return_value=[event_mock]),
        ):
            resp = await client.get(
                "/api/calendar/events",
                params={"from": "2030-09-01", "to": "2030-09-30"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        items = resp.json()
        if items:
            first = items[0]
            assert "all_day" not in first, "'all_day' no debe aparecer — usar alias 'allDay'"


# ---------------------------------------------------------------------------
# Privacidad — padre solo ve attendances de sus hijos
# ---------------------------------------------------------------------------


class TestAttendancesPrivacy:
    """Garantiza que GET /events/{id}/attendances filtra a hijos del padre."""

    async def test_parent_solo_ve_attendances_de_sus_hijos(self, client: AsyncClient):
        """Un padre con athlete_id=10 NO debe ver attendances de athlete_id=99."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()
        event_mock.event_type = EventType.CLUB_EVENT

        own = MagicMock()
        own.id = 1
        own.event_id = 1
        own.athlete_id = 10  # hijo del padre
        own.rsvp_status = "accepted"
        own.rsvp_at = datetime.now(timezone.utc)
        own.rsvp_by_user_id = 3
        own.actual_status = "unknown"
        own.notes = None
        own.created_at = datetime.now(timezone.utc)
        own.updated_at = datetime.now(timezone.utc)

        foreign = MagicMock()
        foreign.id = 2
        foreign.event_id = 1
        foreign.athlete_id = 99  # NO es hijo del padre
        foreign.rsvp_status = "declined"
        foreign.rsvp_at = datetime.now(timezone.utc)
        foreign.rsvp_by_user_id = 77
        foreign.actual_status = "unknown"
        foreign.notes = None
        foreign.created_at = datetime.now(timezone.utc)
        foreign.updated_at = datetime.now(timezone.utc)

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_view_calendar_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.permissions.parent_athlete_ids",
                    AsyncMock(return_value=[10]),
                ):
                    with patch(
                        "app.services.calendar.attendances.list_attendances",
                        AsyncMock(return_value=[own, foreign]),
                    ):
                        resp = await client.get(
                            "/api/calendar/events/1/attendances",
                            headers={"Authorization": "Bearer fake"},
                        )

        assert resp.status_code == 200
        body = resp.json()
        athlete_ids = {row["athlete_id"] for row in body}
        assert athlete_ids == {10}, (
            f"Padre vio attendances ajenas: {athlete_ids}"
        )

    async def test_coach_ve_todas_las_attendances(self, client: AsyncClient):
        """Un coach del club ve todos los atletas (no se filtra)."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()
        event_mock.event_type = EventType.CLUB_EVENT

        a1 = MagicMock(
            id=1, event_id=1, athlete_id=10, rsvp_status="accepted",
            rsvp_at=datetime.now(timezone.utc), rsvp_by_user_id=3,
            actual_status="unknown", notes=None,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        a2 = MagicMock(
            id=2, event_id=1, athlete_id=99, rsvp_status="declined",
            rsvp_at=datetime.now(timezone.utc), rsvp_by_user_id=77,
            actual_status="unknown", notes=None,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_view_calendar_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.calendar.attendances.list_attendances",
                    AsyncMock(return_value=[a1, a2]),
                ):
                    resp = await client.get(
                        "/api/calendar/events/1/attendances",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 200
        body = resp.json()
        athlete_ids = {row["athlete_id"] for row in body}
        assert athlete_ids == {10, 99}, "Coach debe ver TODAS las attendances"


# ---------------------------------------------------------------------------
# DELETE /api/calendar/events/{id}/permanent — Hard delete
# ---------------------------------------------------------------------------


class TestDeleteEventPermanent:
    async def test_delete_event_permanent_as_coach_returns_204(self, client: AsyncClient):
        """Coach con permiso borra permanentemente un evento → 204."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=True),
            ):
                with patch(
                    "app.services.calendar.events.delete_event_permanent",
                    AsyncMock(return_value=None),
                ):
                    resp = await client.delete(
                        "/api/calendar/events/1/permanent",
                        headers={"Authorization": "Bearer fake"},
                    )

        assert resp.status_code == 204

    async def test_delete_event_permanent_birthday_returns_400(self, client: AsyncClient):
        """Intentar borrar un cumpleaños (virtual) → 400."""
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = _override_db()

        birthday_mock = _make_event_mock()
        birthday_mock.event_type = EventType.BIRTHDAY

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=birthday_mock),
        ):
            resp = await client.delete(
                "/api/calendar/events/1/permanent",
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 400

    async def test_delete_event_permanent_unauthorized_role_returns_403(self, client: AsyncClient):
        """Usuario sin permiso de edición → 403."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ):
            with patch(
                "app.routers.calendar.can_edit_calendar_event",
                AsyncMock(return_value=False),
            ):
                resp = await client.delete(
                    "/api/calendar/events/1/permanent",
                    headers={"Authorization": "Bearer fake"},
                )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Auditoría (feature 041, T023, contracts/audit-recording.md §4.5)
#
# Estos tests llaman directamente a la capa de servicio
# (`app.services.calendar.events`) en vez de pasar por el router, porque los
# tests de router de arriba mockean por completo `events_svc.*` y por lo
# tanto nunca ejercitan las llamadas a `record_audit` agregadas dentro de
# esas funciones. `record_audit` se parchea para poder aserir con qué
# argumentos fue invocado, sin depender de una base de datos real.
# ---------------------------------------------------------------------------


def _fake_db():
    """AsyncSession falsa mínima para ejercitar la capa de servicio."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.delete = AsyncMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


class TestCalendarAudit:
    async def test_create_event_records_calendar_event_create(self):
        from app.schemas.calendar import EventCreate

        db = _fake_db()
        user = _coach_user()
        payload = EventCreate(
            event_type=EventType.CLUB_EVENT,
            title="Asamblea anual",
            start_at=datetime(2030, 9, 1, 18, 0, tzinfo=timezone.utc),
            end_at=datetime(2030, 9, 1, 20, 0, tzinfo=timezone.utc),
            event_data={"kind": "meeting"},
            audiences=[],
        )

        created_event = _make_event_mock()
        created_event.id = 42
        created_event.club_id = 1

        with patch(
            "app.services.calendar.audiences.set_audiences",
            AsyncMock(),
        ), patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=created_event),
        ), patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            async def _flush_side_effect():
                # Simula que la sesión asigna el id al hacer flush.
                pass

            db.flush.side_effect = _flush_side_effect

            def _fake_add(obj):
                if not hasattr(obj, "id") or obj.id is None:
                    obj.id = 42

            db.add.side_effect = _fake_add

            result = await events_svc.create_event(
                db=db,
                payload=payload,
                user=user,
                club_id=1,
            )

        assert result is created_event
        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.create
        assert kwargs["entity_type"] == AuditEntityType.calendar_event
        assert kwargs["actor"] is user
        assert kwargs["club_id"] == 1

    async def test_update_event_records_calendar_event_update_with_diff(self):
        from app.schemas.calendar import EventUpdate

        db = _fake_db()
        user = _coach_user()
        event = _make_event_mock()
        event.id = 7
        event.club_id = 1
        event.title = "Título viejo"
        event.status = EventStatus.SCHEDULED
        event.event_type = EventType.CLUB_EVENT

        payload = EventUpdate(title="Título nuevo")

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event),
        ), patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            await events_svc.update_event(db=db, event=event, payload=payload, user=user)

        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.update
        assert kwargs["entity_type"] == AuditEntityType.calendar_event
        assert kwargs["entity_id"] == 7
        assert "title" in kwargs["changed_fields"]
        assert kwargs["diff"]["title"] == ("Título viejo", "Título nuevo")

    async def test_update_event_no_changes_does_not_break(self):
        """Un PATCH sin cambios efectivos igual encola el llamado; record_audit
        (parcheado) decide el no-op — aquí solo se verifica que se invoque con
        listas vacías, sin lanzar excepción."""
        from app.schemas.calendar import EventUpdate

        db = _fake_db()
        user = _coach_user()
        event = _make_event_mock()
        event.id = 7
        event.club_id = 1
        event.event_type = EventType.CLUB_EVENT

        payload = EventUpdate()

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event),
        ), patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(return_value=None),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            await events_svc.update_event(db=db, event=event, payload=payload, user=user)

        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["changed_fields"] == []
        assert kwargs["diff"] == {}

    async def test_cancel_event_records_calendar_event_cancel_with_reason(self):
        db = _fake_db()
        user = _coach_user()
        event = _make_event_mock()
        event.id = 9
        event.club_id = 1
        event.status = EventStatus.SCHEDULED
        event.event_type = EventType.CLUB_EVENT

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event),
        ), patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            await events_svc.cancel_event(db=db, event=event, reason="Lluvia", user=user)

        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.cancel
        assert kwargs["entity_type"] == AuditEntityType.calendar_event
        assert kwargs["entity_id"] == 9
        assert kwargs["reason_code"] is not None
        assert kwargs["changed_fields"] == ["status"]

    async def test_delete_event_permanent_records_calendar_event_delete(self):
        db = _fake_db()
        user = _coach_user()
        event = _make_event_mock()
        event.id = 11
        event.club_id = 1
        event.event_type = EventType.CLUB_EVENT

        with patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            await events_svc.delete_event_permanent(db=db, event=event, user=user)

        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.delete
        assert kwargs["entity_type"] == AuditEntityType.calendar_event
        assert kwargs["entity_id"] == 11
        assert kwargs["actor"] is user
        db.delete.assert_awaited_once_with(event)

    async def test_delete_event_permanent_with_linked_session_records_two_rows(self):
        """Borrado permanente de un evento TRAINING_SESSION también audita el
        `training_session` enlazado (`calendar_event`·`delete` + `training_session`·`delete`)."""
        db = _fake_db()
        user = _coach_user()
        event = _make_event_mock()
        event.id = 12
        event.club_id = 1
        event.event_type = EventType.TRAINING_SESSION
        event.event_data = {"training_session_id": 99}

        linked_ts = MagicMock()
        linked_ts.id = 99
        db.get = AsyncMock(return_value=linked_ts)

        with patch(
            "app.services.calendar.events.record_audit",
            AsyncMock(),
        ) as mock_audit:
            from app.services.calendar import events as events_svc

            await events_svc.delete_event_permanent(db=db, event=event, user=user)

        assert mock_audit.await_count == 2
        recorded = [call.kwargs for call in mock_audit.await_args_list]
        entity_types = {r["entity_type"] for r in recorded}
        assert entity_types == {AuditEntityType.training_session, AuditEntityType.calendar_event}
        for r in recorded:
            assert r["action"] == AuditAction.delete

    async def test_rsvp_new_records_event_attendance_create(self, client: AsyncClient):
        """RSVP de un padre sobre un evento (actor puede ser un padre)."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()
        event_mock.id = 5
        event_mock.club_id = 1
        event_mock.event_type = EventType.CLUB_EVENT

        attendance_mock = MagicMock()
        attendance_mock.id = 501
        attendance_mock.event_id = 5
        attendance_mock.athlete_id = 3
        attendance_mock.rsvp_status = "accepted"
        attendance_mock.rsvp_at = datetime.now(timezone.utc)
        attendance_mock.rsvp_by_user_id = 3
        attendance_mock.actual_status = "unknown"
        attendance_mock.notes = None
        attendance_mock.created_at = datetime.now(timezone.utc)
        attendance_mock.updated_at = datetime.now(timezone.utc)

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ), patch(
            "app.routers.calendar.can_rsvp_event",
            AsyncMock(return_value=True),
        ), patch(
            "app.routers.calendar._get_existing_attendance",
            AsyncMock(return_value=None),
        ), patch(
            "app.services.calendar.attendances.rsvp",
            AsyncMock(return_value=attendance_mock),
        ), patch(
            "app.routers.calendar.record_audit",
            AsyncMock(),
        ) as mock_audit:
            resp = await client.post(
                "/api/calendar/events/5/rsvp",
                json={"athlete_id": 3, "rsvp_status": "accepted"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.create
        assert kwargs["entity_type"] == AuditEntityType.event_attendance
        assert kwargs["athlete_id"] == 3
        assert kwargs["entity_id"] == 501

    async def test_rsvp_existing_records_event_attendance_update(self, client: AsyncClient):
        """Un RSVP repetido sobre el mismo atleta/evento audita `update`, no `create`."""
        app.dependency_overrides[get_current_user] = _parent_user
        app.dependency_overrides[get_db] = _override_db()

        event_mock = _make_event_mock()
        event_mock.id = 5
        event_mock.club_id = 1
        event_mock.event_type = EventType.CLUB_EVENT

        previous = MagicMock()
        previous.rsvp_status = MagicMock(value="tentative")

        attendance_mock = MagicMock()
        attendance_mock.id = 501
        attendance_mock.event_id = 5
        attendance_mock.athlete_id = 3
        attendance_mock.rsvp_status = "accepted"
        attendance_mock.rsvp_at = datetime.now(timezone.utc)
        attendance_mock.rsvp_by_user_id = 3
        attendance_mock.actual_status = "unknown"
        attendance_mock.notes = None
        attendance_mock.created_at = datetime.now(timezone.utc)
        attendance_mock.updated_at = datetime.now(timezone.utc)

        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=event_mock),
        ), patch(
            "app.routers.calendar.can_rsvp_event",
            AsyncMock(return_value=True),
        ), patch(
            "app.routers.calendar._get_existing_attendance",
            AsyncMock(return_value=previous),
        ), patch(
            "app.services.calendar.attendances.rsvp",
            AsyncMock(return_value=attendance_mock),
        ), patch(
            "app.routers.calendar.record_audit",
            AsyncMock(),
        ) as mock_audit:
            resp = await client.post(
                "/api/calendar/events/5/rsvp",
                json={"athlete_id": 3, "rsvp_status": "accepted"},
                headers={"Authorization": "Bearer fake"},
            )

        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == AuditAction.update
        assert kwargs["entity_type"] == AuditEntityType.event_attendance
