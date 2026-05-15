"""Schemas Pydantic para políticas de privacidad y consentimiento parental."""

from datetime import date, datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Schemas de PrivacyPolicy
# ---------------------------------------------------------------------------


class PrivacyPolicySummaryOut(BaseModel):
    """Versión sin content_html para listados y referencias anidadas."""

    id: int
    version: str
    effective_date: date
    title: str
    changelog: str | None
    deprecated_at: date | None

    model_config = {"from_attributes": True}


class PrivacyPolicyOut(PrivacyPolicySummaryOut):
    """Versión completa con el texto de la política para visualización."""

    content_html: str
    content_hash: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Schemas de consentimiento parental (separados de parent_invite.py)
# ---------------------------------------------------------------------------


class ConsentGrants(BaseModel):
    """Checkboxes de consentimiento activos en un registro dado."""

    data_collection: bool
    anthropometry: bool
    training_tracking: bool = False
    third_party_sharing: bool = False


class CurrentConsentOut(BaseModel):
    """Estado de un consentimiento individual (el más reciente no-retirado)."""

    id: int
    policy_version: str
    consented_at: datetime
    is_current_policy: bool
    withdrawn_at: datetime | None
    grants: ConsentGrants

    model_config = {"from_attributes": True}


class AthleteConsentStatus(BaseModel):
    """Estado de consentimiento de un atleta vinculado al padre."""

    athlete_id: int
    athlete_name: str
    # None si el atleta nunca tuvo consentimiento o todos fueron retirados
    current_consent: CurrentConsentOut | None


class ConsentStatusOut(BaseModel):
    """Respuesta de GET /api/me/consent — resumen de la política activa y consentimientos."""

    active_policy: PrivacyPolicySummaryOut
    consents_per_athlete: list[AthleteConsentStatus]


class ConsentRenewIn(BaseModel):
    """Payload para renovar consentimiento (POST /api/me/consent/renew)."""

    athlete_id: int
    policy_version: str
    accept_data_collection: bool
    accept_anthropometry: bool
    accept_third_party_sharing: bool = False


class ConsentWithdrawIn(BaseModel):
    """Payload para revocar consentimiento (POST /api/me/consent/withdraw)."""

    athlete_id: int
    reason: str | None = None


class ConsentEventOut(BaseModel):
    """Representación de un registro de consentimiento (evento individual)."""

    id: int
    athlete_id: int
    policy_version: str
    consented_at: datetime
    withdrawn_at: datetime | None
    grants: ConsentGrants

    model_config = {"from_attributes": True}
