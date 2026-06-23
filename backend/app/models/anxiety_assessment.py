"""Modelo SQLAlchemy para ``anxiety_assessments`` (feature 017).

Una administración de un instrumento a un atleta, atada (opcionalmente) a una
válida del calendario. Las respuestas ítem-por-ítem se guardan siempre
(FR-010) para permitir recálculo determinista. La interpretación se cachea
on-demand (FR-013) con trazabilidad de fuente (``llm``|``rule``).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anxiety_instrument import AnxietyInstrument
    from app.models.anxiety_response_token import AnxietyResponseToken
    from app.models.athlete import Athlete
    from app.models.race_event import RaceEvent
    from app.models.user import User


class AssessmentStatus(str, enum.Enum):
    pending = "pending"
    partial = "partial"
    completed = "completed"


class EventPriority(str, enum.Enum):
    """Prioridad A/B/C copiada del evento para conservar el contexto histórico."""

    A = "A"
    B = "B"
    C = "C"


class InterpretationSource(str, enum.Enum):
    llm = "llm"
    rule = "rule"


class AnxietyAssessment(Base):
    """Una administración de un instrumento a un atleta."""

    __tablename__ = "anxiety_assessments"
    __table_args__ = (
        Index("ix_anxiety_assessments_athlete_scheduled", "athlete_id", "scheduled_at"),
        Index("ix_anxiety_assessments_event", "event_id"),
        Index("ix_anxiety_assessments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("anxiety_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_events.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[EventPriority | None] = mapped_column(
        Enum(
            EventPriority,
            name="anxietyeventpriority",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(
            AssessmentStatus,
            name="anxietyassessmentstatus",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=AssessmentStatus.pending,
    )

    # Respuestas ítem-por-ítem (FR-010). Mapa "<item_id>" → 1..4.
    answers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Puntuaciones por subescala (computadas). selfconfidence nullable (N/A SAS-2).
    score_cognitive: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_somatic: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_selfconfidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    instrument_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    override_ack_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Interpretación cacheada (esquema fijo) + trazabilidad.
    interpretation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    interpretation_source: Mapped[InterpretationSource | None] = mapped_column(
        Enum(
            InterpretationSource,
            name="anxietyinterpretationsource",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    interpretation_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interpreted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Banderas de alerta (p. ej. ansiedad alta + confianza baja).
    flags_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)

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

    # --- Relaciones --------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[AnxietyAssessment.athlete_id]"
    )
    instrument: Mapped["AnxietyInstrument"] = relationship(
        "AnxietyInstrument",
        back_populates="assessments",
        foreign_keys="[AnxietyAssessment.instrument_id]",
    )
    event: Mapped["RaceEvent | None"] = relationship(
        "RaceEvent", foreign_keys="[AnxietyAssessment.event_id]"
    )
    created_by: Mapped["User"] = relationship(
        "User", foreign_keys="[AnxietyAssessment.created_by_user_id]"
    )
    tokens: Mapped[list["AnxietyResponseToken"]] = relationship(
        "AnxietyResponseToken",
        back_populates="assessment",
        foreign_keys="[AnxietyResponseToken.assessment_id]",
        cascade="all, delete-orphan",
    )
