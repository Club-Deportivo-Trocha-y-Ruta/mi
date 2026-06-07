"""Schemas del flujo de restablecimiento de contraseña (specs/003-password-reset-login).

Contrato de privacidad: ninguna respuesta expone si la cuenta existe, ni el
nombre/rol del titular, ni el token en claro. Los mensajes son neutrales.
"""

from pydantic import BaseModel, field_validator


class PasswordResetRequest(BaseModel):
    """Solicitud de enlace de restablecimiento (POST .../request)."""

    email: str

    @field_validator("email")
    @classmethod
    def email_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ingresa un correo electrónico válido.")
        return v.strip()


class PasswordResetConfirm(BaseModel):
    """Confirmación del restablecimiento con token + nueva contraseña."""

    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def token_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Enlace no válido.")
        return v.strip()

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Misma política que el registro de padres (mín. 8 caracteres).
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


class PasswordResetMessage(BaseModel):
    """Respuesta neutral genérica (request y confirm)."""

    message: str


class PasswordResetValidate(BaseModel):
    """Resultado de validar un token (GET .../validate)."""

    valid: bool
