"""Modelo SQLAlchemy para ``race_course_category_setups`` (feature 043).

Una fila por (válida, categoría): cuántas vueltas se corren y sobre cuál
``RaceCourseVariant`` se corren. Unicidad ``(race_event_id, category_id)`` —
una categoría solo puede tener un setup por válida. No lleva relación ORM
hacia ``race_event_id`` ni ``category_id`` a propósito (modelo minimalista,
igual que la mayoría de FKs planas en ``race_result.py``); solo expone la
relación hacia ``variant`` porque el servicio la necesita para renderizar
``lap_distance_m`` y demás datos de la variante junto al setup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import ActorTimestampMixin

if TYPE_CHECKING:
    from app.models.race_course_variant import RaceCourseVariant


class RaceCourseCategorySetup(ActorTimestampMixin, Base):
    """Vueltas + variante de recorrido asignadas a una categoría en una válida."""

    __tablename__ = "race_course_category_setups"
    __table_args__ = (
        UniqueConstraint(
            "race_event_id",
            "category_id",
            name="uq_race_course_setups_event_category",
        ),
        CheckConstraint("laps BETWEEN 1 AND 20", name="ck_race_course_setups_laps_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("race_events.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("race_categories.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("race_course_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    laps: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    variant: Mapped["RaceCourseVariant"] = relationship(
        "RaceCourseVariant",
        back_populates="setups",
        foreign_keys="[RaceCourseCategorySetup.variant_id]",
    )
