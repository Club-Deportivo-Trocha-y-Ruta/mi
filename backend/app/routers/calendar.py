"""Router del módulo de calendario de eventos del club."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
)
from app.models.calendar_event import EventType
from app.models.user import User, UserRole
from app.schemas.calendar import (
    AudienceCreate,
    EventAttendanceRead,
    EventCreate,
    EventListItem,
    EventListQuery,
    EventRead,
    EventReadParent,
    EventUpdate,
    RSVPUpdate,
)
from app.services.calendar import attendances as attendance_svc
from app.services.calendar import events as events_svc
from app.services.permissions import (
    can_edit_calendar_event,
    can_rsvp_event,
    can_view_calendar_event,
    user_club_role,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_club_id_for_user(db: AsyncSession, user: User) -> int:
    """Retorna el primer club del usuario según su rol."""
    from app.models.club import ClubRole

    if user.role == UserRole.coach:
        coach_clubs = [
            m.club_id
            for m in user.club_memberships
            if m.role_in_club == ClubRole.coach
        ]
        if not coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No estás registrado como coach en ningún club",
            )
        return coach_clubs[0]

    if user.role == UserRole.admin:
        admin_clubs = [m.club_id for m in user.club_memberships]
        if not admin_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El administrador no pertenece a ningún club",
            )
        return admin_clubs[0]

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para crear eventos",
    )


async def _get_event_or_404(db: AsyncSession, event_id: int):
    """Obtiene el evento o lanza 404."""
    event = await events_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento {event_id} no encontrado",
        )
    return event


def _event_to_list_item(event, viewer: User | None = None) -> EventListItem:
    """Serializa un CalendarEvent a EventListItem para FullCalendar.

    Para padres, omitimos `description` de extended_props porque puede contener
    detalles internos del entrenador (referencias a otros atletas, notas
    pedagógicas). Location es público (lugar de encuentro) y se mantiene.
    """
    is_parent = viewer is not None and viewer.role == UserRole.parent
    extended: dict = {"location": event.location}
    if not is_parent:
        extended["description"] = event.description
    return EventListItem(
        id=event.id,
        title=event.title,
        start=event.start_at,
        end=event.end_at,
        allDay=event.all_day,
        event_type=event.event_type,
        color_hex=event.color_hex,
        status=event.status,
        extended_props=extended,
    )


def _serialize_event(event, user: User):
    """Serializa un CalendarEvent con el schema apropiado según el rol."""
    if user.role == UserRole.parent:
        return EventReadParent.model_validate(event)
    return EventRead.model_validate(event)


# ---------------------------------------------------------------------------
# GET /calendar/events — Listar eventos en rango
# ---------------------------------------------------------------------------


@router.get("", response_model=list[EventListItem])
async def list_calendar_events(
    from_date: date = Query(..., alias="from", description="Fecha de inicio del rango (ISO date)"),
    to_date: date = Query(..., alias="to", description="Fecha de fin del rango (ISO date)"),
    event_types: list[EventType] | None = Query(default=None),
    athlete_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    mine_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventListItem]:
    # Padres siempre con mine_only=True (forzado en servidor)
    if current_user.role == UserRole.parent:
        mine_only = True

    # Determinar club_id del usuario
    if current_user.role == UserRole.parent:
        # Para padres, buscamos el club de sus atletas
        from app.services.permissions import parent_athlete_ids
        from sqlalchemy import select
        from app.models.athlete import Athlete

        my_athlete_ids = await parent_athlete_ids(db, current_user.id)
        if not my_athlete_ids:
            return []

        result = await db.execute(
            select(Athlete.club_id).where(Athlete.id.in_(my_athlete_ids)).limit(1)
        )
        club_id_row = result.scalar_one_or_none()
        if club_id_row is None:
            return []
        club_id = club_id_row
    else:
        # Admin/coach: usar primer club del usuario
        club_memberships = [m.club_id for m in current_user.club_memberships]
        if not club_memberships:
            return []
        club_id = club_memberships[0]

    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' debe ser anterior o igual a 'to'",
        )

    filters = EventListQuery(
        from_date=from_date,
        to_date=to_date,
        event_types=event_types,
        athlete_id=athlete_id,
        category=category,
        mine_only=mine_only,
    )

    events = await events_svc.list_events_in_range(
        db=db,
        club_id=club_id,
        from_date=from_date,
        to_date=to_date,
        filters=filters,
        viewer=current_user,
    )

    return [
        _event_to_list_item(ev, current_user).model_dump(by_alias=True)  # type: ignore[return-value]
        for ev in events
    ]


# ---------------------------------------------------------------------------
# POST /calendar/events — Crear evento
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventRead)
async def create_calendar_event(
    body: EventCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> EventRead:
    from app.services.notification.task_dispatcher import TaskDispatcher

    if body.event_type == EventType.BIRTHDAY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los cumpleaños se generan automáticamente y no se pueden crear.",
        )

    club_id = await _get_club_id_for_user(db, current_user)
    dispatcher = TaskDispatcher(background_tasks)

    try:
        event = await events_svc.create_event(
            db=db,
            payload=body,
            user=current_user,
            club_id=club_id,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return EventRead.model_validate(event)


# ---------------------------------------------------------------------------
# GET /calendar/events/{id} — Detalle
# ---------------------------------------------------------------------------


@router.get("/{event_id}", response_model=Union[EventRead, EventReadParent])
async def get_calendar_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Union[EventRead, EventReadParent]:
    event = await _get_event_or_404(db, event_id)

    if not await can_view_calendar_event(db, current_user, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver este evento",
        )

    return _serialize_event(event, current_user)


# ---------------------------------------------------------------------------
# PATCH /calendar/events/{id} — Actualizar
# ---------------------------------------------------------------------------


@router.patch("/{event_id}", response_model=EventRead)
async def update_calendar_event(
    event_id: int,
    body: EventUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service=Depends(get_notification_service),
) -> EventRead:
    event = await _get_event_or_404(db, event_id)

    if event.event_type == EventType.BIRTHDAY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los cumpleaños son automáticos y no se pueden editar.",
        )

    if not await can_edit_calendar_event(db, current_user, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para editar este evento",
        )

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    try:
        updated = await events_svc.update_event(
            db=db,
            event=event,
            payload=body,
            user=current_user,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return EventRead.model_validate(updated)


# ---------------------------------------------------------------------------
# DELETE /calendar/events/{id} — Soft cancel
# ---------------------------------------------------------------------------


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_calendar_event(
    event_id: int,
    reason: str = Query(default=""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    notification_service=Depends(get_notification_service),
) -> None:
    event = await _get_event_or_404(db, event_id)

    if event.event_type == EventType.BIRTHDAY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los cumpleaños son automáticos y no se pueden cancelar.",
        )

    if not await can_edit_calendar_event(db, current_user, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para cancelar este evento",
        )

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    try:
        await events_svc.cancel_event(
            db=db,
            event=event,
            reason=reason,
            user=current_user,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# DELETE /calendar/events/{id}/permanent — Hard delete
# ---------------------------------------------------------------------------


@router.delete("/{event_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event_permanent(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    event = await _get_event_or_404(db, event_id)

    if event.event_type == EventType.BIRTHDAY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los cumpleaños son virtuales y no se pueden borrar permanentemente.",
        )

    if not await can_edit_calendar_event(db, current_user, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para borrar este evento permanentemente",
        )

    await events_svc.delete_event_permanent(db, event)


# ---------------------------------------------------------------------------
# POST /calendar/events/{id}/rsvp — RSVP de atleta
# ---------------------------------------------------------------------------


@router.post("/{event_id}/rsvp", response_model=EventAttendanceRead)
async def rsvp_calendar_event(
    event_id: int,
    body: RSVPUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventAttendanceRead:
    event = await _get_event_or_404(db, event_id)

    if event.event_type == EventType.BIRTHDAY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede hacer RSVP a un cumpleaños.",
        )

    if not await can_rsvp_event(db, current_user, event, body.athlete_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para registrar RSVP en este evento",
        )

    try:
        attendance = await attendance_svc.rsvp(
            db=db,
            event=event,
            athlete_id=body.athlete_id,
            status=body.rsvp_status,
            by_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return EventAttendanceRead.model_validate(attendance)


# ---------------------------------------------------------------------------
# GET /calendar/events/{id}/attendances — Lista de asistencias
# ---------------------------------------------------------------------------


@router.get("/{event_id}/attendances", response_model=list[EventAttendanceRead])
async def list_event_attendances(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventAttendanceRead]:
    event = await _get_event_or_404(db, event_id)

    if not await can_view_calendar_event(db, current_user, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver las asistencias de este evento",
        )

    # Privacy: parents may only see their own children's attendances, never
    # other minors'. Coaches/admins see the whole roster.
    parent_only_ids: set[int] | None = None
    if current_user.role == UserRole.parent:
        from app.services.permissions import parent_athlete_ids

        parent_only_ids = set(await parent_athlete_ids(db, current_user.id))

    # Para TRAINING_SESSION, redirigir al servicio de session_attendance
    if event.event_type == EventType.TRAINING_SESSION:
        ts_id = (event.event_data or {}).get("training_session_id")
        if ts_id is None:
            return []

        from sqlalchemy import select as sa_select
        from app.models.training_session import SessionAttendance

        result = await db.execute(
            sa_select(SessionAttendance).where(SessionAttendance.session_id == ts_id)
        )
        sa_records = list(result.scalars().all())

        if parent_only_ids is not None:
            sa_records = [a for a in sa_records if a.athlete_id in parent_only_ids]

        # Mapear SessionAttendance a EventAttendanceRead (campos compatibles)
        return [
            EventAttendanceRead(
                id=a.id,
                event_id=event_id,
                athlete_id=a.athlete_id,
                rsvp_status=None,  # type: ignore[arg-type]
                rsvp_at=None,
                rsvp_by_user_id=None,
                actual_status=None,  # type: ignore[arg-type]
                notes=a.excuse_reason,
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in sa_records
        ]

    attendances = await attendance_svc.list_attendances(db, event)
    if parent_only_ids is not None:
        attendances = [a for a in attendances if a.athlete_id in parent_only_ids]
    return [EventAttendanceRead.model_validate(a) for a in attendances]
