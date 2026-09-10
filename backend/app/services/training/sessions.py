"""Lógica de negocio para sesiones de entrenamiento."""

from __future__ import annotations

import enum
import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.club import Club, ClubMember
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.user import User, UserRole
from app.schemas.training_session import TrainingSessionCreate, TrainingSessionUpdate
from app.services.audit import (
    AUDIT_REASON_LABELS,
    VALUE_ALLOWLIST,
    AuditAction,
    AuditEntityType,
    AuditReasonCode,
    CancelReasonCode,
    compute_changed_fields,
    record_audit,
)
from app.services.request_context import AuditContext

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
    "session_kind": "Tipo de sesión",
    "objectives": "Objetivos",
    "route_text": "Recorrido",
    "strava_url": "Link Strava",
    "coach_notes": "Notas del entrenador",
}


def _humanize(value: Any) -> str:
    """Convierte un valor del modelo a texto legible para el email."""
    if value is None or value == "":
        return "—"
    if isinstance(value, enum.Enum):
        return str(value.value)
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


# ---------------------------------------------------------------------------
# Entrenadores a cargo de la sesión (feature 041, contracts/session-coaches.md
# §3). El conjunto es de REEMPLAZO completo: nunca un parche.
# ---------------------------------------------------------------------------


class SessionCoachValidationError(ValueError):
    """Payload de entrenadores inválido — el router lo traduce a 422 (V1-V4)."""


class SessionCoachConflictError(ValueError):
    """La sesión quedaría sin ningún entrenador — el router lo traduce a 409 (V6)."""


#: Roles que pueden figurar como entrenador de una sesión (V2). Se acepta
#: `admin` además de `coach` porque el router ya permite a un administrador
#: crear y editar sesiones, y el backfill B1 de la migración copia
#: `created_by_user_id`, que en filas anteriores a 041 puede ser un admin.
#: El selector de la UI sigue listando solo `role=coach` (FR-024).
_COACH_ELIGIBLE_ROLES = frozenset({UserRole.coach, UserRole.admin})


def _dedupe_preserving_order(ids: list[int]) -> list[int]:
    """Quita duplicados conservando la primera aparición (§3.2)."""
    seen: set[int] = set()
    ordered: list[int] = []
    for value in ids:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _join_names_es(names: list[str]) -> str:
    """Une nombres en español: "Ana", "Ana y Bruno", "Ana, Bruno y Carla"."""
    clean = [n for n in names if n]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return f"{', '.join(clean[:-1])} y {clean[-1]}"


async def _assert_eligible_coaches(
    db: AsyncSession,
    club_id: int,
    candidate_ids: list[int],
    newly_added_ids: set[int],
) -> None:
    """Aplica las reglas V2, V3 y V4 de §3.3.

    - V2: el id existe y su ``users.role`` está en {coach, admin}.
    - V3: el id tiene membresía en el club de la sesión. Comparte el mensaje
      de V2 a propósito: el entrenador no debe poder deducir si un id existe
      en otro club.
    - V4: un id **recién agregado** no puede estar inactivo. Los que ya
      estaban asignados y ahora están inactivos se aceptan (V5): no se
      reescribe la historia por una desactivación posterior.
    """
    if not candidate_ids:
        return

    rows = await db.execute(
        select(User.id, User.is_active)
        .join(ClubMember, ClubMember.user_id == User.id)
        .where(
            User.id.in_(candidate_ids),
            User.role.in_(_COACH_ELIGIBLE_ROLES),
            ClubMember.club_id == club_id,
        )
    )
    eligible = {user_id: is_active for user_id, is_active in rows.all()}

    not_coaches = sorted(set(candidate_ids) - set(eligible))
    if not_coaches:
        raise SessionCoachValidationError(
            f"Los siguientes usuarios no son entrenadores del club: {not_coaches}"
        )

    inactive_new = sorted(
        user_id
        for user_id in newly_added_ids
        if not eligible.get(user_id, False)
    )
    if inactive_new:
        raise SessionCoachValidationError(
            f"No puedes asignar a un entrenador inactivo: {inactive_new}"
        )


