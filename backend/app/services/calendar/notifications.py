"""Notificaciones de eventos de calendario.

Despacha emails a padres/acudientes cuando un evento es creado, reagendado
o cancelado. Reutiliza el patrón de throttle de services/training/sessions.py.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calendar_event import EventType

if TYPE_CHECKING:
    from app.models.calendar_event import CalendarEvent
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttle en memoria (mismo patrón que services/training/sessions.py)
# ---------------------------------------------------------------------------

_THROTTLE_TTL = timedelta(minutes=60)
_recent_dispatches: dict[tuple, datetime] = {}


def _should_throttle(parent_id: int, athlete_id: int, event_id: int, kind: str) -> bool:
    """Retorna True si ya se despachó el mismo (parent, athlete, event, kind) en <60 min."""
    now = datetime.now(timezone.utc)
    expired = [k for k, ts in _recent_dispatches.items() if now - ts > _THROTTLE_TTL]
    for k in expired:
        del _recent_dispatches[k]

    key = (parent_id, athlete_id, event_id, kind)
    if key in _recent_dispatches:
        return True
    _recent_dispatches[key] = now
    return False


def _hash_id(value: int) -> str:
    """Hash corto de un ID para logs sin exponer el valor real."""
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


def _format_event_type_label(event_type: EventType) -> str:
    """Etiqueta en español para cada tipo de evento."""
    labels = {
        EventType.TRAINING_SESSION: "Entrenamiento",
        EventType.COMPETITION: "Competencia",
        EventType.CLUB_EVENT: "Evento del club",
        EventType.PERSONAL_TRAINING: "Entrenamiento personal",
        EventType.GROUP_TRAINING: "Entrenamiento grupal",
        EventType.REST_DAY: "Día de descanso",
    }
    return labels.get(event_type, "Evento")


def _format_date(dt: datetime) -> str:
    """Formatea datetime como fecha legible en español."""
    try:
        return dt.strftime("%-d de %B de %Y")
    except ValueError:
        return dt.strftime("%d de %B de %Y")


def _format_time(dt: datetime) -> str:
    """Formatea datetime como hora HH:MM."""
    return dt.strftime("%H:%M")


async def _resolve_parents_for_event(
    db: AsyncSession,
    event: "CalendarEvent",
) -> list[tuple]:
    """Resuelve pares (parent_user, athlete) para todos los atletas del evento.

    Retorna lista de tuplas (ParentAthlete, Athlete, User).
    """
    from app.models.athlete import Athlete, ParentAthlete
    from app.models.user import User
    from app.services.calendar.audiences import resolve_athletes

    athletes = await resolve_athletes(db, event)
    if not athletes:
        return []

    athlete_ids = [a.id for a in athletes]

    stmt = (
        select(ParentAthlete, Athlete)
        .join(Athlete, Athlete.id == ParentAthlete.athlete_id)
        .where(ParentAthlete.athlete_id.in_(athlete_ids))
        .options(selectinload(ParentAthlete.parent))
    )
    rows = await db.execute(stmt)
    return list(rows.all())


async def notify_event_invite(
    db: AsyncSession,
    event: "CalendarEvent",
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Notifica a padres que sus atletas han sido convocados a un evento.

    No dispara para TRAINING_SESSION (usa TRAINING_SESSION_INVITE).
    """
    if event.event_type == EventType.TRAINING_SESSION:
        return

    from app.models.club import Club
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    club_result = await db.execute(select(Club).where(Club.id == event.club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    event_type_label = _format_event_type_label(event.event_type)
    event_date = _format_date(event.start_at)
    event_time = _format_time(event.start_at)
    kind = "calendar_event_invite"

    pairs = await _resolve_parents_for_event(db, event)

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        if _should_throttle(parent.id, athlete.id, event.id, kind):
            logger.debug(
                "Throttle activo — omitiendo invitación | parent_hash=%s athlete_hash=%s event_id=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                event.id,
            )
            continue

        parent_name = (
            f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"
        )
        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()

        try:
            request = NotificationRequest(
                recipient=NotificationRecipient(email=parent.email, name=parent_name),
                template=NotificationTemplate.CALENDAR_EVENT_INVITE,
                context={
                    "parent_name": parent_name,
                    "athlete_name": athlete_name,
                    "event_title": event.title,
                    "event_type_label": event_type_label,
                    "event_date": event_date,
                    "event_time": event_time,
                    "location": event.location or "Por definir",
                    "club_name": club_name,
                },
                send_async=True,
            )
            await notification_service.send(request, dispatcher=dispatcher)
            logger.info(
                "Invitación de evento despachada | parent_hash=%s athlete_hash=%s event_id=%s kind=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                event.id,
                kind,
            )
        except Exception as exc:
            logger.warning(
                "Error despachando invitación de evento | parent_hash=%s athlete_hash=%s kind=%s error=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                kind,
                type(exc).__name__,
            )


async def notify_event_rescheduled(
    db: AsyncSession,
    event: "CalendarEvent",
    old_values: dict,
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Notifica a padres que un evento fue reagendado."""
    from app.models.club import Club
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    club_result = await db.execute(select(Club).where(Club.id == event.club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    kind = "calendar_event_rescheduled"
    new_date = _format_date(event.start_at)
    new_time = _format_time(event.start_at)

    old_start = old_values.get("start_at", event.start_at)
    old_date = _format_date(old_start) if isinstance(old_start, datetime) else str(old_start)
    old_time = _format_time(old_start) if isinstance(old_start, datetime) else ""
    new_location = event.location or "Por definir"

    pairs = await _resolve_parents_for_event(db, event)

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        if _should_throttle(parent.id, athlete.id, event.id, kind):
            continue

        parent_name = (
            f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"
        )
        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()

        try:
            request = NotificationRequest(
                recipient=NotificationRecipient(email=parent.email, name=parent_name),
                template=NotificationTemplate.CALENDAR_EVENT_RESCHEDULED,
                context={
                    "parent_name": parent_name,
                    "athlete_name": athlete_name,
                    "event_title": event.title,
                    "old_date": old_date,
                    "old_time": old_time,
                    "new_date": new_date,
                    "new_time": new_time,
                    "new_location": new_location,
                    "club_name": club_name,
                },
                send_async=True,
            )
            await notification_service.send(request, dispatcher=dispatcher)
            logger.info(
                "Reagendado de evento notificado | parent_hash=%s athlete_hash=%s event_id=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                event.id,
            )
        except Exception as exc:
            logger.warning(
                "Error notificando reagendado | parent_hash=%s kind=%s error=%s",
                _hash_id(parent.id),
                kind,
                type(exc).__name__,
            )


async def notify_event_cancelled(
    db: AsyncSession,
    event: "CalendarEvent",
    reason: str,
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Notifica a padres que un evento fue cancelado."""
    from app.models.club import Club
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    club_result = await db.execute(select(Club).where(Club.id == event.club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    kind = "calendar_event_cancelled"
    original_date = _format_date(event.start_at)

    pairs = await _resolve_parents_for_event(db, event)

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        if _should_throttle(parent.id, athlete.id, event.id, kind):
            continue

        parent_name = (
            f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"
        )
        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()

        try:
            request = NotificationRequest(
                recipient=NotificationRecipient(email=parent.email, name=parent_name),
                template=NotificationTemplate.CALENDAR_EVENT_CANCELLED,
                context={
                    "parent_name": parent_name,
                    "athlete_name": athlete_name,
                    "event_title": event.title,
                    "original_date": original_date,
                    "reason": reason or "Sin motivo especificado",
                    "club_name": club_name,
                },
                send_async=True,
            )
            await notification_service.send(request, dispatcher=dispatcher)
            logger.info(
                "Cancelación de evento notificada | parent_hash=%s athlete_hash=%s event_id=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                event.id,
            )
        except Exception as exc:
            logger.warning(
                "Error notificando cancelación | parent_hash=%s kind=%s error=%s",
                _hash_id(parent.id),
                kind,
                type(exc).__name__,
            )
