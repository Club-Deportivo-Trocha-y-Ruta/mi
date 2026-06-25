"""SQLAlchemy model for ``technique_skills`` (feature 018).

The A–H skill taxonomy seeded from the research report §2. Each skill maps to a
single letter code and a focus line used for catalog filtering and athlete
progress tracking.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.technique_exercise import TechniqueExercise
    from app.models.technique_exercise import AthleteSkillProgress


class TechniqueSkill(Base):
    """Habilidad técnica del catálogo (A–H). Dato de referencia; no se elimina."""

    __tablename__ = "technique_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Single letter A–H; uniqueness enforced at DB level.
    code: Mapped[str] = mapped_column(String(1), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    focus: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Relaciones --------------------------------------------------------
    # Back-population from the M2M association table (selectinload in list reads).
    exercises: Mapped[list["TechniqueExercise"]] = relationship(
        "TechniqueExercise",
        secondary="technique_exercise_skills",
        back_populates="skills",
        viewonly=True,
    )
