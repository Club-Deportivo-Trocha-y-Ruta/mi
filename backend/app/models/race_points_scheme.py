"""Modelo SQLAlchemy para `race_points_schemes` (esquema de puntos configurable).

Schema previo: migración `04536432643f` (2026-05-15). Este modelo Paso 2 (Fase 1.7)
solo mapea la tabla existente.

`position_points` es un JSON ordenado tipo `{"1": 40, "2": 36, "3": 33, ...}` con
puntos por puesto. `attendance_points` se suman por participar (FINISHED + MINUS_LAPS).
`dnf_points`, `dsq_points`, `dns_points` son puntos por terminar en esos estados.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    JSON,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RacePointsScheme(Base):
    """Esquema de puntos oficial — distribución por posición + base por asistencia/DNF/DSQ.

    Una serie referencia el esquema por `code` (no por id). Permite tener múltiples
    esquemas históricos sin perder trazabilidad.
    """

    __tablename__ = "race_points_schemes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_race_points_schemes_code"),
        CheckConstraint("attendance_points >= 0", name="ck_race_points_attendance_nonneg"),
        CheckConstraint("dnf_points >= 0", name="ck_race_points_dnf_nonneg"),
        CheckConstraint("dns_points >= 0", name="ck_race_points_dns_nonneg"),
        CheckConstraint("dsq_points >= 0", name="ck_race_points_dsq_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # JSON ordenado: {"1": 40, "2": 36, "3": 33, "4": 30, "5": 27, ...}
    position_points: Mapped[dict] = mapped_column(JSON, nullable=False)
    attendance_points: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dnf_points: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dsq_points: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dns_points: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
