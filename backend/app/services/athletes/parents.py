"""Helpers ORM para consultas sobre la relación padre↔atleta.

Centralizan los patrones de acceso comunes (lookup del primer padre con
email para enviar notificaciones, etc.) y los expresan como un único
SQL JOIN para evitar N+1.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import ParentAthlete
from app.models.user import User


async def get_primary_parent_with_email(
    db: AsyncSession, athlete_id: int
) -> User | None:
    """Devuelve el primer padre vinculado al atleta que tenga email.

    Implementación: un único JOIN ``users × parent_athlete`` en lugar
    del patrón N+1 ``SELECT parent_athlete; for each: SELECT user``.

    Filtra soft-deleted (``deleted_at IS NULL``) y exige ``email IS NOT
    NULL`` porque el caller típico es el envío de la notificación de
    bienvenida.
    """
    stmt = (
        select(User)
        .join(ParentAthlete, ParentAthlete.parent_id == User.id)
        .where(
            ParentAthlete.athlete_id == athlete_id,
            User.email.is_not(None),
            User.deleted_at.is_(None),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


__all__ = ["get_primary_parent_with_email"]
