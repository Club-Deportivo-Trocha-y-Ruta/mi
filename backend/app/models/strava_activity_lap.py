"""Modelos SQLAlchemy para ``strava_activity_laps`` e
``interval_match_results`` (feature 026).

``StravaActivityLap`` (data-model.md §5): una fila por vuelta (lap) de una
actividad de Strava ya sincronizada. Es propiedad de la actividad, no de
ninguna estructura ni resultado de emparejamiento (D7): al recalcular se
borran e insertan de nuevo dentro de una sola transacción, de modo que
``UNIQUE(strava_activity_id, lap_index)`` siempre refleja el último estado
upstream.

``IntervalMatchResult`` (data-model.md §6): comparación persistida
plan-vs-realidad (una por par estructura↔actividad). Es un artefacto
derivado — muere con el plan (``ondelete=CASCADE`` sobre ambas FKs).

PRIVACIDAD (Ley 1581, menores de edad — ver data-model.md §5 "Explicitly
ABSENT columns" y research.md): al igual que ``strava_activities``, este
modelo de laps NO tiene, y NUNCA debe ganar, columnas de ubicación o mapa
(``start_latlng``, ``end_latlng``, polyline/mapa de cualquier tipo), ni el
``name`` libre de la vuelta, ni ``average_cadence`` (diferido a v2), ni
``average_watts`` (no hay potencia para esta población). El ingest
(``services/intervals/match_runner.py``) hace allow-list exacto de los
campos persistidos y descarta todo lo demás del payload crudo antes del
flush; ``tests/privacy/test_laps_privacy.py`` afirma que el modelo no tiene
atributos geográficos.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.strava_activity import StravaActivity


class MatchTrigger(str, enum.Enum):
    """Qué disparó el cálculo de un resultado de emparejamiento (observabilidad)."""

    link = "link"
    structure_change = "structure_change"
    manual = "manual"


class StravaActivityLap(Base):
    """Vuelta (lap) persistida de una actividad de Strava (FR-012/FR-013, D4).

    Sin columnas geo/mapa, sin ``name`` libre, sin cadencia ni potencia
    (ver docstring de módulo — privacidad Ley 1581 + alcance).
    """

    __tablename__ = "strava_activity_laps"
    __table_args__ = (
        UniqueConstraint(
            "strava_activity_id",
            "lap_index",
            name="uq_strava_activity_laps_activity_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    strava_activity_id: Mapped[int] = mapped_column(
        ForeignKey("strava_activities.id", ondelete="CASCADE"), nullable=False
    )

    # Orden del dispositivo (``lap_index`` de Strava).
    lap_index: Mapped[int] = mapped_column(Integer, nullable=False)

    elapsed_time_s: Mapped[int] = mapped_column(Integer, nullable=False)
    moving_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL cuando el dispositivo no registró frecuencia cardíaca.
    average_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ``average_speed`` de Strava (m/s).
    average_speed_m_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Marca de refresco: última vez que se trajo/reescribió esta vuelta.
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # --- Relaciones ----------------------------------------------------------
    strava_activity: Mapped["StravaActivity"] = relationship(
        "StravaActivity",
        foreign_keys="[StravaActivityLap.strava_activity_id]",
    )


class IntervalMatchResult(Base):
    """Comparación persistida plan-vs-realidad, una por par estructura↔actividad.

    Artefacto derivado: ``ondelete=CASCADE`` sobre ambas FKs — muere con el
    plan (estructura) o con la actividad (D7). Recalcular = upsert por
    ``UNIQUE(structure_id, strava_activity_id)``.
    """

    __tablename__ = "interval_match_results"
    __table_args__ = (
        UniqueConstraint(
            "structure_id",
            "strava_activity_id",
            name="uq_interval_match_results_structure_activity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    structure_id: Mapped[int] = mapped_column(
        ForeignKey("interval_structures.id", ondelete="CASCADE"), nullable=False
    )
    strava_activity_id: Mapped[int] = mapped_column(
        ForeignKey("strava_activities.id", ondelete="CASCADE"), nullable=False
    )

    # Se incrementa cuando cambian las reglas de emparejamiento.
    engine_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Forma validada por Pydantic antes de persistir (ver data-model.md §6).
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    triggered_by: Mapped[MatchTrigger] = mapped_column(
        Enum(
            MatchTrigger,
            name="matchtrigger",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
