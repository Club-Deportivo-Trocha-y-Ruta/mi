"""Router de políticas de privacidad y consentimiento parental.

Endpoints:
  GET  /api/auth/active-policy      — público, retorna la política activa completa
  GET  /api/me/consent              — padre autenticado, estado de consentimientos
  POST /api/me/consent/renew        — padre, renovar consentimiento (append-only)
  POST /api/me/consent/withdraw     — padre, revocar consentimiento
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_role
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction
from app.models.user import User, UserRole
from app.schemas.privacy_policy import (
    ConsentEventOut,
    ConsentRenewIn,
    ConsentStatusOut,
    ConsentWithdrawIn,
    PrivacyPolicyOut,
)
from app.services.audit import AuditEntityType, record_audit
from app.services.privacy import (
    get_active_policy,
    get_consent_status,
    get_current_consent_for_athlete,
    renew_consent,
    withdraw_consent,
)

# Router para endpoints bajo /api/auth (público)
public_router = APIRouter()

# Router para endpoints bajo /api/me/consent (autenticado, solo padres)
consent_router = APIRouter()

_only_parent = require_role([UserRole.parent])


# ---------------------------------------------------------------------------
# Endpoint público
# ---------------------------------------------------------------------------


@public_router.get(
    "/active-policy",
    response_model=PrivacyPolicyOut,
    summary="Política de privacidad activa",
    description="Retorna el texto completo de la política de privacidad vigente. Público, sin autenticación.",
)
async def get_active_policy_endpoint(
    db: AsyncSession = Depends(get_db),
) -> PrivacyPolicyOut:
    """Retorna la versión activa de la política de privacidad (sin autenticación).

    Útil para mostrar el texto en el wizard de onboarding y en /privacidad.
    """
    policy = await get_active_policy(db)
    return PrivacyPolicyOut.model_validate(policy)


# ---------------------------------------------------------------------------
# Endpoints autenticados (solo padres)
# ---------------------------------------------------------------------------


@consent_router.get(
    "",
    response_model=ConsentStatusOut,
    summary="Estado de consentimientos del padre",
)
async def get_my_consent_status(
    current_user: User = Depends(_only_parent),
    db: AsyncSession = Depends(get_db),
) -> ConsentStatusOut:
    """Retorna el estado de consentimiento del padre para cada atleta vinculado.

    Incluye la política activa actual y si el consentimiento existente corresponde
    a esa versión o a una versión anterior (is_current_policy).
    """
    return await get_consent_status(current_user.id, db)


@consent_router.post(
    "/renew",
    response_model=ConsentEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Renovar consentimiento parental",
)
async def renew_my_consent(
    body: ConsentRenewIn,
    request: Request,
    current_user: User = Depends(_only_parent),
    db: AsyncSession = Depends(get_db),
) -> ConsentEventOut:
    """Registra un nuevo consentimiento (INSERT) para el atleta indicado.

    Si existía un consentimiento vigente para el mismo atleta, lo marca como
    supersedido automáticamente. El anterior no se elimina (append-only).

    Errores posibles:
    - 400 si la versión de política no existe.
    - 403 si el padre no está vinculado al atleta.
    """
    # Capturar IP y user-agent para trazabilidad (Ley 1581, Art. 26)
    ip_address: str | None = request.client.host if request.client else None
    user_agent: str | None = request.headers.get("user-agent")

    athlete_result = await db.execute(select(Athlete).where(Athlete.id == body.athlete_id))
    athlete = athlete_result.scalar_one_or_none()
    club_id = athlete.club_id if athlete is not None else None

    previous = await get_current_consent_for_athlete(current_user.id, body.athlete_id, db)

    new_consent = await renew_consent(
        parent_user_id=current_user.id,
        athlete_id=body.athlete_id,
        policy_version=body.policy_version,
        accept_data_collection=body.accept_data_collection,
        accept_anthropometry=body.accept_anthropometry,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db,
        accept_third_party_sharing=body.accept_third_party_sharing,
    )

    if previous is not None:
        await record_audit(
            db,
            action=AuditAction.update,
            entity_type=AuditEntityType.parental_consent,
            entity_id=previous.id,
            actor=current_user,
            club_id=club_id,
            athlete_id=body.athlete_id,
            changed_fields=["withdrawn_at", "withdrawal_reason"],
        )

    await record_audit(
        db,
        action=AuditAction.create,
        entity_type=AuditEntityType.parental_consent,
        entity_id=new_consent.id,
        actor=current_user,
        club_id=club_id,
        athlete_id=body.athlete_id,
    )

    return _to_consent_event_out(new_consent)


@consent_router.post(
    "/withdraw",
    response_model=ConsentEventOut,
    summary="Revocar consentimiento parental",
)
async def withdraw_my_consent(
    body: ConsentWithdrawIn,
    current_user: User = Depends(_only_parent),
    db: AsyncSession = Depends(get_db),
) -> ConsentEventOut:
    """Revoca el consentimiento vigente del padre para el atleta indicado.

    Solo modifica `withdrawn_at` y `withdrawal_reason` — el resto del registro
    permanece inmutable. Si no hay consentimiento vigente retorna 404.

    Errores posibles:
    - 403 si el padre no está vinculado al atleta.
    - 404 si no hay consentimiento vigente para revocar.
    """
    consent = await withdraw_consent(
        parent_user_id=current_user.id,
        athlete_id=body.athlete_id,
        reason=body.reason,
        db=db,
    )

    athlete_result = await db.execute(select(Athlete).where(Athlete.id == body.athlete_id))
    athlete = athlete_result.scalar_one_or_none()
    club_id = athlete.club_id if athlete is not None else None

    await record_audit(
        db,
        action=AuditAction.update,
        entity_type=AuditEntityType.parental_consent,
        entity_id=consent.id,
        actor=current_user,
        club_id=club_id,
        athlete_id=body.athlete_id,
        changed_fields=["withdrawn_at", "withdrawal_reason"],
    )

    return _to_consent_event_out(consent)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _to_consent_event_out(consent) -> ConsentEventOut:
    """Convierte un ORM ParentalConsent a ConsentEventOut."""
    from app.schemas.privacy_policy import ConsentGrants

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
