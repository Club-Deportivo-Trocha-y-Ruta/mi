from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.club import Club


class ClubProjectProfile(Base):
    """Perfil de proyecto del club (1:1 con ``clubs``).

    Metadata estática del "Informe Técnico Mensual" estilo financiador:
    nombre del proyecto, entidad ejecutora, responsable, propósito, objetivos
    (general y específicos) y localización territorial. Reutilizado como
    encabezado en cada reporte mensual del club.
    """

    __tablename__ = "club_project_profiles"
    __table_args__ = (
        UniqueConstraint("club_id", name="uq_club_project_profile_club"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    executing_entity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    report_responsible: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    general_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    specific_objectives: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    territory_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    territory_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relación 1:1 con el club
    club: Mapped[Club] = relationship(
        "Club",
        foreign_keys="[ClubProjectProfile.club_id]",
    )
