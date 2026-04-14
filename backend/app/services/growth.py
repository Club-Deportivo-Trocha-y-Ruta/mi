from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anthropometry import NutritionalStatus
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource


@dataclass
class GrowthPercentiles:
    bmi: Decimal | None
    height_z_score: Decimal | None
    height_percentile: Decimal | None
    bmi_z_score: Decimal | None
    bmi_percentile: Decimal | None
    weight_z_score: Decimal | None
    weight_percentile: Decimal | None
    nutritional_status_height: str | None  # Clasificación T/E (NutritionalStatus value)
    nutritional_status_bmi: str | None  # Clasificación IMC/E (NutritionalStatus value)


async def get_lms_params(
    db: AsyncSession,
    indicator: GrowthIndicator,
    sex: str,  # 'M' | 'F'
    age_months: float,
    source: GrowthSource = GrowthSource.CDC,
) -> tuple[float, float, float] | None:
    """
    Busca los parámetros LMS interpolando linealmente entre los dos puntos más
    cercanos. Si la edad está fuera de rango, usa el extremo más cercano.
    Retorna (L, M, S) o None si la tabla está vacía.
    """
    result = await db.execute(
        select(GrowthReferenceLms)
        .where(
            GrowthReferenceLms.source == source,
            GrowthReferenceLms.indicator == indicator,
            GrowthReferenceLms.sex == sex,
        )
        .order_by(GrowthReferenceLms.age_months)
    )
    rows = result.scalars().all()

    if not rows:
        return None

    # Caso borde: edad menor o igual al primer punto
    if age_months <= float(rows[0].age_months):
        r = rows[0]
        return float(r.L), float(r.M), float(r.S)

    # Caso borde: edad mayor o igual al último punto
    if age_months >= float(rows[-1].age_months):
        r = rows[-1]
        return float(r.L), float(r.M), float(r.S)

    # Encontrar el par (lower, upper) para interpolación
    lower = None
    upper = None
    for i, row in enumerate(rows):
        row_age = float(row.age_months)
        if row_age <= age_months:
            lower = row
        if row_age >= age_months and upper is None:
            upper = row

    # Coincidencia exacta
    if lower is not None and upper is not None and float(lower.age_months) == float(upper.age_months):
        return float(lower.L), float(lower.M), float(lower.S)

    # Interpolación lineal
    if lower is not None and upper is not None:
        age_lower = float(lower.age_months)
        age_upper = float(upper.age_months)
        t = (age_months - age_lower) / (age_upper - age_lower)
        L_interp = float(lower.L) + t * (float(upper.L) - float(lower.L))
        M_interp = float(lower.M) + t * (float(upper.M) - float(lower.M))
        S_interp = float(lower.S) + t * (float(upper.S) - float(lower.S))
        return L_interp, M_interp, S_interp

    # Fallback: retorna el último lower encontrado
    if lower is not None:
        return float(lower.L), float(lower.M), float(lower.S)

    r = rows[0]
    return float(r.L), float(r.M), float(r.S)


def calculate_z_score(value: float, L: float, M: float, S: float) -> float:
    """
    Fórmula LMS de Cole & Green (1992):
      Z = ((value/M)^L - 1) / (L * S)    si L != 0
      Z = ln(value/M) / S                  si L == 0

    Limitado a [-3, 3] para evitar valores extremos fuera de escala clínica.
    """
    if abs(L) < 1e-10:
        z = math.log(value / M) / S
    else:
        z = (((value / M) ** L) - 1) / (L * S)

    return max(-3.0, min(3.0, z))


def z_to_percentile(z: float) -> float:
    """
    Convierte Z-score a percentil usando la distribución normal estándar.

    Implementación exacta mediante la función de error complementaria:
        CDF(z) = erfc(-z / sqrt(2)) / 2
    Esto es equivalente a scipy.stats.norm.cdf(z) sin dependencia externa.
    """
    return float(math.erfc(-z / math.sqrt(2)) / 2 * 100)


