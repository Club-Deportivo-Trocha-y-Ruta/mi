"""Endpoints `/api/ai/*` — capa de IA.

Convenciones:
  - Padres NO llaman directamente a los endpoints POST. Reciben outputs vía
    `NotificationService` cuando el coach lo solicita. Bloqueado a nivel
    de router con un guard explícito (defense in depth). En cambio SÍ
    pueden leer la caché de los atletas a los que tienen acceso (GET).
  - Si la capa está apagada (`AI_ENABLED=false`) los endpoints que generan
    devuelven **503**. Los endpoints de lectura de caché siguen sirviendo
    contenido previamente generado: el coach debe poder ver lo que se
    generó ayer aunque hoy el LLM esté caído.
  - Errores de la capa se mapean: `LLMTimeoutError`/`LLMUnavailableError`
    → 503; `LLMSchemaError` → 502; `LLMConfigError` → 500.
  - Caché: `(athlete_id, anthropometric_record_id, use_case)`. Una
    medición nueva cambia el `record_id` y por tanto invalida el caché
    implícitamente sin DELETE explícito.
  - **Consentimiento parental (Ley 1581/2012)**: antes de invocar al LLM
    se verifica que el atleta tenga consentimiento vigente con
    `third_party_sharing=True`. Si no, se devuelve **451** (Unavailable
    For Legal Reasons).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_anthropometric_record_explainer_use_case,
    get_current_user,
    get_db,
    get_phv_explainer_use_case,
    require_role,
    verify_athlete_access,
)
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.user import User, UserRole
from app.schemas.ai import (
    AIHealthResponse,
    AnthropometricRecordExplanationResponse,
    PHVExplanationResponse,
)
from app.services.ai.errors import (
    LLMConfigError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.ai.use_cases.anthropometric_record_explainer import (
    USE_CASE_KEY as RECORD_USE_CASE,
    AnthropometricRecordExplainerUseCase,
)
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase
from app.services.privacy import athlete_has_ai_processing_consent

logger = logging.getLogger(__name__)
router = APIRouter()

_PHV_USE_CASE = "phv_explainer"


def _forbid_parents(current_user: User) -> None:
    """Defense in depth — los padres no consumen estos endpoints directamente."""
    if current_user.role == UserRole.parent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los padres no pueden consultar la explicación directamente.",
        )


async def _ensure_ai_consent(athlete_id: int, db: AsyncSession) -> None:
    """Bloquea con 451 si el atleta no tiene consentimiento IA vigente."""
    allowed = await athlete_has_ai_processing_consent(athlete_id, db)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Falta consentimiento parental vigente con autorización para "
                "compartir datos con terceros (procesamiento con IA). "
                "Solicita a la familia renovar el consentimiento."
            ),
        )


async def _latest_record(
    db: AsyncSession, athlete_id: int
) -> AnthropometricRecord | None:
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_record_or_404(
    db: AsyncSession, athlete_id: int, record_id: int
) -> AnthropometricRecord:
    """Valida que el record pertenece al atleta; 404 si no."""
    result = await db.execute(
        select(AnthropometricRecord).where(
            AnthropometricRecord.id == record_id,
            AnthropometricRecord.athlete_id == athlete_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medición no encontrada o no pertenece a este atleta.",
        )
    return record


def _aware_utc(dt: datetime) -> datetime:
    """MySQL DATETIME no almacena tzinfo. Reaplicamos UTC antes de serializar."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    _admin=Depends(require_role([UserRole.admin])),
) -> AIHealthResponse:
    return AIHealthResponse(
        enabled=settings.ai_enabled,
        provider=settings.ai_provider,
        model=settings.ai_model,
    )


