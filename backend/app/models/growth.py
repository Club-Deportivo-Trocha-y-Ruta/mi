from __future__ import annotations

import enum

from sqlalchemy import DECIMAL, Enum, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GrowthSource(str, enum.Enum):
    WHO = "WHO"
    CDC = "CDC"


class GrowthIndicator(str, enum.Enum):
    height_for_age = "height_for_age"
    weight_for_age = "weight_for_age"
    bmi_for_age = "bmi_for_age"


class GrowthReferenceLms(Base):
    __tablename__ = "growth_reference_lms"
    __table_args__ = (
        UniqueConstraint("source", "indicator", "sex", "age_months", name="uq_lms_source_indicator_sex_age"),
        Index("ix_lms_source_indicator_sex", "source", "indicator", "sex"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[GrowthSource] = mapped_column(
        Enum(GrowthSource, values_callable=lambda e: [x.value for x in e])
    )
    indicator: Mapped[GrowthIndicator] = mapped_column(
        Enum(GrowthIndicator, values_callable=lambda e: [x.value for x in e])
    )
    sex: Mapped[str] = mapped_column(Enum("M", "F", name="sex_enum"))
    age_months: Mapped[float] = mapped_column(DECIMAL(5, 1))
    L: Mapped[float] = mapped_column(DECIMAL(15, 12))
    M: Mapped[float] = mapped_column(DECIMAL(10, 6))
    S: Mapped[float] = mapped_column(DECIMAL(15, 12))
