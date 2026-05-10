"""Tests del servicio de notificaciones de calendario.

Cubre: templates correctos, contexto correcto, throttle (segunda invocación
en <60 min no envía), sin PII en logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.calendar_event import AudienceType, EventType
from app.schemas.notification import NotificationTemplate
from app.services.calendar import notifications as notif_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2030, 6, 15, 17, 0, tzinfo=timezone.utc)
_END = datetime(2030, 6, 15, 18, 30, tzinfo=timezone.utc)


def _make_event(
    event_id: int = 1,
    event_type: EventType = EventType.CLUB_EVENT,
    club_id: int = 1,
    location: str = "Pista Comfacauca",
):
    ev = MagicMock()
    ev.id = event_id
    ev.event_type = event_type
    ev.club_id = club_id
    ev.title = "Evento de prueba"
    ev.location = location
    ev.start_at = _NOW
    ev.end_at = _END
    ev.audiences = []
    return ev


def _make_parent(parent_id: int = 1, email: str = "padre@test.com"):
    p = MagicMock()
    p.id = parent_id
    p.email = email
    p.first_name = "Carlos"
    p.last_name = "García"
    return p


def _make_athlete(athlete_id: int = 10):
    a = MagicMock()
    a.id = athlete_id
    a.first_name = "Juan"
    a.last_name = "García"
    return a


def _make_pa_pair(parent, athlete):
    """Simula la tupla (ParentAthlete, Athlete) que retorna la query."""
    pa = MagicMock()
    pa.parent = parent
    return (pa, athlete)


def _make_notification_service():
    ns = MagicMock()
    ns.send = AsyncMock()
    return ns


def _make_club_result(name: str = "Club Trocha y Ruta"):
    club = MagicMock()
    club.name = name
    result = MagicMock()
    result.scalar_one_or_none.return_value = club
    return result


# ---------------------------------------------------------------------------
# Fixture: reset throttle entre tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_throttle():
    """Limpia el dict de throttle antes de cada test para independencia."""
    notif_svc._recent_dispatches.clear()
    yield
    notif_svc._recent_dispatches.clear()


# ---------------------------------------------------------------------------
# _format_event_type_label
# ---------------------------------------------------------------------------


class TestFormatEventTypeLabel:
    def test_training_session_label(self):
        label = notif_svc._format_event_type_label(EventType.TRAINING_SESSION)
        assert label == "Entrenamiento"

    def test_competition_label(self):
        label = notif_svc._format_event_type_label(EventType.COMPETITION)
        assert label == "Competencia"

    def test_club_event_label(self):
        label = notif_svc._format_event_type_label(EventType.CLUB_EVENT)
        assert label == "Evento del club"

    def test_personal_training_label(self):
        label = notif_svc._format_event_type_label(EventType.PERSONAL_TRAINING)
        assert label == "Entrenamiento personal"

    def test_group_training_label(self):
        label = notif_svc._format_event_type_label(EventType.GROUP_TRAINING)
        assert label == "Entrenamiento grupal"

    def test_rest_day_label(self):
        label = notif_svc._format_event_type_label(EventType.REST_DAY)
        assert label == "Día de descanso"


# ---------------------------------------------------------------------------
# notify_event_invite
# ---------------------------------------------------------------------------


class TestNotifyEventInvite:
    async def test_no_despacha_para_training_session(self):
        event = _make_event(event_type=EventType.TRAINING_SESSION)
        ns = _make_notification_service()
        db = AsyncMock()

        await notif_svc.notify_event_invite(db, event, ns, None)

        ns.send.assert_not_awaited()

    async def test_despacha_template_correcto(self):
        event = _make_event(event_type=EventType.CLUB_EVENT)
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_invite(db, event, ns, None)

        ns.send.assert_awaited_once()
        call_args = ns.send.await_args
        request = call_args[0][0]
        assert request.template == NotificationTemplate.CALENDAR_EVENT_INVITE

    async def test_contexto_correcto(self):
        event = _make_event(event_type=EventType.CLUB_EVENT, location="Pista Centro")
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result("Club Test"))

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_invite(db, event, ns, None)

        request = ns.send.await_args[0][0]
        ctx = request.context
        assert "parent_name" in ctx
        assert "athlete_name" in ctx
        assert "event_title" in ctx
        assert "event_type_label" in ctx
        assert "event_date" in ctx
        assert "event_time" in ctx
        assert "location" in ctx
        assert "club_name" in ctx
        # Verificar que no hay PII sensible (DOB no debe estar)
        assert "birth_date" not in ctx
        assert "fecha_nacimiento" not in ctx

    async def test_throttle_segunda_invocacion_no_envia(self):
        event = _make_event(event_type=EventType.CLUB_EVENT)
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            # Primera invocación — debe enviar
            await notif_svc.notify_event_invite(db, event, ns, None)
            # Segunda invocación — NO debe enviar (throttle 60 min)
            await notif_svc.notify_event_invite(db, event, ns, None)

        assert ns.send.await_count == 1, "Solo debe enviarse una vez en 60 min"

    async def test_no_envia_si_padre_sin_email(self):
        event = _make_event(event_type=EventType.CLUB_EVENT)
        parent = _make_parent(email="")  # email vacío
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_invite(db, event, ns, None)

        ns.send.assert_not_awaited()


# ---------------------------------------------------------------------------
# notify_event_rescheduled
# ---------------------------------------------------------------------------


class TestNotifyEventRescheduled:
    async def test_despacha_template_rescheduled(self):
        event = _make_event()
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()
        old_values = {"start_at": _NOW}

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_rescheduled(
                db, event, old_values, ns, None
            )

        ns.send.assert_awaited_once()
        request = ns.send.await_args[0][0]
        assert request.template == NotificationTemplate.CALENDAR_EVENT_RESCHEDULED

    async def test_contexto_incluye_fechas_viejas_y_nuevas(self):
        new_start = datetime(2030, 7, 1, 10, 0, tzinfo=timezone.utc)
        event = _make_event()
        event.start_at = new_start
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()
        old_values = {"start_at": _NOW}

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_rescheduled(
                db, event, old_values, ns, None
            )

        request = ns.send.await_args[0][0]
        ctx = request.context
        required_keys = {
            "parent_name", "athlete_name", "event_title",
            "old_date", "old_time", "new_date", "new_time",
            "new_location", "club_name",
        }
        assert required_keys.issubset(ctx.keys())

    async def test_throttle_rescheduled(self):
        event = _make_event()
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()
        old_values = {"start_at": _NOW}

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_rescheduled(db, event, old_values, ns, None)
            await notif_svc.notify_event_rescheduled(db, event, old_values, ns, None)

        assert ns.send.await_count == 1


# ---------------------------------------------------------------------------
# notify_event_cancelled
# ---------------------------------------------------------------------------


class TestNotifyEventCancelled:
    async def test_despacha_template_cancelled(self):
        event = _make_event()
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_cancelled(db, event, "Lluvia", ns, None)

        ns.send.assert_awaited_once()
        request = ns.send.await_args[0][0]
        assert request.template == NotificationTemplate.CALENDAR_EVENT_CANCELLED

    async def test_contexto_incluye_motivo(self):
        event = _make_event()
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_cancelled(
                db, event, "Fuerza mayor", ns, None
            )

        request = ns.send.await_args[0][0]
        ctx = request.context
        required_keys = {
            "parent_name", "athlete_name", "event_title",
            "original_date", "reason", "club_name",
        }
        assert required_keys.issubset(ctx.keys())
        assert ctx["reason"] == "Fuerza mayor"

    async def test_no_hay_pii_en_contexto(self):
        """El contexto no debe contener datos personales de menores."""
        event = _make_event()
        parent = _make_parent()
        athlete = _make_athlete()
        ns = _make_notification_service()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_club_result())

        with patch.object(
            notif_svc,
            "_resolve_parents_for_event",
            AsyncMock(return_value=[_make_pa_pair(parent, athlete)]),
        ):
            await notif_svc.notify_event_cancelled(db, event, "Cancelado", ns, None)

        request = ns.send.await_args[0][0]
        ctx = request.context
        # Verificar ausencia de PII de menores
        for key in ("birth_date", "dob", "fecha_nacimiento", "phone", "address"):
            assert key not in ctx, f"PII sensible '{key}' encontrado en contexto"
