import logging

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
    is_refresh_revoked,
    persist_refresh_token,
    revoke_refresh_token,
    verify_password,
)
from app.services.invitations import consume_invite, get_valid_invite

router = APIRouter()
logger = logging.getLogger(__name__)


def _mask_email(email: str | None) -> str:
    """Enmascara un email para logs: ``a***@dominio``. Nunca expone PII."""
    if not email or "@" not in email:
        return "<empty>"
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _client_ip(request: Request) -> str:
    """Obtiene la IP del cliente para logs (o ``unknown``)."""
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


# ---------------------------------------------------------------------------
# Rate-limit decorators
#
# Se importan tarde y de forma tolerante para que el módulo siga importable
# en escenarios de test donde ``app.main`` aún no fue inicializado (los tests
# del router de auth usan ``override_dependency`` y montan FastAPI ad-hoc).
# ---------------------------------------------------------------------------


def _limit(spec: str):
    """Decorator wrapper. Si slowapi no está disponible (ej. import circular en
    tests unitarios del servicio), retorna identity decorator.
    """
    try:
        from app.main import limiter  # noqa: WPS433 — import diferido intencional
    except Exception:  # pragma: no cover — sólo en escenarios degradados
        def _noop(func):
            return func
        return _noop
    return limiter.limit(spec)


@router.post("/login", response_model=TokenResponse)
@_limit("10/minute")
async def login(
    body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    # Excluir soft-deleted: el login debe rechazar usuarios eliminados.
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password or ""):
        logger.warning(
            "login_failed email=%s ip=%s",
            _mask_email(body.email),
            _client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )

    if not user.is_active:
        logger.warning(
            "login_failed_inactive email=%s ip=%s",
            _mask_email(body.email),
            _client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario desactivado",
        )

    if not user.can_login:
        logger.warning(
            "login_failed_no_login email=%s ip=%s",
            _mask_email(body.email),
            _client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario sin permisos de acceso",
        )

    club_ids = [m.club_id for m in user.club_memberships]
    token_data = {"sub": str(user.id), "role": user.role.value, "club_ids": club_ids}

    access_token = create_access_token(token_data)
    refresh_token, jti, expires_at = create_refresh_token(token_data)
    await persist_refresh_token(
        db, jti=jti, user_id=user.id, expires_at=expires_at
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
@_limit("30/minute")
async def refresh(
    body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)
):
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

    # jti es obligatorio para refresh tokens emitidos por la app (A3).
    # Tokens viejos sin jti se aceptan sólo para compatibilidad mientras
    # se rotan, pero saltan el chequeo de revocación.
    incoming_jti = payload.get("jti")
    if incoming_jti and await is_refresh_revoked(db, incoming_jti):
        logger.warning(
            "refresh_revoked_jti_attempt ip=%s",
            _client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revocado",
        )

    user_id = int(sub)
    # Excluir soft-deleted en refresh: tokens de usuarios eliminados deben fallar.
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not user.can_login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no válido",
        )

    club_ids = [m.club_id for m in user.club_memberships]
    token_data = {"sub": str(user.id), "role": user.role.value, "club_ids": club_ids}

    access_token = create_access_token(token_data)
    new_refresh, new_jti, new_expires_at = create_refresh_token(token_data)

    # Rotación: revocar el viejo (si tiene jti) y persistir el nuevo.
    if incoming_jti:
        await revoke_refresh_token(db, incoming_jti, replaced_by=new_jti)
    await persist_refresh_token(
        db, jti=new_jti, user_id=user.id, expires_at=new_expires_at
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
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
@_limit("20/minute")
async def validate_invite_token(
    token: str,
    request: Request,
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


@router.post(
    "/parent-register",
    response_model=ParentRegisterOut,
    status_code=status.HTTP_201_CREATED,
)
@_limit("5/hour")
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
