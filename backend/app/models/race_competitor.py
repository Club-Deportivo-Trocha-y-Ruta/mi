"""Modelo SQLAlchemy para `race_competitors` (corredores observados en válidas).

Schema previo: migración `0c28a22dc064` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente — no introduce columnas nuevas.

Equivale al `riders` del `design.md §3.3`. Convenciones de nombres distintas:
- `normalized_name`           → equivale a `full_name_normalized` del design.
- `display_name`              → equivale a `full_name_raw` del design.
- `club_text`                 → equivale a `club_raw` del design.

Campos del design que NO existen físicamente en la tabla:
- `full_name_normalized` separado (se usa `normalized_name`).
- `city_raw` (no almacenada; el parser la captura para resolución de homónimos
  durante ingesta pero no se persiste — el matcher prioriza nombre + club).
- `club_normalized` (no almacenada; se calcula on-demand desde `club_text`).
- `is_trocha_y_ruta` flag explícito (se deriva de `athlete_id IS NOT NULL`
  cuando hay match confirmado; el parser persiste `club_text` para que la
  comparación fuzzy pueda re-ejecutarse sin migración).
- `first_seen_event_id` (no almacenada; consultable vía `MIN(race_results.event_id)`).

El servicio de ingesta (Paso 3-4) puede materializar estos derivables si la
performance de query lo requiere — por ahora se computan on-demand.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.race_result import RaceResult
    from app.models.user import User


class CompetitorSex(str, enum.Enum):
    """Sexo registrado del corredor (puede ser NULL si no se infiere de la categoría).

    No se persiste `MIXED` aquí: a nivel de persona, el sexo es binario para
    el dominio (M/F). Una persona puede correr en categoría `MIXED` igual.
    """

    M = "M"
    F = "F"


class RaceCompetitor(Base):
    """Persona física que ha corrido al menos una válida (TyR o no).

    `athlete_id` se setea sólo cuando el coach confirma el match contra un
    `Athlete` registrado del club. Es la única forma de marcar un competidor
    como Trocha y Ruta a nivel de modelo (el fuzzy match contra `club_text`
    se ejecuta en cada ingesta y no se persiste como flag).
    """

    __tablename__ = "race_competitors"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_race_competitors_normalized_name"),
        Index("ix_race_competitors_athlete_id", "athlete_id"),
        Index("ix_race_competitors_club_text", "club_text"),
        # Auditoría: "links creados por X coach" — usado en audit dashboards.
        Index("ix_race_competitors_linked_by_user", "linked_by_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    club_text: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sex: Mapped[CompetitorSex | None] = mapped_column(
        Enum(CompetitorSex, name="racecompetitorsex", values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )
    athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    linked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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
    athlete: Mapped["Athlete | None"] = relationship(
        "Athlete",
        foreign_keys="[RaceCompetitor.athlete_id]",
    )
    linked_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys="[RaceCompetitor.linked_by_user_id]",
    )
    results: Mapped[list["RaceResult"]] = relationship(
        "RaceResult",
        back_populates="competitor",
        foreign_keys="[RaceResult.competitor_id]",
    )
