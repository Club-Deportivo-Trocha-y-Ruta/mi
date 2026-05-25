"""Modelo SQLAlchemy para `race_results` (un resultado por corredor x válida x categoría).

Schema previo: migración `04536432643f` (2026-05-15). Migración delta Paso 2
(Fase 1.7) agrega:
- valor `minus_laps` al enum `raceresultstatus` (DNS se mantiene del schema previo).
- índice `ix_race_results_category_points` (puntos descendente por categoría).

Convenciones de nombres del design vs schema real:
- `time_seconds` (design)   → `race_time_ms` (real, mayor precisión).
- `points` (design)         → `points_awarded`.
- `laps_down` (design)      → `laps_behind`.
- `rider_id` (design)       → `competitor_id`.

El edge-cases.md §4.7 confirma que `MINUS_LAPS` es necesario (Válida IV mostró
`(-1 VUELTA)` y `(-2 VUELTAS)`). Se agrega como nuevo valor al enum existente.

`bib_number` se persiste como `SmallInteger`: si una válida futura usa dorsales
alfanuméricos (`1A`, `E-23` per edge-cases.md §4.8), habrá que migrar a `String(10)`.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARCHAR  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.race_category import RaceCategory
    from app.models.race_competitor import RaceCompetitor
    from app.models.race_event import RaceEvent
    from app.models.race_import import RaceImport
    from app.models.race_result_revision import RaceResultRevision
    from app.models.user import User


class ResultStatus(str, enum.Enum):
    """Estado del corredor al cierre de la válida.

    - `FINISHED`: terminó en mismo número de vueltas que el ganador.
    - `MINUS_LAPS`: terminó pero perdió N vueltas (-1 VUELTA, -2 VUELTAS) — agregado en delta Paso 2.
    - `DNF`: Did Not Finish.
    - `DSQ`: descalificado.
    - `DNS`: Did Not Start — heredado del schema previo (no observado en V-IV pero típico federación).

    El design.md §3.4 lista solo 4 (`FINISHED, DNF, DSQ, MINUS_LAPS`).
    Aquí se mantiene `DNS` por compatibilidad con migración previa que ya lo creó.
    """

    FINISHED = "finished"
    DNF = "dnf"
    DNS = "dns"
    DSQ = "dsq"
    MINUS_LAPS = "minus_laps"


class RaceResult(Base):
    """Resultado de un corredor en una válida + categoría.

    Unicidad `(event_id, category_id, competitor_id)` ya existe en schema previo
    — un corredor puede aparecer en distintas categorías del mismo evento (caso
    Sebastian Yule Mendoza V-IV: TET_SP + TET_CP). El UNIQUE lo permite porque
    `category_id` está en la clave.

    `imported_from_id` referencia el `race_imports.id` que originó el insert
    (audit trail). `deleted_at` permite soft-delete.
    """

    __tablename__ = "race_results"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "category_id", "competitor_id", name="uq_race_results_event_category_competitor"
        ),
        CheckConstraint(
            "(status = 'finished' AND race_time_ms IS NOT NULL) "
            "OR (status != 'finished' AND race_time_ms IS NULL) "
            "OR (status = 'finished' AND laps_behind IS NOT NULL)",
            name="ck_race_results_time_consistent_with_status",
        ),
        CheckConstraint(
            "laps_behind IS NULL OR laps_behind >= 1",
            name="ck_race_results_laps_behind_positive",
        ),
        CheckConstraint("points_awarded >= 0", name="ck_race_results_points_nonneg"),
        CheckConstraint(
            "position IS NULL OR position >= 1",
            name="ck_race_results_position_positive",
        ),
        Index("ix_race_results_athlete_event", "athlete_id", "event_id"),
        Index("ix_race_results_category_event", "category_id", "event_id"),
        # Reemplaza ix_race_results_deleted_at por un índice compuesto que
        # cubre la query típica "results activos de un evento": WHERE event_id
        # = ? AND deleted_at IS NULL.
        Index("ix_race_results_event_deleted", "event_id", "deleted_at"),
        Index("ix_race_results_event_category_position", "event_id", "category_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("race_events.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("race_categories.id", ondelete="RESTRICT"), nullable=False
    )
    competitor_id: Mapped[int] = mapped_column(
        ForeignKey("race_competitors.id", ondelete="RESTRICT"), nullable=False
    )
    athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    # `bib_number` se guarda como cadena para soportar dorsales alfanuméricos
    # (edge-cases.md §4.8: `1A`, `E-23`). Conserva el string del PDF tal cual.
    bib_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    position: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[ResultStatus] = mapped_column(
        Enum(ResultStatus, name="raceresultstatus", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    race_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    laps_behind: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    points_awarded: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    imported_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("race_imports.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Relaciones
    event: Mapped["RaceEvent"] = relationship(
        "RaceEvent",
        back_populates="results",
        foreign_keys="[RaceResult.event_id]",
    )
    category: Mapped["RaceCategory"] = relationship(
        "RaceCategory",
        back_populates="results",
        foreign_keys="[RaceResult.category_id]",
    )
    competitor: Mapped["RaceCompetitor"] = relationship(
        "RaceCompetitor",
        back_populates="results",
        foreign_keys="[RaceResult.competitor_id]",
    )
    athlete: Mapped["Athlete | None"] = relationship(
        "Athlete",
        foreign_keys="[RaceResult.athlete_id]",
    )
    imported_from: Mapped["RaceImport | None"] = relationship(
        "RaceImport",
        foreign_keys="[RaceResult.imported_from_id]",
    )
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys="[RaceResult.created_by_user_id]",
    )
    revisions: Mapped[list["RaceResultRevision"]] = relationship(
        "RaceResultRevision",
        back_populates="result",
        foreign_keys="[RaceResultRevision.result_id]",
        order_by="RaceResultRevision.changed_at",
    )
