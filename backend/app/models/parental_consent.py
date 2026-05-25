from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.privacy_policy import PrivacyPolicy
    from app.models.user import User


class ParentalConsent(Base):
    __tablename__ = "parental_consents"
    __table_args__ = (
        Index("ix_parental_consents_parent_athlete", "parent_user_id", "athlete_id"),
        Index("ix_parental_consents_athlete_id", "athlete_id"),
        Index("ix_parental_consents_policy_id", "policy_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="RESTRICT"))

    # Versión de política como string — deprecado, conservar para compatibilidad
    # y como fallback de lectura. La FK policy_id es la fuente canónica.
    consent_version: Mapped[str] = mapped_column(String(20))

    # FK a la versión de política vigente al momento de dar el consentimiento
    policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("privacy_policies.id", ondelete="RESTRICT"), nullable=True
    )

    consented_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    consent_method: Mapped[str] = mapped_column(
        String(50), default="digital_wizard"
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Checkboxes de consentimiento
    data_collection: Mapped[bool] = mapped_column(Boolean, default=False)
    training_tracking: Mapped[bool] = mapped_column(Boolean, default=False)
    anthropometry: Mapped[bool] = mapped_column(Boolean, default=False)
    third_party_sharing: Mapped[bool] = mapped_column(Boolean, default=False)

    # None = consentimiento vigente; fecha = consentimiento retirado.
    # Son los únicos campos que pueden actualizarse (no INSERT nuevas filas).
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    # Versión de política vinculada (lazy="joined" para evitar N+1 en listados)
    policy: Mapped[PrivacyPolicy | None] = relationship(
        "PrivacyPolicy",
        foreign_keys="[ParentalConsent.policy_id]",
        lazy="joined",
    )
