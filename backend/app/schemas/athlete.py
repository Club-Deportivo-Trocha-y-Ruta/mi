from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.models.anthropometry import MaturationStatus
from app.models.athlete import Sex
from app.schemas.anthropometry import AnthropometryOut, GrowthPercentiles


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
    parental_consent_obtained: bool = False
    parental_consent_date: datetime | None = None

    model_config = {"from_attributes": True}


class AthleteDetailOut(AthleteOut):
    latest_anthropometry: AnthropometryOut | None = None


class AthleteListOut(BaseModel):
    items: list[AthleteOut]
    total: int


class AnthropometryParentView(BaseModel):
    """Vista reducida de antropometría para padres — sin notas del coach ni mesociclo."""

    id: int
    athlete_id: int
    evaluation_date: date
    weight_kg: float
    standing_height_cm: float
    sitting_height_cm: float
    maturation_status: MaturationStatus
    age_at_phv: float
    maturity_offset: float
    # Percentiles (para curvas de crecimiento)
    height_z_score: float | None = None
    height_percentile: float | None = None
    bmi: float | None = None
    growth_percentiles: GrowthPercentiles | None = None
    # Excluidos: notes, training_implications, evaluated_by, mesocycle, arm_span_cm

    model_config = {"from_attributes": True}


class AthleteParentView(BaseModel):
    """Vista de atleta para padres — datos básicos + última antropometría reducida."""

    id: int
    first_name: str
    last_name: str
    birth_date: date
    sex: Sex
    age_decimal: float | None = None
    category: str | None = None
    club_join_date: date | None = None
    latest_anthropometry: AnthropometryParentView | None = None

    model_config = {"from_attributes": True}