def classify_nutritional_status_height(z_score: float) -> NutritionalStatus:
    """
    Clasificación T/E según Resolución 2465/2016 MinSalud Colombia
    (Artículo 1, Cuadro No. 3 — indicadores para 5-17 años):

    - Z < -2:        retraso_talla        (Talla baja / Retraso en talla)
    - -2 <= Z < -1:  riesgo_retraso_talla (Riesgo de retraso en talla)
    - Z >= -1:       talla_adecuada       (Talla adecuada para la edad)

    Nota: La resolución no define un corte superior para talla alta en este
    grupo etario, pero se conserva talla_alta para Z > 2 por consistencia
    clínica con la escala OMS completa.
    """
    if z_score < -2.0:
        return NutritionalStatus.retraso_talla
    if z_score < -1.0:
        return NutritionalStatus.riesgo_retraso_talla
    if z_score <= 2.0:
        return NutritionalStatus.talla_adecuada
    return NutritionalStatus.talla_alta


def classify_nutritional_status_bmi(z_score: float) -> NutritionalStatus:
    """
    Clasificación IMC/E según Resolución 2465/2016 MinSalud Colombia
    (Artículo 1, Cuadro No. 3 — indicadores para 5-17 años):

    - Z > +2:         obesidad
    - +1 < Z <= +2:   sobrepeso
    - -1 <= Z <= +1:  adecuado
    - -2 <= Z < -1:   delgadez       (Riesgo de delgadez en la norma)
    - Z < -2:         delgadez_severa (Delgadez en la norma)

    Nota: delgadez_severa se reserva para Z < -3 en otras fuentes, pero
    aquí se usa como equivalente al umbral < -2 de la norma colombiana,
    manteniendo compatibilidad con el enum NutritionalStatus del modelo.
    """
    if z_score > 2.0:
        return NutritionalStatus.obesidad
    if z_score > 1.0:
        return NutritionalStatus.sobrepeso
    if z_score >= -1.0:
        return NutritionalStatus.adecuado
    if z_score >= -2.0:
        return NutritionalStatus.delgadez
    return NutritionalStatus.delgadez_severa


async def calculate_growth_percentiles(
    db: AsyncSession,
    weight_kg: float,
    standing_height_cm: float,
    sex: str,
    age_months: float,
    source: GrowthSource = GrowthSource.CDC,
) -> GrowthPercentiles:
    """
    Calcula todos los percentiles de un registro antropométrico.
    BMI = weight_kg / (standing_height_cm / 100) ** 2
    """
    bmi_value = weight_kg / (standing_height_cm / 100) ** 2
    bmi_decimal = Decimal(str(round(bmi_value, 2)))

    # Obtener parámetros LMS para cada indicador
    lms_height = await get_lms_params(
        db, GrowthIndicator.height_for_age, sex, age_months, source
    )
    lms_bmi = await get_lms_params(
        db, GrowthIndicator.bmi_for_age, sex, age_months, source
    )
    lms_weight = await get_lms_params(
        db, GrowthIndicator.weight_for_age, sex, age_months, source
    )

    # Talla para la Edad
    if lms_height is not None:
        L_h, M_h, S_h = lms_height
        hz = calculate_z_score(standing_height_cm, L_h, M_h, S_h)
        height_z = Decimal(str(round(hz, 3)))
        height_pct = Decimal(str(round(z_to_percentile(hz), 1)))
        nut_height: str | None = classify_nutritional_status_height(hz).value
    else:
        height_z = None
        height_pct = None
        nut_height = None

    # IMC para la Edad
    if lms_bmi is not None:
        L_b, M_b, S_b = lms_bmi
        bz = calculate_z_score(bmi_value, L_b, M_b, S_b)
        bmi_z = Decimal(str(round(bz, 3)))
        bmi_pct = Decimal(str(round(z_to_percentile(bz), 1)))
        nut_bmi: str | None = classify_nutritional_status_bmi(bz).value
    else:
        bmi_z = None
        bmi_pct = None
        nut_bmi = None

    # Peso para la Edad
    if lms_weight is not None:
        L_w, M_w, S_w = lms_weight
        wz = calculate_z_score(weight_kg, L_w, M_w, S_w)
        weight_z: Decimal | None = Decimal(str(round(wz, 3)))
        weight_pct: Decimal | None = Decimal(str(round(z_to_percentile(wz), 1)))
    else:
        weight_z = None
        weight_pct = None

    return GrowthPercentiles(
        bmi=bmi_decimal,
        height_z_score=height_z,
        height_percentile=height_pct,
        bmi_z_score=bmi_z,
        bmi_percentile=bmi_pct,
        weight_z_score=weight_z,
        weight_percentile=weight_pct,
        nutritional_status_height=nut_height,
        nutritional_status_bmi=nut_bmi,
    )


