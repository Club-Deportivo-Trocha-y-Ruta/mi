"""Router ``/api/race-analysis/race-events/*`` — gestión de eventos de carrera.

Endpoints implementados:

- ``GET    /``                                       — listado filtrado con flags derivados.
- ``GET    /{race_event_id}/results``                — resultados por categoría (coach/admin/parent).
- ``GET    /{race_event_id}/standings``              — clasificación de temporada (coach/admin/parent).
- ``GET    /{race_event_id}/roster``                 — nómina de convocados (coach/admin; parent → solo propios hijos).
- ``POST   /``                                      — crea evento vacío (coach + admin).
- ``POST   /{race_event_id}/roster``                — añade atleta a la nómina (coach + admin).
- ``PATCH  /{race_event_id}``                       — edita metadata (coach + admin).
- ``PATCH  /{race_event_id}/roster/{entry_id}``     — actualiza entrada de nómina (coach + admin).
- ``DELETE /{race_event_id}``                       — borra evento limpio (admin only).
- ``DELETE /{race_event_id}/cleanup``               — borra válida duplicada sin resultados + su calendario (coach only).
- ``DELETE /{race_event_id}/roster/{entry_id}``     — elimina entrada de nómina (coach + admin).
- ``PATCH  /{race_event_id}/conditions``            — actualiza condiciones de carrera (coach + admin).
- ``PUT    /race-results/{result_id}/coach-note``   — escribe/reemplaza nota del entrenador (coach + admin).
- ``DELETE /race-results/{result_id}/coach-note``   — elimina nota del entrenador (coach + admin).

Convenciones:
- RBAC: coach + admin en escritura. Admin exclusivo para DELETE de evento.
- Parent en lectura con scope reducido a sus propios hijos (FR-030).
- Update parcial con ``exclude_unset=True``.
- Privacidad: logs contienen solo IDs — nunca nombres de atletas (Ley 1581).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult
from app.models.user import User, UserRole
from app.schemas.race_event import (
    CalendarAutoCreateRead,
    CalendarLinkRead,
    CalendarLinkRequest,
    RaceEventCreate,
    RaceEventListResponse,
    RaceEventRead,
    RaceEventUpdate,
)
from app.schemas.race_imports import RaceEventConditionsRead, RaceEventConditionsUpdate
from app.schemas.race_results import CoachNoteUpdate, EventResultsRead, EventStandingsRead, ResultRow
from app.schemas.race_roster import RosterEntryCreate, RosterEntryRead, RosterEntryUpdate, RosterRead
import app.services.race_events as race_events_svc
import app.services.race.results_read as results_svc
import app.services.race.roster as roster_svc
import app.services.race.standings as standings_svc
from app.models.race_series import RaceSeries, RaceSeriesKind
from app.services.permissions import allowed_athlete_ids_for
from app.services.race.series_rules import assert_championship_single_event, derive_event_fields_for_series

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET / — Listado de eventos con filtros
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=RaceEventListResponse,
    summary="Listar eventos de carrera",
)
async def list_race_events(
    season: Optional[int] = Query(default=None, ge=2020, le=2100, description="Año de temporada de la serie."),
    status: Optional[RaceEventStatus] = Query(default=None, description="Filtrar por estado del evento."),
    is_championship: Optional[bool] = Query(default=None, description="Filtrar solo campeonatos departamentales."),
    location: Optional[str] = Query(default=None, max_length=150, description="Búsqueda parcial por municipio/lugar."),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventListResponse:
    """Listado de eventos de carrera con flags derivados.

    Campos derivados por evento:
    - ``has_results``: existen resultados ingestados en ``race_results``.
    - ``has_calendar_event``: existe al menos un ``calendar_event`` asociado.
    - ``conditions_completeness``: completitud de los campos de clima.

    Ordenado por ``event_date`` ascendente.

    Códigos de respuesta:
    - 200: listado (puede estar vacío si no hay eventos o no coincide el filtro).
    - 403: usuario sin rol coach o admin.
    """
    items = await race_events_svc.list_race_events(
        db=db,
        season=season,
        status_filter=status,
        is_championship=is_championship,
        location=location,
    )
    return RaceEventListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# GET /{race_event_id}/results — Resultados por categoría
# ---------------------------------------------------------------------------


@router.get(
    "/{race_event_id}/results",
    response_model=EventResultsRead,
    summary="Resultados del evento por categoría",
)
async def get_race_event_results(
    race_event_id: int,
    category_id: Optional[int] = Query(
        default=None,
        description="Filtrar por categoría.",
    ),
    club_only: bool = Query(
        default=False,
        description="Solo mostrar resultados de atletas del club (con athlete_id confirmado).",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.admin, UserRole.coach, UserRole.parent])
    ),
) -> EventResultsRead:
    """Retorna el orden de llegada del evento agrupado por categoría.

    - Filas ordenadas por ``category.sort_order`` y luego ``position ASC NULLS LAST``.
    - Excluye resultados con ``deleted_at IS NOT NULL``.
    - ``is_our_club = True`` cuando ``athlete_id IS NOT NULL`` (atleta TyR confirmado).
    - Parent: solo ve las filas de sus propios hijos (FR-030).

    Códigos de respuesta:
    - 200: resultados (puede tener ``categories=[]`` si no hay datos ingestados).
    - 404: evento no existe.
    - 403: usuario sin rol coach, admin o parent.
    """
    scoped = await allowed_athlete_ids_for(current_user, db)

    payload = await results_svc.get_event_results(
        db,
        race_event_id,
        category_id=category_id,
        club_only=club_only,
        allowed_athlete_ids=scoped,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )
    logger.info(
        "race_events_results_get race_event_id=%s user_id=%s",
        race_event_id,
        current_user.id,
    )
    return payload


# ---------------------------------------------------------------------------
# GET /{race_event_id}/standings — Clasificación de temporada
# ---------------------------------------------------------------------------


@router.get(
    "/{race_event_id}/standings",
    response_model=EventStandingsRead,
    summary="Clasificación acumulada de la temporada",
)
async def get_race_event_standings(
    race_event_id: int,
    category_id: Optional[int] = Query(
        default=None,
        description="Filtrar por categoría.",
    ),
    club_only: bool = Query(
        default=False,
        description="Solo mostrar clasificados del club.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.admin, UserRole.coach, UserRole.parent])
    ),
) -> EventStandingsRead:
    """Retorna la clasificación acumulada de la temporada para la serie del evento.

    - Agrega ``SUM(points_awarded)``, ``COUNT``, podios y mejor posición
      directamente desde ``race_results`` (no usa la vista ``season_standings``).
    - Ranking por ``total_points DESC``, desempate por podios DESC, mejor posición ASC.
    - Parent: solo ve sus propios hijos (FR-030).
    - Para eventos de series tipo ``championship``, el ranking acumulado no aplica;
      se retorna un payload vacío (``categories=[]``) en lugar de 404.

    Códigos de respuesta:
    - 200: clasificación (puede tener ``categories=[]`` si no hay resultados aún o
      el evento es un campeonato).
    - 404: evento no existe o no tiene serie asociada.
    - 403: usuario sin rol coach, admin o parent.
    """
    scoped = await allowed_athlete_ids_for(current_user, db)

    payload = await standings_svc.get_event_standings(
        db,
        race_event_id,
        category_id=category_id,
        club_only=club_only,
        allowed_athlete_ids=scoped,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe o no tiene serie.",
        )
    logger.info(
        "race_events_standings_get race_event_id=%s user_id=%s categories=%s",
        race_event_id,
        current_user.id,
        len(payload.categories),
    )
    return payload


# ---------------------------------------------------------------------------
# GET /{race_event_id}/roster — Nómina de convocados
# ---------------------------------------------------------------------------


@router.get(
    "/{race_event_id}/roster",
    response_model=RosterRead,
    summary="Nómina de convocados para un evento de carrera",
)
async def get_race_event_roster(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.admin, UserRole.coach, UserRole.parent])
    ),
) -> RosterRead:
    """Retorna la nómina de convocados del evento con reconciliación.

    La reconciliación compara la nómina contra los resultados ingestados:

    - ``called_up_no_result``: atletas convocados sin resultado en la válida.
    - ``result_not_called_up``: atletas con resultado pero no en la nómina.

    Parent: solo ve las entradas de sus propios hijos; reconciliación vacía
    (FR-030, Ley 1581 — no se expone información de otros menores).

    Códigos de respuesta:
    - 200: nómina (puede tener ``entries=[]`` si no hay convocados).
    - 404: evento no existe.
    - 403: usuario sin rol coach, admin o parent.
    """
    scoped = await allowed_athlete_ids_for(current_user, db)
    payload = await roster_svc.get_roster(
        db,
        race_event_id,
        allowed_athlete_ids=scoped,
    )
    logger.info(
        "race_events_roster_get race_event_id=%s user_id=%s",
        race_event_id,
        current_user.id,
    )
    return payload


# ---------------------------------------------------------------------------
# POST /{race_event_id}/roster — Añadir atleta a la nómina
# ---------------------------------------------------------------------------


@router.post(
    "/{race_event_id}/roster",
    response_model=RosterEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir atleta a la nómina de convocados",
)
async def add_race_event_roster_entry(
    race_event_id: int,
    body: RosterEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RosterEntryRead:
    """Añade un atleta del club a la nómina de convocados del evento.

    El atleta debe existir en la tabla ``athletes`` (pertenecer a un club).
    No puede añadirse el mismo atleta dos veces para el mismo evento.

    Códigos de respuesta:
    - 201: entrada creada.
    - 404: evento no existe.
    - 409: el atleta ya está en la nómina para este evento.
    - 422: el atleta no existe o no pertenece a ningún club.
    - 403: usuario sin rol coach o admin.
    """
    entry = await roster_svc.add_roster_entry(
        db,
        race_event_id,
        payload=body,
        created_by_user_id=current_user.id,
    )
    logger.info(
        "race_events_roster_add race_event_id=%s entry_id=%s user_id=%s",
        race_event_id,
        entry.id,
        current_user.id,
    )
    return entry


# ---------------------------------------------------------------------------
# PATCH /{race_event_id}/roster/{entry_id} — Actualizar entrada de nómina
# ---------------------------------------------------------------------------


@router.patch(
    "/{race_event_id}/roster/{entry_id}",
    response_model=RosterEntryRead,
    summary="Actualizar una entrada de la nómina",
)
async def update_race_event_roster_entry(
    race_event_id: int,
    entry_id: int,
    body: RosterEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RosterEntryRead:
    """Actualización parcial del estado y/o nota de una entrada de nómina.

    Solo los campos presentes en el body se aplican; los ausentes conservan
    su valor.

    Códigos de respuesta:
    - 200: actualización exitosa.
    - 404: entrada o evento no existe.
    - 422: valor fuera de rango.
    - 403: usuario sin rol coach o admin.
    """
    entry = await roster_svc.update_roster_entry(
        db,
        race_event_id,
        entry_id=entry_id,
        payload=body,
    )
    logger.info(
        "race_events_roster_update race_event_id=%s entry_id=%s user_id=%s",
        race_event_id,
        entry_id,
        current_user.id,
    )
    return entry


# ---------------------------------------------------------------------------
# DELETE /{race_event_id}/roster/{entry_id} — Eliminar entrada de nómina
# ---------------------------------------------------------------------------


@router.delete(
    "/{race_event_id}/roster/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar entrada de la nómina",
)
async def delete_race_event_roster_entry(
    race_event_id: int,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    """Elimina un atleta de la nómina de convocados del evento.

    Coach y admin pueden eliminar entradas.

    Códigos de respuesta:
    - 204: eliminado correctamente (sin body).
    - 404: entrada o evento no existe.
    - 403: usuario sin rol coach o admin.
    """
    await roster_svc.delete_roster_entry(
        db,
        race_event_id,
        entry_id=entry_id,
    )
    logger.info(
        "race_events_roster_delete race_event_id=%s entry_id=%s user_id=%s",
        race_event_id,
        entry_id,
        current_user.id,
    )


# ---------------------------------------------------------------------------
# GET /{race_event_id} — Detalle de un evento
# ---------------------------------------------------------------------------


@router.get(
    "/{race_event_id}",
    response_model=RaceEventRead,
    summary="Detalle de un evento de carrera",
)
async def get_race_event(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventRead:
    """Retorna el ``RaceEvent`` completo (metadata + condiciones).

    Códigos de respuesta:
    - 200: evento encontrado.
    - 404: evento no existe.
    - 403: usuario sin rol coach o admin.
    """
    from sqlalchemy import exists
    from app.models.calendar_event import CalendarEvent

    result = await db.execute(select(RaceEvent).where(RaceEvent.id == race_event_id))
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )
    # Flag derivado: ¿hay calendar_event vinculado?
    has_cal_result = await db.execute(
        select(exists().where(CalendarEvent.race_event_id == race_event_id))
    )
    has_calendar_event = bool(has_cal_result.scalar())
    payload = RaceEventRead.model_validate(event)
    payload.has_calendar_event = has_calendar_event
    return payload


# ---------------------------------------------------------------------------
# POST / — Crear evento vacío
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=RaceEventRead,
    status_code=201,
    summary="Crear evento de carrera",
)
async def create_race_event(
    body: RaceEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventRead:
    """Crea un nuevo evento de carrera vacío (sin resultados).

    El evento se asocia a una serie existente. El servidor deriva
    ``sequence_number`` e ``is_championship`` del tipo de la serie (spec 014):
    - Series tipo ``championship``: ``sequence_number=1``, ``is_championship=True``.
      Un segundo evento en la misma serie devuelve 409.
    - Series tipo ``cup``: ``sequence_number`` requerido del cliente,
      ``is_championship=False``.

    Los campos de condiciones de carrera son opcionales y pueden completarse
    después con ``PATCH /{id}/conditions``.

    Códigos de respuesta:
    - 201: evento creado correctamente.
    - 404: la serie referenciada no existe.
    - 409: campeonato con evento ya existente, o duplicado ``(series_id, sequence_number)`` en copa.
    - 422: campo fuera de rango, serie no existe, o sequence_number ausente en copa.
    - 403: usuario sin rol coach o admin.
    """
    # Load the target series — 422 if missing (FIX-3: reference validation error,
    # not a resource-not-found; preserves the test contract in test_race_events_crud.py
    # test_post_series_id_inexistente which asserts 422).
    series_result = await db.execute(
        select(RaceSeries).where(RaceSeries.id == body.series_id)
    )
    series: Optional[RaceSeries] = series_result.scalar_one_or_none()
    if series is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Serie con id={body.series_id} no existe.",
        )

    # For cups, sequence_number is required
    if series.kind == RaceSeriesKind.cup and body.sequence_number is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sequence_number es requerido para series de tipo 'cup'.",
        )

    # Guard: championship must not already have an event (INV-2)
    await assert_championship_single_event(db, series)

    # Derive sequence_number and is_championship from series kind (client values ignored)
    derived_sequence, derived_is_championship = derive_event_fields_for_series(
        series.kind, body.sequence_number
    )

    # Build a modified payload with derived values — use model_copy to avoid mutating body
    derived_body = body.model_copy(
        update={
            "sequence_number": derived_sequence,
            "is_championship": derived_is_championship,
        }
    )

    event = await race_events_svc.create_race_event(
        db=db,
        payload=derived_body,
        user_id=current_user.id,
    )

    # FR-024: create a linked CalendarEvent unless the caller opts out.
    if body.create_calendar_event:
        from app.services.race.calendar_sync import create_linked_calendar_event
        await create_linked_calendar_event(db=db, race_event=event, user=current_user)

    return RaceEventRead.model_validate(event)


# ---------------------------------------------------------------------------
# PATCH /{race_event_id} — Editar metadata
# ---------------------------------------------------------------------------


@router.patch(
    "/{race_event_id}",
    response_model=RaceEventRead,
    summary="Editar metadata de un evento de carrera",
)
async def update_race_event(
    race_event_id: int,
    body: RaceEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> RaceEventRead:
    """Actualización parcial de metadata de un evento.

    Solo los campos enviados se aplican; los ausentes conservan su valor.
    No modifica condiciones de carrera (clima, temperatura, etc.) — para
    eso usar ``PATCH /{id}/conditions``.

    Códigos de respuesta:
    - 200: actualización exitosa.
    - 404: evento no existe.
    - 409: nueva ``sequence_number`` ya está tomada en la misma serie.
    - 422: valor fuera de rango.
    - 403: usuario sin rol coach o admin.
    """
    event = await race_events_svc.update_race_event(
        db=db,
        race_event_id=race_event_id,
        payload=body,
    )
    return RaceEventRead.model_validate(event)


# ---------------------------------------------------------------------------
# DELETE /{race_event_id} — Borrar evento limpio
# ---------------------------------------------------------------------------


@router.delete(
    "/{race_event_id}",
    status_code=204,
    summary="Eliminar evento de carrera",
)
async def delete_race_event(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_role([UserRole.admin])),
) -> None:
    """Elimina un evento de carrera si no tiene dependencias.

    Solo el rol ``admin`` puede borrar. Los coaches deben hacer
    ``PATCH /{id}`` con ``status=cancelled`` en su lugar.

    Verificaciones antes de borrar:
    - Sin resultados ingestados en ``race_results`` → 409.
    - Sin asociación a evento de calendario → 409.

    Códigos de respuesta:
    - 204: eliminado correctamente (sin body).
    - 404: evento no existe.
    - 409: tiene resultados ingestados o está vinculado a un calendario.
    - 403: usuario sin rol admin.
    """
    await race_events_svc.delete_race_event(db=db, race_event_id=race_event_id)


# ---------------------------------------------------------------------------
# DELETE /{race_event_id}/cleanup — Eliminar válida duplicada + su calendario (coach)
# ---------------------------------------------------------------------------


@router.delete(
    "/{race_event_id}/cleanup",
    status_code=204,
    summary="Eliminar válida duplicada (sin resultados) y su evento de calendario",
)
async def cleanup_duplicate_race_event(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.coach])),
) -> None:
    """Elimina una válida **duplicada sin resultados** junto con su evento de calendario.

    Acción del coach para limpiar un duplicado (el mismo evento real cargado dos
    veces). A diferencia del ``DELETE /{id}`` general (admin only, que rechaza si hay
    calendario vinculado), aquí el evento de calendario asociado se **borra** en la
    misma operación. Las válidas con resultados quedan protegidas (409).

    Códigos de respuesta:
    - 204: eliminado correctamente (sin body). La válida y su calendario ya no existen.
    - 404: la válida no existe (p. ej. ya eliminada — lista desactualizada).
    - 409: la válida tiene resultados ingestados → protegida, no se puede eliminar.
    - 403: usuario sin rol coach.
    """
    await race_events_svc.cleanup_duplicate_race_event(db=db, race_event_id=race_event_id)
    logger.info(
        "race_event_cleanup_request race_event_id=%s user_id=%s",
        race_event_id,
        current_user.id,
    )


# ---------------------------------------------------------------------------
# POST /{race_event_id}/calendar-link — Vincular CalendarEvent existente (FR-025)
# ---------------------------------------------------------------------------


@router.post(
    "/{race_event_id}/calendar-link",
    response_model=CalendarLinkRead,
    status_code=status.HTTP_200_OK,
    summary="Vincular un CalendarEvent existente a una válida",
)
async def link_calendar_event(
    race_event_id: int,
    body: CalendarLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> CalendarLinkRead:
    """Asocia un ``CalendarEvent`` de tipo *competition* ya existente con esta válida.

    Establece el vínculo 1:1 en ambas FKs:
    - ``race_events.calendar_event_id = body.calendar_event_id``
    - ``calendar_events.race_event_id = race_event_id``

    Códigos de respuesta:
    - 200: vinculado correctamente.
    - 404: la válida o el evento de calendario no existen.
    - 409: cualquiera de los dos lados ya está vinculado (strict 1:1).
    - 403: usuario sin rol coach o admin.
    """
    from sqlalchemy import select as sa_select

    # Load the race_event — 404 if missing
    result = await db.execute(sa_select(RaceEvent).where(RaceEvent.id == race_event_id))
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )

    from app.services.race.calendar_sync import link_existing_calendar_event
    cal = await link_existing_calendar_event(
        db=db,
        race_event=event,
        calendar_event_id=body.calendar_event_id,
        user=current_user,
    )

    logger.info(
        "race_events_calendar_link race_event_id=%s cal_id=%s user_id=%s",
        race_event_id,
        cal.id,
        current_user.id,
    )
    return CalendarLinkRead(race_event_id=race_event_id, calendar_event_id=cal.id)


# ---------------------------------------------------------------------------
# POST /{race_event_id}/calendar-event — Crear y vincular all-day CalendarEvent (FR-008)
# ---------------------------------------------------------------------------


@router.post(
    "/{race_event_id}/calendar-event",
    response_model=CalendarAutoCreateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear y vincular evento de calendario all-day para una válida",
)
async def create_calendar_event_for_race_event(
    race_event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.coach])),
) -> CalendarAutoCreateRead:
    """Crea un ``CalendarEvent`` all-day de tipo *competition* y lo vincula a la válida.

    El evento se construye automáticamente con los datos de la válida
    (``name`` → ``title``, ``location``, ``event_date`` → all-day en America/Bogota).
    No requiere body — el coach solo hace clic en «Asociar».

    Estricto 1:1: si la válida ya tiene un calendario vinculado → 409.

    Códigos de respuesta:
    - 201: evento creado y vinculado. Body: ``{race_event_id, calendar_event_id, has_calendar_event: true}``.
    - 404: ``race_event_id`` no existe.
    - 409: la válida ya tiene un evento de calendario vinculado.
    - 403: usuario sin rol coach.
    """
    result = await db.execute(select(RaceEvent).where(RaceEvent.id == race_event_id))
    event: Optional[RaceEvent] = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de carrera con id={race_event_id} no existe.",
        )

    if event.calendar_event_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La válida id={race_event_id} ya está vinculada al evento de calendario id={event.calendar_event_id}.",
        )

    from app.services.race.calendar_sync import create_linked_calendar_event

    cal = await create_linked_calendar_event(
        db=db,
        race_event=event,
        user=current_user,
        all_day=True,
    )
    await db.commit()

    logger.info(
        "race_events_calendar_autocreate race_event_id=%s cal_id=%s user_id=%s",
        race_event_id,
        cal.id,
        current_user.id,
    )
    return CalendarAutoCreateRead(
        race_event_id=race_event_id,
        calendar_event_id=cal.id,
        has_calendar_event=True,
    )


# ---------------------------------------------------------------------------
# PATCH /{race_event_id}/conditions — Condiciones de carrera (endpoint previo)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PUT /race-results/{result_id}/coach-note  — T006
# ---------------------------------------------------------------------------


def _result_row_from_orm(row: RaceResult) -> ResultRow:
    """Serialize a ``RaceResult`` ORM instance to ``ResultRow``.

    Used by the coach-note PUT/DELETE handlers where we already hold
    the ORM object (no extra query needed).
    """
    return ResultRow(
        result_id=row.id,
        position=row.position,
        competitor_id=row.competitor_id,
        display_name=row.competitor.display_name,
        club_text=row.competitor.club_text,
        athlete_id=row.athlete_id,
        is_our_club=(row.athlete_id is not None),
        status=row.status.value if hasattr(row.status, "value") else str(row.status),
        race_time_ms=row.race_time_ms,
        laps_behind=row.laps_behind,
        points_awarded=row.points_awarded if row.points_awarded is not None else 0,
        bib_number=row.bib_number,
        coach_note=row.coach_note,
        coach_note_updated_at=row.coach_note_updated_at,
    )


@router.put(
    "/race-results/{result_id}/coach-note",
    response_model=ResultRow,
    summary="Escribir o reemplazar nota del entrenador para un resultado de carrera",
)
async def set_race_result_coach_note(
    result_id: int,
    body: CoachNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ResultRow:
    """Escribe (o reemplaza) la nota cualitativa del entrenador para un resultado.

    La nota es exclusiva del coach/admin — no proviene del proceso de ingest
    del PDF y nunca se sobreescribe en reimportaciones.

    Solo se puede anotar resultados de atletas del club (``athlete_id IS NOT NULL``).
    El campo ``coach_note`` del body ya llega limpio (strip + validación de longitud).

    Códigos de respuesta:
    - 200: nota guardada. Body: ``ResultRow`` actualizado.
    - 404: resultado no existe o fue eliminado (soft-delete).
    - 409: el resultado no pertenece a un atleta del club.
    - 422: nota vacía o excede 500 caracteres.
    - 403: usuario sin rol coach o admin.
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(RaceResult)
        .options(selectinload(RaceResult.competitor))
        .where(RaceResult.id == result_id, RaceResult.deleted_at.is_(None))
    )
    race_result: Optional[RaceResult] = result.scalar_one_or_none()
    if race_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resultado de carrera con id={result_id} no existe.",
        )

    if race_result.athlete_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El resultado id={result_id} pertenece a un competidor externo "
                "sin atleta del club vinculado. No se puede anotar."
            ),
        )

    race_result.coach_note = body.coach_note
    race_result.coach_note_author_id = current_user.id
    race_result.coach_note_updated_at = datetime.now(timezone.utc)

    await db.flush()

    logger.info(
        "race_result_coach_note_set result_id=%s athlete_id=%s user_id=%s",
        result_id,
        race_result.athlete_id,
        current_user.id,
    )

    return _result_row_from_orm(race_result)


