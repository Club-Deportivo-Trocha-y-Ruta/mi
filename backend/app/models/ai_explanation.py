from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete
    from app.models.user import User


class AthleteAIExplanation(Base):
    """Caché de outputs de IA por (atleta, medición, use case).

    El texto persistido ya está saneado por `Guardrails` y `_scrub` en el
    use case, así que es seguro de leer por cualquier rol con acceso al
    atleta. La cache key incluye `anthropometric_record_id`: cuando se
    crea una medición nueva, el ID cambia y el cache se invalida
    implícitamente sin necesidad de DELETE.
    """

    __tablename__ = "athlete_ai_explanations"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "anthropometric_record_id",
            "use_case",
            name="uq_ai_expl_athlete_record_usecase",
        ),
        Index("ix_ai_expl_athlete_id", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    anthropometric_record_id: Mapped[int] = mapped_column(
        ForeignKey("anthropometric_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Discriminador para futuros use cases (training_plan_explainer, etc.)
    use_case: Mapped[str] = mapped_column(
        String(64), nullable=False, default="phv_explainer"
    )

    # Payload — refleja PHVExplanationResponse
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    age_group: Mapped[str] = mapped_column(String(16), nullable=False)
    maturation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )

    # Auditoría: ¿quién pidió la generación?
    generated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[AthleteAIExplanation.athlete_id]",
    )
    record: Mapped[AnthropometricRecord] = relationship(
        "AnthropometricRecord",
        foreign_keys="[AthleteAIExplanation.anthropometric_record_id]",
    )
    generated_by: Mapped[User] = relationship(
        "User",
        foreign_keys="[AthleteAIExplanation.generated_by_user_id]",
    )
