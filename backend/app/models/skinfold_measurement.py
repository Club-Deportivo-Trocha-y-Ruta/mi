"""Skinfold set attached 1:1 to an anthropometric record (feature 046).

Source of truth: ``specs/046-body-composition-skinfolds/data-model.md`` §1.

One row per ``anthropometric_records`` row that has a skinfold set; an absent
row means no skinfolds were taken for that evaluation (the case for every
historical record). Six sites, each either explicitly declined
(``{site}_declined = true`` → ``{site}_mm`` and ``{site}_readings`` NULL) or
measured (2–3 raw readings in ``{site}_readings``, the computed site value in
``{site}_mm``). Sums and the Slaughter estimate are persisted; every value is
filled by ``app/services/body_composition.py::apply_set`` — never write the
columns by hand. ``athlete_id`` is denormalised for trend queries and must
equal the parent record's athlete (validated in the service).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import ActorTimestampMixin

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete
    from app.models.user import User


def _declined_column() -> Mapped[bool]:
    return mapped_column(Boolean, nullable=False, default=False, server_default="0")


class SkinfoldMeasurement(ActorTimestampMixin, Base):
    __tablename__ = "skinfold_measurements"
    __table_args__ = (
        UniqueConstraint("anthropometric_record_id", name="uq_skinfold_measurements_record"),
        Index("ix_skinfold_measurements_athlete", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anthropometric_record_id: Mapped[int] = mapped_column(
        ForeignKey("anthropometric_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id"), nullable=False
    )

    # Site values (mean of 2 / median of 3); NULL when declined.
    triceps_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    biceps_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    subscapular_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    medial_calf_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    iliac_crest_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    supraspinale_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)

    # Explicit per-site decline.
    triceps_declined: Mapped[bool] = _declined_column()
    biceps_declined: Mapped[bool] = _declined_column()
    subscapular_declined: Mapped[bool] = _declined_column()
    medial_calf_declined: Mapped[bool] = _declined_column()
    iliac_crest_declined: Mapped[bool] = _declined_column()
    supraspinale_declined: Mapped[bool] = _declined_column()

    # Raw readings [r1, r2] or [r1, r2, r3]; NULL when declined.
    triceps_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    biceps_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    subscapular_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    medial_calf_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    iliac_crest_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    supraspinale_readings: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    # Sums: Σ4 = triceps + biceps + subscapular + medial_calf; Σ6 = all six.
    sum4_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    sum6_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)

    # Slaughter (triceps + calf) estimate; NULL when triceps or calf declined.
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    fat_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    fat_free_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    equation_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    protocol_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="v1", server_default="v1"
    )
    caliper_model: Mapped[str] = mapped_column(
        String(32), nullable=False, default="slim_guide", server_default="slim_guide"
    )
    measured_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    record: Mapped[AnthropometricRecord] = relationship(
        "AnthropometricRecord",
        back_populates="skinfolds",
        foreign_keys="[SkinfoldMeasurement.anthropometric_record_id]",
    )
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[SkinfoldMeasurement.athlete_id]",
    )
    measurer: Mapped[User] = relationship(
        "User",
        foreign_keys="[SkinfoldMeasurement.measured_by]",
    )
