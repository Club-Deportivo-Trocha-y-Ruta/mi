"""Lógica de asistencia y RSVP para eventos de calendario (no-training)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calendar_event import (
    ActualAttendanceStatus,
    EventAttendance,
    EventType,
    RSVPStatus,
)

if TYPE_CHECKING:
    from app.models.calendar_event import CalendarEvent
    from app.models.user import User

logger = logging.getLogger(__name__)


async def rsvp(
    db: AsyncSession,
    event: "CalendarEvent",
    athlete_id: int,
    status: RSVPStatus,
    by_user: "User",
) -> EventAttendance:
    """Upsert del RSVP de un atleta a un evento.

    Lanza ValueError si el evento es de tipo TRAINING_SESSION
    (esos usan session_attendance).
    """
    if event.event_type == EventType.TRAINING_SESSION:
        raise ValueError(
            "Los eventos de tipo entrenamiento usan los endpoints "
            "/training-sessions para gestionar asistencia"
        )

    # Buscar registro existente
    result = await db.execute(
        select(EventAttendance).where(
            EventAttendance.event_id == event.id,
            EventAttendance.athlete_id == athlete_id,
        )
    )
    attendance = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if attendance is None:
        attendance = EventAttendance(
            event_id=event.id,
            athlete_id=athlete_id,
            rsvp_status=status,
            rsvp_at=now,
            rsvp_by_user_id=by_user.id,
        )
        db.add(attendance)
    else:
        attendance.rsvp_status = status
        attendance.rsvp_at = now
        attendance.rsvp_by_user_id = by_user.id

    await db.commit()
    await db.refresh(attendance)
    return attendance


async def mark_actual(
    db: AsyncSession,
    event: "CalendarEvent",
    athlete_id: int,
    status: ActualAttendanceStatus,
) -> EventAttendance:
    """Marca la asistencia real de un atleta a un evento."""
    result = await db.execute(
        select(EventAttendance).where(
            EventAttendance.event_id == event.id,
            EventAttendance.athlete_id == athlete_id,
        )
    )
    attendance = result.scalar_one_or_none()

    if attendance is None:
        attendance = EventAttendance(
            event_id=event.id,
            athlete_id=athlete_id,
            actual_status=status,
        )
        db.add(attendance)
    else:
        attendance.actual_status = status

    await db.commit()
    await db.refresh(attendance)
    return attendance


async def list_attendances(
    db: AsyncSession,
    event: "CalendarEvent",
) -> list[EventAttendance]:
    """Lista todas las asistencias de un evento con eager load del atleta."""
    result = await db.execute(
        select(EventAttendance)
        .where(EventAttendance.event_id == event.id)
        .options(selectinload(EventAttendance.athlete))
        .order_by(EventAttendance.id)
    )
    return list(result.scalars().all())
