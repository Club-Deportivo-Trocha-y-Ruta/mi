from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.user import User


class ClubRole(str, enum.Enum):
    admin = "admin"
    coach = "coach"
    parent = "parent"
    athlete = "athlete"


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50), unique=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    members: Mapped[list[ClubMember]] = relationship(
        "ClubMember",
        back_populates="club",
        foreign_keys="[ClubMember.club_id]",
    )
    athletes: Mapped[list[Athlete]] = relationship(
        "Athlete",
        back_populates="club",
        foreign_keys="[Athlete.club_id]",
    )


class ClubMember(Base):
    __tablename__ = "club_members"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id"),
        Index("ix_club_members_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role_in_club: Mapped[ClubRole] = mapped_column(Enum(ClubRole))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    club: Mapped[Club] = relationship(
        "Club",
        back_populates="members",
        foreign_keys="[ClubMember.club_id]",
    )
    user: Mapped[User] = relationship(
        "User",
        back_populates="club_memberships",
        foreign_keys="[ClubMember.user_id]",
    )
