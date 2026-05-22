"""Modelo SQLAlchemy para ``race_competitor_link_audit`` (audit trail de link/unlink).

Resuelve R3-M1: cuando se hace ``unlink``, los campos ``linked_by_user_id`` y
``linked_at`` se setean a NULL en ``race_competitors`` y se pierde la traza
de quién originalmente realizó el enlace. Esta tabla persiste el historial
completo de link/unlink con la causa (acción), actor (user_id) y resultados
propagados a ``race_results``.

Reglas:

- **Append-only**. El servicio NUNCA hace UPDATE ni DELETE sobre filas de esta
  tabla (sólo INSERT). Si en el futuro se requiere "purgar" historial antiguo,
  debe hacerse por separado con una política explícita (no automática).
- **Sin nombres**. El audit guarda únicamente IDs + timestamp + acción. Para
  reconstruir nombres se hace JOIN al momento de leer (CLAUDE.md: privacidad
  menores — el audit no debe contener PII en bruto).
- **Inmutable a hard-delete de FKs**. Las FKs usan ``ON DELETE SET NULL`` en
  ``previous_athlete_id`` y ``new_athlete_id`` para que el audit sobreviva
  aunque el athlete sea hard-deleted. ``competitor_id`` y ``user_id`` se
  preservan con ``RESTRICT`` para evitar borrar el historial accidentalmente.

Acciones registradas:

- ``link``    — competitor pasó de ``athlete_id=NULL`` a ``athlete_id=X``.
- ``unlink``  — competitor pasó de ``athlete_id=X`` a ``athlete_id=NULL``.
- ``relink``  — reservado para futuro flow que permita mover competitor entre
                athletes en una sola operación. Hoy bloqueado por 409, así
                que el enum lo declara pero el código no lo emite aún.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.dialects.sqlite import INTEGER as SQLITE_INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.race_competitor import RaceCompetitor
    from app.models.user import User


class LinkAuditAction(str, enum.Enum):
    """Tipo de transición registrada en el audit."""

    link = "link"
    unlink = "unlink"
    relink = "relink"


class RaceCompetitorLinkAudit(Base):
    """Una fila por cada transición link/unlink de un ``RaceCompetitor``.

    El servicio inserta una fila cada vez que muta efectivamente el estado de
    enlace de un competitor. Idempotent re-link NO genera filas (no hubo
    transición real).
    """

    __tablename__ = "race_competitor_link_audit"
    __table_args__ = (
        Index("ix_link_audit_competitor_id", "competitor_id"),
        Index("ix_link_audit_user_id", "user_id"),
        Index("ix_link_audit_created_at", "created_at"),
    )

    # BigInteger en MySQL (capacidad para múltiples décadas de audit rows
    # incluso a alta tasa de link/unlink). Variant SQLite usa INTEGER para
    # que el PK actúe como ROWID alias y autoincremente — sin esto los
    # tests fallan con "NOT NULL constraint failed".
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(SQLITE_INTEGER(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    competitor_id: Mapped[int] = mapped_column(
        ForeignKey("race_competitors.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[LinkAuditAction] = mapped_column(
        Enum(
            LinkAuditAction,
            name="link_audit_action",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    previous_athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    new_athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    results_propagated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones (sólo lectura — el audit es append-only)
    competitor: Mapped["RaceCompetitor"] = relationship(
        "RaceCompetitor",
        foreign_keys="[RaceCompetitorLinkAudit.competitor_id]",
    )
    previous_athlete: Mapped["Athlete | None"] = relationship(
        "Athlete",
        foreign_keys="[RaceCompetitorLinkAudit.previous_athlete_id]",
    )
    new_athlete: Mapped["Athlete | None"] = relationship(
        "Athlete",
        foreign_keys="[RaceCompetitorLinkAudit.new_athlete_id]",
    )
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceCompetitorLinkAudit.user_id]",
    )
