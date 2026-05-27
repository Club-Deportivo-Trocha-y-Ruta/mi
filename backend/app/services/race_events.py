"""Servicio de gestión de ``race_events`` (CRUD de metadata).

Responsabilidades:
- ``create_race_event``  — crea un evento vacío validando FK series y unicidad.
- ``update_race_event``  — actualización parcial de metadata (no condiciones).
- ``delete_race_event``  — borrado seguro previa verificación de dependencias.
- ``list_race_events``   — listado filtrado con flags derivados vía subqueries.

Convenciones:
- AsyncSession exclusivamente (nunca Session síncrona).
- Queries con ``select()`` moderno; nunca ``session.query()``.
- Los 409 de unicidad y dependencias se lanzan aquí para mantener la capa
  de router limpia de lógica de negocio.
- El campo ``calendar_event_id`` de ``race_events`` es la FK directa
  (1:1 inversa); la FK de ``calendar_events.race_event_id`` es la que
  bloquea el DELETE con ``RESTRICT``.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import CalendarEvent
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeries
from app.schemas.race_event import (
    ConditionsCompleteness,
    RaceEventCreate,
    RaceEventListItem,
    RaceEventUpdate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_CONDICIONES_CAMPOS = ("climate", "temperature_c", "surface_condition", "altitude_msnm", "weather_notes")


def _completeness(event: RaceEvent) -> ConditionsCompleteness:
    """Calcula qué tan completos están los campos de condiciones del evento."""
    presentes = sum(1 for campo in _CONDICIONES_CAMPOS if getattr(event, campo) is not None)
    if presentes == 0:
        return "empty"
    if presentes == len(_CONDICIONES_CAMPOS):
        return "complete"
    return "partial"


async def _check_series_exists(db: AsyncSession, series_id: int) -> None:
    """Lanza 422 si la serie referenciada no existe."""
    result = await db.execute(select(RaceSeries.id).where(RaceSeries.id == series_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La serie con id={series_id} no existe.",
        )


async def _check_sequence_unique(
    db: AsyncSession,
    series_id: int,
    sequence_number: int,
    exclude_event_id: Optional[int] = None,
) -> None:
    """Lanza 409 si la combinación (series_id, sequence_number) ya está tomada."""
    stmt = select(RaceEvent.id).where(
        RaceEvent.series_id == series_id,
        RaceEvent.sequence_number == sequence_number,
    )
    if exclude_event_id is not None:
        stmt = stmt.where(RaceEvent.id != exclude_event_id)

    result = await db.execute(stmt)
    conflicto = result.scalar_one_or_none()
    if conflicto is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe un evento con sequence_number={sequence_number} "
                f"en la serie id={series_id} (evento id={conflicto})."
            ),
        )


# ---------------------------------------------------------------------------
# CRUD público
# ---------------------------------------------------------------------------


async def create_race_event(
    db: AsyncSession,
    payload: RaceEventCreate,
    user_id: int,
) -> RaceEvent:
    """Crea un nuevo ``RaceEvent`` vacío (sin resultados).

    Valida:
    1. Que la serie referenciada existe → 422.
    2. Que ``(series_id, sequence_number)`` no está duplicado → 409.
    """
    await _check_series_exists(db, payload.series_id)
    await _check_sequence_unique(db, payload.series_id, payload.sequence_number)

    event = RaceEvent(
        series_id=payload.series_id,
        sequence_number=payload.sequence_number,
        name=payload.name,
        event_date=payload.event_date,
        location=payload.location,
        is_championship=payload.is_championship,
        status=payload.status or RaceEventStatus.SCHEDULED,
        climate=payload.climate,
        temperature_c=payload.temperature_c,
        surface_condition=payload.surface_condition,
        altitude_msnm=payload.altitude_msnm,
        weather_notes=payload.weather_notes,
        created_by_user_id=user_id,
    )
    db.add(event)
    await db.flush()  # Obtener el id asignado por la DB sin cerrar la transacción.

    logger.info(
        "race_event_created event_id=%s series_id=%s sequence=%s user_id=%s",
        event.id,
        event.series_id,
        event.sequence_number,
        user_id,
    )
    return event


async def update_race_event(
    db: AsyncSession,
    race_event_id: int,
    payload: RaceEventUpdate,
) -> RaceEvent:
    """Actualiza metadata de un ``RaceEvent`` (no toca condiciones de carrera).

    Solo los campos presentes en el payload se aplican (``exclude_unset=True``).
    Si se cambia ``sequence_number``, verifica unicidad dentro de la misma serie.

    Retorna el evento actualizado.
    Lanza 404 si el evento no existe, 409 si hay conflicto de unicidad.
    """
    result = await db.execute(select(RaceEvent).where(RaceEvent.id == race_event_id))
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )

    campos = payload.model_dump(exclude_unset=True)
    if not campos:
        # Body vacío — retornar sin modificar.
        return event

    # Verificar unicidad si se está cambiando sequence_number.
    nueva_seq = campos.get("sequence_number")
    if nueva_seq is not None and nueva_seq != event.sequence_number:
        await _check_sequence_unique(db, event.series_id, nueva_seq, exclude_event_id=race_event_id)

    for campo, valor in campos.items():
        setattr(event, campo, valor)

    await db.flush()

    logger.info(
        "race_event_updated event_id=%s campos=%s",
        race_event_id,
        sorted(campos.keys()),
    )
    return event


async def delete_race_event(db: AsyncSession, race_event_id: int) -> None:
    """Elimina un ``RaceEvent`` si no tiene dependencias.

    Verificaciones antes de borrar:
    1. Existe el evento → 404 si no.
    2. No tiene resultados ingestados en ``race_results`` → 409.
    3. No está referenciado en ``calendar_events.race_event_id`` → 409.
       (Aunque la FK usa RESTRICT, queremos un mensaje de error legible
       en español antes de que MySQL rechace la operación.)

    Si todo está limpio → DELETE + la sesión hace commit desde ``get_db``.
    """
    # Verificar existencia del evento.
    result = await db.execute(select(RaceEvent).where(RaceEvent.id == race_event_id))
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )

    # Verificar resultados ingestados.
    tiene_resultados = await db.execute(
        select(exists().where(RaceResult.event_id == race_event_id))
    )
    if tiene_resultados.scalar():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar: tiene resultados ingestados.",
        )

    # Verificar asociación a evento de calendario.
    resultado_cal = await db.execute(
        select(CalendarEvent.id).where(CalendarEvent.race_event_id == race_event_id).limit(1)
    )
    cal_id = resultado_cal.scalar_one_or_none()
    if cal_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar: está asociada a un evento de calendario (id={cal_id}).",
        )

    await db.delete(event)
    await db.flush()

    logger.info("race_event_deleted event_id=%s", race_event_id)


async def list_race_events(
    db: AsyncSession,
    season: Optional[int] = None,
    status_filter: Optional[RaceEventStatus] = None,
    is_championship: Optional[bool] = None,
    location: Optional[str] = None,
) -> list[RaceEventListItem]:
    """Listado de ``RaceEvent`` con filtros opcionales.

    Los flags ``has_results`` y ``has_calendar_event`` se calculan mediante
    subqueries escalares para evitar cargar listas completas de resultados.

    Ordenado por ``event_date`` ascendente.

    Si ``season`` no se especifica, retorna todos los eventos sin filtro
    de año (el frontend puede aplicar el default de temporada actual).
    """
    # Subquery EXISTS para has_results.
    sq_results = (
        select(func.count(RaceResult.id))
        .where(RaceResult.event_id == RaceEvent.id)
        .correlate(RaceEvent)
        .scalar_subquery()
    )
    # Subquery EXISTS para has_calendar_event.
    sq_calendar = (
        select(func.count(CalendarEvent.id))
        .where(CalendarEvent.race_event_id == RaceEvent.id)
        .correlate(RaceEvent)
        .scalar_subquery()
    )

    stmt = (
        select(
            RaceEvent,
            sq_results.label("n_results"),
            sq_calendar.label("n_calendar"),
        )
        .order_by(RaceEvent.event_date.asc())
    )

    # Filtros opcionales.
    if status_filter is not None:
        stmt = stmt.where(RaceEvent.status == status_filter)
    if is_championship is not None:
        stmt = stmt.where(RaceEvent.is_championship == is_championship)
    if location is not None:
        # Búsqueda parcial case-insensitive.
        stmt = stmt.where(RaceEvent.location.ilike(f"%{location}%"))

    if season is not None:
        # Filtrar por año de la serie asociada.
        stmt = stmt.join(RaceSeries, RaceEvent.series_id == RaceSeries.id).where(
            RaceSeries.season_year == season
        )

    rows = await db.execute(stmt)
    items: list[RaceEventListItem] = []
    for event, n_results, n_calendar in rows.all():
        items.append(
            RaceEventListItem(
                id=event.id,
                series_id=event.series_id,
                sequence_number=event.sequence_number,
                name=event.name,
                event_date=event.event_date,
                location=event.location,
                is_championship=event.is_championship,
                status=event.status,
                has_results=n_results > 0,
                has_calendar_event=n_calendar > 0,
                conditions_completeness=_completeness(event),
            )
        )

    return items
