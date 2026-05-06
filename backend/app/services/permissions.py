from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.training_session import SessionAttendance, TrainingSession
from app.models.user import User, UserRole


def require_role(user_role: UserRole, allowed_roles: list[UserRole]) -> None:
    """Verifica que el rol del usuario este en la lista de roles permitidos."""
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta accion",
        )


# ---------------------------------------------------------------------------
# Helpers de consulta
# ---------------------------------------------------------------------------


async def parent_athlete_ids(db: AsyncSession, user_id: int) -> list[int]:
    """Retorna los IDs de atletas vinculados a un usuario padre."""
    result = await db.execute(
        select(ParentAthlete.athlete_id).where(ParentAthlete.parent_id == user_id)
    )
    return list(result.scalars().all())


async def user_club_role(
    db: AsyncSession, user_id: int, club_id: int
) -> ClubRole | None:
    """Retorna el rol del usuario en un club, o None si no es miembro."""
    result = await db.execute(
        select(ClubMember.role_in_club).where(
            ClubMember.user_id == user_id,
            ClubMember.club_id == club_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Permisos de sesiones de entrenamiento
# ---------------------------------------------------------------------------


async def can_view_session(
    db: AsyncSession,
    user: User,
    session: TrainingSession,
) -> bool:
    """
    Admin: siempre.
    Coach: si pertenece al mismo club.
    Parent: si alguno de sus atletas fue convocado a la sesión.
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, session.club_id)
        return role is not None

    if user.role == UserRole.parent:
        athlete_ids = await parent_athlete_ids(db, user.id)
        if not athlete_ids:
            return False
        result = await db.execute(
            select(SessionAttendance.id).where(
                SessionAttendance.session_id == session.id,
                SessionAttendance.athlete_id.in_(athlete_ids),
            )
        )
        return result.first() is not None

    return False


def can_edit_session(user: User, session: TrainingSession) -> bool:
    """Admin o el coach que creó la sesión (asumido mismo club — verificar en router)."""
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.coach:
        return True
    return False


async def can_view_athlete_feedback(
    db: AsyncSession,
    user: User,
    athlete_id: int,
) -> bool:
    """
    Admin: siempre.
    Coach: siempre (se asume mismo club — el router lo valida).
    Parent: solo si el atleta le pertenece.
    """
    if user.role in {UserRole.admin, UserRole.coach}:
        return True

    if user.role == UserRole.parent:
        ids = await parent_athlete_ids(db, user.id)
        return athlete_id in ids

    return False


async def can_view_monthly_report(
    db: AsyncSession,
    user: User,
    club_id: int,
    individual: bool = False,
) -> bool:
    """
    Admin/coach del club: acceso total.
    Parent: solo vista agregada (individual=False).
    """
    if user.role == UserRole.admin:
        return True

    if user.role == UserRole.coach:
        role = await user_club_role(db, user.id, club_id)
        return role is not None

    if user.role == UserRole.parent:
        return not individual

    return False
