"""Modelo SQLAlchemy para ``race_course_variants`` (feature 043).

Una fila por variante de recorrido de una válida (ej. "Circuito completo",
"Recorrido reducido"). La variante se extrae server-side de un GPX grabado
por el coach: se detecta y recorta a **una sola vuelta** (posición + altitud
únicamente) y solo esa vuelta se persiste en ``geometry`` — el archivo
original nunca se guarda (no hay ``storage_path``, no hay bucket) y no se
persiste ningún timestamp de la grabación (ni por punto ni del archivo).
Esto es intencional (FR-003): la grabación es un dato personal del coach, no
un artefacto de auditoría de la club.

``detection_method`` documenta cómo se determinó qué es "una vuelta" a partir
del recorrido crudo: ``closed_loop`` (el track cierra sobre sí mismo y se
detectaron N vueltas), ``manual`` (el coach indicó ``recorded_laps``) o
``single`` (el track ya traía una sola vuelta, sin loop detectable).
``source_sha256`` es el hash del archivo subido — se guarda solo para
detectar re-subidas del mismo archivo (409 ``duplicate_recording``), nunca
para recuperar el contenido.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import ActorTimestampMixin

if TYPE_CHECKING:
    from app.models.race_course_category_setup import RaceCourseCategorySetup
    from app.models.race_event import RaceEvent
    from app.models.user import User


class RaceCourseVariant(ActorTimestampMixin, Base):
    """Variante de recorrido de una válida — geometría de una sola vuelta.

    Unicidad ``(race_event_id, label)``: el coach no puede tener dos
    variantes con el mismo nombre en la misma válida. ``geometry`` es una
    lista de ternas ``[lat, lon, ele|null]`` (``ele`` es ``null`` cuando el
    GPX no traía altitud, en cuyo caso ``has_elevation=False`` y
    ``elevation_gain_m`` también queda ``NULL``).
    """

    __tablename__ = "race_course_variants"
    __table_args__ = (
        UniqueConstraint(
            "race_event_id", "label", name="uq_race_course_variants_event_label"
        ),
        Index("ix_race_course_variants_event", "race_event_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("race_events.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    lap_distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    elevation_gain_m: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, default=None
    )
    has_elevation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    point_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    geometry: Mapped[list] = mapped_column(JSON, nullable=False)
    detection_method: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_laps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    # SHA256 del archivo subido (descartado tras procesar) — solo para
    # detectar re-subidas duplicadas, nunca para recuperar el contenido.
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    event: Mapped["RaceEvent"] = relationship(
        "RaceEvent",
        back_populates="course_variants",
        foreign_keys="[RaceCourseVariant.race_event_id]",
    )
    # Solo lectura — usada para listar categorías que referencian esta
    # variante y armar el mensaje 409 "variant_in_use" al intentar borrarla.
    setups: Mapped[list["RaceCourseCategorySetup"]] = relationship(
        "RaceCourseCategorySetup",
        back_populates="variant",
        viewonly=True,
    )
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceCourseVariant.created_by_user_id]",
    )
