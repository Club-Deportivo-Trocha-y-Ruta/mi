from __future__ import annotations

import logging
from datetime import date, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_role, verify_athlete_access
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.growth import GrowthIndicator, GrowthSource
from app.models.user import User, UserRole
from app.schemas.body_composition import BodyCompositionFamilySummary
from app.schemas.growth import GrowthSummaryOut, LatestAiAnalysis
from app.services.ai.anthro.guardrails_step import FAMILY_DELIVERABLE_VERDICTS
from app.services.ai.use_cases.anthropometric_record_explainer import (
    USE_CASE_KEY as RECORD_USE_CASE,
)
from app.services.body_composition import load_athlete_records
from app.services.body_composition import load_reading as load_body_composition_reading
from app.services.growth import get_reference_curve
from app.services.growth_summary import build_growth_summary
from app.services.privacy import athlete_has_ai_processing_consent

logger = logging.getLogger(__name__)

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


async def _compute_latest_ai_analysis(
    db: AsyncSession,
    athlete: Athlete,
    latest_record: AnthropometricRecord | None,
    current_user: User,
) -> LatestAiAnalysis | None:
    """Proyecta la fila de análisis de IA (feature 042) más reciente sobre la
    pestaña de crecimiento — `contracts/growth-summary-latest-analysis.md`.

    Siempre la fila **familiar** (`RECORD_USE_CASE`), nunca la de coach (§1
    del contrato) — así la misma línea es segura de mostrar en ambos modos.
    Una sola consulta indexada adicional (`(athlete_id, use_case)`, más el
    filtro por `schema_version`), dentro de la misma petición que ya trae
    las dos mediciones — sin round trip extra (SC-008). Nunca lanza: el
    llamador (`get_growth_summary`) la envuelve en `try/except` (§5 del
    contrato) para que un fallo de esta lectura jamás tumbe la pestaña.
    """
    if latest_record is None or not settings.ai_enabled:
        return None
    if not await athlete_has_ai_processing_consent(athlete.id, db):
        return None

    result = await db.execute(
        select(AthleteAIExplanation)
        .where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.use_case == RECORD_USE_CASE,
            AthleteAIExplanation.schema_version == "v2",
        )
        .order_by(AthleteAIExplanation.generated_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.structured_json:
        return None

    summary_line = row.structured_json.get("summary_line")
    if not summary_line:
        return None

    # Compuerta familiar por rol (FR-016) — idéntica a
    # `routers/ai.py::_family_gate_blocks`: un padre nunca ve una fila
    # `flagged`/`fallback`/`skipped`; `critic_verdict IS NULL` (fila legado,
    # no debería darse aquí porque ya filtramos `schema_version="v2"`, pero
    # se trata igual que en `ai.py` por si acaso) siempre es entregable.
    verdict = row.critic_verdict
    is_parent = current_user.role == UserRole.parent
    if is_parent and verdict is not None and verdict not in FAMILY_DELIVERABLE_VERDICTS:
        return None

    generated_at = row.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    # data-model.md §4: hay una medición más nueva que la analizada, o la
    # medición analizada fue corregida después de generarse el análisis.
    updated_at = latest_record.updated_at
    is_stale = latest_record.id != row.anthropometric_record_id or (
        updated_at is not None and updated_at.replace(tzinfo=timezone.utc) > generated_at
    )

    return LatestAiAnalysis(
        record_id=row.anthropometric_record_id,
        generated_at=generated_at,
        summary_line=summary_line,
        has_warning_signs=bool(row.structured_json.get("warning_signs")),
        critic_verdict=None if is_parent else verdict,
        is_stale=is_stale,
    )


@router.get("/athletes/{athlete_id}/growth-summary", response_model=GrowthSummaryOut)
async def get_growth_summary(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
) -> GrowthSummaryOut:
    """
    Resumen de crecimiento decisión-primero para la pestaña del entrenador
    (feature 040 / US2): etapa, velocidad, próxima medición y alertas,
    calculados sobre las dos mediciones antropométricas más recientes.

    ``verify_athlete_access`` ya aplica el RBAC (admin: cualquiera; coach:
    atletas de sus clubes; parent: solo atletas vinculados). No se
    recalculan Z-scores/percentiles/bandas: se leen tal como fueron
    guardados por ``POST /athletes/{id}/anthropometry`` (OMS 2007).

    Feature 042 (T067): además incorpora ``latest_ai_analysis`` — la línea
    de resumen del análisis de IA más reciente, consentimiento-gated y
    tolerante a fallos (nunca puede provocar un 500 de este endpoint; ver
    ``contracts/growth-summary-latest-analysis.md`` §5).
    """
    # Feature 046 (T080, privacy-audit F6): ONE SELECT loads every record with
    # its skinfold set (`load_athlete_records`, LEFT JOIN + contains_eager);
    # it replaces the pre-046 `ORDER BY … DESC LIMIT 2` query, so the only
    # extra query on this path is the FUPRECOL reference lookup (≤ 1, and
    # none without a counted set) — the T041 query budget. The body
    # composition then comes from the same `load_reading` as the coach
    # detail, the newsletter annex and the AI leaf.
    records = await load_athlete_records(db, athlete.id)
    latest = records[-1] if records else None
    previous = records[-2] if len(records) > 1 else None
    loaded_body_composition = await load_body_composition_reading(
        db, athlete, records=records
    )

    summary = build_growth_summary(
        athlete=athlete,
        latest=latest,
        previous=previous,
        today=date.today(),
        body_composition=loaded_body_composition,
    )

    # Feature 046: parents get exactly the 5-key family projection, built
    # explicitly from `family_band` — never the coach model or `band`.
    if current_user.role == UserRole.parent and summary.body_composition is not None:
        coach_body_composition = summary.body_composition
        summary.body_composition = BodyCompositionFamilySummary(
            has_data=coach_body_composition.has_data,
            latest_set_date=coach_body_composition.latest_set_date,
            family_band=coach_body_composition.family_band,
            family_label=coach_body_composition.family_label,
            family_sentence=coach_body_composition.family_sentence,
        )

    try:
        summary.latest_ai_analysis = await _compute_latest_ai_analysis(
            db, athlete, latest, current_user
        )
    except Exception:
        logger.warning(
            "growth_summary.latest_ai_analysis_failed",
            extra={"athlete_id": athlete.id},
        )
        summary.latest_ai_analysis = None

    return summary
