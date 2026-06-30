"""SQLAlchemy models for the technique & gymkhana catalog (feature 018).

Includes:
- Module-level enums: AgeBand, ExerciseDifficulty, SessionSegment, SkillProgressStatus
- Association tables: technique_exercise_skills, technique_exercise_materials
- TechniqueExercise        — catalog row (seeded + coach-custom)
- TechniqueExerciseAgeBand — one row per (exercise, age_band) target
- TechniqueSessionExercise — link from an existing TrainingSession to exercises
- AthleteSkillProgress     — append-only skill-tracking events per athlete
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.club import Club
    from app.models.technique_material import TechniqueMaterial
    from app.models.technique_skill import TechniqueSkill
    from app.models.training_session import TrainingSession
    from app.models.user import User


# ---------------------------------------------------------------------------
# Enums — values_callable stores the .value string (project convention)
# ---------------------------------------------------------------------------


class AgeBand(str, enum.Enum):
    """Age range a catalog exercise targets."""

    BAND_7_9 = "7-9"
    BAND_10_12 = "10-12"
    BAND_13_15 = "13-15"


class ExerciseDifficulty(str, enum.Enum):
    """Progression difficulty of a technique exercise."""

    FACIL = "facil"
    MEDIA = "media"
    AVANZADA = "avanzada"


class SessionSegment(str, enum.Enum):
    """Segment of a training session where an exercise is placed."""

    CALENTAMIENTO = "calentamiento"
    PRINCIPAL = "principal"
    VUELTA_CALMA = "vuelta_calma"


class SkillProgressStatus(str, enum.Enum):
    """Three-state mastery level recorded for an athlete on a skill."""

    INTRODUCIDO = "introducido"
    EN_PROGRESO = "en_progreso"
    DOMINADO = "dominado"


# ---------------------------------------------------------------------------
# Secondary association tables (Core Table — no ORM class needed)
# ---------------------------------------------------------------------------

# M2M: exercise ↔ skill (CASCADE on exercise side, RESTRICT on skill)
technique_exercise_skills = Table(
    "technique_exercise_skills",
    Base.metadata,
    Column(
        "exercise_id",
        Integer,
        ForeignKey("technique_exercises.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ),
    Column(
        "skill_id",
        Integer,
        ForeignKey("technique_skills.id", ondelete="RESTRICT"),
        nullable=False,
        primary_key=True,
    ),
)

# M2M: exercise ↔ material (CASCADE on exercise side, RESTRICT on material)
technique_exercise_materials = Table(
    "technique_exercise_materials",
    Base.metadata,
    Column(
        "exercise_id",
        Integer,
        ForeignKey("technique_exercises.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ),
    Column(
        "material_id",
        Integer,
        ForeignKey("technique_materials.id", ondelete="RESTRICT"),
        nullable=False,
        primary_key=True,
    ),
)


# ---------------------------------------------------------------------------
# TechniqueExercise — catalog row
# ---------------------------------------------------------------------------


class TechniqueExercise(Base):
    """Ejercicio del catálogo de técnica/gymkhana. Nunca se elimina físicamente."""

    __tablename__ = "technique_exercises"
    __table_args__ = (
        # Supports the default catalog query: non-hidden first, then by difficulty.
        Index("idx_technique_exercise_visibility", "is_hidden", "difficulty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stable slug for idempotent seed; unique across shared + club-custom exercises.
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    # Step-by-step coaching method (NICA Dilo→Muéstralo→Háganlo→Revísenlo).
    how_to: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[ExerciseDifficulty] = mapped_column(
        SAEnum(ExerciseDifficulty, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # "🎉 juego puro" engagement flag.
    is_game: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Gymkhana exercises carry a circuit layout (FR-008).
    is_gymkhana: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Preformatted monospace croquis (research D1); null for non-gymkhana exercises.
    layout_ascii: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain-language text alternative for screen readers (WCAG AA — research D1).
    layout_alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured SVG circuit layout for feature 019 (Phase A); null until migrated/authored.
    layout_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Research confidence tag (🟢/🟡/⚪ + refs), informational only.
    confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # True for rows originating from the verified research report (D3).
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Soft-hide from default catalog (FR-019); never hard-deleted.
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # null = shared/seeded; set for club-custom exercises.
    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relaciones --------------------------------------------------------
    # M2M collections — use selectinload in list/detail reads (research D2).
    skills: Mapped[list["TechniqueSkill"]] = relationship(
        "TechniqueSkill",
        secondary=technique_exercise_skills,
        back_populates="exercises",
    )
    materials: Mapped[list["TechniqueMaterial"]] = relationship(
        "TechniqueMaterial",
        secondary=technique_exercise_materials,
        back_populates="exercises",
    )
    # One-to-many age bands; use selectinload.
    age_bands: Mapped[list["TechniqueExerciseAgeBand"]] = relationship(
        "TechniqueExerciseAgeBand",
        back_populates="exercise",
        cascade="all, delete-orphan",
    )
    club: Mapped["Club | None"] = relationship(
        "Club", foreign_keys="[TechniqueExercise.club_id]"
    )
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys="[TechniqueExercise.created_by_user_id]"
    )
    # Sessions that include this exercise (via link table).
    session_exercises: Mapped[list["TechniqueSessionExercise"]] = relationship(
        "TechniqueSessionExercise",
        back_populates="exercise",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# TechniqueExerciseAgeBand — one row per (exercise, age_band) target
# ---------------------------------------------------------------------------


class TechniqueExerciseAgeBand(Base):
    """Banda de edad a la que se dirige un ejercicio del catálogo.

    PK compuesto (exercise_id, age_band). Un ejercicio para 7–15 tiene tres filas.
    """

    __tablename__ = "technique_exercise_age_bands"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "age_band", name="uq_technique_exercise_age_band"
        ),
    )

    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("technique_exercises.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    age_band: Mapped[AgeBand] = mapped_column(
        SAEnum(AgeBand, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        primary_key=True,
    )

    # --- Relaciones --------------------------------------------------------
    exercise: Mapped["TechniqueExercise"] = relationship(
        "TechniqueExercise", back_populates="age_bands"
    )


# ---------------------------------------------------------------------------
# TechniqueSessionExercise — link from TrainingSession to catalog exercises
# ---------------------------------------------------------------------------


class TechniqueSessionExercise(Base):
    """Vínculo entre una sesión de entrenamiento y un ejercicio del catálogo.

    La presencia de ≥ 1 fila indica que la sesión fue ensamblada con el builder
    de técnica (FR-011/013/020). ON DELETE CASCADE de sesiones; RESTRICT de
    ejercicios para que el hide-not-delete mantenga sesiones guardadas intactas.
    """

    __tablename__ = "technique_session_exercises"
    __table_args__ = (
        Index("idx_tse_session", "training_session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("technique_exercises.id", ondelete="RESTRICT"), nullable=False
    )
    segment: Mapped[SessionSegment] = mapped_column(
        SAEnum(SessionSegment, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Order within the segment (0-based or 1-based; service layer normalizes).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Relaciones --------------------------------------------------------
    training_session: Mapped["TrainingSession"] = relationship(
        "TrainingSession",
        back_populates="technique_exercises",
        foreign_keys="[TechniqueSessionExercise.training_session_id]",
    )
    exercise: Mapped["TechniqueExercise"] = relationship(
        "TechniqueExercise",
        back_populates="session_exercises",
        foreign_keys="[TechniqueSessionExercise.exercise_id]",
    )


# ---------------------------------------------------------------------------
# AthleteSkillProgress — append-only skill-tracking events (US4, minors data)
# ---------------------------------------------------------------------------


class AthleteSkillProgress(Base):
    """Evento de progreso de habilidad técnica para un atleta (append-only).

    El estado actual = fila más reciente por (athlete_id, skill_id).
    La evolución de temporada = filas ordenadas por recorded_at dentro de season.
    Dato de menores: acceso restringido a coach/admin (FR-021, D6).
    """

    __tablename__ = "athlete_skill_progress"
    __table_args__ = (
        Index("idx_asp_athlete_skill_time", "athlete_id", "skill_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("technique_skills.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[SkillProgressStatus] = mapped_column(
        SAEnum(SkillProgressStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Mastery-climate phrasing; minors-safe. No PII stored here.
    coach_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Year for season scoping (FR-016).
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relaciones --------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[AthleteSkillProgress.athlete_id]"
    )
    skill: Mapped["TechniqueSkill"] = relationship(
        "TechniqueSkill", foreign_keys="[AthleteSkillProgress.skill_id]"
    )
    recorded_by: Mapped["User"] = relationship(
        "User", foreign_keys="[AthleteSkillProgress.recorded_by_user_id]"
    )
