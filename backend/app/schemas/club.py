from datetime import datetime

from pydantic import BaseModel

from app.models.club import ClubRole


class ClubCreate(BaseModel):
    name: str
    code: str
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