async def _current_coach_ids_locked(db: AsyncSession, session_id: int) -> set[int]:
    """Lee los entrenadores actuales bloqueando las filas (``FOR UPDATE``).

    El bloqueo (research R-18) hace que dos reemplazos concurrentes se
    serialicen en un conjunto coherente en vez de intercalarse. En SQLite el
    dialecto omite ``FOR UPDATE``, que es inocuo para la vía de test offline.
    """
    result = await db.execute(
        select(TrainingSessionCoach.coach_user_id)
        .where(TrainingSessionCoach.session_id == session_id)
        .with_for_update()
    )
    return set(result.scalars().all())


async def _record_coach_audit(
    db: AsyncSession,
    *,
    session: TrainingSession,
    coach_user_id: int,
    action: AuditAction,
    ctx: AuditContext | None,
) -> None:
    """Fila de auditoría por entrenador agregado o quitado (§9).

    ``entity_id`` es el id de la sesión: el puente tiene clave primaria
    compuesta y no un id propio.
    """
    if ctx is None:
        return
    before, after = (
        (None, coach_user_id)
        if action == AuditAction.create
        else (coach_user_id, None)
    )
    await record_audit(
        db,
        action=action,
        entity_type=AuditEntityType.training_session_coach,
        entity_id=session.id,
        actor=ctx.actor,
        actor_kind=ctx.actor_kind,
        club_id=session.club_id,
        changed_fields=["coach_user_id"],
        diff={"coach_user_id": (before, after)},
        request_id=ctx.request_id,
    )


async def _replace_session_coaches(
    db: AsyncSession,
    session: TrainingSession,
    coach_user_ids: list[int],
    *,
    added_by_user_id: int,
    ctx: AuditContext | None = None,
) -> None:
    """Deja el conjunto de entrenadores de la sesión EXACTAMENTE en
    ``coach_user_ids`` (§3.2), auditando cada alta y cada baja (§9).

    No hace commit: la mutación y sus filas de auditoría comparten la
    transacción del llamador (FR-001).
    """
    new_ids_ordered = _dedupe_preserving_order(coach_user_ids)
    new_ids = set(new_ids_ordered)

    if not new_ids:  # V1/V6 a nivel de servicio
        raise SessionCoachConflictError(
            "Una sesión debe tener al menos un entrenador."
        )

    current_ids = await _current_coach_ids_locked(db, session.id)
    to_add = [uid for uid in new_ids_ordered if uid not in current_ids]
    to_remove = sorted(current_ids - new_ids)

    # V4 solo sobre `new_ids - current_ids`; V5 deja pasar a los ya asignados.
    await _assert_eligible_coaches(
        db, session.club_id, new_ids_ordered, set(to_add)
    )

    # Defensa en profundidad (V6): con semántica de reemplazo un payload no
    # vacío nunca puede llegar a cero, pero el conteo se verifica igual.
    if len(current_ids - set(to_remove)) + len(to_add) == 0:  # pragma: no cover
        raise SessionCoachConflictError(
            "Una sesión debe tener al menos un entrenador."
        )

    # Se muta la COLECCIÓN de la relación (que tiene delete-orphan) en vez de
    # emitir DELETE/INSERT sueltos: así la sesión en memoria queda coherente y
    # la relectura posterior no devuelve el conjunto viejo. La colección se
    # carga explícitamente si hace falta: un lazy load en contexto async
    # reventaría con MissingGreenlet.
    if "session_coaches" in sa_inspect(session).unloaded:
        await db.refresh(session, attribute_names=["session_coaches"])
    loaded_rows = {row.coach_user_id: row for row in (session.session_coaches or [])}
    for coach_user_id in to_remove:
        row = loaded_rows.get(coach_user_id)
        if row is not None:
            session.session_coaches.remove(row)
        else:  # pragma: no cover — fila creada por otra transacción
            await db.execute(
                delete(TrainingSessionCoach).where(
                    TrainingSessionCoach.session_id == session.id,
                    TrainingSessionCoach.coach_user_id == coach_user_id,
                )
            )
        await _record_coach_audit(
            db,
            session=session,
            coach_user_id=coach_user_id,
            action=AuditAction.delete,
            ctx=ctx,
        )

    # `added_at` se fija con un desplazamiento creciente para que el orden de
    # inserción quede reflejado en el orden de lectura. En MySQL la columna es
    # DATETIME sin fracción de segundo, así que los microsegundos pueden
    # colapsar en un empate; por eso la lectura desempata por `coach_user_id`
    # (ver `_ordered_session_coaches`).
    base_now = datetime.now(timezone.utc)
    for offset, coach_user_id in enumerate(to_add):
        session.session_coaches.append(
            TrainingSessionCoach(
                session_id=session.id,
                coach_user_id=coach_user_id,
                added_by_user_id=added_by_user_id,
                added_at=base_now + timedelta(microseconds=offset),
            )
        )
        await _record_coach_audit(
            db,
            session=session,
            coach_user_id=coach_user_id,
            action=AuditAction.create,
            ctx=ctx,
        )


