"""Lógica de negocio para sesiones de entrenamiento."""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.club import Club, ClubMember
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.models.user import User
from app.schemas.training_session import TrainingSessionCreate, TrainingSessionUpdate

if TYPE_CHECKING:
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttle en memoria: evita duplicados dentro de 60 min
# (sin tabla notification_log — TODO: persistir en sprint 2)
# ---------------------------------------------------------------------------

_THROTTLE_TTL = timedelta(minutes=60)
_recent_dispatches: dict[tuple, datetime] = {}


def _should_throttle(parent_id: int, athlete_id: int, kind: str) -> bool:
    """Retorna True si ya se despachó el mismo (parent, athlete, kind) en <60 min."""
    now = datetime.now(timezone.utc)
    # Limpiar entradas expiradas
    expired = [k for k, ts in _recent_dispatches.items() if now - ts > _THROTTLE_TTL]
    for k in expired:
        del _recent_dispatches[k]

    key = (parent_id, athlete_id, kind)
    if key in _recent_dispatches:
        return True
    _recent_dispatches[key] = now
    return False


def _hash_id(value: int) -> str:
    """Hash corto de un ID para logs sin exponer el valor real."""
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


# Etiquetas legibles en español para el diff de update_session
_FIELD_LABELS: dict[str, str] = {
    "scheduled_date": "Fecha",
    "scheduled_start_time": "Hora de inicio",
    "duration_min": "Duración (min)",
    "location": "Lugar",
    "technical_focus": "Foco técnico",
    "description": "Descripción",
    "route_text": "Recorrido",
    "strava_url": "Link Strava",
    "coach_notes": "Notas del entrenador",
}


def _humanize(value: Any) -> str:
    """Convierte un valor del modelo a texto legible para el email."""
    if value is None or value == "":
        return "—"
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


async def _assert_coach_in_club(
    db: AsyncSession, user_id: int, club_id: int
) -> None:
    """Lanza ValueError si el usuario no pertenece al club."""
    result = await db.execute(
        select(ClubMember.id).where(
            ClubMember.user_id == user_id,
            ClubMember.club_id == club_id,
        )
    )
    if result.first() is None:
        raise ValueError("El usuario no pertenece al club especificado")


