from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User


class ParentalConsent(Base):
    __tablename__ = "parental_consents"
    __table_args__ = (
        Index("ix_parental_consents_parent_athlete", "parent_user_id", "athlete_id"),
        Index("ix_parental_consents_athlete_id", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    consent_version: Mapped[str] = mapped_column(String(20))
    consented_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    consent_method: Mapped[str] = mapped_column(
        String(50), default="digital_wizard"
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Checkboxes de consentimiento
    data_collection: Mapped[bool] = mapped_column(Boolean, default=False)
    training_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    anthropometry: Mapped[bool] = mapped_column(Boolean, default=False)
    third_party_sharing: Mapped[bool] = mapped_column(Boolean, default=False)

    # None = consentimiento vigente; fecha = consentimiento retirado
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    # Padre/acudiente que otorgó el consentimiento
    parent: Mapped[User] = relationship(
        "User",
        foreign_keys="[ParentalConsent.parent_user_id]",
    )
    # Atleta menor al que aplica el consentimiento
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[ParentalConsent.athlete_id]",
    )
