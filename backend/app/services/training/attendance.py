"""Lógica de negocio para asistencia y rúbrica de atletas en sesiones."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.training_session import AttendanceStatus, SessionAttendance
from app.schemas.training_session import AttendanceUpdate
from app.services.audit import (
    VALUE_ALLOWLIST,
    AuditAction,
    AuditEntityType,
    compute_changed_fields,
    record_audit,
)
from app.services.request_context import AuditContext

#: Campos de rúbrica/feedback — si alguno tiene dato, la fila de asistencia
#: removida de la convocatoria se archiva (action=archive) en vez de
#: eliminarse (action=delete), para no perder historial (FR-016,
#: contracts/audit-recording.md §4.6).
_DATA_FIELDS = (
    "rpe_omni",
    "rubric_effort",
    "rubric_attitude",
    "rubric_technique",
    "individual_feedback",
)


async def bulk_upsert_convocatoria(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
    *,
    club_id: int | None = None,
    ctx: AuditContext | None = None,
) -> list[SessionAttendance]:
    """
    Reemplaza la convocatoria de una sesión.

    - Atletas en athlete_ids que ya existen → se conservan.
    - Atletas nuevos → se insertan con status AUSENTE (placeholder).
    - Atletas que estaban y no están en la nueva lista:
        - sin ningún dato de rúbrica/RPE/feedback → se eliminan (delete).
        - con algún dato → se archivan (``archived_at``, action=archive).
    """
    existing_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id == session_id
        )
    )
    existing = {row.athlete_id: row for row in existing_result.scalars().all()}

    new_set = set(athlete_ids)
    existing_set = set(existing.keys())

    to_remove = existing_set - new_set
    rows_to_delete: list[SessionAttendance] = []
    rows_to_archive: list[SessionAttendance] = []
    for athlete_id in to_remove:
        row = existing[athlete_id]
        has_data = any(getattr(row, field) is not None for field in _DATA_FIELDS)
        if has_data:
            row.archived_at = datetime.now(timezone.utc)
            rows_to_archive.append(row)
        else:
            rows_to_delete.append(row)

    if rows_to_delete:
        await db.execute(
            delete(SessionAttendance).where(
                SessionAttendance.id.in_([row.id for row in rows_to_delete])
            )
        )

    # Insertar los nuevos
    to_add = new_set - existing_set
    rows_to_create: list[SessionAttendance] = []
    for athlete_id in to_add:
        row = SessionAttendance(
            session_id=session_id,
            athlete_id=athlete_id,
            status=AttendanceStatus.AUSENTE,
        )
        db.add(row)
        rows_to_create.append(row)

    if ctx is not None and (rows_to_create or rows_to_archive or rows_to_delete):
        if rows_to_create:
            await db.flush()  # obtener ids autogenerados antes de auditar
        for row in rows_to_create:
            await record_audit(
                db,
                action=AuditAction.create,
                entity_type=AuditEntityType.session_attendance,
                entity_id=row.id,
                actor=ctx.actor,
                actor_kind=ctx.actor_kind,
                club_id=club_id,
                athlete_id=row.athlete_id,
                request_id=ctx.request_id,
            )
        for row in rows_to_archive:
            await record_audit(
                db,
                action=AuditAction.archive,
                entity_type=AuditEntityType.session_attendance,
                entity_id=row.id,
                actor=ctx.actor,
                actor_kind=ctx.actor_kind,
                club_id=club_id,
                athlete_id=row.athlete_id,
                request_id=ctx.request_id,
            )
        for row in rows_to_delete:
            await record_audit(
                db,
                action=AuditAction.delete,
                entity_type=AuditEntityType.session_attendance,
                entity_id=row.id,
                actor=ctx.actor,
                actor_kind=ctx.actor_kind,
                club_id=club_id,
                athlete_id=row.athlete_id,
                request_id=ctx.request_id,
            )

    await db.commit()

    result = await db.execute(
        select(SessionAttendance)
        .where(SessionAttendance.session_id == session_id)
        .options(selectinload(SessionAttendance.athlete))
    )
    return list(result.scalars().all())


async def update_attendance(
    db: AsyncSession,
    session_id: int,
    athlete_id: int,
    payload: AttendanceUpdate,
    *,
    club_id: int | None = None,
    ctx: AuditContext | None = None,
) -> SessionAttendance:
    """
    Actualiza el registro de asistencia y rúbrica de un atleta en una sesión.
    Lanza ValueError si el registro no existe.
    """
    result = await db.execute(
        select(SessionAttendance)
        .where(
            SessionAttendance.session_id == session_id,
            SessionAttendance.athlete_id == athlete_id,
        )
        .options(selectinload(SessionAttendance.athlete))
    )
    attendance = result.scalar_one_or_none()

    if attendance is None:
        raise ValueError(
            f"No existe registro de asistencia para atleta {athlete_id} "
            f"en sesión {session_id}"
        )

    update_data = payload.model_dump(exclude_unset=True)
    previous_values = {field: getattr(attendance, field) for field in update_data}

    for field, value in update_data.items():
        setattr(attendance, field, value)

    if ctx is not None:
        changed_fields, diff = compute_changed_fields(
            before=previous_values,
            after=update_data,
            allow_list=VALUE_ALLOWLIST[AuditEntityType.session_attendance],
        )
        await record_audit(
            db,
            action=AuditAction.update,
            entity_type=AuditEntityType.session_attendance,
            entity_id=attendance.id,
            actor=ctx.actor,
            actor_kind=ctx.actor_kind,
            club_id=club_id,
            athlete_id=athlete_id,
            changed_fields=changed_fields,
            diff=diff,
            request_id=ctx.request_id,
        )

    await db.commit()
    await db.refresh(attendance, attribute_names=["athlete"])
    return attendance


async def athlete_attendance_history(
    db: AsyncSession,
    athlete_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[SessionAttendance]:
    """
    Retorna el historial de asistencia de un atleta, opcionalmente filtrado
    por rango de fechas de la sesión asociada.
    """
    from app.models.training_session import TrainingSession

    stmt = (
        select(SessionAttendance)
        .join(TrainingSession, SessionAttendance.session_id == TrainingSession.id)
        .where(SessionAttendance.athlete_id == athlete_id)
    )

    if date_from:
        stmt = stmt.where(TrainingSession.scheduled_date >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.scheduled_date <= date_to)

    stmt = stmt.order_by(TrainingSession.scheduled_date.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())
