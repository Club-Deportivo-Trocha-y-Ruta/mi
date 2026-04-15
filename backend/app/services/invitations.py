"""Servicio de invitaciones: genera, valida y consume tokens de onboarding para padres."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete
from app.models.club import ClubMember, ClubRole
from app.models.parent_invite import ParentInvite
from app.models.user import User, UserRole
from app.services.auth import hash_password

INVITE_EXPIRY_HOURS = 72


async def create_invite(
    athlete_id: int,
    email: str,
    created_by_user_id: int,
    db: AsyncSession,
) -> ParentInvite:
    """Genera un token de invitación para un padre.

    Si ya existe uno no-usado y no-expirado para el mismo atleta+email,
    lo retorna directamente sin crear un duplicado.
    """
    existing_stmt = select(ParentInvite).where(
        ParentInvite.athlete_id == athlete_id,
        ParentInvite.email == email,
        ParentInvite.used == False,  # noqa: E712
        ParentInvite.expires_at > datetime.now(timezone.utc),
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        return existing

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS)

    invite = ParentInvite(
        athlete_id=athlete_id,
        email=email,
        token=token,
        expires_at=expires_at,
        used=False,
        created_by=created_by_user_id,
    )
    db.add(invite)
    await db.flush()
    return invite


async def get_valid_invite(token: str, db: AsyncSession) -> ParentInvite:
    """Retorna la invitación si el token es válido.

    Lanza HTTPException 404/410 si no existe, fue usado o expiró.
    """
    stmt = select(ParentInvite).where(ParentInvite.token == token)
    invite = (await db.execute(stmt)).scalar_one_or_none()

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de invitación no encontrado",
        )
    if invite.used:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este token ya fue utilizado",
        )
    if invite.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El token de invitación ha expirado",
        )

    return invite


async def consume_invite(
    invite: ParentInvite,
    first_name: str,
    last_name: str,
    password: str,
    phone: str | None,
    db: AsyncSession,
) -> User:
    """Crea el usuario padre, lo vincula con el atleta y marca el token como usado.

    Operación atómica: si cualquier paso falla, el caller (get_db) hace rollback.
    """
    # Verificar que el email no esté ya registrado
    existing_user = (
        await db.execute(select(User).where(User.email == invite.email))
    ).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo electrónico",
        )

    # Cargar el atleta para obtener club_id
    athlete = (
        await db.execute(select(Athlete).where(Athlete.id == invite.athlete_id))
    ).scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # Crear usuario padre
    new_user = User(
        email=invite.email,
        hashed_password=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=UserRole.parent,
        can_login=True,
        created_by=invite.created_by,
    )
    db.add(new_user)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo electrónico",
        )

    # Crear membresía al club del atleta
    membership = ClubMember(
        club_id=athlete.club_id,
        user_id=new_user.id,
        role_in_club=ClubRole.parent,
    )
    db.add(membership)

    # Vincular parent-athlete (relación "acudiente" por defecto al usar token)
    pa = ParentAthlete(
        parent_id=new_user.id,
        athlete_id=invite.athlete_id,
        relationship_type=FamilyRelationship.acudiente,
    )
    db.add(pa)

    # Marcar invite como usado
    invite.used = True
    invite.used_by = new_user.id

    await db.flush()
    return new_user
