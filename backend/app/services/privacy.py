"""Servicio de gestión de políticas de privacidad y consentimiento parental.

Principio append-only (Ley 1581/2012):
- `privacy_policies` nunca se modifica tras inserción.
- `parental_consents` solo admite UPDATE de `withdrawn_at` y `withdrawal_reason`.
  Toda renovación es INSERT de un nuevo registro.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete, ParentAthlete
from app.models.parental_consent import ParentalConsent
from app.models.privacy_policy import PrivacyPolicy
from app.schemas.privacy_policy import (
    AthleteConsentStatus,
    ConsentEventOut,
    ConsentGrants,
    ConsentStatusOut,
    CurrentConsentOut,
)


# ---------------------------------------------------------------------------
# Helpers de política
# ---------------------------------------------------------------------------


async def get_active_policy(db: AsyncSession) -> PrivacyPolicy:
    """Retorna la política activa: la de effective_date más reciente con deprecated_at NULL."""
    stmt = (
        select(PrivacyPolicy)
        .where(PrivacyPolicy.deprecated_at.is_(None))
        .order_by(PrivacyPolicy.effective_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay política de privacidad activa configurada",
        )
    return policy


async def get_policy_by_version(version: str, db: AsyncSession) -> PrivacyPolicy | None:
    """Retorna la política correspondiente a la versión dada, o None si no existe."""
    stmt = select(PrivacyPolicy).where(PrivacyPolicy.version == version)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Helpers de consentimiento
# ---------------------------------------------------------------------------


async def get_current_consent_for_athlete(
    parent_user_id: int,
    athlete_id: int,
    db: AsyncSession,
) -> ParentalConsent | None:
    """Retorna el consentimiento vigente (no retirado) del padre para el atleta dado.

    Vigente = el más reciente con withdrawn_at IS NULL.
    """
    stmt = (
        select(ParentalConsent)
        .where(
            ParentalConsent.parent_user_id == parent_user_id,
            ParentalConsent.athlete_id == athlete_id,
            ParentalConsent.withdrawn_at.is_(None),
        )
        .order_by(ParentalConsent.consented_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def athlete_has_ai_processing_consent(
    athlete_id: int, db: AsyncSession
) -> bool:
    """Indica si el atleta tiene autorización vigente para procesamiento con IA.

    Bajo Ley 1581/2012 Art. 9, enviar datos de menores a un tercero (Anthropic/Google)
    requiere autorización expresa para esa finalidad. El campo
    `third_party_sharing` actúa como compuerta para el procesamiento con LLM.

    Regla:
      - Si el atleta NO tiene padres vinculados (caso degenerado dev/admin):
        se autoriza por defecto.
      - Si tiene padres vinculados y existe AL MENOS un consentimiento vigente
        con `third_party_sharing=True`: se autoriza.
      - En cualquier otro caso (sin consentimiento o todos `False`): se deniega.
    """
    pa_stmt = select(ParentAthlete.parent_id).where(
        ParentAthlete.athlete_id == athlete_id
    )
    parent_ids = [row for row in (await db.execute(pa_stmt)).scalars().all()]
    if not parent_ids:
        return True

    stmt = (
        select(ParentalConsent.id)
        .where(
            ParentalConsent.athlete_id == athlete_id,
            ParentalConsent.parent_user_id.in_(parent_ids),
            ParentalConsent.withdrawn_at.is_(None),
            ParentalConsent.third_party_sharing.is_(True),
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


def _build_consent_event_out(consent: ParentalConsent) -> ConsentEventOut:
    """Construye un ConsentEventOut desde un registro ORM."""
    policy_version = (
        consent.policy.version if consent.policy else consent.consent_version
    )
    return ConsentEventOut(
        id=consent.id,
        athlete_id=consent.athlete_id,
        policy_version=policy_version,
        consented_at=consent.consented_at,
        withdrawn_at=consent.withdrawn_at,
        grants=ConsentGrants(
            data_collection=consent.data_collection,
            anthropometry=consent.anthropometry,
            training_tracking=consent.training_tracking,
            third_party_sharing=consent.third_party_sharing,
        ),
    )


async def get_consent_status(
    parent_user_id: int,
    db: AsyncSession,
) -> ConsentStatusOut:
    """Retorna el estado de consentimiento del padre para todos sus atletas vinculados."""
    from app.schemas.privacy_policy import PrivacyPolicySummaryOut

    active_policy = await get_active_policy(db)

    # Cargar todos los atletas vinculados al padre
    pa_stmt = (
        select(ParentAthlete)
        .options(selectinload(ParentAthlete.athlete))
        .where(ParentAthlete.parent_id == parent_user_id)
    )
    pa_result = await db.execute(pa_stmt)
    parent_athlete_rows = pa_result.scalars().all()

    consents_per_athlete: list[AthleteConsentStatus] = []

    for pa in parent_athlete_rows:
        athlete = pa.athlete
        if athlete is None:
            continue

        consent = await get_current_consent_for_athlete(
            parent_user_id, athlete.id, db
        )

        current_consent_out: CurrentConsentOut | None = None
        if consent is not None:
            policy_version = (
                consent.policy.version if consent.policy else consent.consent_version
            )
            current_consent_out = CurrentConsentOut(
                id=consent.id,
                policy_version=policy_version,
                consented_at=consent.consented_at,
                is_current_policy=(policy_version == active_policy.version),
                withdrawn_at=consent.withdrawn_at,
                grants=ConsentGrants(
                    data_collection=consent.data_collection,
                    anthropometry=consent.anthropometry,
                    training_tracking=consent.training_tracking,
                    third_party_sharing=consent.third_party_sharing,
                ),
            )

        consents_per_athlete.append(
            AthleteConsentStatus(
                athlete_id=athlete.id,
                athlete_name=f"{athlete.first_name} {athlete.last_name}",
                current_consent=current_consent_out,
            )
        )

    return ConsentStatusOut(
        active_policy=PrivacyPolicySummaryOut.model_validate(active_policy),
        consents_per_athlete=consents_per_athlete,
    )


async def renew_consent(
    parent_user_id: int,
    athlete_id: int,
    policy_version: str,
    accept_data_collection: bool,
    accept_anthropometry: bool,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> ParentalConsent:
    """Registra un nuevo consentimiento (INSERT).

    Si existe un consentimiento vigente previo para el mismo padre+atleta,
    lo marca como supersedido antes de insertar el nuevo. Garantiza append-only:
    no hace UPDATE del consentimiento previo salvo withdrawn_at y withdrawal_reason.
    """
    # Validar que la versión de política existe
    policy = await get_policy_by_version(policy_version, db)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Versión de política '{policy_version}' no existe",
        )

    # Validar que el padre está vinculado al atleta
    pa_stmt = select(ParentAthlete).where(
        ParentAthlete.parent_id == parent_user_id,
        ParentAthlete.athlete_id == athlete_id,
    )
    pa = (await db.execute(pa_stmt)).scalar_one_or_none()
    if pa is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes un atleta vinculado con ese identificador",
        )

    now_utc = datetime.now(timezone.utc)

    # Marcar el consentimiento anterior como supersedido (append-only)
    previous = await get_current_consent_for_athlete(parent_user_id, athlete_id, db)
    if previous is not None:
        previous.withdrawn_at = now_utc
        previous.withdrawal_reason = "superseded by new consent"
        await db.flush()

    # Insertar nuevo registro — no UPDATE del anterior
    new_consent = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version=policy_version,
        policy_id=policy.id,
        consented_at=now_utc,
        consent_method="digital_renewal",
        ip_address=ip_address,
        user_agent=user_agent,
        data_collection=accept_data_collection,
        # Política v1.1: tracking y terceros no son finalidades activas
        training_tracking=False,
        anthropometry=accept_anthropometry,
        third_party_sharing=False,
    )
    db.add(new_consent)
    await db.flush()
    await db.refresh(new_consent)
    return new_consent


async def withdraw_consent(
    parent_user_id: int,
    athlete_id: int,
    reason: str | None,
    db: AsyncSession,
) -> ParentalConsent:
    """Revoca el consentimiento vigente del padre para el atleta.

    Solo modifica withdrawn_at y withdrawal_reason — el resto del registro
    permanece inmutable (append-only). Si no hay consentimiento vigente, lanza 404.
    """
    # Validar vinculación padre-atleta
    pa_stmt = select(ParentAthlete).where(
        ParentAthlete.parent_id == parent_user_id,
        ParentAthlete.athlete_id == athlete_id,
    )
    pa = (await db.execute(pa_stmt)).scalar_one_or_none()
    if pa is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes un atleta vinculado con ese identificador",
        )

    consent = await get_current_consent_for_athlete(parent_user_id, athlete_id, db)
    if consent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay consentimiento vigente para revocar",
        )

    consent.withdrawn_at = datetime.now(timezone.utc)
    consent.withdrawal_reason = reason
    await db.flush()
    await db.refresh(consent)
    return consent
