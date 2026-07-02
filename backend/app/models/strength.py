"""SQLAlchemy models for the strength training exercise library (feature 021).

Includes:
- Module-level enums: EquipmentKind, MovementCategory, StrengthProgressStatus
  (reuses AgeBand from app.models.technique_exercise)
- StrengthExercise         — catalog row (seeded + club-custom)
- StrengthExerciseAgeBand  — one row per (exercise, age_band) target
- StrengthBlock            — reusable, first-class block of exercises
- StrengthBlockEntry       — ordered exercise entry within a block
- StrengthSessionBlock     — attach link from an existing TrainingSession to a block
- StrengthProgressNote     — append-only per-athlete progress events
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.technique_exercise import AgeBand

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.club import Club
    from app.models.training_session import TrainingSession
    from app.models.user import User


# ---------------------------------------------------------------------------
# Enums — values_callable stores the .value string (project convention)
# ---------------------------------------------------------------------------


class EquipmentKind(str, enum.Enum):
    """Equipment requirement of a strength exercise."""

    SIN_EQUIPO = "sin_equipo"
    EQUIPO_GYM = "equipo_gym"


class MovementCategory(str, enum.Enum):
    """RT4T 5-category movement taxonomy."""

    EMPUJE_SUPERIOR = "empuje_superior"
    TRACCION_SUPERIOR = "traccion_superior"
    INFERIOR_BILATERAL = "inferior_bilateral"
    INFERIOR_UNILATERAL = "inferior_unilateral"
    CORE_ESTABILIDAD = "core_estabilidad"


class StrengthProgressStatus(str, enum.Enum):
    """Three-state mastery level recorded for an athlete on an exercise."""

    INTRODUCIDO = "introducido"
    EN_PROGRESO = "en_progreso"
    DOMINADO = "dominado"


# ---------------------------------------------------------------------------
# StrengthExercise — catalog row
# ---------------------------------------------------------------------------


class StrengthExercise(Base):
    """Ejercicio del catálogo de fuerza. Nunca se elimina físicamente."""

    __tablename__ = "strength_exercises"
    __table_args__ = (
        # Supports the default catalog query: non-hidden first, filtered by equipment.
        Index("idx_strength_exercise_visibility", "is_hidden", "equipment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stable slug for idempotent seed; unique across shared + club-custom exercises.
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    # Step-by-step execution guidance.
    how_to: Mapped[str] = mapped_column(Text, nullable=False)
    # Newline-separated list of common execution errors.
    common_errors: Mapped[str] = mapped_column(Text, nullable=False)
    # Original ASCII figure (no third-party photos).
    illustration_ascii: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain-language alt text for screen readers (WCAG AA — Constitution III).
    illustration_alt: Mapped[str] = mapped_column(String(500), nullable=False)
    equipment: Mapped[EquipmentKind] = mapped_column(
        SAEnum(EquipmentKind, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        index=True,
    )
    # Free-text detail for equipo_gym rows, e.g. "banda elástica".
    equipment_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    movement_category: Mapped[MovementCategory] = mapped_column(
        SAEnum(MovementCategory, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Default per-entry minutes for the running total (FR-010).
    suggested_duration_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # e.g. "2x10-15" — text, honors RM ranges without prescribing load.
    suggested_reps: Mapped[str] = mapped_column(String(60), nullable=False)
    # True for rows originating from the verified research report.
    is_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Soft-hide from default catalog; never hard-deleted.
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
    # One-to-many age bands; use selectinload.
    age_bands: Mapped[list["StrengthExerciseAgeBand"]] = relationship(
        "StrengthExerciseAgeBand",
        back_populates="exercise",
        cascade="all, delete-orphan",
    )
    club: Mapped["Club | None"] = relationship(
        "Club", foreign_keys="[StrengthExercise.club_id]"
    )
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys="[StrengthExercise.created_by_user_id]"
    )
    # Block entries referencing this exercise (RESTRICT — hide-not-delete).
    block_entries: Mapped[list["StrengthBlockEntry"]] = relationship(
        "StrengthBlockEntry",
        back_populates="exercise",
    )


# ---------------------------------------------------------------------------
# StrengthExerciseAgeBand — one row per (exercise, age_band) target
# ---------------------------------------------------------------------------


class StrengthExerciseAgeBand(Base):
    """Banda de edad a la que se dirige un ejercicio de fuerza.

    PK compuesto (exercise_id, age_band). Un ejercicio puede tener 10-12 y 13-15.
    """

    __tablename__ = "strength_exercise_age_bands"
    __table_args__ = (
        UniqueConstraint(
            "exercise_id", "age_band", name="uq_strength_exercise_age_band"
        ),
    )

    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("strength_exercises.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    age_band: Mapped[AgeBand] = mapped_column(
        SAEnum(AgeBand, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        primary_key=True,
    )

    # --- Relaciones --------------------------------------------------------
    exercise: Mapped["StrengthExercise"] = relationship(
        "StrengthExercise", back_populates="age_bands"
    )


# ---------------------------------------------------------------------------
# StrengthBlock — reusable, first-class block of exercises
# ---------------------------------------------------------------------------


class StrengthBlock(Base):
    """Bloque reutilizable de ejercicios de fuerza, propiedad de un club."""

    __tablename__ = "strength_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_age_band: Mapped[AgeBand] = mapped_column(
        SAEnum(AgeBand, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Configurable business rule (FR-009); default 30.
    duration_target_min: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=30
    )
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Soft-archive.
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    club: Mapped["Club"] = relationship(
        "Club", foreign_keys="[StrengthBlock.club_id]"
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys="[StrengthBlock.created_by_user_id]"
    )
    # Ordered entries; selectinload in service layer + order_by=position here
    # so the collection is deterministically ordered regardless of backend
    # (MySQL/aiosqlite do not guarantee row order without ORDER BY).
    entries: Mapped[list["StrengthBlockEntry"]] = relationship(
        "StrengthBlockEntry",
        back_populates="block",
        cascade="all, delete-orphan",
        order_by="StrengthBlockEntry.position",
    )
    # Sessions this block is attached to (link table).
    session_blocks: Mapped[list["StrengthSessionBlock"]] = relationship(
        "StrengthSessionBlock",
        back_populates="block",
    )


# ---------------------------------------------------------------------------
# StrengthBlockEntry — ordered exercise entry within a block
# ---------------------------------------------------------------------------


class StrengthBlockEntry(Base):
    """Entrada ordenada de un ejercicio dentro de un bloque de fuerza.

    FK a ejercicio con RESTRICT: hide-not-delete mantiene bloques guardados intactos.
    """

    __tablename__ = "strength_block_entries"
    __table_args__ = (
        UniqueConstraint("block_id", "position", name="uq_strength_block_entry_position"),
        Index("idx_sbe_block", "block_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[int] = mapped_column(
        ForeignKey("strength_blocks.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("strength_exercises.id", ondelete="RESTRICT"), nullable=False
    )
    # Order within the block.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Per-block override of the exercise's suggested default.
    duration_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reps: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # FR-011 recorded override: true iff exercise age bands ∌ block.target_age_band.
    is_age_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    override_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # --- Relaciones --------------------------------------------------------
    block: Mapped["StrengthBlock"] = relationship(
        "StrengthBlock",
        back_populates="entries",
        foreign_keys="[StrengthBlockEntry.block_id]",
    )
    exercise: Mapped["StrengthExercise"] = relationship(
        "StrengthExercise",
        back_populates="block_entries",
        foreign_keys="[StrengthBlockEntry.exercise_id]",
    )


# ---------------------------------------------------------------------------
# StrengthSessionBlock — attach link from TrainingSession to a StrengthBlock
# ---------------------------------------------------------------------------


class StrengthSessionBlock(Base):
    """Vínculo entre una sesión de entrenamiento y un bloque de fuerza.

    Un bloque es reutilizable entre sesiones (sin copy-on-attach). ON DELETE
    CASCADE de sesiones; RESTRICT de bloques para que sobrevivan al borrado
    de la sesión.
    """

    __tablename__ = "strength_session_blocks"
    __table_args__ = (
        UniqueConstraint(
            "training_session_id", "block_id", name="uq_strength_session_block"
        ),
        Index("idx_ssb_session", "training_session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    block_id: Mapped[int] = mapped_column(
        ForeignKey("strength_blocks.id", ondelete="RESTRICT"), nullable=False
    )
    # Order within the session, if multiple blocks are attached.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    attached_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    attached_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # --- Relaciones --------------------------------------------------------
    training_session: Mapped["TrainingSession"] = relationship(
        "TrainingSession",
        back_populates="strength_blocks",
        foreign_keys="[StrengthSessionBlock.training_session_id]",
    )
    block: Mapped["StrengthBlock"] = relationship(
        "StrengthBlock",
        back_populates="session_blocks",
        foreign_keys="[StrengthSessionBlock.block_id]",
    )
    attached_by: Mapped["User"] = relationship(
        "User", foreign_keys="[StrengthSessionBlock.attached_by_user_id]"
    )


# ---------------------------------------------------------------------------
# StrengthProgressNote — append-only per-athlete progress events (minors data)
# ---------------------------------------------------------------------------


class StrengthProgressNote(Base):
    """Evento de progreso de fuerza para un atleta (append-only).

    El estado actual = fila más reciente por (athlete_id, exercise_id).
    Dato de menores: acceso restringido a coach/admin.
    """

    __tablename__ = "strength_progress_notes"
    __table_args__ = (
        Index("idx_spn_athlete_exercise_time", "athlete_id", "exercise_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("strength_exercises.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[StrengthProgressStatus] = mapped_column(
        SAEnum(StrengthProgressStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Mastery-climate phrasing; minors-safe. No PII stored here.
    coach_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # --- Relaciones --------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[StrengthProgressNote.athlete_id]"
    )
    exercise: Mapped["StrengthExercise"] = relationship(
        "StrengthExercise", foreign_keys="[StrengthProgressNote.exercise_id]"
    )
    recorded_by: Mapped["User"] = relationship(
        "User", foreign_keys="[StrengthProgressNote.recorded_by_user_id]"
    )
