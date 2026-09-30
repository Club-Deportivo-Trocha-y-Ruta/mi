"""Aggregate router and shared dependencies for feature 047 (IMDERTY).

This module owns the RBAC dependencies shared by every IMDERTY sub-router
and mounts them into a single ``router`` included once in ``app.main``.
Each sub-router (``imderty_profile``, ``imderty_barrios``,
``imderty_settings``, ``imderty_sheet``) owns its own routes so stories can
work on disjoint files; this module intentionally adds no business routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.athlete import Athlete
from app.models.club import Club
from app.models.user import User, UserRole
from app.routers.imderty_barrios import router as imderty_barrios_router
from app.routers.imderty_profile import router as imderty_profile_router
from app.routers.imderty_settings import router as imderty_settings_router
from app.routers.imderty_sheet import router as imderty_sheet_router
from app.services.permissions import coach_club_ids as _coach_club_ids


async def require_athlete_staff(
    athlete_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Athlete:
    """Admin, or a coach whose club owns the athlete; 403/404 otherwise.

    404 when the athlete does not exist or is archived, 403 when the caller is not admin
    and is not a coach of the athlete's club (this includes parents and
    athletes, per contracts/api.md).
    """
    # Un atleta archivado queda fuera del alcance IMDERTY (404, igual que la
    # vista del coach en athletes.py) — contracts/athlete-archive.md §1.
    result = await db.execute(
        select(Athlete).where(
            Athlete.id == athlete_id, Athlete.deleted_at.is_(None)
        )
    )
    athlete = result.scalar_one_or_none()
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    if current_user.role == UserRole.admin:
        return athlete

    if current_user.role == UserRole.coach and athlete.club_id in _coach_club_ids(
        current_user
    ):
        return athlete

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para esta acción",
    )


async def require_club_staff(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Club:
    """Admin, or a coach whose club membership matches ``club_id``.

    403/404 with the same shape as ``require_athlete_staff``.
    """
    result = await db.execute(select(Club).where(Club.id == club_id))
    club = result.scalar_one_or_none()
    if club is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club no encontrado",
        )

    if current_user.role == UserRole.admin:
        return club

    if current_user.role == UserRole.coach and club_id in _coach_club_ids(current_user):
        return club

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para esta acción",
    )


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Admin only; 403 for every other role."""
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta acción",
        )
    return current_user


router = APIRouter()
router.include_router(imderty_profile_router)
router.include_router(imderty_barrios_router)
router.include_router(imderty_settings_router)
router.include_router(imderty_sheet_router)
