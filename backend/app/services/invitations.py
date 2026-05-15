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
from app.models.parental_consent import ParentalConsent
from app.models.user import User, UserRole
from app.schemas.parent_invite import ParentalConsentData
from app.services.auth import hash_password

INVITE_EXPIRY_HOURS = 72


async def create_invite(
    athlete_id: int,
    email: str,
    created_by_user_id: int,
    db: AsyncSession,
    parent_user_id: int | None = None,
) -> ParentInvite:
    """Genera un token de invitación para un padre.

    Si ya existe uno no-usado y no-expirado para el mismo atleta+email,
    lo retorna directamente sin crear un duplicado. Si se reutiliza y trae un
    parent_user_id distinto al almacenado, se actualiza para apuntar al usuario
    pre-creado correcto.
    """
    existing_stmt = select(ParentInvite).where(
        ParentInvite.athlete_id == athlete_id,
        ParentInvite.email == email,
        ParentInvite.used == False,  # noqa: E712
        ParentInvite.expires_at > datetime.now(timezone.utc),
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        if parent_user_id is not None and existing.parent_user_id != parent_user_id:
            existing.parent_user_id = parent_user_id
            await db.flush()
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
        parent_user_id=parent_user_id,
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
    relationship_type: str = "acudiente",
    consent: ParentalConsentData | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    """Crea el usuario padre, lo vincula con el atleta y marca el token como usado.

    Opcionalmente registra el consentimiento parental digital y actualiza el
    campo parental_consent_obtained del atleta en la misma transacción atómica.

    Args:
        invite: Invitación válida (no usada, no expirada).
        first_name: Nombre del padre/acudiente.
        last_name: Apellido del padre/acudiente.
        password: Contraseña en texto plano (se hashea internamente).
        phone: Teléfono de contacto (opcional).
        db: Sesión async de SQLAlchemy.
        relationship_type: Parentesco declarado ('padre', 'madre', 'acudiente').
        consent: Datos de consentimiento parental aceptados en el wizard.
        ip_address: IP del cliente para trazabilidad del consentimiento.
    """
    # Cargar el atleta para obtener club_id y actualizar consentimiento
    athlete = await db.get(Athlete, invite.athlete_id)

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    # Mapear string → FamilyRelationship enum (el validator del schema ya
    # garantiza que el valor es uno de los tres permitidos)
    try:
        family_rel = FamilyRelationship(relationship_type)
    except ValueError:
        family_rel = FamilyRelationship.acudiente

    # Si la invitación tiene parent_user_id, hacer UPDATE del usuario existente
    # en lugar de INSERT — evita duplicados cuando el coach pre-creó al padre.
    if invite.parent_user_id is not None:
        target_user = await db.get(User, invite.parent_user_id)
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El usuario padre referenciado por la invitación no existe",
            )

        # Validar que el email destino no choque con otra cuenta distinta
        email_owner_stmt = select(User).where(
            User.email == invite.email, User.id != target_user.id
        )
        email_owner = (await db.execute(email_owner_stmt)).scalar_one_or_none()
        if email_owner is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con este correo electrónico",
            )

        target_user.email = invite.email
        target_user.hashed_password = hash_password(password)
        target_user.first_name = first_name
        target_user.last_name = last_name
        target_user.phone = phone
        target_user.role = UserRole.parent
        target_user.can_login = True
        target_user.is_active = True

        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con este correo electrónico",
            )

        new_user = target_user

        # Asegurar membresía en el club (idempotente)
        membership_stmt = select(ClubMember).where(
            ClubMember.user_id == new_user.id,
            ClubMember.club_id == athlete.club_id,
        )
        existing_membership = (await db.execute(membership_stmt)).scalar_one_or_none()
        if existing_membership is None:
            db.add(
                ClubMember(
                    club_id=athlete.club_id,
                    user_id=new_user.id,
                    role_in_club=ClubRole.parent,
                )
            )

        # Actualizar (o crear) ParentAthlete con el parentesco final del wizard
        pa_stmt = select(ParentAthlete).where(
            ParentAthlete.parent_id == new_user.id,
            ParentAthlete.athlete_id == invite.athlete_id,
        )
        pa_existing = (await db.execute(pa_stmt)).scalar_one_or_none()
        if pa_existing is not None:
            pa_existing.relationship_type = family_rel
        else:
            db.add(
                ParentAthlete(
                    parent_id=new_user.id,
                    athlete_id=invite.athlete_id,
                    relationship_type=family_rel,
                )
            )
    else:
        # Camino legacy: invitación sin pre-creación. Verificar email libre y
        # crear todo desde cero.
        existing_user = (
            await db.execute(select(User).where(User.email == invite.email))
        ).scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con este correo electrónico",
            )

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

        db.add(
            ClubMember(
                club_id=athlete.club_id,
                user_id=new_user.id,
                role_in_club=ClubRole.parent,
            )
        )
        db.add(
            ParentAthlete(
                parent_id=new_user.id,
                athlete_id=invite.athlete_id,
                relationship_type=family_rel,
            )
        )

    # Registrar consentimiento parental si fue proporcionado
    if consent is not None:
        from app.models.privacy_policy import PrivacyPolicy

        now_utc = datetime.now(timezone.utc)

        # Resolver policy_id desde la versión de política indicada
        policy_stmt = select(PrivacyPolicy).where(
            PrivacyPolicy.version == consent.privacy_policy_version
        )
        policy = (await db.execute(policy_stmt)).scalar_one_or_none()
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"La versión de política '{consent.privacy_policy_version}' no existe. "
                    "Actualiza la aplicación y vuelve a intentarlo."
                ),
            )

        # training_tracking aún no está activo como finalidad — siempre False.
        # third_party_sharing: habilitado desde política v1.2; se propaga desde
        # el campo accept_third_party_sharing del wizard de onboarding.
        # (Ley 1581/2012, principio de finalidad y consentimiento informado)
        parental_consent = ParentalConsent(
            parent_user_id=new_user.id,
            athlete_id=invite.athlete_id,
            consent_version=consent.privacy_policy_version,
            policy_id=policy.id,
            consented_at=now_utc,
            consent_method="digital_wizard",
            ip_address=ip_address,
            user_agent=user_agent,
            data_collection=consent.accept_data_collection,
            training_tracking=False,
            anthropometry=consent.accept_anthropometry,
            third_party_sharing=consent.accept_third_party_sharing,
        )
        db.add(parental_consent)

        # Actualizar estado de consentimiento en el atleta
        athlete.parental_consent_obtained = True
        athlete.parental_consent_date = now_utc

    # Marcar invite como usado
    invite.used = True
    invite.used_by = new_user.id

    await db.flush()
    return new_user
