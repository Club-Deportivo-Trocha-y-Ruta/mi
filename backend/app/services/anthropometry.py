"""Derivación de los campos calculados de un registro antropométrico.

Feature 048 (research R1): la lógica vivía inline en
``routers/anthropometry.py::create_anthropometry``. Se extrae aquí para que
POST y el futuro PUT apliquen exactamente las mismas reglas (FR-002):

- Maturity offset de Mirwald (``calculate_mirwald_offset``).
- Percentiles OMS 2007 con fallback a ``None`` si la tabla LMS está vacía o
  el cálculo falla.
- ``weight_z_score``/``weight_percentile`` en ``None`` por encima de
  ``WEIGHT_AGE_MAX_MONTHS`` (la OMS no publica peso/edad > 10 años).
- IMC calculado siempre, desacoplado de la tabla LMS.
- ``nutritional_status`` = clasificación IMC/E; ``growth_source`` = OMS.

Sin efectos secundarios: no escribe en la BD (solo lee tablas LMS), no audita
ni notifica. Nunca registra valores de medición en logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.growth import GrowthSource
from app.services.category import compute_age_decimal
from app.services.growth import calculate_growth_percentiles
from app.services.phv import calculate_mirwald_offset

# La OMS 2007 solo publica peso/edad hasta los 10 años (feature 040 / R-02).
# Por encima de este umbral (en meses) weight_z_score/weight_percentile se
# guardan en NULL: no existe referencia poblacional con la que clasificarlos.
WEIGHT_AGE_MAX_MONTHS: float = 120.5


@dataclass(frozen=True)
class DerivedFields:
    """Campos calculados de un ``AnthropometricRecord``.

    Los tipos reflejan exactamente lo que el router asignaba antes de la
    extracción (floats redondeados de Mirwald, ``Decimal`` del IMC, valores
    de ``GrowthPercentiles``), para no cambiar nada de lo que se persiste.
    """

    # Mirwald
    leg_length_cm: Any
    leg_sitting_ratio: Any
    maturity_offset: Any
    age_at_phv: Any
    maturation_status: Any
    training_implications: str | None
    # OMS 2007 (None si la tabla LMS está vacía)
    height_z_score: Decimal | None
    height_percentile: Decimal | None
    bmi: Decimal
    bmi_z_score: Decimal | None
    bmi_percentile: Decimal | None
    weight_z_score: Decimal | None
    weight_percentile: Decimal | None
    nutritional_status: str | None
    growth_source: GrowthSource
    # Solo para la respuesta (no es columna): clasificación T/E del cálculo.
    nutritional_status_height: str | None


async def derive_record_fields(
    db: AsyncSession,
    athlete: Athlete,
    *,
    evaluation_date: date,
    weight_kg: Decimal,
    standing_height_cm: Decimal,
    sitting_height_cm: Decimal,
) -> DerivedFields:
    """Calcula todos los campos derivados para las medidas dadas."""
    # Edad decimal a la fecha de evaluación
    age = compute_age_decimal(athlete.birth_date, evaluation_date)

    # Cálculos PHV Mirwald
    phv = calculate_mirwald_offset(
        sex=athlete.sex.value,
        age=age,
        weight=float(weight_kg),
        standing_height=float(standing_height_cm),
        sitting_height=float(sitting_height_cm),
    )

    # Calcular percentiles de crecimiento (graceful fallback si tabla LMS vacía)
    # Feature 040: la OMS 2007 es la única referencia poblacional del servidor.
    age_months = age * 12
    try:
        growth = await calculate_growth_percentiles(
            db=db,
            weight_kg=float(weight_kg),
            standing_height_cm=float(standing_height_cm),
            sex=athlete.sex.value,
            age_months=age_months,
            source=GrowthSource.WHO,
        )
    except Exception:
        growth = None

    # Si todos los z-scores son None la tabla LMS está vacía — tratar como sin datos
    if growth is not None and growth.height_z_score is None and growth.bmi_z_score is None:
        growth = None

    # La OMS no publica peso/edad por encima de los 10 años (feature 040 / R-02):
    # weight_z_score/weight_percentile se guardan en NULL para esas edades, sin
    # importar lo que haya calculado calculate_growth_percentiles.
    weight_over_who_range = age_months > WEIGHT_AGE_MAX_MONTHS

    # BMI desacoplado de la tabla LMS (feature 003 / FR-001a): se calcula y
    # persiste SIEMPRE que haya peso y talla, sin depender de las constantes de
    # referencia. Los percentiles/z-scores siguen condicionados a LMS.
    bmi_value = float(weight_kg) / (float(standing_height_cm) / 100) ** 2
    bmi_decimal = Decimal(str(round(bmi_value, 2)))

    return DerivedFields(
        leg_length_cm=phv["leg_length_cm"],
        leg_sitting_ratio=phv["leg_sitting_ratio"],
        maturity_offset=phv["maturity_offset"],
        age_at_phv=phv["age_at_phv"],
        maturation_status=phv["maturation_status"],
        training_implications=phv["training_implications"],
        height_z_score=growth.height_z_score if growth else None,
        height_percentile=growth.height_percentile if growth else None,
        bmi=bmi_decimal,
        bmi_z_score=growth.bmi_z_score if growth else None,
        bmi_percentile=growth.bmi_percentile if growth else None,
        weight_z_score=(
            growth.weight_z_score if growth and not weight_over_who_range else None
        ),
        weight_percentile=(
            growth.weight_percentile if growth and not weight_over_who_range else None
        ),
        # nutritional_status almacena la clasificación IMC/E (la más clínica)
        nutritional_status=growth.nutritional_status_bmi if growth else None,
        # Referencia poblacional usada para los campos anteriores (feature 040):
        # todo registro nuevo se calcula contra la OMS 2007.
        growth_source=GrowthSource.WHO,
        nutritional_status_height=growth.nutritional_status_height if growth else None,
    )


def apply_derived_fields(record: AnthropometricRecord, derived: DerivedFields) -> None:
    """Copia los campos derivados sobre ``record`` (sin tocar las medidas
    capturadas, ``evaluated_by`` ni ``notes``). ``nutritional_status_height``
    no es columna y no se asigna."""
    record.leg_length_cm = derived.leg_length_cm
    record.leg_sitting_ratio = derived.leg_sitting_ratio
    record.maturity_offset = derived.maturity_offset
    record.age_at_phv = derived.age_at_phv
    record.maturation_status = derived.maturation_status
    record.training_implications = derived.training_implications
    record.height_z_score = derived.height_z_score
    record.height_percentile = derived.height_percentile
    record.bmi = derived.bmi
    record.bmi_z_score = derived.bmi_z_score
    record.bmi_percentile = derived.bmi_percentile
    record.weight_z_score = derived.weight_z_score
    record.weight_percentile = derived.weight_percentile
    record.nutritional_status = derived.nutritional_status
    record.growth_source = derived.growth_source
