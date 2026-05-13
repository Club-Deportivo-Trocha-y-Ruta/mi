"""Lógica de audiencias: resolución de atletas destinatarios de un evento."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.calendar_event import AudienceType, EventAudience
from app.services.category import get_category

if TYPE_CHECKING:
    from app.models.calendar_event import CalendarEvent
    from app.schemas.calendar import AudienceCreate

logger = logging.getLogger(__name__)


async def set_audiences(
    db: AsyncSession,
    event: "CalendarEvent",
    audience_specs: "list[AudienceCreate]",
) -> None:
    """Borra y reinsertar las audiencias de un evento.

    Ejecutar dentro de la misma transacción que el evento.
    No hace commit — el llamador es responsable.
    """
    # Borrar audiencias existentes con DELETE directo (evita lazy load en async SQLAlchemy).
    await db.execute(delete(EventAudience).where(EventAudience.event_id == event.id))

    for spec in audience_specs:
        db.add(
            EventAudience(
                event_id=event.id,
                audience_type=spec.audience_type,
                audience_value=spec.audience_value,
            )
        )


async def resolve_athletes(
    db: AsyncSession,
    event: "CalendarEvent",
) -> list[Athlete]:
    """Resuelve la lista de atletas concretos para la audiencia del evento.

    Unifica todos los registros de event_audiences del evento y retorna
    la unión deduplicada de atletas.
    """
    seen_ids: set[int] = set()
    athletes: list[Athlete] = []

    for audience in event.audiences:
        batch = await _resolve_single_audience(db, audience, event.club_id)
        for ath in batch:
            if ath.id not in seen_ids:
                seen_ids.add(ath.id)
                athletes.append(ath)

    return athletes


async def _resolve_single_audience(
    db: AsyncSession,
    audience: EventAudience,
    club_id: int,
) -> list[Athlete]:
    """Resuelve un único registro de audiencia a lista de atletas."""
    atype = audience.audience_type
    avalue = audience.audience_value or {}

    if atype == AudienceType.ALL_CLUB:
        result = await db.execute(
            select(Athlete).where(Athlete.club_id == club_id)
        )
        return list(result.scalars().all())

    if atype == AudienceType.CATEGORY:
        target_category = avalue.get("category", "")
        # Cargamos todos los atletas del club y filtramos por categoría FCC
        result = await db.execute(
            select(Athlete).where(Athlete.club_id == club_id)
        )
        all_athletes = list(result.scalars().all())
        return [
            a for a in all_athletes
            if get_category(a.birth_date.year, a.sex.value) == target_category
        ]

    if atype == AudienceType.ATHLETE_LIST:
        ids = avalue.get("athlete_ids", [])
        if not ids:
            return []
        result = await db.execute(
            select(Athlete).where(
                Athlete.id.in_(ids),
                Athlete.club_id == club_id,
            )
        )
        return list(result.scalars().all())

    if atype == AudienceType.INDIVIDUAL:
        athlete_id = avalue.get("athlete_id")
        if athlete_id is None:
            return []
        result = await db.execute(
            select(Athlete).where(
                Athlete.id == athlete_id,
                Athlete.club_id == club_id,
            )
        )
        ath = result.scalar_one_or_none()
        return [ath] if ath else []

    logger.warning("AudienceType desconocido: %s", atype)
    return []


async def event_visible_to_athlete(
    db: AsyncSession,
    event: "CalendarEvent",
    athlete_id: int,
) -> bool:
    """Retorna True si el atleta está en la unión de audiencias del evento."""
    athletes = await resolve_athletes(db, event)
    return any(a.id == athlete_id for a in athletes)


async def any_athlete_in_audience(
    db: AsyncSession,
    event: "CalendarEvent",
    athlete_ids: list[int],
) -> bool:
    """Retorna True si alguno de los athlete_ids está en la audiencia del evento.

    Útil para padres con múltiples hijos.
    """
    if not athlete_ids:
        return False
    athletes = await resolve_athletes(db, event)
    resolved_ids = {a.id for a in athletes}
    return bool(resolved_ids.intersection(athlete_ids))
