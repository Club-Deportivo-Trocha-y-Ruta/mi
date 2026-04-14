from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.growth import GrowthIndicator, GrowthSource
from app.models.user import UserRole
from app.services.growth import get_reference_curve

router = APIRouter()

# Cache simple en memoria (los datos LMS son estáticos — no cambian en runtime)
_curve_cache: dict[tuple, list[dict]] = {}


class CurvePoint(BaseModel):
    age_months: float
    sd_minus3: float
    sd_minus2: float
    sd_minus1: float
    sd_0: float
    sd_plus1: float
    sd_plus2: float
    sd_plus3: float
    P3: float
    P10: float
    P25: float
    P50: float
    P75: float
    P90: float
    P97: float


class GrowthReferenceResponse(BaseModel):
    indicator: str
    sex: str
    source: str
    curves: list[CurvePoint]


@router.get("/growth-reference", response_model=GrowthReferenceResponse)
async def get_growth_reference(
    indicator: GrowthIndicator = Query(
        ...,
        description="Indicador: height_for_age | weight_for_age | bmi_for_age",
    ),
    sex: str = Query(..., description="Sexo: M | F"),
    source: GrowthSource = Query(
        GrowthSource.CDC,
        description="Fuente de referencia: CDC | WHO",
    ),
    age_min: float = Query(120.0, description="Edad mínima en meses (default: 120)"),
    age_max: float = Query(228.0, description="Edad máxima en meses (default: 228)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role([UserRole.admin, UserRole.coach])),
) -> GrowthReferenceResponse:
    """
    Retorna las curvas de referencia LMS (CDC o WHO) para un indicador,
    sexo y rango de edad específicos.

    Cada punto incluye valores en desviaciones estándar (-3 a +3) y
    percentiles clínicos estándar (P3, P10, P25, P50, P75, P90, P97).

    El resultado se cachea en memoria: datos LMS son estáticos durante
    el ciclo de vida del proceso.
    """
    if sex not in ("M", "F"):
        raise HTTPException(status_code=422, detail="sex debe ser 'M' o 'F'")

    if age_min >= age_max:
        raise HTTPException(
            status_code=422,
            detail="age_min debe ser menor que age_max",
        )

    cache_key = (indicator, sex, source, age_min, age_max)
    if cache_key not in _curve_cache:
        curves = await get_reference_curve(
            db=db,
            indicator=indicator,
            sex=sex,
            source=source,
            age_range=(age_min, age_max),
        )
        _curve_cache[cache_key] = curves

    return GrowthReferenceResponse(
        indicator=indicator.value,
        sex=sex,
        source=source.value,
        curves=[CurvePoint(**point) for point in _curve_cache[cache_key]],
    )
