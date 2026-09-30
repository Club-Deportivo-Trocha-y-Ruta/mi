"""Motor de plausibilidad de una medición antropométrica (feature 048, R5).

Única fuente de las advertencias "¿seguro que este dato está bien?":

1. ``POST /api/athletes/{id}/anthropometry/plausibility`` (dry-run del paso
   de revisión y del formulario de edición).
2. ``GET /api/athletes/{id}/anthropometry`` → ``plausibility_flags`` por
   registro (marca «Revisar» del historial, solo coach/admin).

Ambas superficies usan exactamente las mismas reglas: lo que se advierte
antes de guardar es lo que el historial marca después.

Puro y determinista: sin I/O, sin ORM, sin logging (los valores son datos de
menores). Las advertencias nunca bloquean; los códigos son API estable y el
texto en español vive en el frontend (``plausibilityCopy.ts``).

Aritmética en ``Decimal`` (a partir de ``str``) para que los bordes de la
tabla R5 sean exactos (p. ej. 70,5/150 = 0,47 no dispara la regla).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol

# ---------------------------------------------------------------------------
# Umbrales (research R5) — un typo, no la variación biológica normal.
# ---------------------------------------------------------------------------

#: La talla de pie bajó más de esto (cm) respecto a la evaluación anterior.
HEIGHT_DROP_CM: float = 1.0
#: Por debajo de este intervalo (días) la velocidad anualizada amplifica
#: milímetros de error: la regla de velocidad no se evalúa.
MIN_VELOCITY_INTERVAL_DAYS: int = 60
#: Velocidad de crecimiento máxima plausible (cm/año); el pico real en
#: juveniles rara vez pasa de ~10–12 cm/año.
MAX_VELOCITY_CM_PER_YEAR: float = 15.0
#: Cambio relativo de peso (fracción) respecto a la evaluación anterior.
MAX_WEIGHT_CHANGE_RATIO: float = 0.10
#: Índice córmico (talla sentado / talla de pie) típico en 9–16 años.
SITTING_RATIO_RANGE: tuple[float, float] = (0.47, 0.57)
#: Envergadura / talla de pie.
ARM_SPAN_RATIO_RANGE: tuple[float, float] = (0.90, 1.10)

_DAYS_PER_YEAR = Decimal("365.25")

PlausibilityCode = Literal[
    "height_decreased",
    "height_velocity_implausible",
    "weight_change_large",
    "sitting_ratio_atypical",
    "arm_span_ratio_atypical",
]
PlausibilityMeasure = Literal["weight", "standing_height", "sitting_height", "arm_span"]

Number = Decimal | float | int


@dataclass(frozen=True)
class MeasureSet:
    """Las cuatro medidas capturadas + la fecha (talla sentado NETA)."""

    evaluation_date: date
    weight_kg: Number
    standing_height_cm: Number
    sitting_height_cm: Number
    arm_span_cm: Number | None = None


@dataclass(frozen=True)
class PlausibilityWarning:
    code: PlausibilityCode
    measure: PlausibilityMeasure


class _RecordLike(Protocol):
    """Lo mínimo que ``flags_for_series`` lee de un ``AnthropometricRecord``."""

    id: int
    evaluation_date: date
    weight_kg: Number
    standing_height_cm: Number
    sitting_height_cm: Number
    arm_span_cm: Number | None


def _d(value: Number) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _outside(ratio: Decimal, bounds: tuple[float, float]) -> bool:
    low, high = bounds
    return ratio < _d(low) or ratio > _d(high)


def check_plausibility(
    current: MeasureSet, previous: MeasureSet | None
) -> list[PlausibilityWarning]:
    """Advertencias de ``current`` frente a ``previous`` (tabla R5).

    ``previous`` es la evaluación anterior por fecha (``None`` en la primera
    evaluación → solo aplican las reglas de proporción). Orden de salida
    estable: talla de pie, peso, talla sentado, envergadura.
    """
    warnings: list[PlausibilityWarning] = []

    standing = _d(current.standing_height_cm)
    weight = _d(current.weight_kg)

    if previous is not None:
        prev_standing = _d(previous.standing_height_cm)
        if standing < prev_standing - _d(HEIGHT_DROP_CM):
            warnings.append(PlausibilityWarning("height_decreased", "standing_height"))

        interval_days = (current.evaluation_date - previous.evaluation_date).days
        gain = standing - prev_standing
        if interval_days >= MIN_VELOCITY_INTERVAL_DAYS and gain > 0:
            velocity = gain * _DAYS_PER_YEAR / Decimal(interval_days)
            if velocity > _d(MAX_VELOCITY_CM_PER_YEAR):
                warnings.append(
                    PlausibilityWarning("height_velocity_implausible", "standing_height")
                )

        prev_weight = _d(previous.weight_kg)
        if prev_weight > 0:
            change = abs(weight - prev_weight) / prev_weight
            if change > _d(MAX_WEIGHT_CHANGE_RATIO):
                warnings.append(PlausibilityWarning("weight_change_large", "weight"))

    if standing > 0:
        if _outside(_d(current.sitting_height_cm) / standing, SITTING_RATIO_RANGE):
            warnings.append(PlausibilityWarning("sitting_ratio_atypical", "sitting_height"))
        if current.arm_span_cm is not None and _outside(
            _d(current.arm_span_cm) / standing, ARM_SPAN_RATIO_RANGE
        ):
            warnings.append(PlausibilityWarning("arm_span_ratio_atypical", "arm_span"))

    return warnings


def measure_set_of(record: _RecordLike) -> MeasureSet:
    """``MeasureSet`` a partir de un registro ya cargado (ORM o similar)."""
    return MeasureSet(
        evaluation_date=record.evaluation_date,
        weight_kg=record.weight_kg,
        standing_height_cm=record.standing_height_cm,
        sitting_height_cm=record.sitting_height_cm,
        arm_span_cm=record.arm_span_cm,
    )


def flags_for_series(records_sorted_by_date: Iterable[_RecordLike]) -> dict[int, list[str]]:
    """Códigos por ``record.id`` para la marca «Revisar» del historial.

    Cada registro se compara con el último registro de fecha ESTRICTAMENTE
    anterior (misma definición de "anterior" que el dry-run). Si hubiera dos
    registros legados con la misma fecha, ambos se comparan con el mismo
    anterior. Se reordena por (fecha, id) por defensa, así que el orden de
    entrada no altera el resultado.
    """
    ordered = sorted(records_sorted_by_date, key=lambda r: (r.evaluation_date, r.id))
    flags: dict[int, list[str]] = {}
    previous: MeasureSet | None = None  # último de una fecha anterior
    current_day: date | None = None
    last_of_day: MeasureSet | None = None
    for record in ordered:
        if record.evaluation_date != current_day:
            # Cambió el día: lo último del día anterior pasa a ser "anterior".
            if last_of_day is not None:
                previous = last_of_day
            current_day = record.evaluation_date
        current = measure_set_of(record)
        flags[record.id] = [w.code for w in check_plausibility(current, previous)]
        last_of_day = current
    return flags
