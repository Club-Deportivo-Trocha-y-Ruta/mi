from datetime import datetime

from pydantic import BaseModel

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str
    last_name: str
    phone: str | None = None
    role: UserRole
    club_id: int | None = None


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


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
