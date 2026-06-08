"""Modelo SQLAlchemy para `race_events` (válida individual de una serie).

Schema previo: migración `04536432643f` (2026-05-15) creó la tabla base.
Migración delta Paso 2 (Fase 1.7) agregó campos de condiciones de carrera y
trazabilidad de PDFs (clima, temperatura, superficie, altitud, notas, pdf_*).

El campo `sequence_number` cumple el rol de `valida_num` del diseño:
- Válidas regulares 1..7.
- Campeonato Departamental = 99 (convención design §3.2).

La unicidad oficial `(series_id, sequence_number)` ya existe (migración previa).
El requisito del design `(season, copa_code, valida_num)` se cumple
transitivamente porque `series` define `(name, season_year)` único.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.calendar_event import CalendarEvent
    from app.models.race_event_roster import RaceEventRoster
    from app.models.race_import import RaceImport
    from app.models.race_result import RaceResult
    from app.models.race_series import RaceSeries
    from app.models.user import User


class RaceEventStatus(str, enum.Enum):
    """Estado operativo del evento (scheduled antes de correr, completed después)."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SurfaceCondition(str, enum.Enum):
    """Condición del trazado el día de la carrera (impacta análisis tiempo-vs-tiempo).

    Convención `design.md §3.2`. Valor `NULL` permitido cuando no se capturó.
    """

    seca = "seca"
    humeda = "humeda"
    barro = "barro"
    lluvia = "lluvia"
    mixta = "mixta"


class RaceEvent(Base):
    """Válida individual de una serie (ej. Válida IV Cali 2026-05-17).

    Las condiciones climáticas se capturan vía CLI interactivo (workflow §6.2)
    porque NO están en el PDF oficial. Los archivos PDF originales se referencian
    para trazabilidad de ingesta (re-procesamiento, audit, debug parser).
    """

    __tablename__ = "race_events"
    __table_args__ = (
        UniqueConstraint("series_id", "sequence_number", name="uq_race_events_series_sequence"),
        Index("ix_race_events_event_date", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("race_series.id", ondelete="RESTRICT"), nullable=False
    )
    # Equivalente a `valida_num` del design (1..7 para válidas regulares, 99 = CD).
    sequence_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_championship: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calendar_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("calendar_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[RaceEventStatus] = mapped_column(
        Enum(RaceEventStatus, name="raceeventstatus", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=RaceEventStatus.SCHEDULED,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # --- Campos clima / condiciones (agregados en migración delta Paso 2 Fase 1.7) ---
    climate: Mapped[str | None] = mapped_column(String(60), nullable=True)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    surface_condition: Mapped[SurfaceCondition | None] = mapped_column(
        Enum(
            SurfaceCondition,
            name="racesurfacecondition",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    altitude_msnm: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    weather_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_results_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pdf_general_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # --- Fin delta ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones
    series: Mapped["RaceSeries"] = relationship(
        "RaceSeries",
        back_populates="events",
        foreign_keys="[RaceEvent.series_id]",
    )
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceEvent.created_by_user_id]",
    )
    calendar_event: Mapped["CalendarEvent | None"] = relationship(
        "CalendarEvent",
        foreign_keys="[RaceEvent.calendar_event_id]",
    )
    results: Mapped[list["RaceResult"]] = relationship(
        "RaceResult",
        back_populates="event",
        foreign_keys="[RaceResult.event_id]",
        cascade="all, delete-orphan",
    )
    imports: Mapped[list["RaceImport"]] = relationship(
        "RaceImport",
        secondary="race_results",
        primaryjoin="RaceEvent.id == RaceResult.event_id",
        secondaryjoin="RaceResult.imported_from_id == RaceImport.id",
        viewonly=True,
    )
    roster_entries: Mapped[list["RaceEventRoster"]] = relationship(
        "RaceEventRoster",
        back_populates="race_event",
        foreign_keys="[RaceEventRoster.race_event_id]",
        cascade="all, delete-orphan",
    )
