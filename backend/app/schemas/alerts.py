"""Schemas para el sistema de alertas de medición antropométrica."""

import enum
from datetime import date

from pydantic import BaseModel


class MeasurementStatus(str, enum.Enum):
    overdue = "overdue"      # Rojo: medición vencida
    due_soon = "due_soon"    # Amarillo: vence en ≤7 días
    ok = "ok"                # Verde: al día
    never = "never"          # Gris: nunca medido


class GrowthAlert(str, enum.Enum):
    rapid_growth = "rapid_growth"            # ≥0.6 cm/mes detectado
    approaching_circa = "approaching_circa"  # offset entre -2 y -1, acercándose al estirón
    phase_changed = "phase_changed"          # cambió de fase PHV desde última medición


class AthleteAlert(BaseModel):
    athlete_id: int
    athlete_name: str
    sex: str
    age_decimal: float
    category: str

    # Estado de medición
    measurement_status: MeasurementStatus
    last_measurement_date: date | None = None
    next_due_date: date | None = None
    days_overdue: int | None = None
    current_phv_status: str | None = None
    measurement_interval_days: int

    # Alertas de crecimiento
    growth_velocity_cm_month: float | None = None
    growth_alerts: list[GrowthAlert] = []

    # Contexto para el entrenador
    training_implications: str | None = None


class AlertsSummary(BaseModel):
    overdue: int
    due_soon: int
    ok: int
    never_measured: int
    rapid_growth_count: int
    athletes: list[AthleteAlert]
