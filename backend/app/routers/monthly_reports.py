"""Router: reportes mensuales de entrenamiento del club."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.dependencies import (
    get_current_user,
    get_db,
    get_llm_provider,
    get_notification_service,
    get_prompt_registry,
    get_task_dispatcher,
    require_role,
)
from app.models.training_session import MonthlyReport
from app.models.user import User, UserRole
from app.schemas.training_session import MonthlyReportCreate, MonthlyReportRead, ParentMonthlySummary
from app.services.notification.service import NotificationService
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.permissions import can_view_monthly_report, user_club_role
from app.services.training.reports import (
    generate_monthly_report,
    parent_monthly_summary,
    send_monthly_report_email,
)

router = APIRouter()


def _get_monthly_report_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    from app.services.ai.use_cases.monthly_report import MonthlyReportUseCase
    return MonthlyReportUseCase(provider=provider, registry=registry)


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/monthly-reports
# ---------------------------------------------------------------------------


@router.post(
    "/{club_id}/monthly-reports",
    response_model=MonthlyReportRead,
    status_code=status.HTTP_201_CREATED,
    tags=["monthly-reports"],
)
async def create_monthly_report(
    club_id: int,
    body: MonthlyReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    ai_use_case=Depends(_get_monthly_report_use_case),
) -> MonthlyReportRead:
    """Genera un reporte mensual de entrenamiento para el club.

    - Solo meses cerrados (no futuro, no mes actual antes del día 28).
    - 409 si ya existe para ese período (usar force_regenerate=true para sobreescribir).
    - La narrativa IA se genera y almacena en ai_summary.
    """
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    from app.services.ai.use_cases.monthly_report import MonthlyReportLLMTimeout

    try:
        report = await generate_monthly_report(
            db=db,
            club_id=club_id,
            year=body.year,
            month=body.month,
            generator_user=current_user,
            coach_observations=body.coach_observations,
            force_regenerate=body.force_regenerate,
            ai_use_case=ai_use_case,
        )
    except MonthlyReportLLMTimeout as exc:
        logger.exception("Timeout en proveedor LLM al generar reporte mensual: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA no está disponible. Intenta de nuevo en unos minutos.",
        )
    except Exception as exc:
        # Captura errores de proveedor LLM (httpx, Anthropic SDK, etc.)
        exc_module = type(exc).__module__ or ""
        if any(
            mod in exc_module
            for mod in ("httpx", "anthropic", "openai")
        ) or "API" in type(exc).__name__:
            logger.exception("Error de proveedor LLM al generar reporte mensual: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El servicio de IA no está disponible. Intenta de nuevo en unos minutos.",
            )
        if isinstance(exc, ValueError):
            msg = str(exc)
            if "Ya existe" in msg:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        raise

    return MonthlyReportRead.model_validate(report)


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/monthly-reports
# ---------------------------------------------------------------------------


@router.get(
    "/{club_id}/monthly-reports",
    response_model=list[MonthlyReportRead],
    tags=["monthly-reports"],
)
async def list_monthly_reports(
    club_id: int,
    limit: int = Query(default=12, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MonthlyReportRead]:
    """Lista reportes mensuales del club (admins y coaches del mismo club)."""
    allowed = await can_view_monthly_report(db, current_user, club_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver los reportes de este club.",
        )

    result = await db.execute(
        select(MonthlyReport)
        .where(MonthlyReport.club_id == club_id)
        .order_by(MonthlyReport.year.desc(), MonthlyReport.month.desc())
        .limit(limit)
        .offset(offset)
    )
    reports = result.scalars().all()
    return [MonthlyReportRead.model_validate(r) for r in reports]


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/monthly-reports/{year}/{month}
# ---------------------------------------------------------------------------


@router.get(
    "/{club_id}/monthly-reports/{year}/{month}",
    response_model=MonthlyReportRead,
    tags=["monthly-reports"],
)
async def get_monthly_report(
    club_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonthlyReportRead:
    """Detalle de un reporte mensual (admins, coaches; padres ven versión agregada sin feedback individual)."""
    allowed = await can_view_monthly_report(db, current_user, club_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver este reporte.",
        )

    result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe reporte para {year}-{month:02d} en el club {club_id}.",
        )

    out = MonthlyReportRead.model_validate(report)

    # Padres ven el reporte agregado pero sin observaciones individuales del coach
    if current_user.role == UserRole.parent:
        out.coach_observations = None

    return out


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/monthly-reports/{year}/{month}/send
# ---------------------------------------------------------------------------


@router.post(
    "/{club_id}/monthly-reports/{year}/{month}/send",
    status_code=status.HTTP_200_OK,
    tags=["monthly-reports"],
)
async def send_monthly_report(
    club_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> dict:
    """Envía el reporte mensual por email a todos los admins del club."""
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe reporte para {year}-{month:02d} en el club {club_id}.",
        )

    try:
        results = await send_monthly_report_email(
            db=db,
            report_id=report.id,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    successes = sum(1 for r in results if r.success)
    return {
        "enviados": successes,
        "total_admins": len(results),
        "sent_at": report.sent_at.isoformat() if report.sent_at else None,
    }


# ---------------------------------------------------------------------------
# GET /api/parents/training/monthly-summary/{year}/{month}
# ---------------------------------------------------------------------------


parent_router = APIRouter()


@parent_router.get(
    "/training/monthly-summary/{year}/{month}",
    response_model=list[ParentMonthlySummary],
    tags=["monthly-reports"],
)
async def get_parent_monthly_summary(
    year: int,
    month: int,
    athlete_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.parent])),
) -> list[ParentMonthlySummary]:
    """Resumen mensual de entrenamiento para el padre — solo sus atletas.

    Si se provee athlete_id, retorna solo el resumen de ese atleta.
    Sin athlete_id, retorna uno por cada atleta vinculado.
    """
    from app.services.permissions import parent_athlete_ids as get_athlete_ids

    ids = await get_athlete_ids(db, current_user.id)
    if not ids:
        return []

    target_ids = [athlete_id] if athlete_id is not None else ids

    summaries: list[ParentMonthlySummary] = []
    for aid in target_ids:
        try:
            summary = await parent_monthly_summary(
                db=db,
                parent_user_id=current_user.id,
                athlete_id=aid,
                year=year,
                month=month,
            )
            summaries.append(summary)
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            )

    return summaries
