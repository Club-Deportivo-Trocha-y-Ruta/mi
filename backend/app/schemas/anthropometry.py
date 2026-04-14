from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.models.anthropometry import MaturationStatus


class AnthropometryCreate(BaseModel):
    evaluation_date: date
    mesocycle: int | None = None
    weight_kg: Decimal
    standing_height_cm: Decimal
    arm_span_cm: Decimal | None = None
    sitting_height_cm: Decimal
    notes: str | None = None


class GrowthPercentiles(BaseModel):
    bmi: Decimal | None = None
    height_z_score: Decimal | None = None
    height_percentile: Decimal | None = None
    bmi_z_score: Decimal | None = None
    bmi_percentile: Decimal | None = None
    weight_z_score: Decimal | None = None
    weight_percentile: Decimal | None = None
    nutritional_status_height: str | None = None
    nutritional_status_bmi: str | None = None


class AnthropometryOut(BaseModel):
    id: int
    athlete_id: int
    evaluation_date: date
    mesocycle: int | None
    weight_kg: Decimal
    standing_height_cm: Decimal
    arm_span_cm: Decimal | None
    sitting_height_cm: Decimal
    leg_length_cm: Decimal
    leg_sitting_ratio: Decimal
    maturity_offset: Decimal
    age_at_phv: Decimal
    maturation_status: MaturationStatus
    training_implications: str | None
    evaluated_by: int
    created_at: datetime
    notes: str | None
    # Campos individuales de percentiles (nullable — compatibilidad backward)
    height_z_score: Decimal | None = None
    height_percentile: Decimal | None = None
    bmi: Decimal | None = None
    bmi_z_score: Decimal | None = None
    bmi_percentile: Decimal | None = None
    weight_z_score: Decimal | None = None
    weight_percentile: Decimal | None = None
    nutritional_status: str | None = None
    # Objeto compuesto (se construye desde el router; no proviene del ORM directamente)
    growth_percentiles: GrowthPercentiles | None = None

    model_config = {"from_attributes": True}
