"""Modelo SQLAlchemy para ``anxiety_baselines`` (feature 017).

Línea base por atleta + subescala + familia de instrumento. La primera
evaluación calificable la siembra (ventana diagnóstica abril/temprana). Un
cambio de instrumento crea una familia de línea base nueva (no comparable,
FR-022).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anxiety_assessment import AnxietyAssessment
    from app.models.athlete import Athlete


class BaselineSubscale(str, enum.Enum):
    cognitive = "cognitive"
    somatic = "somatic"
    selfconfidence = "selfconfidence"


class BaselineInstrumentType(str, enum.Enum):
    csai2 = "csai2"
    csai2r = "csai2r"
    sas2 = "sas2"


class AnxietyBaseline(Base):
    """Línea base por (atleta, subescala, familia de instrumento)."""

    __tablename__ = "anxiety_baselines"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "subscale",
            "instrument_type",
            name="uq_anxiety_baseline_athlete_subscale_instrument",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    subscale: Mapped[BaselineSubscale] = mapped_column(
        Enum(
            BaselineSubscale,
            name="anxietybaselinesubscale",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    instrument_type: Mapped[BaselineInstrumentType] = mapped_column(
        Enum(
            BaselineInstrumentType,
            name="anxietybaselineinstrumenttype",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("anxiety_assessments.id", ondelete="CASCADE"), nullable=False
    )
    established_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[AnxietyBaseline.athlete_id]"
    )
    source_assessment: Mapped["AnxietyAssessment"] = relationship(
        "AnxietyAssessment", foreign_keys="[AnxietyBaseline.source_assessment_id]"
    )
