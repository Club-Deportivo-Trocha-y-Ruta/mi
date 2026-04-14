from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, require_role
from app.models.club import Club, ClubMember
from app.models.user import User, UserRole
from app.schemas.club import (
    ClubCreate,
    ClubDetailOut,
    ClubMemberAdd,
    ClubMemberOut,
    ClubOut,
    ClubUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/clubs — Crear club (solo admin)
# ---------------------------------------------------------------------------
@router.post("/", response_model=ClubOut, status_code=status.HTTP_201_CREATED)
async def create_club(
    body: ClubCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin])),
) -> ClubOut:
    club = Club(
        name=body.name,
        code=body.code,
        location=body.location,
    )
    db.add(club)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un club con el código '{body.code}'",
        )
    return ClubOut.model_validate(club)


# ---------------------------------------------------------------------------
# GET /api/clubs — Listar clubes (autenticado)
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[ClubOut])
async def list_clubs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ClubOut]:
    result = await db.execute(select(Club).order_by(Club.name))
    clubs = result.scalars().all()
    return [ClubOut.model_validate(c) for c in clubs]


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id} — Detalle con miembros (autenticado)
# ---------------------------------------------------------------------------
@router.get("/{club_id}", response_model=ClubDetailOut)
async def get_club(
    club_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClubDetailOut:
    result = await db.execute(
        select(Club)
        .options(
            selectinload(Club.members).selectinload(ClubMember.user)
        )
        .where(Club.id == club_id)
    )
    club = result.scalar_one_or_none()
    if club is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club no encontrado",
        )
    return ClubDetailOut.model_validate(club)


# ---------------------------------------------------------------------------
# PATCH /api/clubs/{club_id} — Editar club (solo admin)
# ---------------------------------------------------------------------------
@router.patch("/{club_id}", response_model=ClubOut)
async def update_club(
    club_id: int,
    body: ClubUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin])),
) -> ClubOut:
    result = await db.execute(select(Club).where(Club.id == club_id))
    club = result.scalar_one_or_none()
    if club is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club no encontrado",
        )

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(club, field, value)

    await db.flush()
    return ClubOut.model_validate(club)


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/members — Asociar usuario a club (solo admin)
# ---------------------------------------------------------------------------
@router.post(
    "/{club_id}/members",
    response_model=ClubMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    club_id: int,
    body: ClubMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin])),
) -> ClubMemberOut:
    # Verificar que el club exista
    club_result = await db.execute(select(Club).where(Club.id == club_id))
    if club_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club no encontrado",
        )

    # Verificar que el usuario exista y esté activo
    user_result = await db.execute(
        select(User).where(User.id == body.user_id, User.is_active == True)  # noqa: E712
    )
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    member = ClubMember(
        club_id=club_id,
        user_id=body.user_id,
        role_in_club=body.role_in_club,
    )
    db.add(member)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El usuario ya es miembro de este club",
        )

    # Recargar con el usuario para que el model_validator pueda aplanar los campos
    await db.refresh(member, attribute_names=["user"])
    return ClubMemberOut.model_validate(member)