# ---------------------------------------------------------------------------
# PHV explanation (global del atleta)
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/phv-explanation",
    responses={
        200: {"model": PHVExplanationResponse},
        204: {"description": "No hay explicación cacheada para la última medición."},
    },
)
async def get_phv_explanation_cached(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
) -> Response:
    """Devuelve la explicación cacheada para la última medición del atleta.

    Importante: este endpoint NO chequea `ai_enabled`. La idea es que las
    explicaciones generadas previamente sigan disponibles aunque el LLM
    esté caído ahora.

    Padres pueden leer el caché de sus atletas — `verify_athlete_access`
    (barrera real) ya valida el vínculo padre↔atleta. No se expone
    `generated_by_user_id` en el schema, así que no hay fuga de identidad
    del coach.
    """
    latest = await _latest_record(db, athlete.id)
    if latest is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.anthropometric_record_id == latest.id,
            AthleteAIExplanation.use_case == _PHV_USE_CASE,
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    payload = PHVExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/athletes/{athlete_id}/phv-explanation",
    response_model=PHVExplanationResponse,
)
async def phv_explanation(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
    use_case: PHVExplainerUseCase = Depends(get_phv_explainer_use_case),
) -> PHVExplanationResponse:
    _forbid_parents(current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    # Última medición + hasta 3 anteriores para construir tendencia.
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(4)
    )
    history = list(result.scalars().all())
    if not history:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El atleta no tiene mediciones antropométricas registradas.",
        )

    try:
        explanation = await use_case.run(
            athlete=athlete,
            latest_record=history[0],
            history=history,
        )
    except (LLMTimeoutError, LLMUnavailableError) as exc:
        logger.warning("ai.unavailable type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )
    except LLMSchemaError as exc:
        logger.warning("ai.schema_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La respuesta del modelo no cumplió las reglas del club.",
        )
    except LLMConfigError as exc:
        logger.error("ai.config_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de IA inválida.",
        )

    now = datetime.now(timezone.utc)
    stmt = mysql_insert(AthleteAIExplanation).values(
        athlete_id=athlete.id,
        anthropometric_record_id=history[0].id,
        use_case=_PHV_USE_CASE,
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        generated_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_duplicate_key_update(
        text=stmt.inserted.text,
        model=stmt.inserted.model,
        provider=stmt.inserted.provider,
        generated_at=stmt.inserted.generated_at,
        age_group=stmt.inserted.age_group,
        maturation_status=stmt.inserted.maturation_status,
        generated_by_user_id=stmt.inserted.generated_by_user_id,
        updated_at=now,
    )
    await db.execute(stmt)

    return PHVExplanationResponse(
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
    )


# ---------------------------------------------------------------------------
# Análisis particular por medición
# ---------------------------------------------------------------------------


@router.get(
    "/athletes/{athlete_id}/measurements/{record_id}/explanation",
    responses={
        200: {"model": AnthropometricRecordExplanationResponse},
        204: {"description": "No hay análisis cacheado para esta medición."},
    },
)
async def get_measurement_explanation_cached(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
) -> Response:
    """Devuelve el análisis cacheado para una medición concreta del atleta.

    No verifica `ai_enabled`: análisis previos siguen accesibles aunque el
    LLM esté caído. Padres pueden leer el caché de sus atletas vinculados.
    """
    record = await _get_record_or_404(db, athlete.id, record_id)

    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete.id,
            AthleteAIExplanation.anthropometric_record_id == record.id,
            AthleteAIExplanation.use_case == RECORD_USE_CASE,
        )
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # El cache no almacena los campos derivados (deltas) — los recalculamos
    # baratos desde la medición previa.
    delta_h, delta_w, num_prev = await _delta_summary(db, athlete.id, record)

    payload = AnthropometricRecordExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=_aware_utc(cached.generated_at),
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
        record_id=record.id,
        num_previous_measurements=num_prev,
        delta_height_cm=delta_h,
        delta_weight_kg=delta_w,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/athletes/{athlete_id}/measurements/{record_id}/explanation",
    response_model=AnthropometricRecordExplanationResponse,
)
async def measurement_explanation(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(get_current_user),
    use_case: AnthropometricRecordExplainerUseCase = Depends(
        get_anthropometric_record_explainer_use_case
    ),
) -> AnthropometricRecordExplanationResponse:
    _forbid_parents(current_user)

    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

    await _ensure_ai_consent(athlete.id, db)

    target = await _get_record_or_404(db, athlete.id, record_id)

    # Todas las mediciones previas a target (estrictamente anteriores).
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete.id,
            AnthropometricRecord.evaluation_date < target.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    priors = list(result.scalars().all())

    try:
        explanation = await use_case.run(
            athlete=athlete,
            target_record=target,
            prior_records=priors,
        )
    except (LLMTimeoutError, LLMUnavailableError) as exc:
        logger.warning("ai.unavailable type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )
    except LLMSchemaError as exc:
        logger.warning("ai.schema_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La respuesta del modelo no cumplió las reglas del club.",
        )
    except LLMConfigError as exc:
        logger.error("ai.config_error type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de IA inválida.",
        )

    now = datetime.now(timezone.utc)
    stmt = mysql_insert(AthleteAIExplanation).values(
        athlete_id=athlete.id,
        anthropometric_record_id=target.id,
        use_case=RECORD_USE_CASE,
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        generated_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_duplicate_key_update(
        text=stmt.inserted.text,
        model=stmt.inserted.model,
        provider=stmt.inserted.provider,
        generated_at=stmt.inserted.generated_at,
        age_group=stmt.inserted.age_group,
        maturation_status=stmt.inserted.maturation_status,
        generated_by_user_id=stmt.inserted.generated_by_user_id,
        updated_at=now,
    )
    await db.execute(stmt)

    return AnthropometricRecordExplanationResponse(
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
        record_id=target.id,
        num_previous_measurements=explanation.num_previous_measurements,
        delta_height_cm=explanation.delta_height_cm,
        delta_weight_kg=explanation.delta_weight_kg,
    )


async def _delta_summary(
    db: AsyncSession,
    athlete_id: int,
    target: AnthropometricRecord,
) -> tuple[float | None, float | None, int]:
    """Devuelve (delta_height_cm, delta_weight_kg, num_previous) para el response
    de lectura de caché. None si no hay medición previa."""
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete_id,
            AnthropometricRecord.evaluation_date < target.evaluation_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    priors = list(result.scalars().all())
    num_prev = len(priors)
    if not priors:
        return None, None, 0
    previous = priors[0]
    delta_h = round(
        float(target.standing_height_cm - previous.standing_height_cm), 1
    )
    delta_w = round(float(target.weight_kg - previous.weight_kg), 1)
    return delta_h, delta_w, num_prev
