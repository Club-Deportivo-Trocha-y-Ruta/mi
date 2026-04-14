from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.club import ClubRole


class ClubCreate(BaseModel):
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    location: str | None = None


class ClubUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    is_active: bool | None = None


class ClubOut(BaseModel):
    id: int
    name: str
    code: str
    location: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ClubMemberAdd(BaseModel):
    user_id: int
    role_in_club: ClubRole


class ClubMemberOut(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    role_in_club: ClubRole
    joined_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def flatten_user(cls, data: Any) -> Any:
        # Cuando el objeto viene del ORM, extraemos los campos del usuario relacionado
        if hasattr(data, "user") and data.user is not None:
            return {
                "id": data.id,
                "user_id": data.user_id,
                "first_name": data.user.first_name,
                "last_name": data.user.last_name,
                "role_in_club": data.role_in_club,
                "joined_at": data.joined_at,
            }
        return data


class ClubDetailOut(ClubOut):
    members: list[ClubMemberOut] = []
