"""Modelo SQLAlchemy para `race_imports` (trazabilidad de ingestas PDF).

Schema previo: migración `0edd41998022` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente.

Cada PDF ingestado deja un `RaceImport` con `sha256` para deduplicación,
`stats_json` con conteos (categorías, riders, results) y `error_log` con
warnings (edge cases tipo `time_anomaly`, `dorsal_not_in_results`, etc.).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_series import RaceSeries
    from app.models.user import User


class RaceImportStatus(str, enum.Enum):
    """Ciclo de vida de una ingesta PDF.

    - `pending`: archivo recibido, aún no procesado.
    - `dry_run`: parseo + validación sin escribir resultados.
    - `committed`: ingesta exitosa, race_results escritos.
    - `failed`: error fatal en parseo o validación.
    """

    pending = "pending"
    dry_run = "dry_run"
    committed = "committed"
    failed = "failed"


class RaceImport(Base):
    """Registro de cada PDF procesado (RESULTADOS o GENERAL).

    El `sha256` se calcula sobre el contenido del PDF — sirve como clave de
    idempotencia (re-ingestar el mismo PDF detecta el duplicado vs el `committed`).
    `stats_json` ejemplo: `{"categories": 26, "rows": 227, "tyr": 10, "warnings": 3}`.
    """

    __tablename__ = "race_imports"
    __table_args__ = (
        Index("ix_race_imports_imported_at", "imported_at"),
        Index("ix_race_imports_sha256", "sha256"),
        Index("ix_race_imports_status_sha256", "status", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("race_series.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RaceImportStatus] = mapped_column(
        Enum(RaceImportStatus, name="raceimportstatus", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=RaceImportStatus.pending,
    )
    stats_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    series: Mapped["RaceSeries"] = relationship(
        "RaceSeries",
        back_populates="imports",
        foreign_keys="[RaceImport.series_id]",
    )
    imported_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceImport.imported_by_user_id]",
    )
