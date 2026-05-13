"""Tests del servicio de eventos de calendario.

Cubre: CRUD, creación con TrainingSession paralelo, cancel/reschedule,
propagación de cambios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.calendar_event import (
    CalendarEvent,
    EventStatus,
    EventType,
    AudienceType,
)
from app.schemas.calendar import AudienceCreate, EventCreate, EventUpdate
from app.services.calendar import events as events_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2030, 6, 15, 17, 0, tzinfo=timezone.utc)
_END = datetime(2030, 6, 15, 18, 30, tzinfo=timezone.utc)


def _make_user(user_id: int = 1, role_str: str = "coach"):
    from app.models.user import UserRole
    u = MagicMock()
    u.id = user_id
    u.email = "coach@test.com"
    u.first_name = "Coach"
    u.last_name = "Test"
    u.role = UserRole.coach
    u.club_memberships = []
    return u


def _make_event(
    event_id: int = 1,
    club_id: int = 1,
    event_type: EventType = EventType.CLUB_EVENT,
    status: EventStatus = EventStatus.SCHEDULED,
    start_at: datetime = _NOW,
    end_at: datetime = _END,
    location: str | None = "Bosque Municipal",
    audiences=None,
    event_data=None,
):
    ev = MagicMock(spec=CalendarEvent)
    ev.id = event_id
    ev.club_id = club_id
    ev.event_type = event_type
    ev.status = status
    ev.title = "Evento Test"
    ev.description = None
    ev.location = location
    ev.start_at = start_at
    ev.end_at = end_at
    ev.all_day = False
    ev.timezone = "America/Bogota"
    ev.event_data = event_data or {}
    ev.color_hex = None
    ev.created_by_user_id = 1
    ev.created_at = datetime.now(timezone.utc)
    ev.updated_at = datetime.now(timezone.utc)
    ev.audiences = audiences or []
    ev.attendances = []
    return ev


def _make_payload(
    event_type=EventType.CLUB_EVENT,
    event_data=None,
    audiences=None,
):
    return EventCreate(
        event_type=event_type,
        title="Reunión del club",
        start_at=_NOW,
        end_at=_END,
        event_data=event_data or {"kind": "meeting"},
        audiences=audiences or [AudienceCreate(audience_type=AudienceType.ALL_CLUB)],
    )


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# get_event
# ---------------------------------------------------------------------------


class TestGetEvent:
    async def test_retorna_none_si_no_existe(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        ev = await events_svc.get_event(db, 999)
        assert ev is None

    async def test_retorna_evento_si_existe(self):
        event = _make_event()
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = event
        db.execute = AsyncMock(return_value=result)

        ev = await events_svc.get_event(db, 1)
        assert ev is event


# ---------------------------------------------------------------------------
# create_event — CLUB_EVENT
# ---------------------------------------------------------------------------


class TestCreateEventClubEvent:
    async def test_crea_evento_club_event(self):
        user = _make_user()
        payload = _make_payload(EventType.CLUB_EVENT)

        created_event = _make_event(event_type=EventType.CLUB_EVENT)

        db = _make_db()

        with patch.object(events_svc, "get_event", AsyncMock(return_value=created_event)):
            with patch(
                "app.services.calendar.audiences.set_audiences", AsyncMock()
            ):
                result = await events_svc.create_event(
                    db=db,
                    payload=payload,
                    user=user,
                    club_id=1,
                )

        db.add.assert_called()
        db.commit.assert_awaited()
        assert result is created_event

    async def test_crea_evento_personal_training(self):
        user = _make_user()
        payload = EventCreate(
            event_type=EventType.PERSONAL_TRAINING,
            title="Entrenamiento personal",
            start_at=_NOW,
            end_at=_END,
            event_data={"athlete_id": 5, "intensity": "medium"},
            audiences=[
                AudienceCreate(
                    audience_type=AudienceType.INDIVIDUAL,
                    audience_value={"athlete_id": 5},
                )
            ],
        )

        created_event = _make_event(event_type=EventType.PERSONAL_TRAINING)

        db = _make_db()
        with patch.object(events_svc, "get_event", AsyncMock(return_value=created_event)):
            with patch("app.services.calendar.audiences.set_audiences", AsyncMock()):
                result = await events_svc.create_event(
                    db=db,
                    payload=payload,
                    user=user,
                    club_id=1,
                )

        assert result.event_type == EventType.PERSONAL_TRAINING


# ---------------------------------------------------------------------------
# create_event — TRAINING_SESSION (sin training_session_id)
# ---------------------------------------------------------------------------


class TestCreateEventTrainingSession:
    async def test_crea_training_session_paralelo_sin_ts_id(self):
        """Si event_type=TRAINING_SESSION y no viene training_session_id,
        se debe crear un TrainingSession paralelo."""
        user = _make_user()
        payload = EventCreate(
            event_type=EventType.TRAINING_SESSION,
            title="Descenso técnico",
            start_at=_NOW,
            end_at=_END,
            event_data={"training_session_id": None},
            audiences=[
                AudienceCreate(
                    audience_type=AudienceType.ATHLETE_LIST,
                    audience_value={"athlete_ids": [1, 2]},
                )
            ],
        )

        created_event = _make_event(
            event_type=EventType.TRAINING_SESSION,
            event_data={"training_session_id": 10},
        )

        db = _make_db()

        ts_created = []

        async def mock_handle_ts(db, event, payload, user, club_id):
            ts_created.append(True)
            event.event_data = {"training_session_id": 10}

        with patch.object(events_svc, "get_event", AsyncMock(return_value=created_event)):
            with patch("app.services.calendar.audiences.set_audiences", AsyncMock()):
                with patch.object(
                    events_svc,
                    "_handle_training_session_creation",
                    mock_handle_ts,
                ):
                    result = await events_svc.create_event(
                        db=db,
                        payload=payload,
                        user=user,
                        club_id=1,
                    )

        assert ts_created, "Debió llamarse _handle_training_session_creation"
        assert result is created_event

    async def test_enlaza_ts_existente_si_viene_ts_id(self):
        """Si event_type=TRAINING_SESSION y training_session_id SÍ viene, solo enlaza."""
        user = _make_user()
        payload = EventCreate(
            event_type=EventType.TRAINING_SESSION,
            title="Sesión existente",
            start_at=_NOW,
            end_at=_END,
            event_data={"training_session_id": 42},
            audiences=[
                AudienceCreate(
                    audience_type=AudienceType.ATHLETE_LIST,
                    audience_value={"athlete_ids": [1]},
                )
            ],
        )

        created_event = _make_event(
            event_type=EventType.TRAINING_SESSION,
            event_data={"training_session_id": 42},
        )

        db = _make_db()

        calls = []

        async def mock_handle_ts(db, event, payload, user, club_id):
            calls.append("handle_ts_called")

        with patch.object(events_svc, "get_event", AsyncMock(return_value=created_event)):
            with patch("app.services.calendar.audiences.set_audiences", AsyncMock()):
                with patch.object(
                    events_svc,
                    "_handle_training_session_creation",
                    mock_handle_ts,
                ):
                    await events_svc.create_event(
                        db=db,
                        payload=payload,
                        user=user,
                        club_id=1,
                    )

        # _handle_training_session_creation siempre se llama para TRAINING_SESSION
        assert "handle_ts_called" in calls


# ---------------------------------------------------------------------------
# update_event
# ---------------------------------------------------------------------------


class TestUpdateEvent:
    async def test_update_campos_basicos(self):
        user = _make_user()
        event = _make_event()
        payload = EventUpdate(title="Nuevo título", location="Nuevo lugar")

        refreshed = _make_event(location="Nuevo lugar")
        db = _make_db()

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            result = await events_svc.update_event(db, event, payload, user)

        assert event.title == "Nuevo título"
        assert event.location == "Nuevo lugar"
        db.commit.assert_awaited()

    async def test_update_propaga_al_training_session(self):
        user = _make_user()
        event = _make_event(
            event_type=EventType.TRAINING_SESSION,
            event_data={"training_session_id": 5},
        )
        payload = EventUpdate(location="Nuevo lugar", title="Nueva sesión")
        refreshed = _make_event(event_type=EventType.TRAINING_SESSION)

        db = _make_db()
        propagate_calls = []

        async def mock_propagate(db, event, update_data):
            propagate_calls.append(update_data)

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            with patch.object(
                events_svc, "_propagate_to_training_session", mock_propagate
            ):
                await events_svc.update_event(db, event, payload, user)

        assert propagate_calls, "Debió llamarse _propagate_to_training_session"

    async def test_update_despacha_notificacion_si_cambia_horario(self):
        user = _make_user()
        event = _make_event()
        new_start = datetime(2030, 7, 1, 10, 0, tzinfo=timezone.utc)
        new_end = datetime(2030, 7, 1, 11, 30, tzinfo=timezone.utc)
        payload = EventUpdate(start_at=new_start, end_at=new_end)
        refreshed = _make_event(start_at=new_start, end_at=new_end)

        db = _make_db()
        notify_calls = []

        async def mock_notify(db, event, old_values, ns, dispatcher):
            notify_calls.append(True)

        notification_service = MagicMock()
        dispatcher = MagicMock()

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            with patch(
                "app.services.calendar.notifications.notify_event_rescheduled",
                mock_notify,
            ):
                await events_svc.update_event(
                    db, event, payload, user,
                    notification_service=notification_service,
                    dispatcher=dispatcher,
                )

        assert notify_calls, "Debió despacharse notificación de reagendado"


# ---------------------------------------------------------------------------
# cancel_event
# ---------------------------------------------------------------------------


class TestCancelEvent:
    async def test_cancel_cambia_status(self):
        user = _make_user()
        event = _make_event(status=EventStatus.SCHEDULED)
        refreshed = _make_event(status=EventStatus.CANCELLED)

        db = _make_db()
        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            result = await events_svc.cancel_event(db, event, "Lluvia", user)

        assert event.status == EventStatus.CANCELLED
        db.commit.assert_awaited()

    async def test_cancel_ya_cancelado_lanza_error(self):
        user = _make_user()
        event = _make_event(status=EventStatus.CANCELLED)
        db = _make_db()

        with pytest.raises(ValueError, match="ya está cancelado"):
            await events_svc.cancel_event(db, event, "", user)

    async def test_cancel_propaga_a_training_session(self):
        user = _make_user()
        event = _make_event(
            event_type=EventType.TRAINING_SESSION,
            status=EventStatus.SCHEDULED,
            event_data={"training_session_id": 3},
        )
        refreshed = _make_event(
            event_type=EventType.TRAINING_SESSION,
            status=EventStatus.CANCELLED,
        )

        db = _make_db()
        execute_calls = []

        async def mock_execute(stmt):
            execute_calls.append(stmt)
            return MagicMock()

        db.execute = mock_execute

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            await events_svc.cancel_event(db, event, "Cancelado", user)

        # Verificar que se ejecutó alguna update en training_sessions
        assert len(execute_calls) > 0, "Debió ejecutarse UPDATE en training_sessions"

    async def test_cancel_despacha_notificacion(self):
        user = _make_user()
        event = _make_event(status=EventStatus.SCHEDULED)
        refreshed = _make_event(status=EventStatus.CANCELLED)

        db = _make_db()
        notify_calls = []

        async def mock_notify(db, event, reason, ns, dispatcher):
            notify_calls.append(reason)

        notification_service = MagicMock()
        dispatcher = MagicMock()

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            with patch(
                "app.services.calendar.notifications.notify_event_cancelled",
                mock_notify,
            ):
                await events_svc.cancel_event(
                    db, event, "Lluvia intensa", user,
                    notification_service=notification_service,
                    dispatcher=dispatcher,
                )

        assert "Lluvia intensa" in notify_calls


# ---------------------------------------------------------------------------
# reschedule_event
# ---------------------------------------------------------------------------


class TestRescheduleEvent:
    async def test_reschedule_llama_update_event(self):
        user = _make_user()
        event = _make_event()
        new_start = datetime(2030, 7, 15, 9, 0, tzinfo=timezone.utc)
        new_end = datetime(2030, 7, 15, 10, 30, tzinfo=timezone.utc)
        refreshed = _make_event(start_at=new_start, end_at=new_end)

        db = _make_db()

        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            result = await events_svc.reschedule_event(
                db, event, new_start, new_end, user
            )

        assert result is refreshed


# ---------------------------------------------------------------------------
# mark_completed
# ---------------------------------------------------------------------------


class TestMarkCompleted:
    async def test_marca_como_completado(self):
        event = _make_event(status=EventStatus.SCHEDULED)
        refreshed = _make_event(status=EventStatus.COMPLETED)

        db = _make_db()
        with patch.object(events_svc, "get_event", AsyncMock(return_value=refreshed)):
            result = await events_svc.mark_completed(db, event)

        assert event.status == EventStatus.COMPLETED
        db.commit.assert_awaited()

    async def test_cancelado_no_se_puede_completar(self):
        event = _make_event(status=EventStatus.CANCELLED)
        db = _make_db()

        with pytest.raises(ValueError, match="cancelado"):
            await events_svc.mark_completed(db, event)
