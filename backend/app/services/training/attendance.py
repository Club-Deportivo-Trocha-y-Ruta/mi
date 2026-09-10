"""Lógica de negocio para asistencia y rúbrica de atletas en sesiones."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.training_session import AttendanceStatus, SessionAttendance
from app.models.user import User
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


def _carries_recorded_data(payload_data: dict) -> bool:
    """True si la actualización pone datos reales sobre la fila (§6.2).

    "Registrado por" es quien primero puso datos en la fila —no quien creó el
    placeholder vacío de la convocatoria—, así que un cambio que solo deja el
    estado en AUSENTE sin rúbrica ni retroalimentación no atribuye registro.
    """
    if any(payload_data.get(field) is not None for field in _DATA_FIELDS):
        return True
    status = payload_data.get("status")
    return status is not None and status != AttendanceStatus.AUSENTE


async def bulk_upsert_convocatoria(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
    *,
    actor: User,
    club_id: int | None = None,
    ctx: AuditContext | None = None,
) -> list[SessionAttendance]:
    """
    Reemplaza la convocatoria de una sesión.

    - Atletas en athlete_ids que ya existen y están activos → se conservan.
    - Atletas en athlete_ids cuya fila estaba archivada → se desarchivan
      (``archived_at = NULL``, action=restore). Este paso NO es opcional: la
      fila archivada sigue existiendo, así que re-insertarla violaría
      ``uq_session_attendance`` y omitirlo dejaría al atleta invisible para
      siempre (R-12).
    - Atletas nuevos → se insertan con status AUSENTE (placeholder).
    - Atletas que estaban y no están en la nueva lista:
        - sin ningún dato de rúbrica/RPE/feedback → se eliminan (delete).
        - con algún dato → se archivan (``archived_at``, action=archive).

    ``actor`` es de solo-palabra-clave y sin default (§4): quien mueve la
    convocatoria queda en ``audit_log``, nunca se re-deriva del creador.
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
    for athlete_id in sorted(to_remove):
        row = existing[athlete_id]
        if row.archived_at is not None:
            # Ya estaba archivada y sigue fuera de la convocatoria: nada que hacer.
            continue
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

    # Desarchivar a los que vuelven a la convocatoria (§6.3, `re_added`).
    # `archived_at`, y solo `archived_at`, se limpia: rúbricas, RPE,
    # retroalimentación y `recorded_by_user_id` quedan intactos.
    rows_to_restore: list[tuple[SessionAttendance, datetime]] = []
    for athlete_id in sorted(new_set & existing_set):
        row = existing[athlete_id]
        if row.archived_at is not None:
            rows_to_restore.append((row, row.archived_at))
            row.archived_at = None

    # Insertar los nuevos
    to_add = new_set - existing_set
    rows_to_create: list[SessionAttendance] = []
    for athlete_id in sorted(to_add):
        row = SessionAttendance(
            session_id=session_id,
            athlete_id=athlete_id,
            # AUSENTE como placeholder — se sobreescribe al ejecutar la sesión.
            # `recorded_by_user_id`/`updated_by_user_id` quedan en NULL: el
            # placeholder no es un registro de asistencia (§6.2).
            status=AttendanceStatus.AUSENTE,
        )
        db.add(row)
        rows_to_create.append(row)

    if ctx is not None and (
        rows_to_create or rows_to_archive or rows_to_delete or rows_to_restore
    ):
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
                changed_fields=["status"],
                diff={"status": (None, row.status.value)},
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
                changed_fields=["archived_at"],
                diff={"archived_at": (None, row.archived_at.isoformat())},
                request_id=ctx.request_id,
            )
        for row, previous_archived_at in rows_to_restore:
            await record_audit(
                db,
                action=AuditAction.restore,
                entity_type=AuditEntityType.session_attendance,
                entity_id=row.id,
                actor=ctx.actor,
                actor_kind=ctx.actor_kind,
                club_id=club_id,
                athlete_id=row.athlete_id,
                changed_fields=["archived_at"],
                diff={"archived_at": (previous_archived_at.isoformat(), None)},
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
        .where(
            SessionAttendance.session_id == session_id,
            SessionAttendance.archived_at.is_(None),
        )
        .options(
            selectinload(SessionAttendance.athlete),
            selectinload(SessionAttendance.recorded_by),
            selectinload(SessionAttendance.updated_by),
        )
    )
    return list(result.scalars().all())


async def update_attendance(
    db: AsyncSession,
    session_id: int,
    athlete_id: int,
    payload: AttendanceUpdate,
    *,
    actor: User,
    club_id: int | None = None,
    ctx: AuditContext | None = None,
) -> SessionAttendance:
    """
    Actualiza el registro de asistencia y rúbrica de un atleta en una sesión.
    Lanza ValueError si el registro no existe o está archivado.

    Atribución (§6.2): ``recorded_by_user_id`` se fija con ``actor.id`` SOLO si
    está en NULL y la actualización trae datos reales; ``updated_by_user_id``
    se reescribe siempre con ``actor.id``.
    """
    result = await db.execute(
        select(SessionAttendance)
        .where(
            SessionAttendance.session_id == session_id,
            SessionAttendance.athlete_id == athlete_id,
            SessionAttendance.archived_at.is_(None),
        )
        .options(
            selectinload(SessionAttendance.athlete),
            selectinload(SessionAttendance.recorded_by),
            selectinload(SessionAttendance.updated_by),
        )
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

    if attendance.recorded_by_user_id is None and _carries_recorded_data(
        update_data
    ):
        attendance.recorded_by_user_id = actor.id
    attendance.updated_by_user_id = actor.id

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
    await db.refresh(
        attendance, attribute_names=["athlete", "recorded_by", "updated_by"]
    )
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

    Las filas archivadas (§6.3) quedan fuera: el atleta ya no forma parte de
    esa convocatoria y su historial no debe contarlas.
    """
    from app.models.training_session import TrainingSession

    stmt = (
        select(SessionAttendance)
        .join(TrainingSession, SessionAttendance.session_id == TrainingSession.id)
        .where(
            SessionAttendance.athlete_id == athlete_id,
            SessionAttendance.archived_at.is_(None),
        )
    )

    if date_from:
        stmt = stmt.where(TrainingSession.scheduled_date >= date_from)
    if date_to:
        stmt = stmt.where(TrainingSession.scheduled_date <= date_to)

    stmt = stmt.order_by(TrainingSession.scheduled_date.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())
