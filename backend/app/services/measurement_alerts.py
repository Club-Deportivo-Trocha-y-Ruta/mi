"""Lógica de alertas de medición antropométrica.

Intervalos basados en evidencia científica:
- Pre-PHV (offset < -1): cada 90 días — Sport for Life Canada
- Circa-PHV (offset -1 a +1): cada 30 días — Premier League protocol
- Post-PHV (offset > +1): cada 120 días — crecimiento estable
"""

from datetime import date, timedelta
from decimal import Decimal

from app.models.anthropometry import AnthropometricRecord


# Días entre mediciones según estado de maduración
MEASUREMENT_INTERVALS: dict[str, int] = {
    "Pre-PHV": 90,
    "Circa-PHV": 30,
    "Post-PHV": 120,
}

# Umbral de crecimiento acelerado (cm/mes) — PMC/academias fútbol
GROWTH_VELOCITY_THRESHOLD: float = 0.6

# Días de anticipación para aviso "próximamente"
WARNING_DAYS: int = 7

# Intervalo por defecto si no hay estado PHV
DEFAULT_INTERVAL: int = 90


def get_measurement_interval(maturation_status: str) -> int:
    """Retorna días hasta próxima medición según estado PHV."""
    return MEASUREMENT_INTERVALS.get(maturation_status, DEFAULT_INTERVAL)


def calculate_next_due(last_date: date, maturation_status: str) -> date:
    """Calcula fecha de próxima medición."""
    interval = get_measurement_interval(maturation_status)
    return last_date + timedelta(days=interval)


def calculate_growth_velocity(
    current: AnthropometricRecord,
    previous: AnthropometricRecord | None,
) -> float | None:
    """Calcula velocidad de crecimiento en cm/mes entre dos mediciones.

    Retorna None si no hay medición previa o el intervalo es 0.
    """
    if previous is None:
        return None
    days = (current.evaluation_date - previous.evaluation_date).days
    if days <= 0:
        return None
    height_diff = float(
        Decimal(str(current.standing_height_cm)) - Decimal(str(previous.standing_height_cm))
    )
    return round(height_diff / (days / 30.44), 2)


def detect_approaching_circa(maturity_offset: float) -> bool:
    """Detecta si el atleta se aproxima al estirón (offset entre -2 y -1).

    En este rango el atleta es Pre-PHV pero se acerca a Circa-PHV,
    señal de alerta temprana para el entrenador.
    """
    return -2.0 <= maturity_offset < -1.0
