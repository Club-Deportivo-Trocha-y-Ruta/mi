from datetime import date
from typing import Any

from pydantic import BaseModel, model_validator

from app.models.anthropometry import MaturationStatus
from app.models.athlete import FamilyRelationship, Sex


class ParentAthleteCreate(BaseModel):
    parent_id: int
    athlete_id: int
    relationship: FamilyRelationship


class ParentAthleteOut(BaseModel):
    id: int
    parent_id: int
    athlete_id: int
    relationship: FamilyRelationship
    parent_name: str
    parent_email: str | None
    parent_phone: str | None
    athlete_name: str

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_from_orm(cls, data: Any) -> Any:
        # Si llega un objeto ORM (tiene relationship_type), extraer manualmente.
        # Si llega un dict (p.ej. desde tests o construcción directa), pasar tal cual.
        if hasattr(data, "relationship_type"):
            return {
                "id": data.id,
                "parent_id": data.parent_id,
                "athlete_id": data.athlete_id,
                "relationship": data.relationship_type,
                "parent_name": (
                    f"{data.parent.first_name} {data.parent.last_name}"
                    if data.parent
                    else ""
                ),
                "parent_email": data.parent.email if data.parent else None,
                "parent_phone": data.parent.phone if data.parent else None,
                "athlete_name": (
                    f"{data.athlete.first_name} {data.athlete.last_name}"
                    if data.athlete
                    else ""
                ),
            }
        return data


class ParentAthleteListOut(BaseModel):
    items: list[ParentAthleteOut]
    total: int


class MyAthleteOut(BaseModel):
    """Vista del atleta para el portal de padres — datos básicos + estado de maduración."""

    athlete_id: int
    athlete_first_name: str
    athlete_last_name: str
    birth_date: date
    sex: Sex
    age_decimal: float | None
    category: str | None
    relationship: FamilyRelationship
    latest_anthropometry_date: date | None
    maturation_status: MaturationStatus | None
    standing_height_cm: float | None
    weight_kg: float | None
    # "ok" | "due_soon" | "overdue" | "never"
    measurement_status: str

    # Se construye manualmente en el router (no desde ORM directo)
    model_config = {"from_attributes": False}
