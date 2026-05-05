"""Endpoints `/api/ai/*` — capa de IA.

Convenciones:
  - Padres NO llaman directamente a estos endpoints. Reciben outputs vía
    `NotificationService` cuando el coach lo solicita.
  - Si la capa está apagada (`AI_ENABLED=false`) cualquier endpoint salvo
    `/health` devuelve **503**. El proveedor sigue siendo `FakeLLMProvider`
    para que no se rompa el resto de la app.
  - Errores de la capa se mapean: `LLMTimeoutError`/`LLMUnavailableError`
    → 503; `LLMSchemaError` → 502; `LLMConfigError` → 500.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_db,
    get_phv_explainer_use_case,
    require_role,
    verify_athlete_access,
)
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.user import UserRole
from app.schemas.ai import AIHealthResponse, PHVExplanationResponse
from app.services.ai.errors import (
    LLMConfigError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    _admin=Depends(require_role([UserRole.admin])),
) -> AIHealthResponse:
    return AIHealthResponse(
        enabled=settings.ai_enabled,
        provider=settings.ai_provider,
        model=settings.ai_model,
    )


@router.post(
    "/athletes/{athlete_id}/phv-explanation",
    response_model=PHVExplanationResponse,
)
async def phv_explanation(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    use_case: PHVExplainerUseCase = Depends(get_phv_explainer_use_case),
) -> PHVExplanationResponse:
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )

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
        logger.warning("ai.unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no disponible",
        )
    except LLMSchemaError as exc:
        logger.warning("ai.schema_error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La respuesta del modelo no cumplió las reglas del club.",
        )
    except LLMConfigError as exc:
        logger.error("ai.config_error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuración de IA inválida.",
        )

    return PHVExplanationResponse(
        text=explanation.text,
        model=explanation.model,
        provider=explanation.provider,
        generated_at=explanation.generated_at,
        age_group=explanation.age_group,
        maturation_status=explanation.maturation_status,
    )
