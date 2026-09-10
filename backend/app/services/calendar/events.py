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
from app.services.audit import (
    AUDIT_REASON_LABELS,
    AuditAction,
    AuditEntityType,
    CancelReasonCode,
    record_audit,
)
from app.services.calendar import notifications as _notif_module

if TYPE_CHECKING:
    from app.models.training_session import TrainingSession
    from app.models.user import User
    from app.schemas.calendar import AudienceCreate, EventCreate, EventListQuery, EventUpdate
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher
    from app.services.request_context import AuditContext

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
):
    """Retorna un evento por ID, con eager loading de audiences y attendances.

    Si `event_id` es negativo, intenta reconstruir un cumpleaños virtual
    desde `athlete.birth_date` (ver `services/calendar/birthdays.py`).

    T063 (contracts/session-coaches.md §7.3): un evento con `deleted_at`
    no ``NULL`` es un borrado permanente (soft-delete) y no debe ser
    visible por ningún lector — se filtra igual que un 404.
    """
    if event_id < 0:
        from app.services.calendar.birthdays import (
            decode_birthday_id,
            get_birthday_event,
        )
        if decode_birthday_id(event_id) is not None:
            return await get_birthday_event(db, event_id)
        return None

    stmt = select(CalendarEvent).where(
        CalendarEvent.id == event_id,
        CalendarEvent.deleted_at.is_(None),
    )
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


