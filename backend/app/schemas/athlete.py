from datetime import date, datetime

from pydantic import BaseModel

from app.models.athlete import Sex


class AthleteCreate(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    sex: Sex
    years_in_club: int | None = None
    club_id: int


class AthleteUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    years_in_club: int | None = None


class AthleteOut(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    birth_date: date
    sex: Sex
    years_in_club: int | None
    age_decimal: float | None = None
    category: str | None = None
    club_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
