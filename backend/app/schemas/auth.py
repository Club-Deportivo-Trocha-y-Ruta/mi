from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 1 or len(v) > 128:
            raise ValueError("Contraseña debe tener entre 1 y 128 caracteres")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: int
    email: str | None
    first_name: str
    last_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    can_login: bool
    club_ids: list[int]
    created_at: datetime

    model_config = {"from_attributes": True}
