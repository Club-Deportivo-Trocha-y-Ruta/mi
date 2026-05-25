"""Tablas lookup (catálogos) que reemplazan enums ENUM('...') de MySQL.

Diseño:
- Cada tabla tiene un PK ``code`` (string corto e inmutable) que es la
  representación canónica usada en columnas FK de otras tablas.
- Una columna ``label_es`` con el nombre legible para UI/reportes.
- Una columna ``sort_order`` para orden de presentación estable.
- Columnas extra específicas (ej. ``is_terminal`` para estados) cuando
  expresan invariantes del dominio.

Ventaja vs enum DDL: añadir/quitar valores ya no requiere ALTER COLUMN
sino un INSERT/UPDATE/DELETE en la tabla lookup. Las queries pueden
hacer JOIN para mostrar el label localizado sin código en Python.

A nivel Pydantic los schemas siguen exponiendo strings (no cambia el
contrato del frontend).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# Constantes Python: códigos canónicos. Mantenerlas en sync con el seed de
# la migración f5d0b1a2c3e4. Cualquier código nuevo debe añadirse aquí Y al
# INSERT del seed antes de usarse en un service/router.
# ---------------------------------------------------------------------------

# CalendarEventType
EVENT_TYPE_TRAINING_SESSION = "training_session"
EVENT_TYPE_COMPETITION = "competition"
EVENT_TYPE_CLUB_EVENT = "club_event"
EVENT_TYPE_PERSONAL_TRAINING = "personal_training"
EVENT_TYPE_GROUP_TRAINING = "group_training"
EVENT_TYPE_REST_DAY = "rest_day"
EVENT_TYPE_BIRTHDAY = "birthday"


# RaceImportStatus
IMPORT_STATUS_PENDING = "pending"
IMPORT_STATUS_DRY_RUN = "dry_run"
IMPORT_STATUS_COMMITTED = "committed"
IMPORT_STATUS_FAILED = "failed"


class CalendarEventType(Base):
    """Catálogo de tipos de evento del calendario.

    Reemplaza el enum ENUM('training_session', 'competition', ...).
    """

    __tablename__ = "calendar_event_types"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label_es: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RaceImportStatusLookup(Base):
    """Catálogo de estados de ciclo de vida de una ingesta PDF.

    Reemplaza el enum ENUM('pending', 'dry_run', 'committed', 'failed').
    `is_terminal=True` indica un estado del que no puede salirse
    (committed, failed).

    Renombrado a ``RaceImportStatusLookup`` para no chocar con el enum
    Python ``RaceImportStatus`` de ``app/models/race_import.py``.
    """

    __tablename__ = "race_import_statuses"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    label_es: Mapped[str] = mapped_column(String(100), nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
