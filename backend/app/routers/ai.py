"""Endpoints `/api/ai/*` — capa de IA.

Convenciones:
  - Padres NO llaman directamente a estos endpoints. Reciben outputs vía
    `NotificationService` cuando el coach lo solicita. Bloqueado a nivel
    de router con un guard explícito (defense in depth).
  - Si la capa está apagada (`AI_ENABLED=false`) los endpoints que generan
    devuelven **503**. Los endpoints de lectura de caché siguen sirviendo
    contenido previamente generado: el coach debe poder ver lo que se
    generó ayer aunque hoy el LLM esté caído.
  - Errores de la capa se mapean: `LLMTimeoutError`/`LLMUnavailableError`
    → 503; `LLMSchemaError` → 502; `LLMConfigError` → 500.
  - Caché: `(athlete_id, latest_anthropometric_record_id, use_case)`. Una
    medición nueva cambia el `record_id` y por tanto invalida el caché
    implícitamente sin DELETE explícito.
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

_PHV_USE_CASE = "phv_explainer"


def _forbid_parents(current_user: User) -> None:
    """Defense in depth — los padres no consumen estos endpoints directamente."""
    if current_user.role == UserRole.parent:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Los padres no pueden consultar la explicación directamente.",
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


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    _admin=Depends(require_role([UserRole.admin])),
) -> AIHealthResponse:
    return AIHealthResponse(
        enabled=settings.ai_enabled,
        provider=settings.ai_provider,
        model=settings.ai_model,
    )


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
    current_user: User = Depends(get_current_user),
) -> Response:
    """Devuelve la explicación cacheada para la última medición del atleta.

    Importante: este endpoint NO chequea `ai_enabled`. La idea es que las
    explicaciones generadas previamente sigan disponibles aunque el LLM
    esté caído ahora.
    """
    _forbid_parents(current_user)

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

    # MySQL DATETIME no almacena tzinfo. Reaplicamos UTC antes de serializar
    # para que el frontend reciba "2026-05-05T20:10:00Z" y lo convierta a la
    # zona horaria local del navegador correctamente.
    generated_at = cached.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    payload = PHVExplanationResponse(
        text=cached.text,
        model=cached.model,
        provider=cached.provider,
        generated_at=generated_at,
        age_group=cached.age_group,
        maturation_status=cached.maturation_status,
    )
    # FastAPI no serializa Pydantic con `Response` directo. Devolvemos
    # el modelo y dejamos que FastAPI lo encode con status 200 implícito
    # cuando no es 204.
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

    # Upsert idempotente — el último escritor gana. Race condition entre
    # coaches del mismo club regenerando a la vez se resuelve a nivel DB.
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