def _lms_value_at_z(L: float, M: float, S: float, z: float) -> float:
    """
    Fórmula inversa LMS:
        value = M * (1 + L * S * z) ** (1/L)    si L != 0
        value = M * exp(S * z)                    si L == 0
    """
    if abs(L) < 1e-10:
        return M * math.exp(S * z)
    base = 1 + L * S * z
    if base <= 0:
        return 0.0
    return M * (base ** (1.0 / L))


async def get_reference_curve(
    db: AsyncSession,
    indicator: GrowthIndicator,
    sex: str,
    source: GrowthSource = GrowthSource.CDC,
    age_range: tuple[float, float] = (120.0, 228.0),
) -> list[dict]:
    """
    Retorna las curvas de referencia para el rango de edad especificado.

    Cada punto tiene:
    {
        "age_months": float,
        "sd_minus3": float,  # -3 SD
        "sd_minus2": float,  # -2 SD (P3)
        "sd_minus1": float,  # -1 SD
        "sd_0": float,       # mediana (P50)
        "sd_plus1": float,   # +1 SD
        "sd_plus2": float,   # +2 SD (P97)
        "sd_plus3": float,   # +3 SD
        "P3": float,
        "P10": float,
        "P25": float,
        "P50": float,
        "P75": float,
        "P90": float,
        "P97": float,
    }

    Z-scores para percentiles estándar:
        P3  -> Z ≈ -1.8808
        P10 -> Z ≈ -1.2816
        P25 -> Z ≈ -0.6745
        P50 -> Z =  0.0
        P75 -> Z ≈  0.6745
        P90 -> Z ≈  1.2816
        P97 -> Z ≈  1.8808
    """
    age_min, age_max = age_range

    result = await db.execute(
        select(GrowthReferenceLms)
        .where(
            GrowthReferenceLms.source == source,
            GrowthReferenceLms.indicator == indicator,
            GrowthReferenceLms.sex == sex,
            GrowthReferenceLms.age_months >= age_min,
            GrowthReferenceLms.age_months <= age_max,
        )
        .order_by(GrowthReferenceLms.age_months)
    )
    rows = result.scalars().all()

    # Z-scores para percentiles estándar
    percentile_z = {
        "P3": -1.8808,
        "P10": -1.2816,
        "P25": -0.6745,
        "P50": 0.0,
        "P75": 0.6745,
        "P90": 1.2816,
        "P97": 1.8808,
    }

    curve: list[dict] = []
    for row in rows:
        L = float(row.L)
        M = float(row.M)
        S = float(row.S)
        point: dict = {
            "age_months": float(row.age_months),
            "sd_minus3": _lms_value_at_z(L, M, S, -3.0),
            "sd_minus2": _lms_value_at_z(L, M, S, -2.0),
            "sd_minus1": _lms_value_at_z(L, M, S, -1.0),
            "sd_0": _lms_value_at_z(L, M, S, 0.0),
            "sd_plus1": _lms_value_at_z(L, M, S, 1.0),
            "sd_plus2": _lms_value_at_z(L, M, S, 2.0),
            "sd_plus3": _lms_value_at_z(L, M, S, 3.0),
        }
        for pname, pz in percentile_z.items():
            point[pname] = _lms_value_at_z(L, M, S, pz)
        curve.append(point)

    return curve
