"""Cálculo de métricas agregadas mensuales del club."""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.schemas.training_session import AthleteAttendanceStats, MonthlyMetrics

_PRESENT_STATUSES = {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}


async def compute_monthly_metrics(
    db: AsyncSession,
    club_id: int,
    year: int,
    month: int,
) -> MonthlyMetrics:
    """
    Calcula métricas agregadas del club para un mes dado.

    Las medias de RPE y rúbrica solo consideran asistencias con
    status PRESENTE o TARDE (invariante de privacidad: datos individuales
    no se exponen en el agregado; solo promedios numéricos).
    """
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
        )
    )
    sessions = list(sessions_result.scalars().all())

    session_ids = [s.id for s in sessions]
    total_planned = sum(1 for s in sessions if s.status == SessionStatus.PLANNED)
    total_executed = sum(1 for s in sessions if s.status == SessionStatus.EXECUTED)
    total_cancelled = sum(1 for s in sessions if s.status == SessionStatus.CANCELLED)
    technical_focus_list = list(
        {s.technical_focus for s in sessions if s.technical_focus}
    )

    # SPEC 1 — Volumen de entrenamiento (minutos). Planificado = sesiones que se
    # iban a hacer (no canceladas); ejecutado = solo las realmente ejecutadas.
    total_minutes_planned = sum(
        s.duration_min
        for s in sessions
        if s.status in (SessionStatus.PLANNED, SessionStatus.EXECUTED)
    )
    total_minutes_executed = sum(
        s.duration_min for s in sessions if s.status == SessionStatus.EXECUTED
    )
    weeks_in_month = last_day / 7
    avg_hours_per_week = (
        round(total_minutes_executed / 60 / weeks_in_month, 1)
        if total_minutes_executed > 0
        else None
    )

    # SPEC 1 — Frecuencia de cada foco técnico (nº de sesiones que lo trabajaron).
    technical_focus_counts = dict(
        Counter(s.technical_focus for s in sessions if s.technical_focus)
    )

    if not session_ids:
        return MonthlyMetrics(
            club_id=club_id,
            year=year,
            month=month,
            total_sessions_planned=0,
            total_sessions_executed=0,
            total_sessions_cancelled=0,
            attendance_by_athlete={},
            technical_focus_list=[],
            avg_rpe=None,
            avg_rubric_effort=None,
            avg_rubric_attitude=None,
            avg_rubric_technique=None,
        )

    attendance_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids)
        )
    )
    all_attendance = list(attendance_result.scalars().all())

    # SPEC 1 — Conteos de asistencia a nivel club por estado.
    attendance_status_totals = {
        "presente": sum(1 for a in all_attendance if a.status == AttendanceStatus.PRESENTE),
        "tarde": sum(1 for a in all_attendance if a.status == AttendanceStatus.TARDE),
        "justificado": sum(1 for a in all_attendance if a.status == AttendanceStatus.JUSTIFICADO),
        "ausente": sum(1 for a in all_attendance if a.status == AttendanceStatus.AUSENTE),
        "lesionado": sum(1 for a in all_attendance if a.status == AttendanceStatus.LESIONADO),
    }

    # Estadísticas por atleta
    athlete_stats: dict[int, dict] = {}
    for att in all_attendance:
        if att.athlete_id not in athlete_stats:
            athlete_stats[att.athlete_id] = {
                "present": 0,
                "absent": 0,
                "justified": 0,
                "late": 0,
                "injured": 0,
                "total": 0,
            }
        stats = athlete_stats[att.athlete_id]
        stats["total"] += 1
        if att.status == AttendanceStatus.PRESENTE:
            stats["present"] += 1
        elif att.status == AttendanceStatus.AUSENTE:
            stats["absent"] += 1
        elif att.status == AttendanceStatus.JUSTIFICADO:
            stats["justified"] += 1
        elif att.status == AttendanceStatus.TARDE:
            stats["late"] += 1
        elif att.status == AttendanceStatus.LESIONADO:
            stats["injured"] += 1

    attendance_by_athlete = {
        athlete_id: AthleteAttendanceStats(
            athlete_id=athlete_id,
            count_present=s["present"],
            count_absent=s["absent"],
            count_justified=s["justified"],
            count_late=s["late"],
            count_injured=s["injured"],
            total_sessions=s["total"],
            attendance_pct=(
                round((s["present"] + s["late"]) / s["total"] * 100, 1)
                if s["total"] > 0
                else 0.0
            ),
        )
        for athlete_id, s in athlete_stats.items()
    }

    # Promedios de RPE y rúbrica — solo asistencias presentes/tarde
    present_att = [a for a in all_attendance if a.status in _PRESENT_STATUSES]

    def _avg(values: list[int | None]) -> float | None:
        nums = [v for v in values if v is not None]
        return round(sum(nums) / len(nums), 2) if nums else None

    avg_rpe = _avg([a.rpe_omni for a in present_att])
    avg_rubric_effort = _avg([a.rubric_effort for a in present_att])
    avg_rubric_attitude = _avg([a.rubric_attitude for a in present_att])
    avg_rubric_technique = _avg([a.rubric_technique for a in present_att])

    return MonthlyMetrics(
        club_id=club_id,
        year=year,
        month=month,
        total_sessions_planned=total_planned,
        total_sessions_executed=total_executed,
        total_sessions_cancelled=total_cancelled,
        attendance_by_athlete=attendance_by_athlete,
        technical_focus_list=technical_focus_list,
        avg_rpe=avg_rpe,
        avg_rubric_effort=avg_rubric_effort,
        avg_rubric_attitude=avg_rubric_attitude,
        avg_rubric_technique=avg_rubric_technique,
        total_minutes_planned=total_minutes_planned,
        total_minutes_executed=total_minutes_executed,
        avg_hours_per_week=avg_hours_per_week,
        technical_focus_counts=technical_focus_counts,
        attendance_status_totals=attendance_status_totals,
    )
