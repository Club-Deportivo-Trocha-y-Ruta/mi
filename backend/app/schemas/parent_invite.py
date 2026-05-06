from datetime import datetime

from pydantic import BaseModel, field_validator

_RELATIONSHIP_TYPES_VALIDOS = {"padre", "madre", "acudiente"}


class ParentalConsentData(BaseModel):
    """Datos de consentimiento parental aceptados durante onboarding.

    Política v1.1 (2026-05-06): solo se solicitan los dos consentimientos
    correspondientes a tratamientos efectivamente implementados — datos
    básicos del atleta y antropometría. Los campos `accept_training_tracking`
    y `accept_third_party` quedan como opcionales por compatibilidad con
    clientes antiguos pero el servicio fuerza su persistencia a False
    (Ley 1581/2012, principio de finalidad y consentimiento informado).
    """

    accept_data_collection: bool
    accept_anthropometry: bool
    accept_training_tracking: bool = False
    accept_third_party: bool = False
    privacy_policy_version: str = "v1.1"


class ParentInviteCreate(BaseModel):
    athlete_id: int
    email: str

    @field_validator("email")
    @classmethod
    def email_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El email no puede estar vacío")
        return v.strip().lower()


class ParentInviteTokenValidation(BaseModel):
    """Respuesta al validar un token de invitación (GET /api/auth/invite/{token})."""

    athlete_id: int
    athlete_name: str
    email: str
    expires_at: datetime
    valid: bool
    role: str = "parent"
    club_name: str = ""


class ParentRegisterRequest(BaseModel):
    """Payload para registrar un padre a partir de un token de invitación
    (POST /api/auth/parent-register)."""

    token: str
    first_name: str
    last_name: str
    password: str
    phone: str | None = None
    relationship_type: str = "acudiente"
    consent: ParentalConsentData = ParentalConsentData(
        accept_data_collection=False,
        accept_anthropometry=False,
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator("relationship_type")
    @classmethod
    def relationship_type_valido(cls, v: str) -> str:
        normalizado = v.strip().lower()
        if normalizado not in _RELATIONSHIP_TYPES_VALIDOS:
            raise ValueError(
                f"El tipo de parentesco debe ser uno de: {', '.join(sorted(_RELATIONSHIP_TYPES_VALIDOS))}"
            )
        return normalizado


class ParentRegisterOut(BaseModel):
    """Respuesta al completar el registro del padre."""

    id: int
    email: str
    first_name: str
    last_name: str
    message: str = "Cuenta creada exitosamente"


class ParentInviteOut(BaseModel):
    """Representación pública de una invitación (sin exponer el token)."""

    id: int
    athlete_id: int
    email: str
    expires_at: datetime
    used: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ParentInviteCreatedOut(ParentInviteOut):
    """Respuesta al CREAR una invitación — incluye el token (exposición única)."""

    token: str


class ParentalConsentOut(BaseModel):
    """Representación pública de un registro de consentimiento parental (uso futuro)."""

    id: int
    athlete_id: int
    consent_version: str
    consented_at: datetime
    consent_method: str
    data_collection: bool
    training_tracking: bool
    anthropometry: bool
    third_party_sharing: bool
    withdrawn_at: datetime | None

    model_config = {"from_attributes": True}
