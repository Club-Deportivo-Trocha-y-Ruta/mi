import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db
from app.models.athlete import Athlete, ParentAthlete
from app.models.parent_invite import ParentInvite
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.schemas.parent_invite import (
    ParentInviteTokenValidation,
    ParentRegisterOut,
    ParentRegisterRequest,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.services.invitations import consume_invite, get_valid_invite

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.email == body.email)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario desactivado",
        )

    if not user.can_login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario sin permisos de acceso",
        )

    club_ids = [m.club_id for m in user.club_memberships]
    token_data = {"sub": str(user.id), "role": user.role.value, "club_ids": club_ids}

    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un refresh token",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
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
            detail="Usuario no válido",
        )

    club_ids = [m.club_id for m in user.club_memberships]
    token_data = {"sub": str(user.id), "role": user.role.value, "club_ids": club_ids}

    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)):
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        role=current_user.role,
        is_active=current_user.is_active,
        can_login=current_user.can_login,
        club_ids=[m.club_id for m in current_user.club_memberships],
        created_at=current_user.created_at,
    )


@router.get("/invite/{token}", response_model=ParentInviteTokenValidation)
async def validate_invite_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ParentInviteTokenValidation:
    """Valida un token de invitación de padre (endpoint público).

    Retorna valid=True si el token existe, no fue usado y no expiró.
    Retorna valid=False (sin lanzar excepción) en los demás casos, para que
    el frontend pueda mostrar un mensaje apropiado al usuario.
    """
    from datetime import datetime, timezone

    stmt = select(ParentInvite).where(ParentInvite.token == token)
    invite = (await db.execute(stmt)).scalar_one_or_none()

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de invitación no encontrado",
        )

    # Cargar atleta junto con su club en una sola query
    athlete_result = await db.execute(
        select(Athlete)
        .options(selectinload(Athlete.club))
        .where(Athlete.id == invite.athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()

    athlete_name = (
        f"{athlete.first_name} {athlete.last_name}" if athlete else "Atleta desconocido"
    )
    club_name = athlete.club.name if athlete and athlete.club else ""

    is_expired = invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
    is_valid = not invite.used and not is_expired

    # Pre-llenar datos del padre cuando el coach pre-creó al usuario
    parent_first_name: str | None = None
    parent_last_name: str | None = None
    parent_phone: str | None = None
    parent_relationship: str | None = None

    if invite.parent_user_id is not None:
        parent_user = await db.get(User, invite.parent_user_id)
        if parent_user is not None:
            parent_first_name = parent_user.first_name
            parent_last_name = parent_user.last_name
            parent_phone = parent_user.phone

        pa_stmt = select(ParentAthlete).where(
            ParentAthlete.parent_id == invite.parent_user_id,
            ParentAthlete.athlete_id == invite.athlete_id,
        )
        pa = (await db.execute(pa_stmt)).scalar_one_or_none()
        if pa is not None:
            parent_relationship = pa.relationship_type.value

    return ParentInviteTokenValidation(
        athlete_id=invite.athlete_id,
        athlete_name=athlete_name,
        email=invite.email,
        expires_at=invite.expires_at,
        valid=is_valid,
        role="parent",
        club_name=club_name,
        parent_user_id=invite.parent_user_id,
        first_name=parent_first_name,
        last_name=parent_last_name,
        phone=parent_phone,
        relationship_type=parent_relationship,
    )


@router.post("/parent-register", response_model=ParentRegisterOut, status_code=status.HTTP_201_CREATED)
async def parent_register(
    body: ParentRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ParentRegisterOut:
    """Registra un padre/acudiente a partir de un token de invitación (endpoint público).

    Flujo:
    1. Valida el token (lanza excepción si inválido/expirado/usado).
    2. Crea el usuario, la membresía al club y la vinculación con el atleta.
    3. Registra el consentimiento parental digital (si fue enviado).
    4. Marca el token como usado.
    """
    invite = await get_valid_invite(body.token, db)

    # Extraer IP del cliente para trazabilidad del consentimiento
    client_ip: str | None = None
    if request.client:
        client_ip = request.client.host

    new_user = await consume_invite(
        invite=invite,
        first_name=body.first_name,
        last_name=body.last_name,
        password=body.password,
        phone=body.phone,
        db=db,
        relationship_type=body.relationship_type,
        consent=body.consent,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    return ParentRegisterOut(
        id=new_user.id,
        email=new_user.email or "",
        first_name=new_user.first_name,
        last_name=new_user.last_name,
    )
