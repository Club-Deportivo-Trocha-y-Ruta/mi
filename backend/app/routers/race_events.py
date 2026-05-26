"""Router ``/api/race-analysis/race-events/*`` — gestión de eventos de carrera.

Endpoints implementados:

- ``PATCH /{race_event_id}/conditions`` — actualización parcial de condiciones
  de carrera (clima, temperatura, superficie, altitud, notas).

Convenciones:
- RBAC: coach + admin. Padres reciben 403.
- Update parcial: solo los campos enviados se aplican (``exclude_unset=True``).
- Sin migración Alembic: las columnas ya existen en ``race_events`` desde la
  migración delta Paso 2 Fase 1.7 (``64c263edd07f``).
- Privacidad: el body completo NO se loguea (``weather_notes`` puede contener
  información eventual; política de logs es siempre conservadora).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.race_event import RaceEvent
from app.models.user import User, UserRole
from app.schemas.race_imports import RaceEventConditionsRead, RaceEventConditionsUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.patch(
    "/{race_event_id}/conditions",
    response_model=RaceEventConditionsRead,
    summary="Actualizar condiciones de carrera",
)
async def update_race_event_conditions(
    race_event_id: int,
    body: RaceEventConditionsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventConditionsRead:
    """Actualización parcial de condiciones de carrera de un ``RaceEvent``.

    Solo los campos presentes en el body se aplican al evento; los ausentes
    conservan su valor actual (``model_dump(exclude_unset=True)``).

    Responde con las condiciones actualizadas del evento.

    Códigos de respuesta:
    - 200: actualización exitosa.
    - 404: ``race_event_id`` no existe.
    - 422: algún campo fuera de rango (validado por Pydantic antes de llegar aquí).
    - 403: usuario sin rol coach o admin.
    """
    # Cargar el evento — 404 si no existe
    result = await db.execute(
        select(RaceEvent).where(RaceEvent.id == race_event_id)
    )
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )

    # Extraer solo los campos que el cliente envió (update parcial)
    campos_actualizados = body.model_dump(exclude_unset=True)

    if not campos_actualizados:
        # Body vacío — retornamos el estado actual sin tocar la DB
        logger.debug(
            "race_events_conditions_patch race_event_id=%s user_id=%s sin_cambios",
            race_event_id,
            current_user.id,
        )
        return RaceEventConditionsRead(
            race_event_id=event.id,
            climate=event.climate,
            temperature_c=event.temperature_c,
            surface_condition=event.surface_condition,
            altitude_msnm=event.altitude_msnm,
            weather_notes=event.weather_notes,
            updated_at=event.updated_at,
        )

    # Aplicar campos al modelo ORM
    for campo, valor in campos_actualizados.items():
        setattr(event, campo, valor)

    await db.flush()

    # Log mínimo: campos modificados (no sus valores — weather_notes es texto libre)
    logger.info(
        "race_events_conditions_patch race_event_id=%s user_id=%s campos=%s",
        race_event_id,
        current_user.id,
        sorted(campos_actualizados.keys()),
    )

    return RaceEventConditionsRead(
        race_event_id=event.id,
        climate=event.climate,
        temperature_c=event.temperature_c,
        surface_condition=event.surface_condition,
        altitude_msnm=event.altitude_msnm,
        weather_notes=event.weather_notes,
        updated_at=event.updated_at,
    )
