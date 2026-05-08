"""Service layer: generación y envío de reportes mensuales del club."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.club import Club, ClubMember, ClubRole
from app.models.training_session import MonthlyReport, TrainingSession
from app.models.user import User
from app.schemas.notification import (
    DocumentFormat,
    DocumentRequest,
    DocumentTemplate,
    NotificationRecipient,
    NotificationRequest,
    NotificationResult,
    NotificationTemplate,
)
from app.schemas.training_session import ParentMonthlySummary
from app.services.permissions import parent_athlete_ids
from app.services.training.metrics import compute_monthly_metrics

if TYPE_CHECKING:
    from app.services.notification.service import NotificationService
    from app.services.notification.task_dispatcher import TaskDispatcher

_MONTH_CLOSE_DAY = 28


def _validate_period(year: int, month: int) -> None:
    today = date.today()
    if year > today.year or (year == today.year and month >= today.month):
        raise ValueError(
            f"El período {year}-{month:02d} no está cerrado todavía. "
            "Solo se pueden generar reportes de meses anteriores."
        )
    if year == today.year and month == today.month - 1 and today.day < _MONTH_CLOSE_DAY:
        raise ValueError(
            f"El mes {year}-{month:02d} todavía no está cerrado (se requiere "
            f"que el día actual sea >= {_MONTH_CLOSE_DAY})."
        )


async def generate_monthly_report(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
    generator_user: User,
    coach_observations: str | None = None,
    force_regenerate: bool = False,
    ai_use_case=None,
) -> MonthlyReport:
    """Genera (o regenera) el reporte mensual de un club.

    Raises:
        ValueError: período no cerrado, mes futuro, o ya existe sin force_regenerate.
    """
    _validate_period(year, month)

    existing_result = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None and not force_regenerate:
        raise ValueError(
            f"Ya existe un reporte para {year}-{month:02d}. "
            "Usa force_regenerate=true para regenerarlo."
        )

    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if club is None:
        raise ValueError(f"Club {club_id} no encontrado.")

    metrics = await compute_monthly_metrics(db, club_id, year, month)

    ai_summary: str | None = None
    if ai_use_case is not None:
        from app.models.athlete import Athlete
        athletes_result = await db.execute(
            select(Athlete).where(Athlete.club_id == club_id)
        )
        real_names: set[str] = {
            f"{a.first_name} {a.last_name}" for a in athletes_result.scalars().all()
        }

        ctx = ai_use_case.build_context_from_metrics(
            club_name=club.name,
            year=year,
            month=month,
            metrics=metrics,
            coach_observations=coach_observations,
            real_names=real_names,
        )
        result = await ai_use_case.run(ctx)
        ai_summary = result.text

    metrics_dict = metrics.model_dump(mode="json")

    now = datetime.now(timezone.utc)

    if existing is not None and force_regenerate:
        existing.ai_summary = ai_summary
        existing.metrics_snapshot = metrics_dict
        existing.coach_observations = coach_observations
        existing.generated_by_user_id = generator_user.id
        existing.generated_at = now
        existing.sent_at = None
        await db.flush()
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return existing

    report = MonthlyReport(
        club_id=club_id,
        year=year,
        month=month,
        ai_summary=ai_summary,
        metrics_snapshot=metrics_dict,
        coach_observations=coach_observations,
        generated_by_user_id=generator_user.id,
        generated_at=now,
    )
    db.add(report)
    await db.flush()
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


async def send_monthly_report_email(
    db: AsyncSession,
    report_id: int,
    notification_service: NotificationService,
    dispatcher: TaskDispatcher,
) -> list[NotificationResult]:
    """Envía el reporte mensual por email a todos los admins del club.

    Actualiza `report.sent_at` al finalizar.
    Retorna lista de resultados de envío (uno por admin).
    """
    report_result = await db.execute(
        select(MonthlyReport)
        .options(selectinload(MonthlyReport.club))
        .where(MonthlyReport.id == report_id)
    )
    report = report_result.scalar_one_or_none()
    if report is None:
        raise ValueError(f"Reporte {report_id} no encontrado.")

    admins_result = await db.execute(
        select(User)
        .join(ClubMember, ClubMember.user_id == User.id)
        .where(
            ClubMember.club_id == report.club_id,
            ClubMember.role_in_club == ClubRole.admin,
        )
    )
    admins = admins_result.scalars().all()

    month_label = _month_label(report.year, report.month)

    results: list[NotificationResult] = []
    for admin in admins:
        doc_request = DocumentRequest(
            template=DocumentTemplate.TRAINING_MONTHLY_REPORT,
            format=DocumentFormat.PDF,
            context={
                "club_name": report.club.name,
                "month_label": month_label,
                "season_year": str(report.year),
                "ai_summary": report.ai_summary or "",
                "metrics_snapshot": report.metrics_snapshot or {},
                "coach_observations": report.coach_observations or "",
            },
            filename_hint=f"reporte_{report.year}_{report.month:02d}",
        )

        notif_request = NotificationRequest(
            recipient=NotificationRecipient(
                email=admin.email,
                name=admin.first_name,
            ),
            template=NotificationTemplate.TRAINING_MONTHLY_REPORT,
            context={
                "admin_name": admin.first_name,
                "club_name": report.club.name,
                "month_label": month_label,
                "season_year": str(report.year),
                "ai_summary_excerpt": (report.ai_summary or "")[:300],
            },
            attachments=[doc_request],
            send_async=True,
        )
        result = await notification_service.send(notif_request, dispatcher=dispatcher)
        results.append(result)

    report.sent_at = datetime.now(timezone.utc)
    await db.flush()
    return results


async def parent_monthly_summary(
    db: AsyncSession,
    parent_user_id: int,
    athlete_id: int,
    year: int,
    month: int,
) -> ParentMonthlySummary:
    """Retorna el resumen mensual de un atleta para su padre.

    Raises:
        PermissionError: si el atleta no pertenece al padre.
        ValueError: si no hay datos del atleta en ese mes.
    """
    ids = await parent_athlete_ids(db, parent_user_id)
    if athlete_id not in ids:
        raise PermissionError(
            "No tienes permiso para ver el resumen de este atleta."
        )

    from app.models.athlete import Athlete
    from app.models.training_session import SessionAttendance, SessionStatus

    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise ValueError(f"Atleta {athlete_id} no encontrado.")

    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = sessions_result.scalars().all()
    session_ids = [s.id for s in sessions]
    focos = list({s.technical_focus for s in sessions if s.technical_focus})

    count_present = 0
    count_total = len(session_ids)

    if session_ids:
        from app.models.training_session import AttendanceStatus
        att_result = await db.execute(
            select(SessionAttendance).where(
                SessionAttendance.session_id.in_(session_ids),
                SessionAttendance.athlete_id == athlete_id,
            )
        )
        attendances = att_result.scalars().all()
        count_present = sum(
            1 for a in attendances
            if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
        )

    pct = round(count_present / count_total * 100, 1) if count_total > 0 else 0.0

    return ParentMonthlySummary(
        athlete_id=athlete_id,
        athlete_name=f"{athlete.first_name} {athlete.last_name}",
        count_present=count_present,
        count_total=count_total,
        percentage=pct,
        focos_técnicos=focos,
    )


def _month_label(year: int, month: int) -> str:
    months_es = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{months_es[month - 1]} {year}"