async def _ensure_race_event_exists(db: AsyncSession, race_event_id: int) -> None:
    """Verifica que ``race_events.id=race_event_id`` exista; raise ValueError si no.

    Mensaje en español para que el router lo convierta a HTTP 400 limpio.
    """
    from app.models.race_event import RaceEvent

    result = await db.execute(
        select(RaceEvent.id).where(RaceEvent.id == race_event_id)
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(
            f"race_event_id={race_event_id} no existe en race_events"
        )


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

    # BE-2: si trae race_event_id (obligatorio para competition por
    # validator), verificar que la fila exista. El CHECK DB ya impide
    # NULL+competition, pero validar acá da un 400 limpio en español.
    if payload.race_event_id is not None:
        await _ensure_race_event_exists(db, payload.race_event_id)

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
        race_event_id=payload.race_event_id,
        created_by_user_id=user.id,
    )
    db.add(event)
    await db.flush()  # obtener event.id

    # Crear audiencias
    await set_audiences(db, event, payload.audiences)
    await db.flush()

    # Integración con TrainingSession
    created_ts = None
    if payload.event_type == EventType.TRAINING_SESSION:
        created_ts = await _handle_training_session_creation(
            db=db,
            event=event,
            payload=payload,
            user=user,
            club_id=club_id,
        )

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.calendar_event,
        entity_id=event.id,
        actor=user,
        club_id=club_id,
    )
    if created_ts is not None:
        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.training_session,
            entity_id=created_ts.id,
            actor=user,
            club_id=club_id,
        )

    await db.commit()

    # Recargar con eager loading
    refreshed = await get_event(db, event.id)
    assert refreshed is not None

    # Notificar (no para TRAINING_SESSION — usa TRAINING_SESSION_INVITE)
    is_future = refreshed.start_at.replace(tzinfo=None) > datetime.now(timezone.utc).replace(tzinfo=None)
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
) -> "TrainingSession | None":
    """Crea o enlaza TrainingSession para un event_type=TRAINING_SESSION.

    Devuelve la ``TrainingSession`` recién creada, o ``None`` si el evento
    solo se enlazó a una sesión ya existente (esa fila ya tiene su propia
    fila ``training_session``·``create`` de auditoría).
    """
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
        return None

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

    return ts


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
    - `filters.coach_user_id` (T064, §8.2): solo eventos cuyo creador es ese
      coach, o cuyo TrainingSession enlazado lo tiene asignado en
      `training_session_coaches`.
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
            # T063 §7.3: un borrado permanente es un soft-delete — nunca
            # debe reaparecer en la lista del calendario.
            CalendarEvent.deleted_at.is_(None),
        )
    )

    # Excluir cancelados salvo que se pida explícitamente
    if not filters.include_cancelled if hasattr(filters, "include_cancelled") else True:
        stmt = stmt.where(CalendarEvent.status != EventStatus.CANCELLED)

    # Filtrar por tipos de evento
    if filters.event_types:
        stmt = stmt.where(CalendarEvent.event_type.in_(filters.event_types))

    # T064 §8.2: coincide por creador directo, o por el bridge N:M de
    # coaches de la sesión de entrenamiento enlazada (FR-026 — "session
    # coaches for sessions; creator for other events").
    if filters.coach_user_id is not None:
        from sqlalchemy import exists as sa_exists

        from app.models.training_session import TrainingSession, TrainingSessionCoach

        coach_id = filters.coach_user_id
        coach_bridge_exists = (
            sa_exists()
            .where(
                TrainingSession.calendar_event_id == CalendarEvent.id,
                TrainingSessionCoach.session_id == TrainingSession.id,
                TrainingSessionCoach.coach_user_id == coach_id,
            )
        )
        stmt = stmt.where(
            (CalendarEvent.created_by_user_id == coach_id) | coach_bridge_exists
        )

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
        events = filtered

    # Cumpleaños virtuales: todos los miembros del club ven todos los cumples.
    # Si el filtro de event_types se pasó y no incluye birthday, omitir.
    # T064 §8.2: también se excluyen siempre que haya `coach_user_id` — son
    # sintéticos (sin `created_by_user_id` ni sesión enlazada) y contarlos
    # ahí desalinearía el calendario general con la vista por coach (SC-008).
    include_birthdays = (
        filters.coach_user_id is None
        and (not filters.event_types or EventType.BIRTHDAY in filters.event_types)
    )
    if include_birthdays:
        from app.services.calendar.birthdays import list_birthday_events_in_range

        birthday_athlete_ids = [filters.athlete_id] if filters.athlete_id else None
        birthdays = await list_birthday_events_in_range(
            db=db,
            club_id=club_id,
            from_date=from_date,
            to_date=to_date,
            athlete_ids=birthday_athlete_ids,
        )
        # Mezclar y ordenar por start_at ascendente
        events = sorted([*events, *birthdays], key=lambda e: e.start_at)

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

    # Snapshot previo para el diff de auditoría (record_audit filtra por
    # VALUE_ALLOWLIST[calendar_event]; los campos no admitidos solo quedan
    # nombrados en changed_fields, sin valor).
    audit_diff: dict[str, tuple[object, object]] = {
        field: (getattr(event, field), update_data[field])
        for field in update_data
        if hasattr(event, field) and getattr(event, field) != update_data[field]
    }
    audit_changed_fields = list(update_data.keys())

    # BE-2: validar reasignación de race_event_id.
    if "race_event_id" in update_data:
        new_rid = update_data["race_event_id"]
        if event.event_type == EventType.COMPETITION and new_rid is None:
            raise ValueError(
                "No se puede desasociar race_event_id de un evento competition. "
                "Cambia el tipo del evento primero o borra el evento."
            )
        if event.event_type != EventType.COMPETITION and new_rid is not None:
            raise ValueError(
                "race_event_id solo aplica para event_type=competition."
            )
        if new_rid is not None:
            await _ensure_race_event_exists(db, new_rid)

    for field, value in update_data.items():
        setattr(event, field, value)

    # Propagar al TrainingSession enlazado
    if event.event_type == EventType.TRAINING_SESSION:
        await _propagate_to_training_session(db, event, update_data)

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.calendar_event,
        entity_id=event.id,
        actor=user,
        club_id=event.club_id,
        changed_fields=audit_changed_fields,
        diff=audit_diff,
    )

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
    reason_code: "CancelReasonCode",
    ctx: "AuditContext",
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> CalendarEvent:
    """Soft-cancel de un evento (T063, contracts/session-coaches.md §7.2).

    Persiste `status`, `cancelled_by_user_id`, `cancelled_at` y
    `cancellation_reason_code` en la misma unidad de trabajo que la fila de
    auditoría. Propaga la cancelación al `TrainingSession` enlazado cuando
    aplica, con su propia fila `training_session`·`cancel` bajo el mismo
    `request_id` (FR-002, US1 AS5) — así el revisor ve una sola operación.
    El actor se recibe siempre vía `ctx` (nunca re-derivado, §4 del
    contrato de auditoría).
    """
    if event.status == EventStatus.CANCELLED:
        raise ValueError("El evento ya está cancelado")

    now = datetime.now(timezone.utc)
    actor_id = ctx.actor.id if ctx.actor is not None else None

    previous_status = event.status
    event.status = EventStatus.CANCELLED
    event.cancelled_by_user_id = actor_id
    event.cancelled_at = now
    event.cancellation_reason_code = reason_code.value

    # Propagar a TrainingSession — misma transacción, mismo request_id.
    if event.event_type == EventType.TRAINING_SESSION:
        ts_id = (event.event_data or {}).get("training_session_id")
        if ts_id:
            from app.models.training_session import SessionStatus, TrainingSession

            ts = await db.get(TrainingSession, ts_id)
            if ts is not None:
                previous_ts_status = ts.status
                ts.status = SessionStatus.CANCELLED
                await record_audit(
                    db,
                    action=AuditAction.cancel,
                    entity_type=AuditEntityType.training_session,
                    entity_id=ts.id,
                    actor=ctx.actor,
                    actor_kind=ctx.actor_kind,
                    club_id=event.club_id,
                    changed_fields=["status"],
                    diff={
                        "status": (
                            previous_ts_status.value,
                            SessionStatus.CANCELLED.value,
                        )
                    },
                    reason_code=reason_code,
                    request_id=ctx.request_id,
                )

    await record_audit(
        db,
        action=AuditAction.cancel,
        entity_type=AuditEntityType.calendar_event,
        entity_id=event.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=event.club_id,
        changed_fields=[
            "status",
            "cancelled_at",
            "cancelled_by_user_id",
            "cancellation_reason_code",
        ],
        # Solo "status" y "cancellation_reason_code" están en VALUE_ALLOWLIST
        # para calendar_event (record_audit descarta el resto del diff).
        diff={
            "status": (previous_status.value, EventStatus.CANCELLED.value),
            "cancellation_reason_code": (None, reason_code.value),
        },
        reason_code=reason_code,
        request_id=ctx.request_id,
    )

    await db.commit()
    refreshed = await get_event(db, event.id)
    assert refreshed is not None

    if notification_service is not None and dispatcher is not None:
        try:
            # Las familias siempre leen la etiqueta en español, nunca el
            # código — se resuelve acá, al momento del despacho, y no se
            # persiste (contracts/session-coaches.md §7.2).
            reason_label = AUDIT_REASON_LABELS[reason_code]
            await _notif_module.notify_event_cancelled(
                db, refreshed, reason_label, notification_service, dispatcher
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
# SOFT DELETE (borrado permanente = borrado blando, T063 §7.3)
# ---------------------------------------------------------------------------


async def delete_event_permanent(
    db: AsyncSession,
    event: CalendarEvent,
    ctx: "AuditContext",
) -> None:
    """"Borrado permanente" de un CalendarEvent — en realidad un soft-delete
    (`deleted_at`/`deleted_by_user_id`), no un `DELETE` de fila
    (contracts/session-coaches.md §7.3): así `entity_id` en la fila de
    auditoría sigue resolviendo a una fila legible. `event_audiences` y
    `event_attendances` ya no se limpian por `ON DELETE CASCADE` — dejan de
    ser alcanzables simplemente porque todo lector filtra `deleted_at IS
    NULL` (`get_event`, `list_events_in_range`, `_get_event_or_404` del
    router).

    Sin `reason_code`: `("calendar_event", delete)` no está en
    `REASON_REQUIRED` — el diálogo de confirmación del frontend no cambia.
    """
    event_id = event.id
    club_id = event.club_id
    now = datetime.now(timezone.utc)
    actor_id = ctx.actor.id if ctx.actor is not None else None

    if event.event_type == EventType.TRAINING_SESSION:
        from app.models.training_session import TrainingSession

        ts_id = (event.event_data or {}).get("training_session_id")
        if ts_id:
            ts = await db.get(TrainingSession, ts_id)
            if ts is not None:
                # GAP fuera del alcance de este agente (T063 solo es dueño
                # de backend/app/services/calendar/*): `TrainingSession`
                # (`app/models/training_session.py`) todavía no tiene
                # columnas `deleted_at`/`deleted_by_user_id`, así que no se
                # le puede aplicar el mismo soft-delete que a CalendarEvent.
                # Defensivo: en cuanto ese modelo las incorpore (con su
                # migración), esta rama empieza a usarlas sin más cambios
                # acá; mientras tanto se conserva el hard-delete previo para
                # no dejar una sesión huérfana sin ningún rastro.
                ts_changed_fields: list[str] | None
                if hasattr(TrainingSession, "deleted_at"):
                    ts.deleted_at = now
                    if hasattr(TrainingSession, "deleted_by_user_id"):
                        ts.deleted_by_user_id = actor_id
                        ts_changed_fields = ["deleted_at", "deleted_by_user_id"]
                    else:
                        ts_changed_fields = ["deleted_at"]
                else:
                    await db.delete(ts)
                    ts_changed_fields = None

                await record_audit(
                    db,
                    action=AuditAction.delete,
                    entity_type=AuditEntityType.training_session,
                    entity_id=ts.id,
                    actor=ctx.actor,
                    actor_kind=ctx.actor_kind,
                    club_id=club_id,
                    changed_fields=ts_changed_fields,
                    request_id=ctx.request_id,
                )

    event.deleted_at = now
    event.deleted_by_user_id = actor_id

    await record_audit(
        db,
        action=AuditAction.delete,
        entity_type=AuditEntityType.calendar_event,
        entity_id=event_id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=club_id,
        changed_fields=["deleted_at", "deleted_by_user_id"],
        request_id=ctx.request_id,
    )

    await db.commit()


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
