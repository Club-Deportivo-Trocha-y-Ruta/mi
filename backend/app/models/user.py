from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, Enum, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.club import ClubMember
    from app.models.athlete import Athlete


class UserRole(str, enum.Enum):
    admin = "admin"
    coach = "coach"
    parent = "parent"
    athlete = "athlete"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Filtra usuarios por rol (listar coaches, parents, etc.)
        Index("ix_users_role", "role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_login: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Self-referential: quién creó a este usuario (Many→1)
    creator: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[User.created_by]",
        back_populates="created_users",
        remote_side="[User.id]",
    )
    # Self-referential: usuarios creados por este usuario (1→Many)
    created_users: Mapped[list[User]] = relationship(
        "User",
        foreign_keys="[User.created_by]",
        back_populates="creator",
    )

    # Membresías a clubes
    club_memberships: Mapped[list[ClubMember]] = relationship(
        "ClubMember",
        back_populates="user",
        foreign_keys="ClubMember.user_id",
    )

    # Perfil de atleta (1-a-1, puede no existir si role != athlete)
    athlete_profile: Mapped[Athlete | None] = relationship(
        "Athlete",
        back_populates="user",
        foreign_keys="Athlete.user_id",
        uselist=False,
    )
