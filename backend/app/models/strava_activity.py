"""Modelo SQLAlchemy para ``strava_activities`` (feature 025).

Una fila por actividad de Strava de un atleta conectado. Ancla de
idempotencia: ``UNIQUE(strava_activity_id)`` — el ingest (webhook o
reconcile) siempre hace upsert por esa clave (FR-005), nunca inserta un
duplicado.

PRIVACIDAD (Ley 1581, menores de edad — ver data-model.md §2 "Explicitly
ABSENT columns" y research.md §7): este modelo NO tiene, y NUNCA debe ganar,
columnas de ubicación o mapa (``start_latlng``, ``end_latlng``,
``map_polyline``, ``description``, fotos, datos de segmentos). El servicio
de ingest (``services/strava/ingest.py``, T015) descarta esos campos del
payload de Strava antes de persistir. ``name`` (título de la actividad)
puede contener texto libre del atleta/familia — nunca se loggea ni se envía
a IA (solo IDs numéricos en logs, ver FR-016).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.strava_connection import StravaConnection
    from app.models.training_session import TrainingSession
    from app.models.user import User


class StravaUpstreamState(str, enum.Enum):
    """Refleja si la actividad sigue existiendo en Strava (FR-013)."""

    present = "present"
    removed_upstream = "removed_upstream"


class StravaIngestSource(str, enum.Enum):
    """Vía por la que llegó/actualizó esta fila (observabilidad SC-001/SC-002)."""

    webhook = "webhook"
    reconcile = "reconcile"


class StravaActivity(Base):
    """Actividad sincronizada desde Strava, asociada a un atleta del club.

    ``training_session_id`` es el único vínculo editable por el entrenador
    (coach-gated linking, FR-007/FR-009): NULL es un estado permanente y
    válido (salida libre, no relacionada al plan de entrenamiento).
    """

    __tablename__ = "strava_activities"
    __table_args__ = (
        Index("ix_strava_activities_athlete_id", "athlete_id"),
        Index("ix_strava_activities_start_date_utc", "start_date_utc"),
        # Sirve tanto la vista de revisión del coach (training_session_id IS
        # NULL ORDER BY start_date_utc DESC) como el detalle de sesión
        # (GET /training-sessions/{id}/activities) — data-model.md §5.
        Index(
            "ix_strava_activities_session_start",
            "training_session_id",
            "start_date_utc",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Clave de idempotencia — ``object_id`` del webhook / ``id`` del listado
    # REST. El ingest hace upsert por esta columna (FR-005).
    strava_activity_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )

    # Denormalizado desde la conexión al momento del ingest (evita join en
    # cada lectura de listas por atleta).
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("strava_connections.id", ondelete="RESTRICT"), nullable=False
    )

    # Título libre de la actividad — NUNCA se loggea, NUNCA se envía a IA.
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # ``sport_type`` de Strava es un conjunto abierto (no se modela como enum).
    sport_type: Mapped[str] = mapped_column(String(50), nullable=False)

    start_date_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Fecha local del atleta — el emparejamiento con sesiones usa fecha local.
    start_date_local: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    elapsed_time_s: Mapped[int] = mapped_column(Integer, nullable=False)
    moving_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_elevation_gain_m: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    # NULL cuando el dispositivo no registró frecuencia cardíaca.
    average_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_heartrate: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_trainer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    upstream_state: Mapped[StravaUpstreamState] = mapped_column(
        Enum(
            StravaUpstreamState,
            name="stravaupstreamstate",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=StravaUpstreamState.present,
        server_default=StravaUpstreamState.present.value,
    )
    ingest_source: Mapped[StravaIngestSource] = mapped_column(
        Enum(
            StravaIngestSource,
            name="stravaingestsource",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # False cuando la primera entrega (típicamente webhook) trajo campos
    # nulos; el job de reconcile la re-consulta y la marca True (FR-015).
    summary_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    # --- Vínculo coach-gated (FR-007/FR-009) --------------------------------
    training_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True
    )
    linked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ``first_seen_at`` vs ``start_date_utc`` mide la latencia de sync (SC-001).
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relaciones ----------------------------------------------------------
    athlete: Mapped["Athlete"] = relationship(
        "Athlete", foreign_keys="[StravaActivity.athlete_id]"
    )
    connection: Mapped["StravaConnection"] = relationship(
        "StravaConnection",
        back_populates="activities",
        foreign_keys="[StravaActivity.connection_id]",
    )
    training_session: Mapped["TrainingSession | None"] = relationship(
        "TrainingSession", foreign_keys="[StravaActivity.training_session_id]"
    )
    linked_by: Mapped["User | None"] = relationship(
        "User", foreign_keys="[StravaActivity.linked_by_user_id]"
    )