# ---------------------------------------------------------------------------
# DELETE /race-results/{result_id}/coach-note  — T007
# ---------------------------------------------------------------------------


@router.delete(
    "/race-results/{result_id}/coach-note",
    response_model=ResultRow,
    summary="Eliminar nota del entrenador para un resultado de carrera",
)
async def clear_race_result_coach_note(
    result_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ResultRow:
    """Elimina la nota cualitativa del entrenador de un resultado.

    La operación es idempotente: si la nota ya es ``None`` se retorna
    el ``ResultRow`` sin modificar la BD.

    Códigos de respuesta:
    - 200: nota eliminada (o ya era nula). Body: ``ResultRow`` actualizado.
    - 404: resultado no existe o fue eliminado (soft-delete).
    - 403: usuario sin rol coach o admin.
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(RaceResult)
        .options(selectinload(RaceResult.competitor))
        .where(RaceResult.id == result_id, RaceResult.deleted_at.is_(None))
    )
    race_result: Optional[RaceResult] = result.scalar_one_or_none()
    if race_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resultado de carrera con id={result_id} no existe.",
        )

    if race_result.coach_note is not None:
        race_result.coach_note = None
        race_result.coach_note_author_id = None
        race_result.coach_note_updated_at = None
        await db.flush()

    logger.info(
        "race_result_coach_note_clear result_id=%s athlete_id=%s user_id=%s",
        result_id,
        race_result.athlete_id,
        current_user.id,
    )

    return _result_row_from_orm(race_result)
