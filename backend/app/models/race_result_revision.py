"""Modelo SQLAlchemy para `race_result_revisions` (audit trail de cambios a results).

Schema previo: migración `0edd41998022` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente.

Cada cambio (create, update, delete) a un `race_result` genera una fila aquí con
el `diff_json` (estado anterior vs nuevo). Si un re-ingest corrige un tiempo
(ej. el `Matias Sabogal time=0:04:33` que era typo del PDF original), el coach
ve quién y cuándo lo cambió.
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
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_result import RaceResult
    from app.models.user import User


class RaceResultRevisionAction(str, enum.Enum):
    """Tipo de cambio registrado.

    `delete` es soft-delete (marca `deleted_at` en race_results) — el id queda
    para mantener consistencia histórica con esta tabla de revisions.
    """

    create = "create"
    update = "update"
    delete = "delete"


class RaceResultRevision(Base):
    """Una fila por cada cambio aplicado a un `race_result`.

    `result_id` puede ser NULL si el race_result fue hard-deleted (raro) — la
    revisión sobrevive porque `ondelete="SET NULL"`. `reason` opcional para
    capturar el por qué del cambio (ej. "corrección oficial federación").
    """

    __tablename__ = "race_result_revisions"
    __table_args__ = (
        Index("ix_race_result_revisions_changed_at", "changed_at"),
        Index("ix_race_result_revisions_changed_by", "changed_by_user_id"),
        Index("ix_race_result_revisions_result_id", "result_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_results.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[RaceResultRevisionAction] = mapped_column(
        Enum(
            RaceResultRevisionAction,
            name="raceresultrevisionaction",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    changed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    diff_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Relaciones
    result: Mapped["RaceResult | None"] = relationship(
        "RaceResult",
        back_populates="revisions",
        foreign_keys="[RaceResultRevision.result_id]",
    )
    changed_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceResultRevision.changed_by_user_id]",
    )
