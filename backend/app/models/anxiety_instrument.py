"""Modelo SQLAlchemy para ``anxiety_instruments`` (feature 017).

Definición + clave de puntuación de una versión de instrumento de ansiedad
competitiva (CSAI-2R, SAS-2, CSAI-2). Se siembra/configura; no lo edita el
usuario. ``scoring_key_json`` es la única fuente para puntuar (FR-004); el
*texto* de los ítems se aprovisiona desde la fuente licenciada y nunca se
inventa.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.anxiety_assessment import AnxietyAssessment


class InstrumentType(str, enum.Enum):
    """Tipo de instrumento. Alineado con las claves en ``data/anxiety_keys``."""

    csai2 = "csai2"
    csai2r = "csai2r"
    sas2 = "sas2"


class InstrumentAgeBand(str, enum.Enum):
    """Banda de edad objetivo por defecto para la selección automática."""

    band_10_12 = "10-12"
    band_13_15 = "13-15"
    import_only = "import"


class AnxietyInstrument(Base):
    """Versión de instrumento + clave de puntuación (sembrado, no editable)."""

    __tablename__ = "anxiety_instruments"
    __table_args__ = (
        Index("ix_anxiety_instruments_type_active", "type", "is_active"),
        Index("ix_anxiety_instruments_age_band", "age_band"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[InstrumentType] = mapped_column(
        Enum(
            InstrumentType,
            name="anxietyinstrumenttype",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    age_band: Mapped[InstrumentAgeBand] = mapped_column(
        Enum(
            InstrumentAgeBand,
            name="anxietyinstrumentageband",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    item_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Mapa ítem→subescala + flags de reverse + rangos. Cargado desde
    # ``data/anxiety_keys/`` y persistido para trazabilidad/recálculo.
    scoring_key_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    assessments: Mapped[list["AnxietyAssessment"]] = relationship(
        "AnxietyAssessment",
        back_populates="instrument",
        foreign_keys="[AnxietyAssessment.instrument_id]",
    )
