from collections.abc import AsyncGenerator, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere un access token",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: sin sujeto",
        )

    user_id = int(sub)
    result = await db.execute(
        select(User)
        .options(selectinload(User.club_memberships))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not user.can_login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    return user


def require_role(allowed_roles: list[UserRole]) -> Callable:
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta acción",
            )
        return current_user
    return _check


async def verify_athlete_access(
    athlete_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> "Athlete":
    """
    Dependencia de ownership: verifica que el usuario tiene acceso al atleta.
    - Admin: acceso total
    - Coach: solo atletas de sus clubes
    - Parent: solo sus atletas vinculados via parent_athlete
    """
    from app.models.athlete import Athlete, ParentAthlete
    from app.models.club import ClubMember, ClubRole

    # Cargar el atleta
    result = await db.execute(select(Athlete).where(Athlete.id == athlete_id))
    athlete = result.scalar_one_or_none()

    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atleta no encontrado",
        )

    if current_user.role == UserRole.admin:
        return athlete

    if current_user.role == UserRole.coach:
        coach_clubs = {
            m.club_id for m in current_user.club_memberships
            if m.role_in_club == ClubRole.coach
        }
        if athlete.club_id not in coach_clubs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )
        return athlete

    if current_user.role == UserRole.parent:
        # Verificar relación parent_athlete con un JOIN eficiente
        stmt = (
            select(Athlete)
            .join(ParentAthlete, ParentAthlete.athlete_id == Athlete.id)
            .where(
                ParentAthlete.parent_id == current_user.id,
                Athlete.id == athlete_id,
            )
        )
        result = await db.execute(stmt)
        linked_athlete = result.scalar_one_or_none()
        if not linked_athlete:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este atleta",
            )
        return athlete

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para esta acción",
    )


# ===========================================================================
# Paso 7 — Dependency Injection para el módulo de notificaciones
# ===========================================================================

from functools import lru_cache

from fastapi import BackgroundTasks


@lru_cache(maxsize=1)
def get_email_settings():
    """Retorna el objeto settings global (singleton vía lru_cache).

    Tip: en tests, sobrescribir con app.dependency_overrides[get_email_settings].
    """
    return settings


@lru_cache(maxsize=1)
def get_template_registry():
    """Retorna una instancia singleton de TemplateRegistry."""
    from app.services.notification.template_registry import TemplateRegistry
    return TemplateRegistry()


def get_document_generator(
    registry=Depends(get_template_registry),
    s=Depends(get_email_settings),
):
    """Construye DocumentGenerator con el registry y settings actuales."""
    from app.services.notification.document_generator import DocumentGenerator
    return DocumentGenerator(registry=registry, settings=s)


def get_notification_service(
    s=Depends(get_email_settings),
    registry=Depends(get_template_registry),
    generator=Depends(get_document_generator),
):
    """Construye NotificationService listo para inyectar en endpoints."""
    from app.services.notification import NotificationService, create_email_client
    email_client = create_email_client(s)
    return NotificationService(
        email_client=email_client,
        registry=registry,
        document_generator=generator,
        settings=s,
    )


def get_task_dispatcher(background_tasks: BackgroundTasks) -> "TaskDispatcher":
    """Construye TaskDispatcher con las BackgroundTasks del request actual."""
    from app.services.notification.task_dispatcher import TaskDispatcher
    return TaskDispatcher(background_tasks)


# ===========================================================================
# Capa de IA — providers, prompts y use cases
# ===========================================================================


@lru_cache(maxsize=1)
def get_llm_provider():
    """Singleton del proveedor LLM elegido vía `AI_PROVIDER`.

    En tests sobrescribir con `app.dependency_overrides[get_llm_provider]`
    apuntando a una instancia de `FakeLLMProvider`.
    """
    from app.services.ai.factory import create_llm_provider
    return create_llm_provider(settings)


@lru_cache(maxsize=1)
def get_prompt_registry():
    """Singleton del PromptRegistry."""
    from app.services.ai.prompts.registry import PromptRegistry
    return PromptRegistry()


def get_phv_explainer_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    """Construye el use case con sus colaboradores."""
    from app.services.ai.context_builders import AthleteAIContextBuilder
    from app.services.ai.use_cases.phv_explainer import PHVExplainerUseCase

    return PHVExplainerUseCase(
        provider=provider,
        registry=registry,
        context_builder=AthleteAIContextBuilder(),
    )


def get_anthropometric_record_explainer_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    """Construye el use case de análisis particular por medición."""
    from app.services.ai.context_builders import AthleteAIContextBuilder
    from app.services.ai.use_cases.anthropometric_record_explainer import (
        AnthropometricRecordExplainerUseCase,
    )

    return AnthropometricRecordExplainerUseCase(
        provider=provider,
        registry=registry,
        context_builder=AthleteAIContextBuilder(),
    )


def get_session_clarify_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    """Construye el use case para generar preguntas de clarificación de sesión (feature 006)."""
    from app.services.ai.use_cases.session_assistant import SessionClarifyUseCase

    return SessionClarifyUseCase(provider=provider, registry=registry)


def get_session_draft_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    """Construye el use case para generar borrador de sesión (feature 006)."""
    from app.services.ai.use_cases.session_assistant import SessionDraftUseCase

    return SessionDraftUseCase(provider=provider, registry=registry)


def get_anxiety_interpretation_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    """Construye el use case de interpretación de ansiedad competitiva (feature 017)."""
    from app.services.ai.use_cases.anxiety_interpretation import (
        AnxietyInterpretationUseCase,
    )

    return AnxietyInterpretationUseCase(provider=provider, registry=registry)

