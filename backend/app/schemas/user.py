from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.user import UserRole
from app.services.audit import AccountStateReasonCode


class UserCreate(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str
    last_name: str
    phone: str | None = None
    role: UserRole
    club_id: int | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    # Motivo de la desactivación/reactivación (feature 041, T021 mínimo viable
    # para que record_audit pueda exigirlo en `deactivate`, por
    # contracts/audit-recording.md §4.2). Nunca se persiste en `users` — solo
    # viaja a `audit_log.reason_code`. La validación fina por grupo y el
    # copy 422 completo quedan a cargo de T046 (contracts/staff-admin.md §4).
    reason_code: AccountStateReasonCode | None = None


class UserOut(BaseModel):
    id: int
    email: str | None
    first_name: str
    last_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    can_login: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int