def _ordered_session_coaches(
    session: TrainingSession,
) -> list[TrainingSessionCoach]:
    """Filas del puente ordenadas por ``added_at`` y, ante empate, por
    ``coach_user_id`` (ver la nota de precisión en ``_replace_session_coaches``).
    """
    def _key(row: TrainingSessionCoach) -> tuple[datetime, int]:
        # Las filas recién agregadas en memoria traen `added_at` con zona
        # horaria y las releídas de la base vienen sin ella (la columna es
        # DATETIME sin zona): se normaliza a naive-UTC para poder ordenarlas
        # juntas sin un TypeError.
        added_at = row.added_at
        if added_at.tzinfo is not None:
            added_at = added_at.astimezone(timezone.utc).replace(tzinfo=None)
        return (added_at, row.coach_user_id)

    return sorted(session.session_coaches or [], key=_key)


async def _load_session_coaches(
    db: AsyncSession, session: TrainingSession
) -> list[User]:
    """Carga los entrenadores a cargo de la sesión, en orden de ``added_at``.

    Reemplaza al viejo ``_load_session_coach``, que resolvía el "entrenador"
    del email a partir de ``created_by_user_id`` y por eso le decía a las
    familias que había cancelado quien creó la sesión, no quien la canceló
    (el bug de US4).
    """
    result = await db.execute(
        select(User)
        .join(
            TrainingSessionCoach,
            TrainingSessionCoach.coach_user_id == User.id,
        )
        .where(TrainingSessionCoach.session_id == session.id)
        .order_by(
            TrainingSessionCoach.added_at.asc(),
            TrainingSessionCoach.coach_user_id.asc(),
        )
    )
    return list(result.scalars().all())


def _actor_display_name(actor: User) -> str:
    """Nombre legible del actor para el contexto de los emails."""
    name = actor.display_name if hasattr(actor, "display_name") else ""
    if not name:
        name = f"{actor.first_name} {actor.last_name}".strip()
    if not name:
        name = actor.email.split("@")[0] if actor.email else "Entrenador"
    return name


async def _coach_names_context(
    db: AsyncSession, session: TrainingSession, actor: User
) -> tuple[str, list[str], str]:
    """Devuelve ``(acting_coach_name, coach_names, coaches_text)`` de §5.1.

    El cuerpo del email nombra a QUIEN ACTUÓ; la firma nombra a QUIEN DIRIGE.
    """
    coaches = await _load_session_coaches(db, session)
    coach_names = [_actor_display_name(c) for c in coaches]
    if not coach_names:
        # Sesión sin filas de puente (dato previo al backfill): se cae al
        # actor para no dejar la firma vacía en el email.
        coach_names = [_actor_display_name(actor)]
    return _actor_display_name(actor), coach_names, _join_names_es(coach_names)


