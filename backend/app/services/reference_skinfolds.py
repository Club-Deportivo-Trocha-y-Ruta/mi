"""
Contexto de percentil poblacional para pliegues cutáneos (feature 046).

Envoltura delgada sobre ``app/services/growth.py`` que reutiliza la
maquinaria LMS existente (``get_lms_params``/``calculate_z_score``/
``z_to_percentile``) con la fuente ``FUPRECOL`` (Ramírez-Vélez et al. 2016,
escolares de Bogotá, lado izquierdo, 9–17.9 años). El resultado es contexto
poblacional, nunca un veredicto individual — ver
``docs/21-body-composition/research-protocol.md``.

No hay efectos secundarios: solo lecturas contra ``growth_reference_lms``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.services.growth import calculate_z_score, interpolate_lms, z_to_percentile

ReferenceCode = Literal["low_extreme", "low", "normal", "high", "high_extreme", "unavailable"]

# Rango de edad soportado por las tablas FUPRECOL (9.0–18.0 años).
AGE_MIN_MONTHS: float = 108.0
AGE_MAX_MONTHS: float = 216.0


class ReferenceSiteContext(TypedDict):
    percentile: float | None
    code: ReferenceCode


def _classify(percentile: float) -> ReferenceCode:
    if percentile < 5.0:
        return "low_extreme"
    if percentile < 10.0:
        return "low"
    if percentile < 85.0:
        return "normal"
    if percentile < 95.0:
        return "high"
    return "high_extreme"


_UNAVAILABLE: ReferenceSiteContext = {"percentile": None, "code": "unavailable"}

#: Sitio → indicador FUPRECOL (tríceps y subescapular son los únicos publicados).
_SITE_INDICATORS: dict[str, GrowthIndicator] = {
    "triceps": GrowthIndicator.triceps_skinfold_for_age,
    "subscapular": GrowthIndicator.subscapular_skinfold_for_age,
}


def _site_from_rows(rows: list, age_months: float, value_mm: float) -> ReferenceSiteContext:
    lms = interpolate_lms(rows, age_months)
    if lms is None:
        return dict(_UNAVAILABLE)  # type: ignore[return-value]
    L, M, S = lms
    percentile = z_to_percentile(calculate_z_score(value_mm, L, M, S))
    return {"percentile": percentile, "code": _classify(percentile)}


async def reference_context(
    db: AsyncSession,
    sex: str,
    age_months: float,
    triceps_mm: float | None,
    subscapular_mm: float | None,
) -> dict[str, ReferenceSiteContext]:
    """
    Calcula el contexto percentil FUPRECOL por sitio (tríceps, subescapular).

    ``triceps_mm``/``subscapular_mm`` en ``None`` representan un sitio omitido
    en la toma (``declined``) y siempre producen ``unavailable``. Fuera del
    rango 108–216 meses (9.0–18.0 años), o si no hay filas sembradas para el
    indicador/sexo, también se retorna ``unavailable`` — nunca se extrapola
    más allá del rango publicado por el estudio.

    A lo sumo UNA consulta (T080): las filas LMS de los dos indicadores se
    leen juntas y se interpolan en memoria (``growth.interpolate_lms``, la
    misma lógica de ``get_lms_params``), para que el resumen de crecimiento
    respete su presupuesto de consultas. Ninguna consulta si ningún sitio
    tiene valor o la edad está fuera de rango.
    """
    values = {"triceps": triceps_mm, "subscapular": subscapular_mm}
    in_range = AGE_MIN_MONTHS <= age_months <= AGE_MAX_MONTHS
    wanted = {site: v for site, v in values.items() if v is not None and in_range}
    result: dict[str, ReferenceSiteContext] = {
        site: dict(_UNAVAILABLE)  # type: ignore[misc]
        for site in values
    }
    if not wanted:
        return result

    indicators = [_SITE_INDICATORS[site] for site in wanted]
    rows_result = await db.execute(
        select(GrowthReferenceLms)
        .where(
            GrowthReferenceLms.source == GrowthSource.FUPRECOL,
            GrowthReferenceLms.indicator.in_(indicators),
            GrowthReferenceLms.sex == sex,
        )
        .order_by(GrowthReferenceLms.indicator, GrowthReferenceLms.age_months)
    )
    rows_by_indicator: dict[GrowthIndicator, list] = {}
    for row in rows_result.scalars().all():
        rows_by_indicator.setdefault(row.indicator, []).append(row)

    for site, value_mm in wanted.items():
        rows = rows_by_indicator.get(_SITE_INDICATORS[site], [])
        result[site] = _site_from_rows(rows, age_months, float(value_mm))
    return result
