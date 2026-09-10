"""Archivado (soft delete) y restauración de atletas.

``contracts/athlete-archive.md`` §1-§2. Reemplaza la cascada física de
``DELETE /api/athletes/{id}`` por una única ``UPDATE`` sobre ``athletes`` que
preserva toda la evidencia relacionada (consentimiento parental,
antropometría, vínculos familia-atleta, historial de asistencia/carreras).
Ningún dato hijo se toca — ver §6 del contrato.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.audit_log import AuditAction
from app.models.user import User
from app.services.audit import (
    AthleteArchiveReasonCode,
    AthleteRestoreReasonCode,
    AuditEntityType,
    record_audit,
)


async def archive_athlete(
    db: AsyncSession,
    athlete: Athlete,
    actor: User,
    reason_code: AthleteArchiveReasonCode,
) -> None:
    """Archiva un atleta: una UPDATE sobre ``athletes``, ningún DELETE.

    El llamador es responsable de validar permisos y del estado 409/404 de
    "ya archivado" antes de invocar esta función.
    """
    now = datetime.now(timezone.utc)
    athlete.deleted_at = now
    athlete.deleted_by_user_id = actor.id
    athlete.deleted_reason_code = reason_code.value
    athlete.updated_by_user_id = actor.id
    athlete.updated_at = now

    await db.flush()

    await record_audit(
        db,
        action=AuditAction.archive,
        entity_type=AuditEntityType.athlete,
        entity_id=athlete.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=["deleted_at", "deleted_by_user_id", "deleted_reason_code"],
        diff={"deleted_reason_code": (None, reason_code.value)},
        reason_code=reason_code,
    )


async def restore_athlete(
    db: AsyncSession,
    athlete: Athlete,
    actor: User,
    reason_code: AthleteRestoreReasonCode,
) -> None:
    """Restaura un atleta previamente archivado (solo admin, ver router)."""
    now = datetime.now(timezone.utc)
    previous_reason_code = athlete.deleted_reason_code

    athlete.deleted_at = None
    athlete.deleted_by_user_id = None
    athlete.deleted_reason_code = None
    athlete.updated_by_user_id = actor.id
    athlete.updated_at = now

    await db.flush()

    await record_audit(
        db,
        action=AuditAction.restore,
        entity_type=AuditEntityType.athlete,
        entity_id=athlete.id,
        actor=actor,
        club_id=athlete.club_id,
        athlete_id=athlete.id,
        changed_fields=["deleted_at", "deleted_by_user_id", "deleted_reason_code"],
        diff={"deleted_reason_code": (previous_reason_code, None)},
        reason_code=reason_code,
    )
