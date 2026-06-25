"""SQLAlchemy model for ``technique_materials`` (feature 018).

Seeded list of physical materials required by exercises. The ``is_none`` flag
marks the sentinel row ("sin material") so that exercises without equipment
always match any available-materials filter.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.technique_exercise import TechniqueExercise


class TechniqueMaterial(Base):
    """Material físico requerido por un ejercicio técnico."""

    __tablename__ = "technique_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # True for the "sin material" sentinel row (always matches any filter).
    is_none: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- Relaciones --------------------------------------------------------
    exercises: Mapped[list["TechniqueExercise"]] = relationship(
        "TechniqueExercise",
        secondary="technique_exercise_materials",
        back_populates="materials",
        viewonly=True,
    )