async def create_session(
    db: AsyncSession,
    payload: TrainingSessionCreate,
    coach: User,
    club_id: int,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
    ctx: AuditContext | None = None,
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
        objectives=payload.objectives,
    )
    # session_kind tiene server_default en el modelo; solo lo fijamos si el
    # coach lo envió explícitamente, para no pisar el default con None.
    if payload.session_kind is not None:
        session.session_kind = payload.session_kind
    db.add(session)
    await db.flush()  # obtener session.id antes de crear asistencias

    # 041 §3.2 — si el payload no trae `coach_user_ids`, el creador queda como
    # único entrenador; si los trae, reemplazan por completo esa membresía.
    await _replace_session_coaches(
        db,
        session,
        payload.coach_user_ids or [coach.id],
        added_by_user_id=coach.id,
        ctx=ctx,
    )

    for athlete_id in payload.convocados_athlete_ids:
        db.add(
            SessionAttendance(
                session_id=session.id,
                athlete_id=athlete_id,
                # AUSENTE como placeholder — se sobreescribe al ejecutar la sesión
                status=AttendanceStatus.AUSENTE,
            )
        )

    if ctx is not None:
        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.training_session,
            entity_id=session.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=club_id,
            meta={
                "convocados_count": len(payload.convocados_athlete_ids),
                "event_date": session.scheduled_date.isoformat(),
            },
            request_id=ctx.request_id,
        )

    # Crear CalendarEvent paralelo en la misma transacción.
    # ctx solo se reenvía cuando existe: mantiene compatible la firma de 5
    # posicionales que consumen los tests preexistentes de integración
    # calendario-entrenamiento (que parchean la función sin parámetro ctx).
    if ctx is not None:
        await _create_parallel_calendar_event(db, session, payload, coach, club_id, ctx=ctx)
    else:
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
            actor=coach,
            club_id=club_id,
            convocados_athlete_ids=payload.convocados_athlete_ids,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def _notify_parents(
    db: AsyncSession,
    session: TrainingSession,
    actor: User,
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

    # 041 §5.1 — quién actuó (cuerpo) y quiénes dirigen la sesión (firma)
    acting_coach_name, coach_names, coaches_text = await _coach_names_context(
        db, session, actor
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
        # Último portón antes de que salga un correo a la familia: un atleta
        # archivado ya no recibe convocatorias, avisos de cambio ni de
        # cancelación (contracts/athlete-archive.md §5.2).
        .where(
            ParentAthlete.athlete_id.in_(convocados_athlete_ids),
            Athlete.deleted_at.is_(None),
        )
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
                acting_coach_name=acting_coach_name,
                coach_names=coach_names,
                coaches_text=coaches_text,
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
    acting_coach_name: str,
    coach_names: list[str],
    coaches_text: str,
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
            "acting_coach_name": acting_coach_name,
            "coach_names": coach_names,
            "coaches_text": coaches_text,
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
    actor: User,
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

    acting_coach_name, coach_names, coaches_text = await _coach_names_context(
        db, session, actor
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
        # Último portón antes de que salga un correo a la familia: un atleta
        # archivado ya no recibe convocatorias, avisos de cambio ni de
        # cancelación (contracts/athlete-archive.md §5.2).
        .where(
            ParentAthlete.athlete_id.in_(convocados_athlete_ids),
            Athlete.deleted_at.is_(None),
        )
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
                acting_coach_name=acting_coach_name,
                coach_names=coach_names,
                coaches_text=coaches_text,
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
    acting_coach_name: str,
    coach_names: list[str],
    coaches_text: str,
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
            "acting_coach_name": acting_coach_name,
            "coach_names": coach_names,
            "coaches_text": coaches_text,
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
    actor: User,
    club_id: int,
    convocados_athlete_ids: list[int],
    reason: str,
    notification_service: "NotificationService",
    dispatcher: "TaskDispatcher | None",
) -> None:
    """Despacha emails `training_session_cancelled` a los padres de los convocados.

    ``reason`` es la ETIQUETA en español del código de motivo (§7.1); nunca
    texto libre escrito por un entrenador (FR-003).
    """
    if not convocados_athlete_ids:
        return

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    club_name = club.name if club else "Club Trocha y Ruta"

    acting_coach_name, coach_names, coaches_text = await _coach_names_context(
        db, session, actor
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
        # Último portón antes de que salga un correo a la familia: un atleta
        # archivado ya no recibe convocatorias, avisos de cambio ni de
        # cancelación (contracts/athlete-archive.md §5.2).
        .where(
            ParentAthlete.athlete_id.in_(convocados_athlete_ids),
            Athlete.deleted_at.is_(None),
        )
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
                acting_coach_name=acting_coach_name,
                coach_names=coach_names,
                coaches_text=coaches_text,
                club_name=club_name,
                reason=reason,
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
    acting_coach_name: str,
    coach_names: list[str],
    coaches_text: str,
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
            "acting_coach_name": acting_coach_name,
            "coach_names": coach_names,
            "coaches_text": coaches_text,
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
    ctx: AuditContext | None = None,
) -> None:
    """Crea el CalendarEvent paralelo a una TrainingSession recién creada.

    Operación silenciosa: si falla (ej. datos inconsistentes), loguea y continúa
    para no bloquear la creación de la sesión. El registro de auditoría queda
    FUERA del try/except silencioso — una fila de auditoría nunca se descarta
    en silencio (contracts/audit-recording.md §1.3).
    NO dispara notificaciones CALENDAR_EVENT_INVITE — la sesión ya usa TRAINING_SESSION_INVITE.
    """
    created_event_id: int | None = None
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
        created_event_id = event.id

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

    if ctx is not None and created_event_id is not None:
        await record_audit(
            db,
            action=AuditAction.create,
            entity_type=AuditEntityType.calendar_event,
            entity_id=created_event_id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=club_id,
            meta={"event_date": session.scheduled_date.isoformat()},
            request_id=ctx.request_id,
        )


async def update_session(
    db: AsyncSession,
    session_id: int,
    payload: TrainingSessionUpdate,
    *,
    actor: User,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
    ctx: AuditContext | None = None,
) -> TrainingSession:
    """Actualiza campos editables de una sesión planificada.

    ``actor`` es de solo-palabra-clave y NO tiene valor por defecto: un
    default dejaría que un futuro llamador registre a la persona equivocada
    en silencio, que es justo la falla que esta feature elimina (§4).

    Si `payload.send_notification` y se provee `notification_service`, despacha
    `training_session_updated` a los padres de los atletas convocados, incluyendo
    la lista de campos modificados (old → new) en el contexto del template.
    """
    session = await _get_session_or_raise(db, session_id)

    update_data = payload.model_dump(
        exclude_unset=True, exclude={"send_notification", "coach_user_ids"}
    )
    # `coach_user_ids` no es una columna de `training_sessions`: se aplica
    # aparte, como conjunto de reemplazo sobre el puente (§3.2).
    if payload.coach_user_ids is not None:
        await _replace_session_coaches(
            db,
            session,
            payload.coach_user_ids,
            added_by_user_id=actor.id,
            ctx=ctx,
        )
    if "strava_url" in update_data and update_data["strava_url"] is not None:
        update_data["strava_url"] = str(update_data["strava_url"])

    # Capturar valores anteriores ANTES de mutar la sesión
    previous_values: dict[str, Any] = {
        field: getattr(session, field) for field in update_data
    }

    for field, value in update_data.items():
        setattr(session, field, value)

    if ctx is not None:
        changed_fields, diff = compute_changed_fields(
            before=previous_values,
            after=update_data,
            allow_list=VALUE_ALLOWLIST[AuditEntityType.training_session],
        )
        await record_audit(
            db,
            action=AuditAction.update,
            entity_type=AuditEntityType.training_session,
            entity_id=session.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=session.club_id,
            changed_fields=changed_fields,
            diff=diff,
            meta={"event_date": session.scheduled_date.isoformat()},
            request_id=ctx.request_id,
        )

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
        convocados = [
            a.athlete_id
            for a in (refreshed.attendances or [])
            if a.archived_at is None
        ]
        await _notify_parents_update(
            db=db,
            session=refreshed,
            actor=actor,
            club_id=refreshed.club_id,
            convocados_athlete_ids=convocados,
            changes=changes,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def execute_session(
    db: AsyncSession,
    session_id: int,
    *,
    actor: User,
    ctx: AuditContext | None = None,
) -> TrainingSession:
    """
    Marca la sesión como ejecutada y registra el timestamp.
    Lanza ValueError si ya fue ejecutada o cancelada.

    ``actor`` es de solo-palabra-clave y sin default (§4): quién ejecutó la
    sesión vive únicamente en ``audit_log`` (§1, estrechamiento de FR-010),
    así que la única forma de responderlo es que el llamador lo pase.
    """
    session = await _get_session_or_raise(db, session_id)

    if session.status != SessionStatus.PLANNED:
        raise ValueError(
            f"No se puede ejecutar una sesión en estado '{session.status.value}'"
        )

    previous_status = session.status
    session.status = SessionStatus.EXECUTED
    session.executed_at = datetime.now(timezone.utc)

    if ctx is not None:
        await record_audit(
            db,
            action=AuditAction.execute,
            entity_type=AuditEntityType.training_session,
            entity_id=session.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=session.club_id,
            changed_fields=["status"],
            diff={
                "status": (previous_status.value, SessionStatus.EXECUTED.value)
            },
            meta={"event_date": session.scheduled_date.isoformat()},
            request_id=ctx.request_id,
        )

    await db.commit()
    refreshed = await get_session(db, session.id)
    assert refreshed is not None
    return refreshed


async def cancel_session(
    db: AsyncSession,
    session_id: int,
    *,
    actor: User,
    reason_code: CancelReasonCode,
    send_notification: bool = False,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
    ctx: AuditContext | None = None,
) -> TrainingSession:
    """Soft delete: cambia el estado a CANCELLED sin borrar registros.

    ``reason_code`` es obligatorio y pertenece al subgrupo ``cancel_*`` del
    catálogo cerrado (§7.1): el texto libre dejó de llegar a las familias y
    dejó de ser un lugar donde un entrenador pudiera escribir el nombre de un
    menor (FR-003). La etiqueta en español se resuelve al despachar el email y
    nunca se persiste.

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
    convocados_snapshot = [
        a.athlete_id
        for a in (session.attendances or [])
        if a.archived_at is None
    ]

    previous_status = session.status
    session.status = SessionStatus.CANCELLED

    if ctx is not None:
        await record_audit(
            db,
            action=AuditAction.cancel,
            entity_type=AuditEntityType.training_session,
            entity_id=session.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=session.club_id,
            changed_fields=["status"],
            diff={
                "status": (previous_status.value, SessionStatus.CANCELLED.value)
            },
            reason_code=AuditReasonCode(reason_code.value),
            meta={"event_date": session.scheduled_date.isoformat()},
            request_id=ctx.request_id,
        )

    await db.commit()
    refreshed = await get_session(db, session.id)
    assert refreshed is not None

    if (
        send_notification
        and notification_service is not None
        and was_future_planned
        and convocados_snapshot
    ):
        await _notify_parents_cancel(
            db=db,
            session=refreshed,
            actor=actor,
            club_id=refreshed.club_id,
            convocados_athlete_ids=convocados_snapshot,
            reason=AUDIT_REASON_LABELS.get(
                AuditReasonCode(reason_code.value), ""
            ),
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return refreshed


async def update_convocatoria(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
    *,
    actor: User,
    send_notification: bool = False,
    notification_service: "NotificationService | None" = None,
    dispatcher: "TaskDispatcher | None" = None,
    ctx: AuditContext | None = None,
) -> list[SessionAttendance]:
    """Bulk-set de convocatoria; si `send_notification`, notifica a los nuevos
    convocados con `training_session_invite`.

    Delega la mutación a `attendance.bulk_upsert_convocatoria` y orquesta el
    envío de emails comparando contra los convocados previos. ``actor`` es
    quien invita: es el nombre que va en el cuerpo del email (§5.1).
    """
    from app.services.training import attendance as attendance_svc

    session = await _get_session_or_raise(db, session_id)
    # Solo los convocados ACTIVOS cuentan como "previos": un atleta con la
    # fila archivada debe volver a recibir invitación al ser re-convocado.
    previous_ids = {
        a.athlete_id
        for a in (session.attendances or [])
        if a.archived_at is None
    }

    attendances = await attendance_svc.bulk_upsert_convocatoria(
        db=db,
        session_id=session_id,
        athlete_ids=athlete_ids,
        actor=actor,
        club_id=session.club_id,
        ctx=ctx,
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
        await _notify_parents(
            db=db,
            session=refreshed,
            actor=actor,
            club_id=refreshed.club_id,
            convocados_athlete_ids=added_ids,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    return attendances


async def list_sessions(
    db: AsyncSession,
    *,
    club_id: int,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    athlete_id: int | None = None,
    coach_user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TrainingSession]:
    """Lista sesiones del club con filtros opcionales.

    ``coach_user_id`` (§8.1) restringe el listado a las sesiones donde ese
    usuario figura en el puente ``training_session_coaches``; se apoya en el
    índice ``ix_tsc_coach_user_id``.
    """
    from datetime import date

    stmt = select(TrainingSession).where(TrainingSession.club_id == club_id)

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
                    SessionAttendance.athlete_id == athlete_id,
                    SessionAttendance.archived_at.is_(None),
                )
            )
        )
    if coach_user_id:
        stmt = stmt.join(
            TrainingSessionCoach,
            (TrainingSessionCoach.session_id == TrainingSession.id)
            & (TrainingSessionCoach.coach_user_id == coach_user_id),
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
            selectinload(TrainingSession.session_coaches).selectinload(
                TrainingSessionCoach.coach
            ),
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
            # 041 §6.1 — atribución de asistencia precargada para que un
            # roster de 20 filas siga costando un número constante de queries.
            selectinload(TrainingSession.attendances).selectinload(
                SessionAttendance.recorded_by
            ),
            selectinload(TrainingSession.attendances).selectinload(
                SessionAttendance.updated_by
            ),
            selectinload(TrainingSession.session_coaches).selectinload(
                TrainingSessionCoach.coach
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
