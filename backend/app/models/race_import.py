"""Modelo SQLAlchemy para ``race_imports`` (trazabilidad de ingestas PDF).

Schema previo: migración ``0edd41998022`` (2026-05-15). Extendido por
``e8f9a0b1c2d3`` (2026-05-20, F-UP1) para soportar el flow upload UI y por
``f9a0b1c2d3e4`` (2026-05-21, F-UP-REV1) para soportar revisiones integrales.

Cada ingesta deja un ``RaceImport`` con:

- ``sha256`` (CHAR 64) para deduplicación del PDF RESULTADOS — UNIQUE lógico
  contra ``status='committed'``.
- ``stats_json`` con conteos finales (categorías, riders, results) tras commit.
- ``error_log`` con warnings (edge cases: ``time_anomaly``,
  ``dorsal_not_in_results``, etc.).
- (F-UP1) Columnas para el flow upload UI: ``event_id``, ``kind``,
  ``storage_path``/``storage_url`` (RESULTADOS), ``general_storage_path``/
  ``general_storage_url``/``general_sha256`` (GENERAL opcional),
  ``parse_meta_json`` (estado intermedio del wizard),
  ``original_filename`` (preservado pre-sanitización).
- (F-UP-REV1) Columnas de revisión: ``parent_import_id`` (self-ref al committed
  inmediato anterior) y ``revision_reason`` (motivo libre del coach).
  ``is_revision`` se deriva: ``parent_import_id IS NOT NULL``.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

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
    from app.models.race_event import RaceEvent
    from app.models.race_series import RaceSeries
    from app.models.user import User


class RaceImportStatus(str, enum.Enum):
    """Ciclo de vida de una ingesta PDF.

    - ``pending``: archivo recibido, aún no procesado. Limpieza nocturna >24h.
    - ``dry_run``: parseo + validación sin escribir resultados (NUEVO F-UP2:
      antes existía en enum pero código nunca lo emitía).
    - ``committed``: ingesta exitosa, race_results escritos.
    - ``failed``: error fatal en parseo o validación.
    """

    pending = "pending"
    dry_run = "dry_run"
    committed = "committed"
    failed = "failed"


class RaceImportKind(str, enum.Enum):
    """Discrimina qué tipo de PDF(s) trae una ingesta (F-UP1).

    - ``resultados``: solo PDF RESULTADOS (caso típico Sevilla 2026 CSV-only).
    - ``general``: solo PDF GENERAL (raro — uso interno admin).
    - ``both``: RESULTADOS + GENERAL (caso típico Válida IV oficial).

    Default ``resultados`` para imports F1.7 legacy.
    """

    resultados = "resultados"
    general = "general"
    both = "both"


class RaceImport(Base):
    """Registro de cada PDF procesado (RESULTADOS o GENERAL).

    El ``sha256`` se calcula sobre el contenido del PDF — sirve como clave de
    idempotencia (re-ingestar el mismo PDF detecta el duplicado vs el ``committed``).
    ``stats_json`` ejemplo: ``{"categories": 26, "rows": 227, "tyr": 10, "warnings": 3}``.

    F-UP1: columnas upload UI extendidas. Todas nullable para coexistir con los
    3 imports F1.7 legacy (``event_id=NULL``, ``storage_*=NULL``).
    """

    __tablename__ = "race_imports"
    __table_args__ = (
        Index("ix_race_imports_imported_at", "imported_at"),
        Index("ix_race_imports_sha256", "sha256"),
        Index("ix_race_imports_status_sha256", "status", "sha256"),
        # F-UP1
        Index("ix_race_imports_event_id", "event_id"),
        Index("ix_race_imports_status", "status"),
        # F-UP-REV1
        Index("ix_race_imports_parent_id", "parent_import_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("race_series.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RaceImportStatus] = mapped_column(
        Enum(
            RaceImportStatus,
            name="raceimportstatus",
            values_callable=lambda e: [x.value for x in e],
        ),
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

    # ---------------------------------------------------------------------
    # F-UP1: upload UI columns
    # ---------------------------------------------------------------------
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("race_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[RaceImportKind] = mapped_column(
        Enum(
            RaceImportKind,
            name="raceimportkind",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RaceImportKind.resultados,
        server_default="resultados",
    )
    # Storage RESULTADOS
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    storage_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Storage GENERAL (opcional)
    general_storage_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    general_storage_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    general_sha256: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
    # Estado intermedio del wizard (parse → dry-run → commit)
    parse_meta_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Filename original pre-sanitización (path traversal: filename oficial vive
    # en ``filename`` ya sanitizado; el original UI-display se guarda aparte).
    original_filename: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # ---------------------------------------------------------------------
    # F-UP-REV1: revisión integral de resultados
    # ---------------------------------------------------------------------
    # FK self-ref al import committed inmediato anterior. ``ON DELETE SET NULL``
    # preserva las revisiones descendientes si un import previo se hard-deletea
    # (operación de emergencia documentada en runbook). Encadenamiento lineal:
    # revisión-de-revisión apunta al último committed (``committed_at DESC LIMIT 1``
    # en ``detect_revision``).
    parent_import_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("race_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Texto libre del motivo de revisión. Obligatorio si el diff incluye deletes
    # (validación app-level en ``commit_revision``). PRIVACIDAD: nunca se loggea
    # el texto, solo ``len(reason)``.
    revision_reason: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True
    )

    # ---------------------------------------------------------------------
    # Relaciones
    # ---------------------------------------------------------------------
    series: Mapped["RaceSeries"] = relationship(
        "RaceSeries",
        back_populates="imports",
        foreign_keys="[RaceImport.series_id]",
    )
    imported_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceImport.imported_by_user_id]",
    )
    event: Mapped[Optional["RaceEvent"]] = relationship(
        "RaceEvent",
        foreign_keys="[RaceImport.event_id]",
    )
    # Self-ref: parent = import committed anterior (NULL para primer import).
    # ``remote_side=[id]`` indica que el lado "remoto" de la relación es la PK
    # — patrón canónico SQLAlchemy para FK self-ref.
    parent: Mapped[Optional["RaceImport"]] = relationship(
        "RaceImport",
        remote_side="RaceImport.id",
        foreign_keys="[RaceImport.parent_import_id]",
    )

    # ---------------------------------------------------------------------
    # Properties derivadas
    # ---------------------------------------------------------------------
    @property
    def is_revision(self) -> bool:
        """True si este import es revisión de uno previo (no persistido).

        Derivado de ``parent_import_id IS NOT NULL`` — no se persiste para evitar
        drift entre dos campos que deben siempre coincidir.
        """
        return self.parent_import_id is not None
