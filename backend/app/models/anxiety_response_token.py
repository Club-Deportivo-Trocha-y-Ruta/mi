"""Modelo SQLAlchemy para ``anxiety_response_tokens`` (feature 017).

Acceso de un solo uso para que el atleta responda sin login (CL-002). Se
almacena el HASH del token, nunca el valor crudo. El token es inválido si fue
consumido o expiró; enviar respuestas lo consume.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anxiety_assessment import AnxietyAssessment


class AnxietyResponseToken(Base):
    """Token opaco, de un solo uso, con expiración, atado a una evaluación."""

    __tablename__ = "anxiety_response_tokens"
    __table_args__ = (
        Index("ix_anxiety_response_tokens_assessment", "assessment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("anxiety_assessments.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    assessment: Mapped["AnxietyAssessment"] = relationship(
        "AnxietyAssessment",
        back_populates="tokens",
        foreign_keys="[AnxietyResponseToken.assessment_id]",
    )