async def create_session(
    db: AsyncSession,
    payload: TrainingSessionCreate,
    coach: User,
    club_id: int,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> TrainingSession:
    """
    Crea una sesión planificada y genera filas de asistencia para cada atleta
    convocado con estado AUSENTE como placeholder (se actualizan al ejecutar).

    Si se provee notification_service, despacha emails a los padres de los
    convocados de forma asíncrona (no bloquea la respuesta al cliente).
    """
    await _assert_coach_in_club(db, coach.id, club_id)

    session = TrainingSession(
        club_id=club_id,
        created_by_user_id=coach.id,
        status=SessionStatus.PLANNED,
        scheduled_date=payload.scheduled_date,
        scheduled_start_time=payload.scheduled_start_time,
        duration_min=payload.duration_min,
        location=payload.location,
        technical_focus=payload.technical_focus,
        description=payload.description,
        route_text=payload.route_text,
        strava_url=str(payload.strava_url) if payload.strava_url else None,
        coach_notes=payload.coach_notes,
    )
    db.add(session)
    await db.flush()  # obtener session.id antes de crear asistencias

    for athlete_id in payload.convocados_athlete_ids:
        db.add(
            SessionAttendance(
                session_id=session.id,
                athlete_id=athlete_id,
                # AUSENTE como placeholder — se sobreescribe al ejecutar la sesión
                status=AttendanceStatus.AUSENTE,
            )
        )

    # Crear CalendarEvent paralelo en la misma transacción
    await _create_parallel_calendar_event(db, session, payload, coach, club_id)

    await db.commit()

    # Recargar con selectinload para que el router pueda acceder a session.attendances
    # sin disparar lazy loading en contexto async (que provoca MissingGreenlet).
    refreshed = await get_session(db, session.id)
    assert refreshed is not None  # acabamos de crearla

    # Notificar a padres solo si el coach lo solicitó explícitamente,
    # la sesión quedó planificada y es a futuro.
    is_future = refreshed.scheduled_date >= date.today()
    if (
        payload.send_notification
        and notification_service is not None
        and refreshed.status == SessionStatus.PLANNED
        and is_future
    ):
        await _notify_parents(
            db=db,
            session=refreshed,
            coach=coach,
            club_id=club_id,
            convocados_athlete_ids=payload.convocados_athlete_ids,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def _notify_parents(
    db: AsyncSession,
    session: TrainingSession,
    coach: User,
    club_id: int,
    convocados_athlete_ids: list[int],
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Despacha notificaciones a todos los padres de los atletas convocados."""
    if not convocados_athlete_ids:
        return

    # Resolver nombre del club
    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    # Nombre del coach
    coach_name = f"{coach.first_name} {coach.last_name}".strip() or (
        coach.email.split("@")[0] if coach.email else "Entrenador"
    )

    # Formato legible de fecha y hora
    session_date = session.scheduled_date.strftime("%-d de %B de %Y") if session.scheduled_date else ""
    session_time = (
        session.scheduled_start_time.strftime("%H:%M")
        if session.scheduled_start_time
        else "Por definir"
    )

    # Cargar relaciones padre-atleta en una sola query
    from app.models.athlete import Athlete, ParentAthlete

    stmt = (
        select(ParentAthlete, Athlete)
        .join(Athlete, Athlete.id == ParentAthlete.athlete_id)
        .join(User, User.id == ParentAthlete.parent_id)
        .where(ParentAthlete.athlete_id.in_(convocados_athlete_ids))
        .options(selectinload(ParentAthlete.parent))
    )
    rows = await db.execute(stmt)
    pairs = rows.all()

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()

        try:
            await _dispatch_invitation(
                notification_service=notification_service,
                dispatcher=dispatcher,
                parent=parent,
                athlete_id=athlete.id,
                athlete_name=athlete_name,
                session=session,
                session_date=session_date,
                session_time=session_time,
                coach_name=coach_name,
                club_name=club_name,
            )
        except Exception as exc:
            logger.warning(
                "Error despachando notificación | parent_hash=%s athlete_hash=%s kind=training_session_invite error_type=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                type(exc).__name__,
            )


async def _dispatch_invitation(
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
    parent: User,
    athlete_id: int,
    athlete_name: str,
    session: TrainingSession,
    session_date: str,
    session_time: str,
    coach_name: str,
    club_name: str,
) -> None:
    """Despacha la invitación a un padre/acudiente, respetando el throttle."""
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    kind = "training_session_invite"

    if _should_throttle(parent.id, athlete_id, kind):
        logger.debug(
            "Throttle activo — omitiendo notificación | parent_hash=%s athlete_hash=%s kind=%s",
            _hash_id(parent.id),
            _hash_id(athlete_id),
            kind,
        )
        return

    parent_name = f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"

    request = NotificationRequest(
        recipient=NotificationRecipient(email=parent.email, name=parent_name),
        template=NotificationTemplate.TRAINING_SESSION_INVITE,
        context={
            "parent_name": parent_name,
            "athlete_name": athlete_name,
            "session_date": session_date,
            "session_time": session_time,
            "location": session.location or "Por definir",
            "technical_focus": session.technical_focus or "General",
            "duration_min": session.duration_min,
            "coach_name": coach_name,
            "club_name": club_name,
        },
        send_async=True,
    )

    await notification_service.send(request, dispatcher=dispatcher)
    logger.info(
        "Invitación despachada | parent_hash=%s athlete_hash=%s session_id=%s kind=%s",
        _hash_id(parent.id),
        _hash_id(athlete_id),
        session.id,
        kind,
    )


async def _notify_parents_update(
    db: AsyncSession,
    session: TrainingSession,
    coach: User,
    club_id: int,
    convocados_athlete_ids: list[int],
    changes: list[dict[str, str]],
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Despacha emails `training_session_updated` a los padres de los convocados."""
    if not convocados_athlete_ids or not changes:
        return

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    coach_name = f"{coach.first_name} {coach.last_name}".strip() or (
        coach.email.split("@")[0] if coach.email else "Entrenador"
    )

    session_date = (
        session.scheduled_date.strftime("%-d de %B de %Y")
        if session.scheduled_date
        else ""
    )
    session_time = (
        session.scheduled_start_time.strftime("%H:%M")
        if session.scheduled_start_time
        else "Por definir"
    )

    from app.models.athlete import Athlete, ParentAthlete

    stmt = (
        select(ParentAthlete, Athlete)
        .join(Athlete, Athlete.id == ParentAthlete.athlete_id)
        .join(User, User.id == ParentAthlete.parent_id)
        .where(ParentAthlete.athlete_id.in_(convocados_athlete_ids))
        .options(selectinload(ParentAthlete.parent))
    )
    rows = await db.execute(stmt)
    pairs = rows.all()

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()
        try:
            await _dispatch_update(
                notification_service=notification_service,
                dispatcher=dispatcher,
                parent=parent,
                athlete_id=athlete.id,
                athlete_name=athlete_name,
                session=session,
                session_date=session_date,
                session_time=session_time,
                coach_name=coach_name,
                club_name=club_name,
                changes=changes,
            )
        except Exception as exc:
            logger.warning(
                "Error despachando notificación update | parent_hash=%s athlete_hash=%s kind=training_session_updated error_type=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                type(exc).__name__,
            )


async def _dispatch_update(
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
    parent: User,
    athlete_id: int,
    athlete_name: str,
    session: TrainingSession,
    session_date: str,
    session_time: str,
    coach_name: str,
    club_name: str,
    changes: list[dict[str, str]],
) -> None:
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    kind = "training_session_updated"

    if _should_throttle(parent.id, athlete_id, kind):
        logger.debug(
            "Throttle activo — omitiendo notificación | parent_hash=%s athlete_hash=%s kind=%s",
            _hash_id(parent.id),
            _hash_id(athlete_id),
            kind,
        )
        return

    parent_name = (
        f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"
    )

    request = NotificationRequest(
        recipient=NotificationRecipient(email=parent.email, name=parent_name),
        template=NotificationTemplate.TRAINING_SESSION_UPDATED,
        context={
            "parent_name": parent_name,
            "athlete_name": athlete_name,
            "session_date": session_date,
            "session_time": session_time,
            "location": session.location or "Por definir",
            "technical_focus": session.technical_focus or "General",
            "duration_min": session.duration_min,
            "coach_name": coach_name,
            "club_name": club_name,
            "changes": changes,
        },
        send_async=True,
    )

    await notification_service.send(request, dispatcher=dispatcher)
    logger.info(
        "Update despachado | parent_hash=%s athlete_hash=%s session_id=%s kind=%s",
        _hash_id(parent.id),
        _hash_id(athlete_id),
        session.id,
        kind,
    )


async def _notify_parents_cancel(
    db: AsyncSession,
    session: TrainingSession,
    coach: User,
    club_id: int,
    convocados_athlete_ids: list[int],
    reason: str | None,
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Despacha emails `training_session_cancelled` a los padres de los convocados."""
    if not convocados_athlete_ids:
        return

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    coach_name = f"{coach.first_name} {coach.last_name}".strip() or (
        coach.email.split("@")[0] if coach.email else "Entrenador"
    )

    session_date = (
        session.scheduled_date.strftime("%-d de %B de %Y")
        if session.scheduled_date
        else ""
    )
    session_time = (
        session.scheduled_start_time.strftime("%H:%M")
        if session.scheduled_start_time
        else "Por definir"
    )

    from app.models.athlete import Athlete, ParentAthlete

    stmt = (
        select(ParentAthlete, Athlete)
        .join(Athlete, Athlete.id == ParentAthlete.athlete_id)
        .join(User, User.id == ParentAthlete.parent_id)
        .where(ParentAthlete.athlete_id.in_(convocados_athlete_ids))
        .options(selectinload(ParentAthlete.parent))
    )
    rows = await db.execute(stmt)
    pairs = rows.all()

    for pa, athlete in pairs:
        parent = pa.parent
        if parent is None or not parent.email:
            continue

        athlete_name = f"{athlete.first_name} {athlete.last_name}".strip()
        try:
            await _dispatch_cancel(
                notification_service=notification_service,
                dispatcher=dispatcher,
                parent=parent,
                athlete_id=athlete.id,
                athlete_name=athlete_name,
                session=session,
                session_date=session_date,
                session_time=session_time,
                coach_name=coach_name,
                club_name=club_name,
                reason=reason or "",
            )
        except Exception as exc:
            logger.warning(
                "Error despachando notificación cancel | parent_hash=%s athlete_hash=%s kind=training_session_cancelled error_type=%s",
                _hash_id(parent.id),
                _hash_id(athlete.id),
                type(exc).__name__,
            )


async def _dispatch_cancel(
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
    parent: User,
    athlete_id: int,
    athlete_name: str,
    session: TrainingSession,
    session_date: str,
    session_time: str,
    coach_name: str,
    club_name: str,
    reason: str,
) -> None:
    from app.schemas.notification import (
        NotificationRecipient,
        NotificationRequest,
        NotificationTemplate,
    )

    kind = "training_session_cancelled"

    if _should_throttle(parent.id, athlete_id, kind):
        logger.debug(
            "Throttle activo — omitiendo notificación | parent_hash=%s athlete_hash=%s kind=%s",
            _hash_id(parent.id),
            _hash_id(athlete_id),
            kind,
        )
        return

    parent_name = (
        f"{parent.first_name} {parent.last_name}".strip() or "Padre/Acudiente"
    )

    request = NotificationRequest(
        recipient=NotificationRecipient(email=parent.email, name=parent_name),
        template=NotificationTemplate.TRAINING_SESSION_CANCELLED,
        context={
            "parent_name": parent_name,
            "athlete_name": athlete_name,
            "session_date": session_date,
            "session_time": session_time,
            "location": session.location or "Por definir",
            "coach_name": coach_name,
            "club_name": club_name,
            "reason": reason,
        },
        send_async=True,
    )

    await notification_service.send(request, dispatcher=dispatcher)
    logger.info(
        "Cancel despachado | parent_hash=%s athlete_hash=%s session_id=%s kind=%s",
        _hash_id(parent.id),
        _hash_id(athlete_id),
        session.id,
        kind,
    )


async def _create_parallel_calendar_event(
    db: AsyncSession,
    session: TrainingSession,
    payload: "TrainingSessionCreate",
    coach: User,
    club_id: int,
) -> None:
    """Crea el CalendarEvent paralelo a una TrainingSession recién creada.

    Operación silenciosa: si falla (ej. datos inconsistentes), loguea y continúa
    para no bloquear la creación de la sesión.
    NO dispara notificaciones CALENDAR_EVENT_INVITE — la sesión ya usa TRAINING_SESSION_INVITE.
    """
    try:
        from datetime import datetime, timezone as tz, timedelta

        from app.models.calendar_event import (
            AudienceType,
            CalendarEvent,
            EventAudience,
            EventStatus,
            EventType,
        )

        # Construir start_at y end_at desde la sesión
        scheduled_dt = datetime.combine(
            session.scheduled_date, session.scheduled_start_time
        ).replace(tzinfo=tz.utc)
        end_dt = scheduled_dt + timedelta(minutes=session.duration_min)

        event = CalendarEvent(
            club_id=club_id,
            event_type=EventType.TRAINING_SESSION,
            status=EventStatus.SCHEDULED,
            title=session.technical_focus,
            description=session.description,
            location=session.location,
            start_at=scheduled_dt,
            end_at=end_dt,
            all_day=False,
            timezone="America/Bogota",
            event_data={"training_session_id": session.id},
            created_by_user_id=coach.id,
        )
        db.add(event)
        await db.flush()

        # Crear audiencia ATHLETE_LIST con los convocados
        if payload.convocados_athlete_ids:
            db.add(
                EventAudience(
                    event_id=event.id,
                    audience_type=AudienceType.ATHLETE_LIST,
                    audience_value={"athlete_ids": list(payload.convocados_athlete_ids)},
                )
            )

        # Enlazar la sesión al evento
        session.calendar_event_id = event.id

        logger.debug(
            "CalendarEvent paralelo creado | session_id=%s event_id=%s",
            session.id,
            event.id,
        )
    except Exception as exc:
        logger.warning(
            "No se pudo crear CalendarEvent paralelo para session_id=%s error=%s",
            session.id,
            type(exc).__name__,
        )


async def update_session(
    db: AsyncSession,
    session_id: int,
    payload: TrainingSessionUpdate,
    *,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> TrainingSession:
    """Actualiza campos editables de una sesión planificada.

    Si `payload.send_notification` y se provee `notification_service`, despacha
    `training_session_updated` a los padres de los atletas convocados, incluyendo
    la lista de campos modificados (old → new) en el contexto del template.
    """
    session = await _get_session_or_raise(db, session_id)

    update_data = payload.model_dump(exclude_unset=True, exclude={"send_notification"})
    if "strava_url" in update_data and update_data["strava_url"] is not None:
        update_data["strava_url"] = str(update_data["strava_url"])

    # Capturar valores anteriores ANTES de mutar la sesión
    previous_values: dict[str, Any] = {
        field: getattr(session, field) for field in update_data
    }

    for field, value in update_data.items():
        setattr(session, field, value)

    await db.commit()
    refreshed = await get_session(db, session.id)
    assert refreshed is not None

    # Computar diff legible (solo campos que cambiaron)
    changes: list[dict[str, str]] = []
    for field, new_val in update_data.items():
        old_val = previous_values[field]
        if old_val != new_val:
            changes.append(
                {
                    "field_label": _FIELD_LABELS.get(field, field),
                    "old": _humanize(old_val),
                    "new": _humanize(new_val),
                }
            )

    is_future = refreshed.scheduled_date >= date.today()
    if (
        payload.send_notification
        and notification_service is not None
        and changes
        and refreshed.status == SessionStatus.PLANNED
        and is_future
    ):
        convocados = [a.athlete_id for a in (refreshed.attendances or [])]
        coach = await _load_session_coach(db, refreshed)
        await _notify_parents_update(
            db=db,
            session=refreshed,
            coach=coach,
            club_id=refreshed.club_id,
            convocados_athlete_ids=convocados,
            changes=changes,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def execute_session(db: AsyncSession, session_id: int) -> TrainingSession:
    """
    Marca la sesión como ejecutada y registra el timestamp.
    Lanza ValueError si ya fue ejecutada o cancelada.
    """
    session = await _get_session_or_raise(db, session_id)

    if session.status != SessionStatus.PLANNED:
        raise ValueError(
            f"No se puede ejecutar una sesión en estado '{session.status.value}'"
        )

    session.status = SessionStatus.EXECUTED
    session.executed_at = datetime.now(timezone.utc)

    await db.commit()
    refreshed = await get_session(db, session.id)
    assert refreshed is not None
    return refreshed


async def cancel_session(
    db: AsyncSession,
    session_id: int,
    *,
    send_notification: bool = False,
    reason: str | None = None,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> TrainingSession:
    """Soft delete: cambia el estado a CANCELLED sin borrar registros.

    Si `send_notification` y la sesión era futura PLANNED, despacha
    `training_session_cancelled` a los padres de los convocados.
    """
    session = await _get_session_or_raise(db, session_id)

    if session.status == SessionStatus.CANCELLED:
        raise ValueError("La sesión ya está cancelada")

    was_future_planned = (
        session.status == SessionStatus.PLANNED
        and session.scheduled_date >= date.today()
    )
    convocados_snapshot = [a.athlete_id for a in (session.attendances or [])]

    session.status = SessionStatus.CANCELLED
    await db.commit()
    refreshed = await get_session(db, session.id)
    assert refreshed is not None

    if (
        send_notification
        and notification_service is not None
        and was_future_planned
        and convocados_snapshot
    ):
        coach = await _load_session_coach(db, refreshed)
        await _notify_parents_cancel(
            db=db,
            session=refreshed,
            coach=coach,
            club_id=refreshed.club_id,
            convocados_athlete_ids=convocados_snapshot,
            reason=reason,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def update_convocatoria(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
    *,
    send_notification: bool = False,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
) -> list[SessionAttendance]:
    """Bulk-set de convocatoria; si `send_notification`, notifica a los nuevos
    convocados con `training_session_invite`.

    Delega la mutación a `attendance.bulk_upsert_convocatoria` y orquesta el
    envío de emails comparando contra los convocados previos.
    """
    from app.services.training import attendance as attendance_svc

    session = await _get_session_or_raise(db, session_id)
    previous_ids = {a.athlete_id for a in (session.attendances or [])}

    attendances = await attendance_svc.bulk_upsert_convocatoria(
        db=db, session_id=session_id, athlete_ids=athlete_ids
    )

    added_ids = [aid for aid in athlete_ids if aid not in previous_ids]
    is_future = session.scheduled_date >= date.today()

    if (
        send_notification
        and notification_service is not None
        and added_ids
        and session.status == SessionStatus.PLANNED
        and is_future
    ):
        # Recargar sesión con atletas para tener datos frescos en el email
        refreshed = await get_session(db, session_id)
        assert refreshed is not None
        coach = await _load_session_coach(db, refreshed)
        await _notify_parents(
            db=db,
            session=refreshed,
            coach=coach,
            club_id=refreshed.club_id,
            convocados_athlete_ids=added_ids,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return attendances


async def _load_session_coach(db: AsyncSession, session: TrainingSession) -> User:
    """Carga el usuario creador de la sesión (coach) — se usa para el contexto
    de los emails de update/cancel/update_convocatoria.
    """
    result = await db.execute(
        select(User).where(User.id == session.created_by_user_id)
    )
    coach = result.scalar_one_or_none()
    if coach is None:  # pragma: no cover — invariante de FK NOT NULL
        raise ValueError(
            f"Coach con id={session.created_by_user_id} no encontrado"
        )
    return coach


async def list_sessions(
    db: AsyncSession,
    *,
    club_id: int | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    athlete_id: int | None = None,
    athlete_ids: set[int] | None = None,
    club_ids: set[int] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TrainingSession]:
    """Lista sesiones con filtros opcionales.

    Acepta los filtros singulares legacy (``club_id``, ``athlete_id``) y los
    plurales (``club_ids``, ``athlete_ids``) introducidos para resolver
    N+1: el caller del rol *parent* puede ahora pedir en UNA query las
    sesiones de todos sus hijos. Ambas variantes son compatibles entre
    sí; los valores singulares se mergean con los respectivos sets.
    """
    from datetime import date

    stmt = select(TrainingSession)

    # Club filter (singular + plural mergeable).
    effective_club_ids: set[int] = set(club_ids) if club_ids else set()
    if club_id is not None:
        effective_club_ids.add(club_id)
    if effective_club_ids:
        if len(effective_club_ids) == 1:
            stmt = stmt.where(TrainingSession.club_id == next(iter(effective_club_ids)))
        else:
            stmt = stmt.where(TrainingSession.club_id.in_(effective_club_ids))

    if status:
        stmt = stmt.where(TrainingSession.status == status)
    if date_from:
        stmt = stmt.where(
            TrainingSession.scheduled_date >= date.fromisoformat(date_from)
        )
    if date_to:
        stmt = stmt.where(
            TrainingSession.scheduled_date <= date.fromisoformat(date_to)
        )

    # Athlete filter — singular preserva compatibilidad, plural elimina N+1.
    effective_athlete_ids: set[int] = set(athlete_ids) if athlete_ids else set()
    if athlete_id is not None:
        effective_athlete_ids.add(athlete_id)
    if effective_athlete_ids:
        stmt = stmt.where(
            TrainingSession.id.in_(
                select(SessionAttendance.session_id).where(
                    SessionAttendance.athlete_id.in_(effective_athlete_ids)
                )
            )
        )

    from app.models.session_media import SessionMedia

    stmt = (
        stmt.order_by(
            TrainingSession.scheduled_date.desc(),
            TrainingSession.scheduled_start_time.desc(),
            TrainingSession.id.desc(),
        )
        .limit(limit)
        .offset(offset)
        .options(
            selectinload(TrainingSession.attendances),
            selectinload(TrainingSession.media).selectinload(SessionMedia.athletes),
        )
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_session(db: AsyncSession, session_id: int) -> TrainingSession | None:
    """Retorna la sesión por ID, o None si no existe."""
    from app.models.session_media import SessionMedia

    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.id == session_id)
        .options(
            selectinload(TrainingSession.attendances).selectinload(
                SessionAttendance.athlete
            ),
            selectinload(TrainingSession.media).selectinload(SessionMedia.athletes),
        )
    )
    return result.scalar_one_or_none()


async def _get_session_or_raise(db: AsyncSession, session_id: int) -> TrainingSession:
    """Retorna la sesión o lanza ValueError si no existe."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Sesión {session_id} no encontrada")
    return session
