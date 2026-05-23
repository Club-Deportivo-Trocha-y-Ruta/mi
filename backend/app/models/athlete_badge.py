from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete


class BadgeType(str, enum.Enum):
    attendance_100 = "attendance_100"
    attendance_90 = "attendance_90"
    attendance_75 = "attendance_75"
    first_podium = "first_podium"
    mtp = "mtp"        # Mejor Tiempo Personal
    top10 = "top10"


class BadgeSource(str, enum.Enum):
    attendance = "attendance"
    race = "race"


class AthleteBadge(Base):
    """Insignia idempotente por periodo (asistencia o competitiva).

    La restricción UNIQUE (athlete_id, badge_type, period_year, period_month)
    garantiza que el badge_evaluator sea idempotente: evaluar el mismo periodo
    dos veces no duplica insignias.
    """

    __tablename__ = "athlete_badges"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "badge_type",
            "period_year",
            "period_month",
            name="uq_athlete_badge_period",
        ),
        Index("idx_athlete_badges_athlete_period", "athlete_id", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    badge_type: Mapped[BadgeType] = mapped_column(
        Enum(BadgeType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    badge_source: Mapped[BadgeSource] = mapped_column(
        Enum(BadgeSource, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    period_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    athlete: Mapped["Athlete"] = relationship(
        "Athlete",
        back_populates="badges",
        foreign_keys="[AthleteBadge.athlete_id]",
    )
