"""Modelos SQLAlchemy para el entrenamiento por intervalos estructurados
(feature 026).

Incluye:
- Enums de módulo: IntervalBlockType, HRZone
- IntervalStructure       — plan de intervalos autoría del entrenador, 1:1 con
                            una sesión de entrenamiento (FR-001)
- IntervalStructureBlock  — pasos ordenados de una estructura (FR-002/FR-003)
- IntervalTemplate        — plantilla reutilizable, independiente de sesión
                            (FR-008)
- IntervalTemplateBlock   — pasos de una plantilla (copy-on-attach, FR-009)

El enum ``ageband`` se **reutiliza** desde ``app.models.technique_exercise``
(migración ``e1f2a3b4c5d6``) — no se redefine ni se recrea (misma regla que
siguió la feature 021).

PRIVACIDAD / no-negociables (Ley 1581, menores): el modelo de bloques solo
declara dimensiones objetivo de zona de FC y **cadencia** — NO existe columna
de potencia (FR-005, D2). La cadencia objetivo siempre es ≥ 60 rpm (validado
en la capa de servicio, sin excepción por banda de edad — FR-004).
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
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
# Reutiliza el enum ageband existente (feature 018) — no lo redefinas.
from app.models.technique_exercise import AgeBand

if TYPE_CHECKING:
    from app.models.club import Club
    from app.models.interval_match_result import IntervalMatchResult
    from app.models.training_session import TrainingSession
    from app.models.user import User


# ---------------------------------------------------------------------------
# Enums — values_callable almacena el string .value (convención del proyecto)
# ---------------------------------------------------------------------------


class IntervalBlockType(str, enum.Enum):
    """Tipo de bloque dentro de una estructura de intervalos."""

    WARMUP = "warmup"
    WORK = "work"
    RECOVERY = "recovery"
    COOLDOWN = "cooldown"


class HRZone(str, enum.Enum):
    """Zona objetivo de frecuencia cardíaca (única dimensión de intensidad
    junto con la cadencia — no hay potencia)."""

    Z1 = "Z1"
    Z2 = "Z2"
    Z3 = "Z3"
    Z4 = "Z4"
    Z5 = "Z5"


# ---------------------------------------------------------------------------
# IntervalStructure — plan de intervalos 1:1 con una sesión
# ---------------------------------------------------------------------------


class IntervalStructure(Base):
    """Plan de intervalos autoría del entrenador, adjunto 1:1 a una sesión de
    entrenamiento (FR-001).

    La banda de edad declarada (``target_age_band``) dirige el age-gating (D3):
    las estructuras 10-12 con bloques Z1–Z2 requieren confirmación explícita
    (FR-007) y cualquier bloque Z3/Z4/Z5 en esa banda se bloquea (FR-006).
    """

    __tablename__ = "interval_structures"
    __table_args__ = (
        # 1:1 — una sesión tiene a lo sumo una estructura.
        UniqueConstraint(
            "training_session_id", name="uq_interval_structure_session"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    training_session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_age_band: Mapped[AgeBand] = mapped_column(
        SAEnum(AgeBand, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # True solo para estructuras 10-12 confirmadas (FR-007).
    age_gate_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    age_gate_confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    age_gate_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
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

    # --- Relaciones ----------------------------------------------------------
    blocks: Mapped[list["IntervalStructureBlock"]] = relationship(
        "IntervalStructureBlock",
        back_populates="structure",
        cascade="all, delete-orphan",
        order_by="IntervalStructureBlock.position",
        foreign_keys="[IntervalStructureBlock.structure_id]",
    )
    training_session: Mapped["TrainingSession"] = relationship(
        "TrainingSession",
        back_populates="interval_structure",
        foreign_keys="[IntervalStructure.training_session_id]",
    )
    match_results: Mapped[list["IntervalMatchResult"]] = relationship(
        "IntervalMatchResult",
        back_populates="structure",
        cascade="all, delete-orphan",
        foreign_keys="[IntervalMatchResult.structure_id]",
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys="[IntervalStructure.created_by_user_id]"
    )
    age_gate_confirmed_by: Mapped["User | None"] = relationship(
        "User", foreign_keys="[IntervalStructure.age_gate_confirmed_by_user_id]"
    )


# ---------------------------------------------------------------------------
# IntervalStructureBlock — pasos ordenados de una estructura
# ---------------------------------------------------------------------------


class IntervalStructureBlock(Base):
    """Paso ordenado de una estructura de intervalos (FR-002/FR-003).

    Los grupos de repetición comparten un mismo ``repeat_group``; el
    flattening expande cada grupo ``repeat_count`` veces en orden de posición.
    """

    __tablename__ = "interval_structure_blocks"
    __table_args__ = (
        UniqueConstraint(
            "structure_id", "position", name="uq_interval_structure_block_position"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[int] = mapped_column(
        ForeignKey("interval_structures.id", ondelete="CASCADE"), nullable=False
    )
    # Orden de autoría (los grupos de repetición cuentan una sola vez).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[IntervalBlockType] = mapped_column(
        SAEnum(IntervalBlockType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Duración planificada; también es el duration_hint del matching (check > 0).
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    # Única dimensión objetivo junto a la cadencia — no hay columna de potencia.
    target_zone: Mapped[HRZone] = mapped_column(
        SAEnum(HRZone, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # FR-004 — cadencia objetivo (check >= 60, cualquier banda, sin excepción).
    target_cadence_rpm: Mapped[int] = mapped_column(Integer, nullable=False)
    # Bloques con el mismo valor forman un grupo de repetición.
    repeat_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL ⇢ el bloque corre una vez; check >= 2 cuando está seteado.
    repeat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Relaciones ----------------------------------------------------------
    structure: Mapped["IntervalStructure"] = relationship(
        "IntervalStructure",
        back_populates="blocks",
        foreign_keys="[IntervalStructureBlock.structure_id]",
    )


# ---------------------------------------------------------------------------
# IntervalTemplate — plantilla reutilizable, independiente de sesión
# ---------------------------------------------------------------------------


class IntervalTemplate(Base):
    """Estructura reutilizable e independiente de sesión (FR-008).

    Al adjuntarse a una sesión (copy-on-attach, FR-009) sus bloques se **clonan**
    dentro de ``interval_structure_blocks``; no se retiene FK, editar o eliminar
    una plantilla nunca toca las sesiones que la usaron.
    """

    __tablename__ = "interval_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_age_band: Mapped[AgeBand] = mapped_column(
        SAEnum(AgeBand, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # Vocabulario controlado en el frontend (string, no enum, para que el
    # vocabulario evolucione sin migración).
    mesocycle_phase: Mapped[str] = mapped_column(String(50), nullable=False)
    competition_proximity: Mapped[str] = mapped_column(String(50), nullable=False)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Archivado suave (refleja strength_blocks); nunca se borra físicamente.
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
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

    # --- Relaciones ----------------------------------------------------------
    blocks: Mapped[list["IntervalTemplateBlock"]] = relationship(
        "IntervalTemplateBlock",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="IntervalTemplateBlock.position",
        foreign_keys="[IntervalTemplateBlock.template_id]",
    )
    club: Mapped["Club"] = relationship(
        "Club", foreign_keys="[IntervalTemplate.club_id]"
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys="[IntervalTemplate.created_by_user_id]"
    )


# ---------------------------------------------------------------------------
# IntervalTemplateBlock — pasos de una plantilla (mismo set que structure_block)
# ---------------------------------------------------------------------------


class IntervalTemplateBlock(Base):
    """Paso de una plantilla de intervalos.

    Conjunto de columnas idéntico a ``interval_structure_blocks`` con
    ``template_id`` en lugar de ``structure_id``; mismas validaciones.
    """

    __tablename__ = "interval_template_blocks"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "position", name="uq_interval_template_block_position"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("interval_templates.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[IntervalBlockType] = mapped_column(
        SAEnum(IntervalBlockType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    target_zone: Mapped[HRZone] = mapped_column(
        SAEnum(HRZone, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    target_cadence_rpm: Mapped[int] = mapped_column(Integer, nullable=False)
    repeat_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repeat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Relaciones ----------------------------------------------------------
    template: Mapped["IntervalTemplate"] = relationship(
        "IntervalTemplate",
        back_populates="blocks",
        foreign_keys="[IntervalTemplateBlock.template_id]",
    )
