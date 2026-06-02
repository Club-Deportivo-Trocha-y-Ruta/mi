"""Router: reportes mensuales de entrenamiento del club."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.dependencies import (
    get_current_user,
    get_db,
    get_llm_provider,
    get_notification_service,
    get_prompt_registry,
    require_role,
)
from app.models.athlete import Athlete
from app.models.training_session import MonthlyReport
from app.models.user import User, UserRole
from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate
from app.schemas.training_session import MonthlyReportCreate, MonthlyReportRead, ParentMonthlySummary
from app.services.notification.service import NotificationService
from app.services.permissions import can_view_monthly_report, user_club_role
from app.services.training.reports import (
    _month_label,
    build_report_photo_evidence,
    generate_monthly_report,
    parent_monthly_summary,
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
    else:
        # Solo coach/admin reciben los nombres reales de atletas (para la tabla
        # de asistencia del UI). Nunca a padres: verían nombres de otros menores.
        athletes_result = await db.execute(
            select(Athlete).where(Athlete.club_id == club_id)
        )
        out.athlete_names = {
            str(a.id): f"{a.first_name} {a.last_name}"
            for a in athletes_result.scalars().all()
        }

    return out


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/pdf
# ---------------------------------------------------------------------------


@router.get(
    "/{club_id}/monthly-reports/{year}/{month}/pdf",
    summary="Descargar el reporte mensual del club en PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF"},
        403: {"description": "Sin acceso al club"},
        404: {"description": "Reporte no encontrado"},
    },
    tags=["monthly-reports"],
)
async def download_monthly_report_pdf(
    club_id: int,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Response:
    """Genera y retorna el reporte mensual del club en PDF (coach/admin)."""
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    result = await db.execute(
        select(MonthlyReport)
        .options(selectinload(MonthlyReport.club))
        .where(
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

    # Nombres reales de atletas del club, resueltos al renderizar (no se persisten
    # en el snapshot). Claves str para coincidir con las del metrics_snapshot JSON.
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    athlete_names = {
        str(a.id): f"{a.first_name} {a.last_name}"
        for a in athletes_result.scalars().all()
    }

    # Evidencia fotográfica del mes (thumbnails consentidos embebidos en base64).
    # El helper degrada limpio: si no hay storage/fotos, retorna [].
    photos = await build_report_photo_evidence(db, club_id, year, month)

    doc_request = DocumentRequest(
        template=DocumentTemplate.TRAINING_MONTHLY_REPORT,
        format=DocumentFormat.PDF,
        context={
            "club_name": report.club.name,
            "month_label": _month_label(report.year, report.month),
            "season_year": str(report.year),
            "ai_summary": report.ai_summary or "",
            "metrics_snapshot": report.metrics_snapshot or {},
            "coach_observations": report.coach_observations or "",
            "athlete_names": athlete_names,
            "photos": photos,
        },
        filename_hint=f"reporte_{report.year}_{report.month:02d}",
    )

    generated = await notification_service.generate_document_only(doc_request)

    return Response(
        content=generated.data,
        media_type=generated.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{generated.filename}"',
            "Content-Length": str(len(generated.data)),
        },
    )


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
