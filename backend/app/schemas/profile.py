"""Schemas del módulo de perfil / ajustes de cuenta (specs/004-user-profile).

Contrato de privacidad: ninguna respuesta expone ``hashed_password``,
``token_hash``, el token en claro, ``requested_ip`` ni datos de otra cuenta.
Las operaciones actúan siempre sobre el usuario autenticado.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.models.user import UserRole


class ProfileOut(BaseModel):
    """Vista de lectura del perfil propio."""

    id: int
    email: str | None
    first_name: str
    last_name: str
    phone: str | None
    role: UserRole

    model_config = {"from_attributes": True}


class ProfileBasicUpdate(BaseModel):
    """Actualización de información básica. Al menos un campo debe venir."""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("El nombre no puede estar vacío.")
            if len(v) > 100:
                raise ValueError("El nombre es demasiado largo.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if v == "":
                return None
            if len(v) > 20:
                raise ValueError("El teléfono es demasiado largo.")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProfileBasicUpdate":
        if (
            self.first_name is None
            and self.last_name is None
            and self.phone is None
        ):
            raise ValueError("Debes indicar al menos un campo para actualizar.")
        return self


class PasswordChangeRequest(BaseModel):
    """Cambio de contraseña en sesión (requiere la contraseña actual)."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Misma política que el resto del proyecto (mín. 8 caracteres).
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v

    @model_validator(mode="after")
    def new_differs_from_current(self) -> "PasswordChangeRequest":
        if self.current_password == self.new_password:
            raise ValueError(
                "La nueva contraseña debe ser distinta de la actual."
            )
        return self


class EmailChangeRequestBody(BaseModel):
    """Solicitud de cambio de correo (requiere la contraseña actual)."""

    current_password: str
    new_email: EmailStr


class EmailChangeConfirm(BaseModel):
    """Confirmación del cambio de correo con el token del enlace."""

    token: str

    @field_validator("token")
    @classmethod
    def token_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Enlace no válido.")
        return v.strip()


class ProfileMessage(BaseModel):
    """Respuesta neutral genérica."""

    message: str
