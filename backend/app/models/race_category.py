"""Modelo SQLAlchemy para `race_categories` (catálogo de categorías Copa Valle XCO).

Schema previo: migración `0c28a22dc064` (2026-05-15).
Delta agregado en migración Paso 2 (Fase 1.7): columna `tier` enum (menores/juvenil/adulto/master).

Convenciones:
- Enum Python con `values_callable` para almacenar `M`/`F`/`MIXED` y `menores`/etc en DB.
- 26 codes oficiales 2026 (no 22 — typo del design corregido en `edge-cases.md` §2).
- Seed independiente: `backend/scripts/seed_race_categories.py`.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.race_result import RaceResult


class CategoryGender(str, enum.Enum):
    """Género competitivo de la categoría.

    `MIXED` para categorías como `PROMO` o teteros, donde no hay corte por sexo.
    """

    M = "M"
    F = "F"
    MIXED = "MIXED"


class CategoryTier(str, enum.Enum):
    """Tier etario agrupado para filtros analíticos.

    - `menores`: TET_*, PRE_*, INF_*, PJUV_*.
    - `juvenil`: JUN_*.
    - `adulto`: ELITE_*, PROMO.
    - `master`: MAS_*.
    """

    menores = "menores"
    juvenil = "juvenil"
    adulto = "adulto"
    master = "master"


class RaceCategory(Base):
    """Catálogo de categorías oficiales Copa Valle 2026 (26 entradas).

    El campo `sex` mapea al `CategoryGender` (M/F/MIXED). En la migración previa
    se llamaba `racecategorysex` (M/F/MIXED) — se mantiene compatible.

    El campo `tier` (agregado en Paso 2 Fase 1.7) sirve para analíticas que
    agrupan por bloque etario sin enumerar cada code.
    """

    __tablename__ = "race_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_race_categories_code"),
        CheckConstraint(
            "age_max IS NULL OR age_min IS NULL OR age_max >= age_min",
            name="ck_race_categories_age_max_gte_min",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    sex: Mapped[CategoryGender] = mapped_column(
        Enum(CategoryGender, name="racecategorysex", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    age_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    age_max: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    birth_year_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    birth_year_max: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Tier — agregado en migración delta Paso 2 (Fase 1.7).
    tier: Mapped[CategoryTier | None] = mapped_column(
        Enum(CategoryTier, name="racecategorytier", values_callable=lambda e: [x.value for x in e]),
        nullable=True,
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
    results: Mapped[list["RaceResult"]] = relationship(
        "RaceResult",
        back_populates="category",
        foreign_keys="[RaceResult.category_id]",
    )
