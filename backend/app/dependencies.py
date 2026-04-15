from collections.abc import AsyncGenerator, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un access token",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: sin sujeto",
        )

    user_id = int(sub)
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not user.can_login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    return user


def require_role(allowed_roles: list[UserRole]) -> Callable:
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta acción",
            )
        return current_user
    return _check


async def verify_athlete_access(
    athlete_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> "Athlete":
    """
    Dependencia de ownership: verifica que el usuario tiene acceso al atleta.
    - Admin: acceso total
    - Coach: solo atletas de sus clubes
    - Parent: solo sus atletas vinculados via parent_athlete
    """
    from app.models.athlete import Athlete, ParentAthlete
    from app.models.club import ClubMember, ClubRole

    # Cargar el atleta
    result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = result.scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    if current_user.role == UserRole.admin:
        return athlete

    if current_user.role == UserRole.coach:
        coach_clubs = {
            m.club_id for m in current_user.club_memberships
            if m.role_in_club == ClubRole.coach
        }
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )
        return athlete

    if current_user.role == UserRole.parent:
        # Verificar relación parent_athlete con un JOIN eficiente
        stmt = (
            select(Athlete)
            .join(ParentAthlete, ParentAthlete.athlete_id == Athlete.id)
            .where(
                ParentAthlete.parent_id == current_user.id,
                Athlete.id == athlete_id,
            )
        )
        result = await db.execute(stmt)
        linked_athlete = result.scalar_one_or_none()
        if not linked_athlete:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )
        return athlete

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para esta acción",
    )
