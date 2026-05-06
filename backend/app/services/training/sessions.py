"""Lógica de negocio para sesiones de entrenamiento."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

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
        age_group=payload.age_group,
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

    await db.commit()
    await db.refresh(session)

    # Notificar a padres solo si la sesión quedó planificada
    if notification_service is not None and session.status == SessionStatus.PLANNED:
        await _notify_parents(
            db=db,
            session=session,
            coach=coach,
            club_id=club_id,
            convocados_athlete_ids=payload.convocados_athlete_ids,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return session


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


async def update_session(
    db: AsyncSession,
    session_id: int,
    payload: TrainingSessionUpdate,
) -> TrainingSession:
    """Actualiza campos editables de una sesión planificada."""
    session = await _get_session_or_raise(db, session_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "strava_url" in update_data and update_data["strava_url"] is not None:
        update_data["strava_url"] = str(update_data["strava_url"])

    for field, value in update_data.items():
        setattr(session, field, value)

    await db.commit()
    await db.refresh(session)
    return session


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
    await db.refresh(session)
    return session


async def cancel_session(db: AsyncSession, session_id: int) -> TrainingSession:
    """Soft delete: cambia el estado a CANCELLED sin borrar registros."""
    session = await _get_session_or_raise(db, session_id)

    if session.status == SessionStatus.CANCELLED:
        raise ValueError("La sesión ya está cancelada")

    session.status = SessionStatus.CANCELLED
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    *,
    club_id: int,
    age_group: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    athlete_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TrainingSession]:
    """Lista sesiones del club con filtros opcionales."""
    from datetime import date

    stmt = select(TrainingSession).where(TrainingSession.club_id == club_id)

    if age_group:
        stmt = stmt.where(TrainingSession.age_group == age_group)
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
    if athlete_id:
        stmt = stmt.where(
            TrainingSession.id.in_(
                select(SessionAttendance.session_id).where(
                    SessionAttendance.athlete_id == athlete_id
                )
            )
        )

    stmt = (
        stmt.order_by(TrainingSession.scheduled_date.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(TrainingSession.attendances))
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_session(db: AsyncSession, session_id: int) -> TrainingSession | None:
    """Retorna la sesión por ID, o None si no existe."""
    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.id == session_id)
        .options(selectinload(TrainingSession.attendances))
    )
    return result.scalar_one_or_none()


async def _get_session_or_raise(db: AsyncSession, session_id: int) -> TrainingSession:
    """Retorna la sesión o lanza ValueError si no existe."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Sesión {session_id} no encontrada")
    return session
