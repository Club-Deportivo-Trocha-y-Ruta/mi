from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User


class MaturationStatus(str, enum.Enum):
    pre_phv = "Pre-PHV"
    circa_phv = "Circa-PHV"
    post_phv = "Post-PHV"


class NutritionalStatus(str, enum.Enum):
    # Talla para la Edad (T/E) — Resolución 2465/2016 MinSalud Colombia
    retraso_talla = "retraso_talla"
    riesgo_retraso_talla = "riesgo_retraso_talla"
    talla_adecuada = "talla_adecuada"
    talla_alta = "talla_alta"
    # IMC para la Edad — Resolución 2465/2016 MinSalud Colombia
    delgadez_severa = "delgadez_severa"
    delgadez = "delgadez"
    adecuado = "adecuado"
    sobrepeso = "sobrepeso"
    obesidad = "obesidad"


class AnthropometricRecord(Base):
    __tablename__ = "anthropometric_records"
    __table_args__ = (
        Index("ix_anthro_athlete_date", "athlete_id", "evaluation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    evaluation_date: Mapped[date] = mapped_column(Date)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    standing_height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    arm_span_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    sitting_height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    leg_length_cm: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    leg_sitting_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    maturity_offset: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    age_at_phv: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    maturation_status: Mapped[MaturationStatus] = mapped_column(
        Enum(MaturationStatus, values_callable=lambda e: [x.value for x in e])
    )
    training_implications: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Campos de percentiles y estado nutricional (WHO/CDC) — nullable para compatibilidad backward
    height_z_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    height_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    bmi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    bmi_z_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    bmi_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    weight_z_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    weight_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    nutritional_status: Mapped[NutritionalStatus | None] = mapped_column(
        Enum(NutritionalStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )

    # Atleta al que pertenece la medición
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        back_populates="anthropometric_records",
        foreign_keys="[AnthropometricRecord.athlete_id]",
    )
    # Coach/admin que realizó la evaluación
    evaluator: Mapped[User] = relationship(
        "User",
        foreign_keys="[AnthropometricRecord.evaluated_by]",
    )
