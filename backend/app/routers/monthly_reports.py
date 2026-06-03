"""Router: reportes mensuales de entrenamiento del club.

Incluye:
- CRUD MonthlyReport (POST crear/regenerar, GET lista, GET detalle, GET PDF)
- CRUD ClubProjectProfile (GET, PUT/PATCH perfil de proyecto del club)
- PATCH bloques de narrativa del Informe Técnico Mensual
- POST regenerar un bloque individual con IA
- GET parent monthly summary

PRIVACIDAD:
- Para padres (role=parent): narrative_blocks=None, competition_results=None,
  coach_observations=None, athlete_names={}.
- Los narrative_blocks contienen narrativa interna del coach; NUNCA se exponen
  fuera del club.
- Los competition_results contienen nombres de menores; solo coach/admin.
- El PDF del Informe Técnico es exclusivo de coach/admin del club.
"""

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
from app.models.club_project_profile import ClubProjectProfile
from app.models.training_session import MonthlyReport
from app.models.user import User, UserRole
from app.schemas.club_project_profile import (
    ClubProjectProfileCreate,
    ClubProjectProfileRead,
    ClubProjectProfileUpdate,
)
from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate
from app.schemas.training_session import (
    MonthlyReportBlocksUpdate,
    MonthlyReportCreate,
    MonthlyReportRead,
    ParentMonthlySummary,
)
from app.services.notification.service import NotificationService
from app.services.permissions import can_view_monthly_report, user_club_role
from app.services.training.reports import (
    _month_label,
    build_report_photo_evidence,
    generate_monthly_report,
    get_conjoint_sessions,
    parent_monthly_summary,
    regenerate_block,
    update_report_blocks,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# DI: use cases IA
# ---------------------------------------------------------------------------


def _get_monthly_report_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    from app.services.ai.use_cases.monthly_report import MonthlyReportUseCase
    return MonthlyReportUseCase(provider=provider, registry=registry)


def _get_monthly_report_blocks_use_case(
    provider=Depends(get_llm_provider),
    registry=Depends(get_prompt_registry),
):
    from app.services.ai.use_cases.monthly_report_blocks import MonthlyReportBlocksUseCase
    return MonthlyReportBlocksUseCase(provider=provider, registry=registry)


# ---------------------------------------------------------------------------
# Helper: construir MonthlyReportRead con filtros de privacidad
# ---------------------------------------------------------------------------


def _build_report_read(report: MonthlyReport, is_parent: bool) -> MonthlyReportRead:
    """Convierte ORM → schema aplicando filtros de privacidad por rol."""
    out = MonthlyReportRead.model_validate(report)
    if is_parent:
        # Padres NO reciben narrativa interna del coach ni nombres de otros menores
        out.coach_observations = None
        out.narrative_blocks = None
        out.competition_results = None
        out.athlete_names = {}
    return out


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
    blocks_use_case=Depends(_get_monthly_report_blocks_use_case),
) -> MonthlyReportRead:
    """Genera un reporte mensual (con bloques de narrativa IA y resultados de competencia).

    - Solo meses cerrados.
    - 409 si ya existe para ese período sin force_regenerate=true.
    - Genera ai_summary (resumen legacy) y narrative_blocks (6 bloques).
    - Los bloques que fallen en la IA se dejan con ai_draft=None (degradación limpia).
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
            blocks_use_case=blocks_use_case,
        )
    except MonthlyReportLLMTimeout as exc:
        logger.exception("Timeout LLM al generar reporte mensual: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA no está disponible. Intenta de nuevo en unos minutos.",
        )
    except Exception as exc:
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

    out = MonthlyReportRead.model_validate(report)
    # Coach/admin recibe nombres reales
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    out.athlete_names = {
        str(a.id): f"{a.first_name} {a.last_name}"
        for a in athletes_result.scalars().all()
    }
    return out


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
    """Lista reportes mensuales del club."""
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
    is_parent = current_user.role == UserRole.parent
    return [_build_report_read(r, is_parent) for r in reports]


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
    """Detalle de un reporte mensual.

    Padres reciben versión filtrada (sin narrative_blocks, competition_results,
    coach_observations, athlete_names).
    """
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

    is_parent = current_user.role == UserRole.parent
    out = _build_report_read(report, is_parent)

    if not is_parent:
        athletes_result = await db.execute(
            select(Athlete).where(Athlete.club_id == club_id)
        )
        out.athlete_names = {
            str(a.id): f"{a.first_name} {a.last_name}"
            for a in athletes_result.scalars().all()
        }

    return out


# ---------------------------------------------------------------------------
# PATCH /api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks
# ---------------------------------------------------------------------------


@router.patch(
    "/{club_id}/monthly-reports/{year}/{month}/blocks",
    response_model=MonthlyReportRead,
    tags=["monthly-reports"],
)
async def patch_report_blocks(
    club_id: int,
    year: int,
    month: int,
    body: MonthlyReportBlocksUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> MonthlyReportRead:
    """Actualiza final_text de los bloques indicados y/o aprueba el reporte.

    Solo acepta claves en ALLOWED_BLOCK_KEYS. Transición de estado:
    solo draft → approved (no reversión).
    """
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    try:
        report = await update_report_blocks(
            db=db,
            club_id=club_id,
            year=year,
            month=month,
            blocks=body.blocks,
            new_status=body.status,
            editor_user=current_user,
        )
    except ValueError as exc:
        msg = str(exc)
        if "No existe reporte" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    out = MonthlyReportRead.model_validate(report)
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    out.athlete_names = {
        str(a.id): f"{a.first_name} {a.last_name}"
        for a in athletes_result.scalars().all()
    }
    return out


# ---------------------------------------------------------------------------
# POST /api/clubs/{club_id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate
# ---------------------------------------------------------------------------


@router.post(
    "/{club_id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate",
    response_model=MonthlyReportRead,
    tags=["monthly-reports"],
)
async def regenerate_report_block(
    club_id: int,
    year: int,
    month: int,
    block_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    blocks_use_case=Depends(_get_monthly_report_blocks_use_case),
) -> MonthlyReportRead:
    """Regenera el ai_draft de un bloque individual con la IA.

    Preserva el final_text editado por el coach si ya difería del ai_draft previo.
    """
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    try:
        report = await regenerate_block(
            db=db,
            club_id=club_id,
            year=year,
            month=month,
            block_key=block_key,
            blocks_use_case=blocks_use_case,
        )
    except ValueError as exc:
        msg = str(exc)
        if "No existe reporte" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    out = MonthlyReportRead.model_validate(report)
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    out.athlete_names = {
        str(a.id): f"{a.first_name} {a.last_name}"
        for a in athletes_result.scalars().all()
    }
    return out


# ---------------------------------------------------------------------------
# GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/pdf (nuevo: técnico)
# ---------------------------------------------------------------------------


@router.get(
    "/{club_id}/monthly-reports/{year}/{month}/pdf",
    summary="Descargar el Informe Técnico Mensual en PDF",
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
    """Genera y retorna el Informe Técnico Mensual en PDF (coach/admin).

    Si el reporte tiene status=draft el PDF incluye un banner BORRADOR.
    Si status=approved el PDF está limpio. El PDF siempre se puede descargar
    independientemente del status (el coach puede necesitar una vista previa).
    """
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

    # Nombres reales de atletas
    athletes_result = await db.execute(
        select(Athlete).where(Athlete.club_id == club_id)
    )
    athlete_names = {
        str(a.id): f"{a.first_name} {a.last_name}"
        for a in athletes_result.scalars().all()
    }

    # Perfil de proyecto del club (puede no existir — degrada a dict vacío)
    project_profile: dict = {}
    try:
        pp_result = await db.execute(
            select(ClubProjectProfile).where(
                ClubProjectProfile.club_id == club_id
            )
        )
        project_profile_obj = pp_result.scalar_one_or_none()
        if project_profile_obj is not None:
            project_profile = dict(project_profile_obj.__dict__)
            project_profile.pop("_sa_instance_state", None)
    except Exception:  # noqa: BLE001
        project_profile = {}

    # Evidencia fotográfica
    photos = await build_report_photo_evidence(db, club_id, year, month)

    # Actividades conjuntas/salidas del mes
    conjoint_sessions = await get_conjoint_sessions(db, club_id, year, month)

    # narrative_blocks: para el PDF usamos el dict raw (con final_text).
    # No enviamos ai_draft al template — solo final_text.
    _raw_nb = report.narrative_blocks
    raw_nb: dict = _raw_nb if isinstance(_raw_nb, dict) else {}
    pdf_narrative_blocks: dict = {
        key: {"final_text": (block.get("final_text") or "") if isinstance(block, dict) else ""}
        for key, block in raw_nb.items()
    }

    # competition_results: lista raw del JSON
    _comp_raw = report.competition_results
    competition_results_raw: list = _comp_raw if isinstance(_comp_raw, list) else []

    from app.models.training_session import MonthlyReportStatus
    _status = report.status
    is_draft = not (isinstance(_status, MonthlyReportStatus) and _status == MonthlyReportStatus.APPROVED)

    doc_request = DocumentRequest(
        template=DocumentTemplate.TRAINING_MONTHLY_TECHNICAL_REPORT,
        format=DocumentFormat.PDF,
        context={
            "club_name": report.club.name,
            "month_label": _month_label(report.year, report.month),
            "season_year": str(report.year),
            "is_draft": is_draft,
            "project_profile": project_profile,
            "narrative_blocks": pdf_narrative_blocks,
            "metrics_snapshot": report.metrics_snapshot or {},
            "athlete_names": athlete_names,
            "competition_results": competition_results_raw,
            "conjoint_sessions": conjoint_sessions,
            "photos": photos,
        },
        filename_hint=f"informe_tecnico_{report.year}_{report.month:02d}",
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
# GET /api/clubs/{club_id}/project-profile
# ---------------------------------------------------------------------------


@router.get(
    "/{club_id}/project-profile",
    response_model=ClubProjectProfileRead,
    tags=["monthly-reports"],
)
async def get_project_profile(
    club_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ClubProjectProfileRead:
    """Obtiene el perfil de proyecto del club (para el Informe Técnico)."""
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    result = await db.execute(
        select(ClubProjectProfile).where(ClubProjectProfile.club_id == club_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El club {club_id} no tiene perfil de proyecto configurado.",
        )
    return ClubProjectProfileRead.model_validate(profile)


# ---------------------------------------------------------------------------
# PUT /api/clubs/{club_id}/project-profile (create-or-replace)
# ---------------------------------------------------------------------------


@router.put(
    "/{club_id}/project-profile",
    response_model=ClubProjectProfileRead,
    status_code=status.HTTP_200_OK,
    tags=["monthly-reports"],
)
async def upsert_project_profile(
    club_id: int,
    body: ClubProjectProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ClubProjectProfileRead:
    """Crea o reemplaza el perfil de proyecto del club (upsert completo)."""
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    result = await db.execute(
        select(ClubProjectProfile).where(ClubProjectProfile.club_id == club_id)
    )
    profile = result.scalar_one_or_none()

    data = body.model_dump()
    if profile is None:
        profile = ClubProjectProfile(club_id=club_id, **data)
        db.add(profile)
    else:
        for key, value in data.items():
            setattr(profile, key, value)

    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(profile)
    return ClubProjectProfileRead.model_validate(profile)


# ---------------------------------------------------------------------------
# PATCH /api/clubs/{club_id}/project-profile (update parcial)
# ---------------------------------------------------------------------------


@router.patch(
    "/{club_id}/project-profile",
    response_model=ClubProjectProfileRead,
    tags=["monthly-reports"],
)
async def patch_project_profile(
    club_id: int,
    body: ClubProjectProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
) -> ClubProjectProfileRead:
    """Actualización parcial del perfil de proyecto del club.

    Solo actualiza los campos presentes en el body (exclude_unset). Si no
    existe el perfil, lo crea con los campos provistos.
    """
    club_role = await user_club_role(db, current_user.id, club_id)
    if current_user.role != UserRole.admin and club_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este club.",
        )

    result = await db.execute(
        select(ClubProjectProfile).where(ClubProjectProfile.club_id == club_id)
    )
    profile = result.scalar_one_or_none()

    data = body.model_dump(exclude_unset=True)
    if profile is None:
        profile = ClubProjectProfile(club_id=club_id, **data)
        db.add(profile)
    else:
        for key, value in data.items():
            setattr(profile, key, value)

    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(profile)
    return ClubProjectProfileRead.model_validate(profile)


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
    """Resumen mensual de entrenamiento para el padre — solo sus atletas."""
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
