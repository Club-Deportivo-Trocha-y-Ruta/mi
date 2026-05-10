"""Lógica de negocio para eventos de calendario.

Maneja CRUD, integración con TrainingSession, notificaciones y filtros de vista.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calendar_event import (
    CalendarEvent,
    EventStatus,
    EventType,
)
from app.services.calendar import notifications as _notif_module

if TYPE_CHECKING:
    from app.models.user import User
    from app.schemas.calendar import AudienceCreate, EventCreate, EventListQuery, EventUpdate
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _eager_options():
    """Opciones de eager loading estándar para CalendarEvent."""
    from app.models.calendar_event import EventAttendance, EventAudience
    return [
        selectinload(CalendarEvent.audiences),
        selectinload(CalendarEvent.attendances).selectinload(EventAttendance.athlete),
    ]


async def get_event(
    db: AsyncSession,
    event_id: int,
    eager: bool = True,
) -> CalendarEvent | None:
    """Retorna un evento por ID, con eager loading de audiences y attendances."""
    stmt = select(CalendarEvent).where(CalendarEvent.id == event_id)
    if eager:
        for opt in _eager_options():
            stmt = stmt.options(opt)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_event_or_raise(db: AsyncSession, event_id: int) -> CalendarEvent:
    event = await get_event(db, event_id)
    if event is None:
        raise ValueError(f"Evento {event_id} no encontrado")
    return event


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


async def create_event(
    db: AsyncSession,
    payload: "EventCreate",
    user: "User",
    club_id: int,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent:
    """Crea un CalendarEvent + audiences en una transacción.

    Si event_type == TRAINING_SESSION y training_session_id no viene en
    event_data, crea también el TrainingSession paralelo y lo enlaza.
    """
    from app.services.calendar.audiences import set_audiences

    # Construir event_data asegurando coherencia
    raw_event_data = payload.event_data or {}

    event = CalendarEvent(
        club_id=club_id,
        event_type=payload.event_type,
        status=payload.status,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        start_at=payload.start_at,
        end_at=payload.end_at,
        all_day=payload.all_day,
        timezone=payload.timezone,
        event_data=raw_event_data,
        color_hex=payload.color_hex,
        created_by_user_id=user.id,
    )
    db.add(event)
    await db.flush()  # obtener event.id

    # Crear audiencias
    await set_audiences(db, event, payload.audiences)
    await db.flush()

    # Integración con TrainingSession
    if payload.event_type == EventType.TRAINING_SESSION:
        await _handle_training_session_creation(
            db=db,
            event=event,
            payload=payload,
            user=user,
            club_id=club_id,
        )

    await db.commit()

    # Recargar con eager loading
    refreshed = await get_event(db, event.id)
    assert refreshed is not None

    # Notificar (no para TRAINING_SESSION — usa TRAINING_SESSION_INVITE)
    is_future = refreshed.start_at > datetime.now(timezone.utc)
    if (
        notification_service is not None
        and dispatcher is not None
        and is_future
        and refreshed.event_type != EventType.TRAINING_SESSION
    ):
        try:
            await _notif_module.notify_event_invite(db, refreshed, notification_service, dispatcher)
        except Exception as exc:
            logger.warning(
                "Error enviando notificaciones de evento nuevo event_id=%s error=%s",
                refreshed.id,
                type(exc).__name__,
            )

    return refreshed


async def _handle_training_session_creation(
    db: AsyncSession,
    event: CalendarEvent,
    payload: "EventCreate",
    user: "User",
    club_id: int,
) -> None:
    """Crea o enlaza TrainingSession para un event_type=TRAINING_SESSION."""
    from app.models.training_session import (
        AttendanceStatus,
        SessionAttendance,
        SessionStatus,
        TrainingSession,
    )
    from app.services.calendar.audiences import resolve_athletes

    raw_event_data = payload.event_data or {}
    existing_ts_id = raw_event_data.get("training_session_id")

    if existing_ts_id is not None:
        # Caso: TrainingSession ya existe — solo enlazar
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(TrainingSession)
            .where(TrainingSession.id == existing_ts_id)
            .values(calendar_event_id=event.id)
        )
        # Actualizar event_data con el ts_id
        event.event_data = {"training_session_id": existing_ts_id}
        return

    # Calcular duración en minutos
    delta_seconds = int((payload.end_at - payload.start_at).total_seconds())
    duration_min = max(15, min(240, delta_seconds // 60))

    ts = TrainingSession(
        club_id=club_id,
        created_by_user_id=user.id,
        status=SessionStatus.PLANNED,
        scheduled_date=payload.start_at.date(),
        scheduled_start_time=payload.start_at.time(),
        duration_min=duration_min,
        location=payload.location or "Por definir",
        technical_focus=payload.title,
        description=payload.description,
        calendar_event_id=event.id,
    )
    db.add(ts)
    await db.flush()

    # Actualizar event_data con el ts_id recién creado
    event.event_data = {"training_session_id": ts.id}

    # Crear placeholders de asistencia para los atletas de la audiencia
    athletes = await resolve_athletes(db, event)
    for athlete in athletes:
        db.add(
            SessionAttendance(
                session_id=ts.id,
                athlete_id=athlete.id,
                status=AttendanceStatus.AUSENTE,
            )
        )


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


async def list_events_in_range(
    db: AsyncSession,
    club_id: int,
    from_date: date,
    to_date: date,
    filters: "EventListQuery",
    viewer: "User",
) -> list[CalendarEvent]:
    """Lista eventos del club en un rango de fechas con filtros y RBAC.

    - coach/admin: todos los eventos del club.
    - parent: solo eventos donde alguno de sus atletas está en audiencia.
    """
    from datetime import datetime as dt

    from app.models.calendar_event import EventAudience
    from app.models.user import UserRole

    from_dt = dt.combine(from_date, dt.min.time())
    to_dt = dt.combine(to_date, dt.max.time())

    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.club_id == club_id,
            CalendarEvent.start_at <= to_dt,
            CalendarEvent.end_at >= from_dt,
        )
    )

    # Excluir cancelados salvo que se pida explícitamente
    if not filters.include_cancelled if hasattr(filters, "include_cancelled") else True:
        stmt = stmt.where(CalendarEvent.status != EventStatus.CANCELLED)

    # Filtrar por tipos de evento
    if filters.event_types:
        stmt = stmt.where(CalendarEvent.event_type.in_(filters.event_types))

    # Eager load
    stmt = stmt.options(*_eager_options()).order_by(CalendarEvent.start_at.asc())

    result = await db.execute(stmt)
    events = list(result.scalars().all())

    # Filtrar por audiencia si es padre o si hay filtro de atleta
    if viewer.role == UserRole.parent or filters.mine_only:
        from app.services.calendar.audiences import any_athlete_in_audience
        from app.services.permissions import parent_athlete_ids

        athlete_ids: list[int] = []
        if viewer.role == UserRole.parent:
            athlete_ids = await parent_athlete_ids(db, viewer.id)
        elif filters.athlete_id:
            athlete_ids = [filters.athlete_id]

        if not athlete_ids:
            return []

        filtered: list[CalendarEvent] = []
        for ev in events:
            if await any_athlete_in_audience(db, ev, athlete_ids):
                filtered.append(ev)
        return filtered

    # Filtro de atleta para coach/admin
    if filters.athlete_id:
        from app.services.calendar.audiences import event_visible_to_athlete
        filtered = []
        for ev in events:
            if await event_visible_to_athlete(db, ev, filters.athlete_id):
                filtered.append(ev)
        return filtered

    return events


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


async def update_event(
    db: AsyncSession,
    event: CalendarEvent,
    payload: "EventUpdate",
    user: "User",
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent:
    """Actualiza un CalendarEvent y propaga cambios al TrainingSession enlazado."""
    # Capturar valores anteriores para detectar cambios de horario/lugar
    old_values: dict = {
        "start_at": event.start_at,
        "end_at": event.end_at,
        "location": event.location,
    }

    update_data = payload.model_dump(exclude_unset=True)
    schedule_changed = any(k in update_data for k in ("start_at", "end_at", "location"))

    for field, value in update_data.items():
        setattr(event, field, value)

    # Propagar al TrainingSession enlazado
    if event.event_type == EventType.TRAINING_SESSION:
        await _propagate_to_training_session(db, event, update_data)

    await db.commit()
    refreshed = await get_event(db, event.id)
    assert refreshed is not None

    # Notificar reagendado
    if (
        schedule_changed
        and notification_service is not None
        and dispatcher is not None
    ):
        try:
            await _notif_module.notify_event_rescheduled(
                db, refreshed, old_values, notification_service, dispatcher
            )
        except Exception as exc:
            logger.warning(
                "Error notificando reagendado event_id=%s error=%s",
                refreshed.id,
                type(exc).__name__,
            )

    return refreshed


async def _propagate_to_training_session(
    db: AsyncSession,
    event: CalendarEvent,
    update_data: dict,
) -> None:
    """Propaga cambios de CalendarEvent al TrainingSession enlazado."""
    from app.models.training_session import TrainingSession
    from sqlalchemy import update as sa_update

    ts_id = (event.event_data or {}).get("training_session_id")
    if not ts_id:
        return

    ts_updates: dict = {}
    if "location" in update_data:
        ts_updates["location"] = update_data["location"] or "Por definir"
    if "title" in update_data:
        ts_updates["technical_focus"] = update_data["title"]
    if "description" in update_data:
        ts_updates["description"] = update_data["description"]
    if "start_at" in update_data:
        new_start = update_data["start_at"]
        ts_updates["scheduled_date"] = new_start.date()
        ts_updates["scheduled_start_time"] = new_start.time()
    if "start_at" in update_data or "end_at" in update_data:
        start = update_data.get("start_at", event.start_at)
        end = update_data.get("end_at", event.end_at)
        delta_seconds = int((end - start).total_seconds())
        ts_updates["duration_min"] = max(15, min(240, delta_seconds // 60))

    if ts_updates:
        await db.execute(
            sa_update(TrainingSession)
            .where(TrainingSession.id == ts_id)
            .values(**ts_updates)
        )


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------


async def cancel_event(
    db: AsyncSession,
    event: CalendarEvent,
    reason: str,
    user: "User",
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent:
    """Soft-cancel de un evento. Propaga a TrainingSession si aplica."""
    if event.status == EventStatus.CANCELLED:
        raise ValueError("El evento ya está cancelado")

    event.status = EventStatus.CANCELLED

    # Propagar a TrainingSession
    if event.event_type == EventType.TRAINING_SESSION:
        ts_id = (event.event_data or {}).get("training_session_id")
        if ts_id:
            from app.models.training_session import SessionStatus, TrainingSession
            from sqlalchemy import update as sa_update
            await db.execute(
                sa_update(TrainingSession)
                .where(TrainingSession.id == ts_id)
                .values(status=SessionStatus.CANCELLED)
            )

    await db.commit()
    refreshed = await get_event(db, event.id)
    assert refreshed is not None

    if notification_service is not None and dispatcher is not None:
        try:
            await _notif_module.notify_event_cancelled(
                db, refreshed, reason, notification_service, dispatcher
            )
        except Exception as exc:
            logger.warning(
                "Error notificando cancelación event_id=%s error=%s",
                refreshed.id,
                type(exc).__name__,
            )

    return refreshed


# ---------------------------------------------------------------------------
# RESCHEDULE
# ---------------------------------------------------------------------------


async def reschedule_event(
    db: AsyncSession,
    event: CalendarEvent,
    new_start: datetime,
    new_end: datetime,
    user: "User",
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent:
    """Atajo de update_event que garantiza dispatch de notificación."""
    from app.schemas.calendar import EventUpdate

    payload = EventUpdate(start_at=new_start, end_at=new_end)
    return await update_event(
        db=db,
        event=event,
        payload=payload,
        user=user,
        notification_service=notification_service,
        dispatcher=dispatcher,
    )


# ---------------------------------------------------------------------------
# MARK COMPLETED
# ---------------------------------------------------------------------------


async def mark_completed(
    db: AsyncSession,
    event: CalendarEvent,
) -> CalendarEvent:
    """Marca un evento como COMPLETED (llámalo cuando end_at sea pasado)."""
    if event.status == EventStatus.CANCELLED:
        raise ValueError("No se puede completar un evento cancelado")

    event.status = EventStatus.COMPLETED
    await db.commit()
    refreshed = await get_event(db, event.id)
    assert refreshed is not None
    return refreshed
