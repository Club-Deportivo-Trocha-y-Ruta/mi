"""Modelo SQLAlchemy para `race_series` (serie de competencias, ej. Copa Valle 2026).

Schema previo: migración `04536432643f` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente — no introduce columnas nuevas.

Una serie agrupa varias `race_events` (válidas) de la misma temporada bajo un
mismo `points_scheme_code`. La unicidad real (`name`, `season_year`) permite tener
distintas copas en paralelo (`Copa Valle 2026`, `Liga Departamental 2026`, etc.).

Spec 014 (2026-06-15): agrega `RaceSeriesKind` enum y columna `kind` (cup |
championship). Championships son series independientes con un único evento anual;
se excluyen del ranking acumulado de temporada. Ver specs/014-cup-vs-championship-series/.

Spec 023 (2026-07-08): agrega `RaceSeriesLevel` enum y columna `level`
(departmental | national) para distinguir el Campeonato Departamental Valle del
Campeonato Nacional Fedeciclismo. Ver specs/023-national-championship-level/.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_event import RaceEvent
    from app.models.race_import import RaceImport


class RaceSeriesKind(str, enum.Enum):
    """Discriminador de tipo de serie de competencias.

    cup          — Copa con rondas numeradas y ranking acumulado de temporada.
    championship — Campeonato anual de un único evento; no contribuye al ranking.
    """

    cup = "cup"
    championship = "championship"


class RaceSeriesLevel(str, enum.Enum):
    """Ámbito territorial del campeonato.

    departmental — Campeonato Departamental (ej. Valle del Cauca).
    national     — Campeonato Nacional Fedeciclismo (ej. Pereira 2026).
    """

    departmental = "departmental"
    national = "national"


class RaceSeries(Base):
    """Serie de competencias deportivas agrupadas por temporada.

    Ejemplo: `name="Copa Valle de Ciclomontañismo", season_year=2026`.
    El campo `points_scheme_code` referencia (FK lógica) `race_points_schemes.code`
    — define cómo se otorgan puntos por posición y por asistencia.

    El campo `kind` discrimina copas (rondas + ranking) de campeonatos (evento único,
    sin ranking acumulado). Ver decisiones D1–D5 en specs/014-cup-vs-championship-series/research.md.

    El campo `level` distingue el ámbito territorial de un campeonato (departmental |
    national). Ver specs/023-national-championship-level/data-model.md.
    """

    __tablename__ = "race_series"
    __table_args__ = (
        UniqueConstraint("name", "season_year", name="uq_race_series_name_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    organizer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    points_scheme_code: Mapped[str] = mapped_column(String(50), nullable=False)
    kind: Mapped[RaceSeriesKind] = mapped_column(
        Enum(
            RaceSeriesKind,
            name="raceserieskind",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RaceSeriesKind.cup,
    )
    level: Mapped[RaceSeriesLevel] = mapped_column(
        Enum(
            RaceSeriesLevel,
            name="raceserieslevel",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RaceSeriesLevel.departmental,
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
