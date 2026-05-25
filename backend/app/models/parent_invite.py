from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User


class ParentInvite(Base):
    __tablename__ = "parent_invites"
    __table_args__ = (
        Index("ix_parent_invites_athlete_id", "athlete_id"),
        Index("ix_parent_invites_token", "token"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(255))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Atleta al que corresponde la invitación
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[ParentInvite.athlete_id]",
    )
    # Coach/admin que generó la invitación (NULL si el creador fue eliminado)
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[ParentInvite.created_by]",
    )
    # Usuario padre/acudiente que activó el token (None hasta que se use)
    used_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[ParentInvite.used_by]",
    )
    # Usuario padre pre-creado por el coach al que se debe vincular la invitación
    parent_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[ParentInvite.parent_user_id]",
    )
