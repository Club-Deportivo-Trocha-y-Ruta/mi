"""Router: Asistente IA para planificación de sesiones (feature 006).

Dos endpoints estáticos bajo /api/clubs/{club_id}/session-assistant:
  POST /clarify  → genera 0–4 preguntas de clarificación
  POST /draft    → genera un borrador editable de sesión

RBAC: solo coach o admin con acceso al club (espeja monthly_reports.py).
PRIVACIDAD:
  - selected_athlete_ids llega al backend únicamente para calcular age_mix
    agregado; se descarta antes de construir el prompt.
  - Ningún ID ni nombre de atleta llega al LLM.
  - ai_log_prompts=false (obligatorio en producción).

Manejo de errores (D8 de research.md):
  - AI disabled (ai_enabled=false o FakeLLMProvider) → HTTP 503 neutral
  - Timeout asyncio → HTTP 503 neutral
  - LLMSchemaError / JSON inválido → HTTP 422 neutral
  - Sin acceso al club → HTTP 403
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_db,
    get_session_clarify_use_case,
    get_session_draft_use_case,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.session_assistant import (
    SessionClarifyRequest,
    SessionClarifyResponse,
    SessionDraftRequest,
    SessionDraftResponse,
)
from app.services.ai.errors import LLMSchemaError
from app.services.ai.use_cases.session_assistant import SessionAssistantLLMTimeout
from app.services.permissions import user_club_role
from app.services.training.session_assistant_context import (
    build_aggregate_context,
    load_club_athlete_name_tokens,
    redact_names,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Mensaje neutro para errores 503 (D8 research.md)
_MSG_503 = "El asistente no está disponible en este momento."
# Mensaje neutro para errores 422 de IA
_MSG_422_AI = "El asistente no pudo generar una respuesta válida. Intenta de nuevo."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_ai_available() -> None:
    """Levanta HTTP 503 si AI está deshabilitado (``settings.ai_enabled=false``).

    Cuando ai_enabled=False la factoría ya devuelve FakeLLMProvider, pero esta
    verificación explícita garantiza un 503 limpio antes de construir el contexto
    o llamar al LLM. En tests con dependency_overrides y ai_enabled=True la función
    es un no-op, lo que permite usar FakeLLMProvider de forma determinista.
    """
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_MSG_503,
        )


async def _check_club_access(
    db: AsyncSession,
    current_user: User,
    club_id: int,
) -> None:
    """Verifica que el usuario tiene acceso al club.

    Admin siempre tiene acceso. Coach solo si es miembro del club.
    Espeja el guard de monthly_reports.py.
    """
    if current_user.role == UserRole.admin:
        return
    club_role = await user_club_role(db, current_user.id, club_id)
    if club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/session-assistant/clarify
# ---------------------------------------------------------------------------


@router.post(
    "/{club_id}/session-assistant/clarify",
    response_model=SessionClarifyResponse,
    status_code=status.HTTP_200_OK,
    tags=["session-assistant"],
    summary="Genera preguntas de clarificación para planificar una sesión",
)
async def clarify_session(
    club_id: int,
    body: SessionClarifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    clarify_use_case=Depends(get_session_clarify_use_case),
) -> SessionClarifyResponse:
    """Retorna 0–4 preguntas de clarificación para el asistente de sesiones.

    - ``questions: []`` significa que el coach puede llamar directamente a /draft.
    - ``selected_athlete_ids`` se usa solo para calcular age_mix; nunca llega al LLM.

    **Latencia**: llamada IA — hasta ``ai_timeout_seconds`` segundos (~30 s).
    """
    _check_ai_available()
    await _check_club_access(db, current_user, club_id)

    # Construir contexto agregado (privacy: IDs descartados aquí)
    context = await build_aggregate_context(
        db=db,
        club_id=club_id,
        selected_athlete_ids=body.selected_athlete_ids,
    )
    # Redactar nombres de atletas del texto libre del coach antes de enviarlo al
    # LLM (defensa en profundidad — el coach podría escribir el nombre de un menor).
    name_tokens = await load_club_athlete_name_tokens(db, club_id)
    context["intent_text"] = redact_names(body.intent_text, name_tokens)

    try:
        result = await clarify_use_case.run(
            context,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    except SessionAssistantLLMTimeout:
        logger.warning("session_assistant.clarify timeout club_id=%d", club_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_MSG_503,
        )
    except LLMSchemaError as exc:
        # No se loguea str(exc): puede contener fragmentos crudos de la salida del
        # LLM. Solo el tipo de excepción (privacidad Ley 1581).
        logger.warning(
            "session_assistant.clarify schema_error club_id=%d exc_type=%s",
            club_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_MSG_422_AI,
        )

    return SessionClarifyResponse.model_validate(result)


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/session-assistant/draft
# ---------------------------------------------------------------------------


@router.post(
    "/{club_id}/session-assistant/draft",
    response_model=SessionDraftResponse,
    status_code=status.HTTP_200_OK,
    tags=["session-assistant"],
    summary="Genera un borrador editable de sesión de entrenamiento",
)
async def draft_session(
    club_id: int,
    body: SessionDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    draft_use_case=Depends(get_session_draft_use_case),
) -> SessionDraftResponse:
    """Retorna un borrador editable de sesión XCO.

    El borrador mapea campo a campo con ``TrainingSessionCreate``.
    ``athlete_call_up`` es un criterio no identificante — el frontend
    lo resuelve a ``convocados_athlete_ids`` contra el roster local.

    Acepta respuestas parciales o vacías (FR-015).

    **Nota privacidad**: ningún ID ni nombre de atleta llega al LLM.
    **Latencia**: llamada IA — hasta ``ai_timeout_seconds`` segundos (~30 s).
    """
    _check_ai_available()
    await _check_club_access(db, current_user, club_id)

    # Construir contexto agregado (privacy: IDs descartados aquí)
    context = await build_aggregate_context(
        db=db,
        club_id=club_id,
        selected_athlete_ids=body.selected_athlete_ids,
    )
    # Redactar nombres del texto libre del coach (intent_text + other_text de cada
    # respuesta) antes de enviarlo al LLM (defensa en profundidad).
    name_tokens = await load_club_athlete_name_tokens(db, club_id)
    context["intent_text"] = redact_names(body.intent_text, name_tokens)

    # Serializar las respuestas para el template (other_text redactado)
    context["answers"] = [
        {
            "question_id": ans.question_id,
            "selected_labels": ans.selected_labels,
            "other_text": redact_names(ans.other_text, name_tokens),
        }
        for ans in body.answers
    ]

    try:
        result = await draft_use_case.run(
            context,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    except SessionAssistantLLMTimeout:
        logger.warning("session_assistant.draft timeout club_id=%d", club_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_MSG_503,
        )
    except LLMSchemaError as exc:
        # No se loguea str(exc): puede contener fragmentos crudos de la salida del
        # LLM. Solo el tipo de excepción (privacidad Ley 1581).
        logger.warning(
            "session_assistant.draft schema_error club_id=%d exc_type=%s",
            club_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_MSG_422_AI,
        )

    return SessionDraftResponse.model_validate(result)
