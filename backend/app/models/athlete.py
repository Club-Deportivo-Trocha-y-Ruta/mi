from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.models.club import Club
    from app.models.parent_invite import ParentInvite
    from app.models.user import User


class Sex(str, enum.Enum):
    M = "M"
    F = "F"


class FamilyRelationship(str, enum.Enum):
    padre = "padre"
    madre = "madre"
    acudiente = "acudiente"


class Athlete(Base):
    __tablename__ = "athletes"
    __table_args__ = (
        Index("ix_athletes_club_id", "club_id"),
        Index("ix_athletes_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(Enum(Sex))
    club_join_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    parental_consent_obtained: Mapped[bool] = mapped_column(default=False)
    parental_consent_date: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    # Usuario vinculado al atleta (1-a-1)
    user: Mapped[User] = relationship(
        "User",
        back_populates="athlete_profile",
        foreign_keys="[Athlete.user_id]",
    )
    # Club al que pertenece
    club: Mapped[Club] = relationship(
        "Club",
        back_populates="athletes",
        foreign_keys="[Athlete.club_id]",
    )
    # Coach/admin que registró al atleta (sin back_populates para evitar ambigüedad con user)
    creator: Mapped[User] = relationship(
        "User",
        foreign_keys="[Athlete.created_by]",
    )
    # Mediciones antropométricas
    anthropometric_records: Mapped[list[AnthropometricRecord]] = relationship(
        "AnthropometricRecord",
        back_populates="athlete",
        foreign_keys="[AnthropometricRecord.athlete_id]",
    )
    # Relaciones con padres/acudientes
    parents: Mapped[list[ParentAthlete]] = relationship(
        "ParentAthlete",
        back_populates="athlete",
        foreign_keys="[ParentAthlete.athlete_id]",
    )
    # --- Race-analysis v2 (BE-1) ------------------------------------------
    # Insights vigentes (no deprecados ni archivados). viewonly porque el
    # ciclo de vida lo maneja persist_insight (BE-2); el ORM solo lee.
    ai_insights: Mapped[list["AthleteAiInsight"]] = relationship(
        "AthleteAiInsight",
        back_populates="athlete",
        primaryjoin=(
            "and_(Athlete.id==AthleteAiInsight.athlete_id, "
            "AthleteAiInsight.deprecated_at.is_(None), "
            "AthleteAiInsight.archived_at.is_(None))"
        ),
        order_by="desc(AthleteAiInsight.generated_at)",
        viewonly=True,
    )
    # Runs del agente cuyo input.athlete_id corresponde a este atleta.
    # No es delete-cascade: si se elimina el atleta, los runs históricos
    # quedan con athlete_id=NULL (la migración define FK SET NULL).
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        "AgentRun",
        back_populates="athlete",
        foreign_keys="[AgentRun.athlete_id]",
        order_by="desc(AgentRun.started_at)",
        viewonly=True,
    )


class ParentAthlete(Base):
    __tablename__ = "parent_athlete"
    __table_args__ = (
        UniqueConstraint("parent_id", "athlete_id", name="uq_parent_athlete"),
        Index("ix_parent_athlete_athlete_id", "athlete_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    # Renombrado de 'relationship' a 'relationship_type' para evitar colisión
    # con la función relationship() importada de sqlalchemy.orm
    relationship_type: Mapped[FamilyRelationship] = mapped_column(
        "relationship", Enum(FamilyRelationship)
    )

    parent: Mapped[User] = relationship(
        "User",
        foreign_keys="[ParentAthlete.parent_id]",
    )
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        back_populates="parents",
        foreign_keys="[ParentAthlete.athlete_id]",
    )
