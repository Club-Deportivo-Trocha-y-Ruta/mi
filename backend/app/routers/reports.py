"""
Router de reportes y documentos — endpoints de descarga y envío por email.

Paso 10 del workflow-notifications.

Endpoints:
  GET  /athletes/{id}/report/pdf       — Descarga reporte antropométrico PDF
  GET  /athletes/{id}/clearance/docx   — Descarga autorización médica DOCX
  POST /athletes/{id}/report/email     — Envía informe mensual al padre por email
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_notification_service,
    get_task_dispatcher,
    require_role,
    verify_athlete_access,
)
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, ParentAthlete
from app.models.club import Club
from app.models.user import User, UserRole
from app.schemas.notification import (
    DocumentFormat,
    DocumentRequest,
    DocumentTemplate,
    NotificationRecipient,
    NotificationRequest,
    NotificationTemplate,
)
from app.services.notification.service import NotificationService
from app.services.notification.task_dispatcher import TaskDispatcher

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: cargar última medición del atleta o 404
# ---------------------------------------------------------------------------

async def _get_latest_record(
    athlete: Athlete, db: AsyncSession
) -> AnthropometricRecord:
    result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete.id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El atleta no tiene mediciones registradas aún.",
        )
    return record


async def _get_club(athlete: Athlete, db: AsyncSession) -> Club:
    result = await db.execute(select(Club).where(Club.id == athlete.club_id))
    return result.scalar_one()


# ---------------------------------------------------------------------------
# GET /athletes/{athlete_id}/report/pdf
# ---------------------------------------------------------------------------

@router.get(
    "/{athlete_id}/report/pdf",
    summary="Descargar reporte antropométrico en PDF",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "Archivo PDF"},
        403: {"description": "Sin acceso al atleta"},
        404: {"description": "Atleta o medición no encontrada"},
    },
)
async def download_anthropometry_pdf(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Response:
    """Genera y retorna el reporte antropométrico del atleta en formato PDF."""
    record = await _get_latest_record(athlete, db)
    club = await _get_club(athlete, db)

    # Calcular edad en años completos — no exponer DOB en el PDF (datos sensibles menores)
    from datetime import date as _date
    today = _date.today()
    age_years = (
        today.year - athlete.birth_date.year
        - ((today.month, today.day) < (athlete.birth_date.month, athlete.birth_date.day))
    )

    doc_request = DocumentRequest(
        template=DocumentTemplate.ANTHROPOMETRY_REPORT,
        format=DocumentFormat.PDF,
        filename_hint=athlete.last_name,
        context={
            "athlete_first_name": athlete.first_name,
            "athlete_last_name": athlete.last_name,
            "age_years": age_years,
            "sex": athlete.sex.value,
            "club_name": club.name,
            "evaluation_date": record.evaluation_date.isoformat(),
            "weight_kg": float(record.weight_kg),
            "standing_height_cm": float(record.standing_height_cm),
            "sitting_height_cm": float(record.sitting_height_cm),
            "maturation_status": record.maturation_status.value
            if hasattr(record.maturation_status, "value")
            else str(record.maturation_status),
            "maturity_offset": float(record.maturity_offset),
            "age_at_phv": float(record.age_at_phv),
            "training_implications": record.training_implications,
            "notes": record.notes,
            "arm_span_cm": float(record.arm_span_cm) if record.arm_span_cm else None,
        },
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
# GET /athletes/{athlete_id}/clearance/docx
# ---------------------------------------------------------------------------

@router.get(
    "/{athlete_id}/clearance/docx",
    summary="Descargar autorización médica en DOCX",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
            "description": "Archivo DOCX editable",
        },
        403: {"description": "Sin acceso al atleta"},
        404: {"description": "Atleta no encontrado"},
    },
)
async def download_medical_clearance_docx(
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
) -> Response:
    """Genera y retorna la autorización médica del atleta en formato DOCX editable."""
    club = await _get_club(athlete, db)

    from datetime import date
    season_year = date.today().year

    doc_request = DocumentRequest(
        template=DocumentTemplate.MEDICAL_CLEARANCE,
        format=DocumentFormat.DOCX,
        filename_hint=athlete.last_name,
        context={
            "athlete_first_name": athlete.first_name,
            "athlete_last_name": athlete.last_name,
            "birth_date": athlete.birth_date.isoformat(),
            "club_name": club.name,
            "season_year": season_year,
            "medical_conditions": [],  # Padre completa en el documento editable
        },
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
# POST /athletes/{athlete_id}/report/email
# ---------------------------------------------------------------------------

@router.post(
    "/{athlete_id}/report/email",
    summary="Enviar informe mensual por email al padre",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Email encolado exitosamente"},
        403: {"description": "Sin permisos"},
        404: {"description": "Atleta no encontrado o sin padre con email"},
    },
)
async def send_monthly_report_email(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    athlete: Athlete = Depends(verify_athlete_access),
    current_user: User = Depends(require_role([UserRole.admin, UserRole.coach])),
    notification_service: NotificationService = Depends(get_notification_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> dict:
    """Envía el informe mensual de progreso al padre/acudiente del atleta por email.

    Retorna inmediatamente con {"queued": true} — el envío ocurre en background.
    """
    # Obtener padre con email
    result = await db.execute(
        select(ParentAthlete)
        .where(ParentAthlete.athlete_id == athlete.id)
    )
    parent_links = result.scalars().all()

    # Buscar el primer padre con email registrado
    parent_user = None
    for link in parent_links:
        u_result = await db.execute(select(User).where(User.id == link.parent_id))
        u = u_result.scalar_one_or_none()
        if u and u.email:
            parent_user = u
            break

    if parent_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El atleta no tiene padre/acudiente con email registrado.",
        )

    club = await _get_club(athlete, db)
    from datetime import date
    now = date.today()
    month_label = now.strftime("%B %Y")
    season_year = now.year

    notification_request = NotificationRequest(
        recipient=NotificationRecipient(
            email=parent_user.email,
            name=f"{parent_user.first_name} {parent_user.last_name}",
        ),
        template=NotificationTemplate.MONTHLY_REPORT,
        send_async=True,
        context={
            "athlete_first_name": athlete.first_name,
            "parent_name": f"{parent_user.first_name} {parent_user.last_name}",
            "club_name": club.name,
            "month_label": month_label,
            "season_year": season_year,
            "measurements": [],  # Se puede ampliar con datos reales en iteraciones futuras
        },
        attachments=[
            DocumentRequest(
                template=DocumentTemplate.MONTHLY_PROGRESS,
                format=DocumentFormat.PDF,
                filename_hint=athlete.last_name,
                context={
                    "athlete_first_name": athlete.first_name,
                    "athlete_last_name": athlete.last_name,
                    "club_name": club.name,
                    "month_label": month_label,
                    "season_year": season_year,
                    "measurements": [],
                },
            )
        ],
    )

    await notification_service.send(notification_request, dispatcher=dispatcher)

    return {"queued": True, "template": NotificationTemplate.MONTHLY_REPORT}
