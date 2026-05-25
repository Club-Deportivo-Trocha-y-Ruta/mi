"""Modelo SQLAlchemy para `race_series` (serie de competencias, ej. Copa Valle 2026).

Schema previo: migración `04536432643f` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente — no introduce columnas nuevas.

Una serie agrupa varias `race_events` (válidas) de la misma temporada bajo un
mismo `points_scheme_code`. La unicidad real (`name`, `season_year`) permite tener
distintas copas en paralelo (`Copa Valle 2026`, `Liga Departamental 2026`, etc.).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_event import RaceEvent
    from app.models.race_import import RaceImport


class RaceSeries(Base):
    """Serie de competencias deportivas agrupadas por temporada.

    Ejemplo: `name="Copa Valle de Ciclomontañismo", season_year=2026`.
    El campo `points_scheme_code` referencia (FK lógica) `race_points_schemes.code`
    — define cómo se otorgan puntos por posición y por asistencia.
    """

    __tablename__ = "race_series"
    __table_args__ = (
        UniqueConstraint("name", "season_year", name="uq_race_series_name_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    organizer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # FK explícita a race_points_schemes.code: garantiza integridad referencial
    # con RESTRICT (no permitir borrar un scheme con series asociadas) y CASCADE
    # de update en caso de renombrar el código.
    points_scheme_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey(
            "race_points_schemes.code",
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="fk_race_series_points_scheme_code",
        ),
        nullable=False,
    )
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
    events: Mapped[list["RaceEvent"]] = relationship(
        "RaceEvent",
        back_populates="series",
        foreign_keys="[RaceEvent.series_id]",
        order_by="RaceEvent.event_date",
    )
    imports: Mapped[list["RaceImport"]] = relationship(
        "RaceImport",
        back_populates="series",
        foreign_keys="[RaceImport.series_id]",
    )
