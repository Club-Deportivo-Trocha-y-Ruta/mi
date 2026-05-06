from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator

from app.models.anthropometry import MaturationStatus


class AnthropometryCreate(BaseModel):
    evaluation_date: date
    weight_kg: Decimal
    standing_height_cm: Decimal
    arm_span_cm: Decimal | None = None
    sitting_height_cm: Decimal
    notes: str | None = None

    @field_validator("evaluation_date")
    @classmethod
    def evaluation_date_must_not_be_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("La fecha de evaluación no puede ser futura")
        return v


class GrowthPercentiles(BaseModel):
    bmi: float | None = None
    height_z_score: float | None = None
    height_percentile: float | None = None
    bmi_z_score: float | None = None
    bmi_percentile: float | None = None
    weight_z_score: float | None = None
    weight_percentile: float | None = None
    nutritional_status_height: str | None = None
    nutritional_status_bmi: str | None = None


class MorphologyMetrics(BaseModel):
    ape_index: float
    arm_span_height_delta_cm: float
    posture_screening_flag: bool
    posture_screening_message: str | None = None
    bike_fit_category: str
    bike_fit_guidance: str
    ape_index_advisory: str | None = None


class AnthropometryOut(BaseModel):
    id: int
    athlete_id: int
    evaluation_date: date
    weight_kg: float
    standing_height_cm: float
    arm_span_cm: float | None
    sitting_height_cm: float
    leg_length_cm: float
    leg_sitting_ratio: float
    maturity_offset: float
    age_at_phv: float
    maturation_status: MaturationStatus
    training_implications: str | None
    evaluated_by: int
    created_at: datetime
    notes: str | None
    # Campos individuales de percentiles (nullable — compatibilidad backward)
    height_z_score: float | None = None
    height_percentile: float | None = None
    bmi: float | None = None
    bmi_z_score: float | None = None
    bmi_percentile: float | None = None
    weight_z_score: float | None = None
    weight_percentile: float | None = None
    nutritional_status: str | None = None
    # Objeto compuesto (se construye desde el router; no proviene del ORM directamente)
    growth_percentiles: GrowthPercentiles | None = None
    morphology: MorphologyMetrics | None = None

    model_config = {"from_attributes": True}
