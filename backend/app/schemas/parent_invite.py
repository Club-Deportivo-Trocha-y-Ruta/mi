from datetime import datetime

from pydantic import BaseModel, field_validator


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


class ParentRegisterRequest(BaseModel):
    """Payload para registrar un padre a partir de un token de invitación
    (POST /api/auth/parent-register)."""

    token: str
    first_name: str
    last_name: str
    password: str
    phone: str | None = None

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
