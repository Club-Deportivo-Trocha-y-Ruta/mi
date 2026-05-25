"""Router para sesiones de entrenamiento, asistencia y upload de recorridos."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Union

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
)
from app.models.athlete import Athlete
from app.models.club import ClubRole
from app.models.session_media import MediaType, SessionMedia
from app.models.training_session import AttendanceStatus, SessionStatus
from app.models.user import User, UserRole
from app.schemas.session_media import (
    SessionMediaRead,
    SessionMediaReadParent,
    SessionMediaUpdate,
)
from app.schemas.training_session import (
    AttendanceBulkSet,
    AttendanceRead,
    AttendanceReadParent,
    AttendanceSummary,
    AttendanceUpdate,
    KidAttendance,
    TrainingSessionCreate,
    TrainingSessionRead,
    TrainingSessionReadParent,
    TrainingSessionUpdate,
)
from app.services import training as training_svc
from app.services.permissions import (
    can_edit_session,
    can_view_session,
    filter_media_for_parent,
    parent_athlete_ids,
    user_club_role,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers de serialización
# ---------------------------------------------------------------------------


def _attendance_to_read(attendance) -> AttendanceRead:
    """Mapea SessionAttendance a AttendanceRead, incluyendo nombre del atleta."""
    name: str | None = None
    athlete = getattr(attendance, "athlete", None)
    if athlete is not None:
        name = f"{athlete.first_name} {athlete.last_name}".strip() or None
    data = AttendanceRead.model_validate(attendance).model_dump()
    data["athlete_name"] = name
    return AttendanceRead.model_validate(data)


def _attendance_to_read_parent(attendance) -> AttendanceReadParent:
    """Mapea SessionAttendance a AttendanceReadParent (incluye individual_feedback)."""
    name: str | None = None
    athlete = getattr(attendance, "athlete", None)
    if athlete is not None:
        name = f"{athlete.first_name} {athlete.last_name}".strip() or None
    data = AttendanceRead.model_validate(attendance).model_dump()
    data["athlete_name"] = name
    return AttendanceReadParent.model_validate(data)


def _build_attendance_summary(attendances: list) -> AttendanceSummary:
    return AttendanceSummary(
        total=len(attendances),
        presentes=sum(1 for a in attendances if a.status == AttendanceStatus.PRESENTE),
        ausentes=sum(1 for a in attendances if a.status == AttendanceStatus.AUSENTE),
        justificados=sum(1 for a in attendances if a.status == AttendanceStatus.JUSTIFICADO),
        tardes=sum(1 for a in attendances if a.status == AttendanceStatus.TARDE),
        lesionados=sum(1 for a in attendances if a.status == AttendanceStatus.LESIONADO),
    )


def _media_to_read(media: SessionMedia) -> SessionMediaRead:
    data = SessionMediaRead.model_validate(media).model_dump()
    data["athlete_ids"] = [a.id for a in (media.athletes or [])]
    return SessionMediaRead.model_validate(data)


def _media_to_read_parent(media: SessionMedia) -> SessionMediaReadParent:
    return SessionMediaReadParent.model_validate(media)


def _session_to_read(session) -> TrainingSessionRead:
    out = TrainingSessionRead.model_validate(session)
    out.attendance_summary = _build_attendance_summary(session.attendances or [])
    active_media = [m for m in (session.media or []) if m.deleted_at is None]
    out.media = [_media_to_read(m) for m in active_media]
    return out


def _session_to_read_parent(session, children_ids: set[int]) -> TrainingSessionReadParent:
    """
    Serializa una sesión para un padre.
    - Omite coach_notes y route_file_path.
    - Recalcula attendance_summary solo con las asistencias de sus hijos.
    - Incluye kid_attendances filtradas.
    """
    kid_attendances_raw = [
        a for a in (session.attendances or []) if a.athlete_id in children_ids
    ]
    summary = _build_attendance_summary(kid_attendances_raw)
    kid_att = [
        KidAttendance(
            athlete_id=a.athlete_id,
            status=a.status,
            excuse_reason=a.excuse_reason,
            rpe_omni=a.rpe_omni,
            rubric_effort=a.rubric_effort,
            rubric_attitude=a.rubric_attitude,
            rubric_technique=a.rubric_technique,
            individual_feedback=a.individual_feedback,
        )
        for a in kid_attendances_raw
    ]
    data = TrainingSessionRead.model_validate(session).model_dump(
        exclude={
            "coach_notes",
            "route_file_path",
            "attendance_summary",
            "kid_attendances",
            "media",
        }
    )
    data["attendance_summary"] = summary
    data["kid_attendances"] = kid_att
    visible_media = filter_media_for_parent(session.media or [], children_ids)
    data["media"] = [
        _media_to_read_parent(m).model_dump() for m in visible_media
    ]
    return TrainingSessionReadParent.model_validate(data)


async def _get_session_or_404(db: AsyncSession, session_id: int):
    """Obtiene la sesión o lanza 404."""
    session = await training_svc.sessions.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sesión {session_id} no encontrada",
        )
    return session


# ---------------------------------------------------------------------------
# Helpers de listado (extraídos de list_training_sessions para legibilidad)
# ---------------------------------------------------------------------------


async def _resolve_club_ids_for_user(db: AsyncSession, user: User) -> set[int]:
    """Retorna los club_ids del usuario según su rol (admin=todos, coach=suyos)."""
    if user.role == UserRole.admin:
        return {m.club_id for m in user.club_memberships}
    if user.role == UserRole.coach:
        return {m.club_id for m in user.club_memberships if m.role_in_club == ClubRole.coach}
    return set()


async def _list_for_parent(
    db: AsyncSession,
    current_user: User,
    session_status: SessionStatus | None,
    from_date: date | None,
    to_date: date | None,
    athlete_id: int | None,
    limit: int,
    offset: int,
) -> list[TrainingSessionReadParent]:
    """Lista sesiones visibles para un padre: solo las de sus hijos, sin datos sensibles."""
    children_ids = await parent_athlete_ids(db, current_user.id)
    if not children_ids:
        return []

    if athlete_id is not None and athlete_id not in children_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a las sesiones de ese atleta",
        )

    children_set = set(children_ids)
    ids_to_query: set[int] = (
        {athlete_id} if athlete_id is not None else set(children_ids)
    )
    if not ids_to_query:
        return []

    # 1 query: cargar todos los atletas hijos vivos para deducir clubes.
    ath_result = await db.execute(
        select(Athlete).where(
            Athlete.id.in_(ids_to_query),
            Athlete.deleted_at.is_(None),
        )
    )
    athletes = list(ath_result.scalars().all())
    if not athletes:
        return []

    club_ids_set = {a.club_id for a in athletes if a.club_id is not None}
    active_athlete_ids = {a.id for a in athletes}

    # 1 query: sesiones donde algún hijo está convocado y el club coincide.
    sessions = await training_svc.sessions.list_sessions(
        db=db,
        status=session_status.value if session_status else None,
        date_from=from_date.isoformat() if from_date else None,
        date_to=to_date.isoformat() if to_date else None,
        athlete_ids=active_athlete_ids,
        club_ids=club_ids_set,
        limit=limit,
        offset=offset,
    )

    return [_session_to_read_parent(s, children_set) for s in sessions]


async def _list_for_clubs(
    db: AsyncSession,
    club_ids: set[int],
    session_status: SessionStatus | None,
    from_date: date | None,
    to_date: date | None,
    athlete_id: int | None,
    limit: int,
    offset: int,
) -> list[TrainingSessionRead]:
    """Lista sesiones para admin/coach por sus clubs."""
    all_sessions: list[TrainingSessionRead] = []
    seen_ids: set[int] = set()
    for cid in club_ids:
        sessions = await training_svc.sessions.list_sessions(
            db=db,
            club_id=cid,
            status=session_status.value if session_status else None,
            date_from=from_date.isoformat() if from_date else None,
            date_to=to_date.isoformat() if to_date else None,
            athlete_id=athlete_id,
            limit=limit,
            offset=offset,
        )
        for s in sessions:
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                all_sessions.append(_session_to_read(s))
    return all_sessions


# ---------------------------------------------------------------------------
# POST /training-sessions — Crear sesión planificada
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=TrainingSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_session(
    body: TrainingSessionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> TrainingSessionRead:
    # El club_id se infiere del primer club del coach; si es admin puede especificar.
    # Tomamos el club del coach según sus membresías.
    if current_user.role == UserRole.coach:
        coach_clubs = {m.club_id for m in current_user.club_memberships if m.role_in_club == ClubRole.coach}
        if not coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No estás registrado como coach en ningún club",
            )
        club_id = next(iter(coach_clubs))
    else:
        # Admin: usa el primer club disponible del usuario o se requiere que
        # venga en query param. Por ahora usamos membresía de admin.
        admin_clubs = {m.club_id for m in current_user.club_memberships}
        if not admin_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El administrador no pertenece a ningún club",
            )
        club_id = next(iter(admin_clubs))

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    try:
        session = await training_svc.sessions.create_session(
            db=db,
            payload=body,
            coach=current_user,
            club_id=club_id,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return _session_to_read(session)


# ---------------------------------------------------------------------------
# GET /training-sessions — Listar sesiones
# ---------------------------------------------------------------------------


@router.get("", response_model=list[Union[TrainingSessionRead, TrainingSessionReadParent]])
async def list_training_sessions(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    session_status: SessionStatus | None = Query(default=None, alias="status"),
    athlete_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Union[TrainingSessionRead, TrainingSessionReadParent]]:
    # Guardia: padre primero (retorno explícito)
    if current_user.role == UserRole.parent:
        return await _list_for_parent(
            db, current_user, session_status, from_date, to_date, athlete_id, limit, offset
        )

    # Admin / coach
    if current_user.role in (UserRole.admin, UserRole.coach):
        club_ids = await _resolve_club_ids_for_user(db, current_user)
        if not club_ids:
            return []
        return await _list_for_clubs(
            db, club_ids, session_status, from_date, to_date, athlete_id, limit, offset
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para listar sesiones",
    )


# ---------------------------------------------------------------------------
# GET /training-sessions/{session_id} — Detalle
# ---------------------------------------------------------------------------


@router.get("/{session_id}", response_model=Union[TrainingSessionRead, TrainingSessionReadParent])
async def get_training_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Union[TrainingSessionRead, TrainingSessionReadParent]:
    session = await _get_session_or_404(db, session_id)

    allowed = await can_view_session(db, current_user, session)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver esta sesión",
        )

    if current_user.role == UserRole.parent:
        children_ids = set(await parent_athlete_ids(db, current_user.id))
        return _session_to_read_parent(session, children_ids)

    return _session_to_read(session)


# ---------------------------------------------------------------------------
# PATCH /training-sessions/{session_id} — Actualizar sesión
# ---------------------------------------------------------------------------


@router.patch("/{session_id}", response_model=TrainingSessionRead)
async def update_training_session(
    session_id: int,
    body: TrainingSessionUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> TrainingSessionRead:
    session = await _get_session_or_404(db, session_id)

    if not await can_edit_session(db, current_user, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para editar esta sesión",
        )

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    try:
        updated = await training_svc.sessions.update_session(
            db,
            session_id,
            body,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return _session_to_read(updated)


# ---------------------------------------------------------------------------
# POST /training-sessions/{session_id}/execute — Marcar ejecutada
# ---------------------------------------------------------------------------


@router.post("/{session_id}/execute", response_model=TrainingSessionRead)
async def execute_training_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> TrainingSessionRead:
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    try:
        executed = await training_svc.sessions.execute_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return _session_to_read(executed)


# ---------------------------------------------------------------------------
# DELETE /training-sessions/{session_id} — Soft delete (cancelled)
# ---------------------------------------------------------------------------


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_training_session(
    session_id: int,
    background_tasks: BackgroundTasks,
    notify: bool = Query(default=False, description="Si True, envía email de cancelación a padres."),
    reason: str | None = Query(default=None, max_length=300, description="Motivo opcional para el email."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> None:
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    if session.status == SessionStatus.EXECUTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede cancelar una sesión que ya fue ejecutada",
        )

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    try:
        await training_svc.sessions.cancel_session(
            db,
            session_id,
            send_notification=notify,
            reason=reason,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


# ===========================================================================
# PASO 5 — Asistencia + Upload
# ===========================================================================


# ---------------------------------------------------------------------------
# GET /training-sessions/{session_id}/attendance — Lista asistencias
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/attendance",
    response_model=list[Union[AttendanceRead, AttendanceReadParent]],
)
async def list_session_attendance(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Union[AttendanceRead, AttendanceReadParent]]:
    """
    Retorna las asistencias de la sesión.

    - admin/coach (mismo club): todas las filas con individual_feedback.
    - parent: solo las filas de SUS atletas convocados, sin individual_feedback.
    - otros: 403.
    """
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.admin:
        attendances = list(session.attendances or [])
        return [_attendance_to_read(a) for a in attendances]

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )
        attendances = list(session.attendances or [])
        return [_attendance_to_read(a) for a in attendances]

    if current_user.role == UserRole.parent:
        my_athlete_ids = await parent_athlete_ids(db, current_user.id)
        attendances = [
            a for a in (session.attendances or []) if a.athlete_id in my_athlete_ids
        ]
        if not attendances:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes atletas convocados en esta sesión",
            )
        return [_attendance_to_read_parent(a) for a in attendances]

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Rol no autorizado",
    )


# ---------------------------------------------------------------------------
# PUT /training-sessions/{session_id}/attendance — Bulk convocatoria
# ---------------------------------------------------------------------------


@router.put("/{session_id}/attendance", response_model=list[AttendanceRead])
async def bulk_set_convocatoria(
    session_id: int,
    body: Union[AttendanceBulkSet, list[int]],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service=Depends(get_notification_service),
) -> list[AttendanceRead]:
    # Acepta tanto el formato nuevo (AttendanceBulkSet) como la lista plana
    # legacy `[1, 2, 3]` para no romper consumidores existentes.
    if isinstance(body, list):
        athlete_ids = body
        send_notification = False
    else:
        athlete_ids = body.athlete_ids
        send_notification = body.send_notification

    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    # Validar que todos los atletas pertenecen al club de la sesión
    if athlete_ids:
        result = await db.execute(
            select(Athlete.id).where(
                Athlete.id.in_(athlete_ids),
                Athlete.club_id == session.club_id,
            )
        )
        valid_ids = set(result.scalars().all())
        invalid_ids = set(athlete_ids) - valid_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Los siguientes atletas no pertenecen al club: {sorted(invalid_ids)}",
            )

    from app.services.notification.task_dispatcher import TaskDispatcher

    dispatcher = TaskDispatcher(background_tasks)

    attendances = await training_svc.sessions.update_convocatoria(
        db=db,
        session_id=session_id,
        athlete_ids=athlete_ids,
        send_notification=send_notification,
        notification_service=notification_service,
        dispatcher=dispatcher,
    )
    return [_attendance_to_read(a) for a in attendances]


# ---------------------------------------------------------------------------
# PATCH /training-sessions/{session_id}/attendance/{athlete_id} — Actualizar
# ---------------------------------------------------------------------------


@router.patch(
    "/{session_id}/attendance/{athlete_id}",
    response_model=AttendanceRead,
)
async def update_attendance(
    session_id: int,
    athlete_id: int,
    body: AttendanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> AttendanceRead:
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    try:
        attendance = await training_svc.attendance.update_attendance(
            db=db,
            session_id=session_id,
            athlete_id=athlete_id,
            payload=body,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return _attendance_to_read(attendance)


# ---------------------------------------------------------------------------
# POST /training-sessions/{session_id}/route-file — Upload .gpx/.fit
# ---------------------------------------------------------------------------

# Tipos MIME válidos por formato
_GPX_CONTENT_TYPES = {"application/gpx+xml", "text/xml", "application/xml"}
_FIT_CONTENT_TYPES = {"application/vnd.garmin.fit", "application/octet-stream"}
_ALLOWED_CONTENT_TYPES = _GPX_CONTENT_TYPES | _FIT_CONTENT_TYPES

_MAX_GPX_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB
_MAX_FIT_SIZE_BYTES = 1 * 1024 * 1024   # 1 MB (reducido H3)

# Firma mágica FIT: primer byte 0x0E y longitud mínima de cabecera 14 bytes
_FIT_MAGIC_BYTE = b"\x0e"
_FIT_MIN_HEADER_LEN = 14


@router.post("/{session_id}/route-file", response_model=TrainingSessionRead)
async def upload_route_file(
    session_id: int,
    file: Annotated[UploadFile, File(description="Archivo .gpx o .fit del recorrido (GPX máx 5 MB, FIT máx 1 MB)")],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> TrainingSessionRead:
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    # Determinar extensión declarada para validaciones específicas
    filename = (file.filename or "").lower()
    is_gpx = filename.endswith(".gpx")
    is_fit = filename.endswith(".fit")

    if not is_gpx and not is_fit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos .gpx o .fit",
        )

    # Validar content-type según extensión
    content_type = (file.content_type or "").split(";")[0].strip()

    if is_gpx:
        # .gpx no puede ser application/octet-stream (H3)
        if content_type and content_type not in _GPX_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tipo de contenido '{content_type}' no permitido para .gpx. "
                    "Se aceptan: application/gpx+xml, text/xml, application/xml"
                ),
            )
    elif is_fit:
        if content_type and content_type not in _FIT_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tipo de contenido '{content_type}' no permitido para .fit. "
                    "Se aceptan: application/vnd.garmin.fit, application/octet-stream"
                ),
            )

    # Leer contenido para validaciones de tamaño y magic bytes
    # (límite mayor + 1 para detectar exceso sin leer todo el archivo)
    max_size = _MAX_GPX_SIZE_BYTES if is_gpx else _MAX_FIT_SIZE_BYTES
    raw = await file.read(max_size + 1)

    if len(raw) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El archivo supera el límite permitido "
                f"({'5 MB' if is_gpx else '1 MB'} para .{'gpx' if is_gpx else 'fit'})"
            ),
        )

    # Magic-byte check para FIT (H3)
    if is_fit:
        if len(raw) < _FIT_MIN_HEADER_LEN or raw[:1] != _FIT_MAGIC_BYTE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo .fit no tiene una cabecera FIT válida",
            )

    # Rebobinar el archivo para que el service pueda leerlo
    import io
    file.file = io.BytesIO(raw)  # type: ignore[assignment]

    try:
        relative_path = await training_svc.route_files.save_route_file(
            file=file,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Actualizar route_file_path en la sesión
    session.route_file_path = relative_path
    await db.commit()
    await db.refresh(session)

    # Recargar con asistencias
    reloaded = await _get_session_or_404(db, session_id)
    return _session_to_read(reloaded)


# ---------------------------------------------------------------------------
# Endpoints media (fotos y videos)
# ---------------------------------------------------------------------------


async def _validate_athlete_ids_for_session(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
) -> list[Athlete]:
    """Verifica que todos los athlete_ids estén convocados a la sesión.

    Los atletas que se etiquetan en una media deben haber sido convocados
    (es decir, tener un registro en session_attendance). Esto bloquea
    etiquetar atletas ajenos a la sesión.
    """
    if not athlete_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe etiquetar al menos un atleta convocado.",
        )

    from app.models.training_session import SessionAttendance

    result = await db.execute(
        select(SessionAttendance.athlete_id).where(
            SessionAttendance.session_id == session_id,
            SessionAttendance.athlete_id.in_(athlete_ids),
        )
    )
    convocados = set(result.scalars().all())
    invalid = set(athlete_ids) - convocados
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Los siguientes atletas no están convocados a la sesión: "
                f"{sorted(invalid)}."
            ),
        )

    ath_result = await db.execute(
        select(Athlete).where(Athlete.id.in_(athlete_ids))
    )
    return list(ath_result.scalars().all())


@router.post("/{session_id}/media", response_model=SessionMediaRead, status_code=status.HTTP_201_CREATED)
async def upload_session_media(
    session_id: int,
    file: Annotated[UploadFile, File(description="Foto (.jpg/.png/.webp) o video (.mp4/.mov)")],
    media_type: Annotated[MediaType, Form(description="photo | video")],
    athlete_ids: Annotated[str, Form(description="IDs separados por coma de atletas etiquetados")],
    consent_ack: Annotated[bool, Form(description="Confirmación de consentimiento parental")],
    caption: Annotated[str | None, Form(max_length=280)] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> SessionMediaRead:
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    if not consent_ack:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Debe marcar la casilla de consentimiento parental (Ley 1581) "
                "antes de subir media de menores."
            ),
        )

    try:
        ids = [int(x.strip()) for x in athlete_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="athlete_ids debe ser una lista de enteros separados por coma.",
        )

    athletes = await _validate_athlete_ids_for_session(db, session_id, ids)

    try:
        stored = await training_svc.media_files.save_session_media(
            file=file, session_id=session_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    if stored.media_type != media_type:
        # El campo `media_type` declarado debe coincidir con lo detectado.
        try:
            await training_svc.media_files.delete_session_media(stored.storage_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El tipo declarado '{media_type.value}' no coincide con el "
                f"archivo detectado '{stored.media_type.value}'."
            ),
        )

    media = SessionMedia(
        session_id=session_id,
        media_type=stored.media_type,
        storage_url=stored.storage_url,
        storage_path=stored.storage_path,
        thumbnail_url=stored.thumbnail_url,
        filename_original=(file.filename or "")[:255],
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        width=stored.width,
        height=stored.height,
        duration_sec=stored.duration_sec,
        caption=caption,
        consent_ack=True,
        uploaded_by_user_id=current_user.id,
    )
    media.athletes = athletes
    db.add(media)
    await db.commit()
    await db.refresh(media)
    # Recargar la relación athletes
    result = await db.execute(
        select(SessionMedia)
        .where(SessionMedia.id == media.id)
        .options(selectinload(SessionMedia.athletes))
    )
    media_loaded = result.scalar_one()
    return _media_to_read(media_loaded)


@router.get("/{session_id}/media")
async def list_session_media(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SessionMediaRead] | list[SessionMediaReadParent]:
    session = await _get_session_or_404(db, session_id)
    allowed = await can_view_session(db, current_user, session)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta sesión.",
        )

    active = [m for m in (session.media or []) if m.deleted_at is None]

    if current_user.role == UserRole.parent:
        children = set(await parent_athlete_ids(db, current_user.id))
        visible = filter_media_for_parent(active, children)
        return [_media_to_read_parent(m) for m in visible]

    return [_media_to_read(m) for m in active]


@router.delete("/{session_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_media(
    session_id: int,
    media_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> None:
    session = await _get_session_or_404(db, session_id)
    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    result = await db.execute(
        select(SessionMedia).where(
            SessionMedia.id == media_id,
            SessionMedia.session_id == session_id,
        )
    )
    media = result.scalar_one_or_none()
    if media is None or media.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media no encontrada.",
        )

    from datetime import datetime, timezone

    media.deleted_at = datetime.now(timezone.utc)
    storage_path = media.storage_path
    await db.commit()

    try:
        await training_svc.media_files.delete_session_media(storage_path)
    except Exception:
        pass

    return None


@router.patch("/{session_id}/media/{media_id}", response_model=SessionMediaRead)
async def update_session_media(
    session_id: int,
    media_id: int,
    payload: SessionMediaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> SessionMediaRead:
    session = await _get_session_or_404(db, session_id)
    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    result = await db.execute(
        select(SessionMedia)
        .where(
            SessionMedia.id == media_id,
            SessionMedia.session_id == session_id,
        )
        .options(selectinload(SessionMedia.athletes))
    )
    media = result.scalar_one_or_none()
    if media is None or media.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media no encontrada.",
        )

    if payload.caption is not None:
        media.caption = payload.caption

    if payload.athlete_ids is not None:
        athletes = await _validate_athlete_ids_for_session(
            db, session_id, payload.athlete_ids
        )
        media.athletes = athletes

    await db.commit()
    await db.refresh(media)
    result2 = await db.execute(
        select(SessionMedia)
        .where(SessionMedia.id == media.id)
        .options(selectinload(SessionMedia.athletes))
    )
    return _media_to_read(result2.scalar_one())
