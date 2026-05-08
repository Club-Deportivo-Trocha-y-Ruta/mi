"""Router para sesiones de entrenamiento, asistencia y upload de recorridos."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import BackgroundTasks

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
)
from app.models.training_session import SessionStatus
from app.models.user import User, UserRole
from app.schemas.training_session import (
    AttendanceRead,
    AttendanceUpdate,
    TrainingSessionCreate,
    TrainingSessionRead,
    TrainingSessionUpdate,
    AttendanceSummary,
)
from app.services import training as training_svc
from app.services.permissions import (
    can_edit_session,
    can_view_session,
    parent_athlete_ids,
    user_club_role,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
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


def _build_attendance_summary(session) -> AttendanceSummary:
    attendances = session.attendances or []
    from app.models.training_session import AttendanceStatus
    return AttendanceSummary(
        total=len(attendances),
        presentes=sum(1 for a in attendances if a.status == AttendanceStatus.PRESENTE),
        ausentes=sum(1 for a in attendances if a.status == AttendanceStatus.AUSENTE),
        justificados=sum(1 for a in attendances if a.status == AttendanceStatus.JUSTIFICADO),
        tardes=sum(1 for a in attendances if a.status == AttendanceStatus.TARDE),
        lesionados=sum(1 for a in attendances if a.status == AttendanceStatus.LESIONADO),
    )


def _session_to_read(session) -> TrainingSessionRead:
    out = TrainingSessionRead.model_validate(session)
    out.attendance_summary = _build_attendance_summary(session)
    return out


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
    from app.models.club import ClubRole
    if current_user.role == UserRole.coach:
        coach_clubs = {m.club_id for m in current_user.club_memberships if m.role_in_club == ClubRole.coach}
        if not coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No estás registrado como coach en ningún club",
            )
        # El cliente debe pasar club_id en la sesión, pero TrainingSessionCreate no lo lleva.
        # Lo obtenemos del coach (primer club) — si tiene varios, usamos el primero.
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


@router.get("", response_model=list[TrainingSessionRead])
async def list_training_sessions(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    session_status: SessionStatus | None = Query(default=None, alias="status"),
    athlete_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TrainingSessionRead]:
    from app.models.club import ClubRole

    # Determinar club_id del usuario para filtrar
    if current_user.role == UserRole.admin:
        club_ids = {m.club_id for m in current_user.club_memberships}
    elif current_user.role == UserRole.coach:
        club_ids = {m.club_id for m in current_user.club_memberships if m.role_in_club == ClubRole.coach}
    elif current_user.role == UserRole.parent:
        # Padre solo ve sesiones de sus atletas
        children_ids = await parent_athlete_ids(db, current_user.id)
        if not children_ids:
            return []
        # Forzar athlete_id a uno de sus hijos; si especificó uno verificar que le pertenece
        if athlete_id is not None and athlete_id not in children_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a las sesiones de ese atleta",
            )
        # Para padres, obtenemos todos los clubs donde sus hijos están convocados
        # La forma más directa: listar sesiones por cada hijo y agregar
        all_sessions: list[TrainingSessionRead] = []
        seen_ids: set[int] = set()
        ids_to_query = [athlete_id] if athlete_id else children_ids
        for child_id in ids_to_query:
            # Necesitamos el club del atleta para hacer la query
            from sqlalchemy import select
            from app.models.athlete import Athlete
            ath_result = await db.execute(select(Athlete).where(Athlete.id == child_id))
            ath = ath_result.scalar_one_or_none()
            if ath is None:
                continue
            sessions = await training_svc.sessions.list_sessions(
                db=db,
                club_id=ath.club_id,
                status=session_status.value if session_status else None,
                date_from=from_date.isoformat() if from_date else None,
                date_to=to_date.isoformat() if to_date else None,
                athlete_id=child_id,
                limit=limit,
                offset=offset,
            )
            for s in sessions:
                if s.id not in seen_ids:
                    seen_ids.add(s.id)
                    read = _session_to_read(s)
                    read.kid_attendances = [
                        {"athlete_id": a.athlete_id, "status": a.status}
                        for a in (s.attendances or [])
                        if a.athlete_id in children_ids
                    ]
                    all_sessions.append(read)
        return all_sessions
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para listar sesiones",
        )

    if not club_ids:
        return []

    # Admin y coach: listar por todos sus clubs
    all_sessions = []
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
# GET /training-sessions/{session_id} — Detalle
# ---------------------------------------------------------------------------


@router.get("/{session_id}", response_model=TrainingSessionRead)
async def get_training_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainingSessionRead:
    session = await _get_session_or_404(db, session_id)

    allowed = await can_view_session(db, current_user, session)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver esta sesión",
        )

    return _session_to_read(session)


# ---------------------------------------------------------------------------
# PATCH /training-sessions/{session_id} — Actualizar sesión
# ---------------------------------------------------------------------------


@router.patch("/{session_id}", response_model=TrainingSessionRead)
async def update_training_session(
    session_id: int,
    body: TrainingSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> TrainingSessionRead:
    session = await _get_session_or_404(db, session_id)

    # Coach debe pertenecer al mismo club
    if current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )

    if not can_edit_session(current_user, session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para editar esta sesión",
        )

    try:
        updated = await training_svc.sessions.update_session(db, session_id, body)
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

    from app.models.training_session import SessionStatus
    if session.status == SessionStatus.EXECUTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede cancelar una sesión que ya fue ejecutada",
        )

    try:
        await training_svc.sessions.cancel_session(db, session_id)
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
    response_model=list[AttendanceRead],
)
async def list_session_attendance(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AttendanceRead]:
    """
    Retorna las asistencias de la sesión.

    - admin/coach (mismo club): todas las filas.
    - parent: solo las filas de SUS atletas convocados.
    - otros: 403.
    """
    session = await _get_session_or_404(db, session_id)

    if current_user.role == UserRole.admin:
        attendances = list(session.attendances or [])
    elif current_user.role == UserRole.coach:
        role = await user_club_role(db, current_user.id, session.club_id)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No perteneces al club de esta sesión",
            )
        attendances = list(session.attendances or [])
    elif current_user.role == UserRole.parent:
        my_athlete_ids = await parent_athlete_ids(db, current_user.id)
        attendances = [
            a for a in (session.attendances or []) if a.athlete_id in my_athlete_ids
        ]
        if not attendances:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes atletas convocados en esta sesión",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol no autorizado",
        )

    return [_attendance_to_read(a) for a in attendances]


# ---------------------------------------------------------------------------
# PUT /training-sessions/{session_id}/attendance — Bulk convocatoria
# ---------------------------------------------------------------------------


@router.put("/{session_id}/attendance", response_model=list[AttendanceRead])
async def bulk_set_convocatoria(
    session_id: int,
    athlete_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> list[AttendanceRead]:
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
        from sqlalchemy import select
        from app.models.athlete import Athlete
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

    attendances = await training_svc.attendance.bulk_upsert_convocatoria(
        db=db,
        session_id=session_id,
        athlete_ids=athlete_ids,
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

_ALLOWED_CONTENT_TYPES = {
    "application/gpx+xml",
    "application/octet-stream",
    "application/vnd.garmin.fit",
    "text/xml",
    "application/xml",
}

# TODO: mover MAX_UPLOAD_SIZE_BYTES a Settings cuando se agregue el campo
_MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/{session_id}/route-file", response_model=TrainingSessionRead)
async def upload_route_file(
    session_id: int,
    file: Annotated[UploadFile, File(description="Archivo .gpx o .fit del recorrido (máx 5 MB)")],
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

    # Validar content-type
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de contenido '{content_type}' no permitido. "
                   "Se aceptan: .gpx (application/gpx+xml, application/xml, text/xml) "
                   "o .fit (application/vnd.garmin.fit, application/octet-stream)",
        )

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
