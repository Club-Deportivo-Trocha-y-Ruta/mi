from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.models.athlete import Sex
from app.schemas.anthropometry import AnthropometryOut


class AthleteCreate(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    sex: Sex
    club_join_date: date | None = None
    club_id: int

    @field_validator("birth_date")
    @classmethod
    def birth_date_must_be_past(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("La fecha de nacimiento debe ser en el pasado")
        return v

    @field_validator("club_join_date")
    @classmethod
    def club_join_date_must_be_past(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("La fecha de ingreso al club debe ser en el pasado o hoy")
        return v


class AthleteUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    club_join_date: date | None = None

    @field_validator("club_join_date")
    @classmethod
    def club_join_date_must_be_past(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("La fecha de ingreso al club debe ser en el pasado o hoy")
        return v


class AthleteOut(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    birth_date: date
    sex: Sex
    club_join_date: date | None
    years_in_club: float | None = None
    age_decimal: float | None = None
    category: str | None = None
    club_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AthleteDetailOut(AthleteOut):
    latest_anthropometry: AnthropometryOut | None = None


class AthleteListOut(BaseModel):
    items: list[AthleteOut]
    total: int
