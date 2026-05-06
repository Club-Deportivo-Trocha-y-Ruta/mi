"""Lógica de negocio para asistencia y rúbrica de atletas en sesiones."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_session import AttendanceStatus, SessionAttendance
from app.schemas.training_session import AttendanceUpdate


async def bulk_upsert_convocatoria(
    db: AsyncSession,
    session_id: int,
    athlete_ids: list[int],
) -> list[SessionAttendance]:
    """
    Reemplaza la convocatoria de una sesión.

    - Atletas en athlete_ids que ya existen → se conservan.
    - Atletas nuevos → se insertan con status AUSENTE (placeholder).
    - Atletas que estaban y no están en la nueva lista → se eliminan.
    """
    existing_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id == session_id
        )
    )
    existing = {row.athlete_id: row for row in existing_result.scalars().all()}

    new_set = set(athlete_ids)
    existing_set = set(existing.keys())

    # Eliminar los que ya no están en la convocatoria
    to_remove = existing_set - new_set
    if to_remove:
        await db.execute(
            delete(SessionAttendance).where(
                SessionAttendance.session_id == session_id,
                SessionAttendance.athlete_id.in_(to_remove),
            )
        )

    # Insertar los nuevos
    to_add = new_set - existing_set
    for athlete_id in to_add:
        db.add(
            SessionAttendance(
                session_id=session_id,
                athlete_id=athlete_id,
                status=AttendanceStatus.AUSENTE,
            )
        )

    await db.commit()

    result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id == session_id
        )
    )
    return list(result.scalars().all())


async def update_attendance(
    db: AsyncSession,
    session_id: int,
    athlete_id: int,
    payload: AttendanceUpdate,
) -> SessionAttendance:
    """
    Actualiza el registro de asistencia y rúbrica de un atleta en una sesión.
    Lanza ValueError si el registro no existe.
    """
    result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id == session_id,
            SessionAttendance.athlete_id == athlete_id,
        )
    )
    attendance = result.scalar_one_or_none()

    if attendance is None:
        raise ValueError(
            f"No existe registro de asistencia para atleta {athlete_id} "
            f"en sesión {session_id}"
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(attendance, field, value)

    await db.commit()
    await db.refresh(attendance)
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
