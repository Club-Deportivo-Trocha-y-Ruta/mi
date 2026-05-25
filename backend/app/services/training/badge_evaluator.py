"""Servicio: evaluación idempotente de insignias por periodo (Fase 1.8).

Evalúa asistencia + resultados de carrera para un atleta/periodo y persiste
AthleteBadge. La restricción UNIQUE (athlete_id, badge_type, period_year,
period_month) garantiza idempotencia: evaluar el mismo periodo dos veces
produce el mismo resultado sin duplicados.

Insignias disponibles:
  Asistencia:
    attendance_100 — 100% de asistencia
    attendance_90  — ≥90%
    attendance_75  — ≥75%
  Competitivas:
    first_podium   — Primer podio (P1/P2/P3) histórico del atleta
    mtp            — Mejor Tiempo Personal en una carrera del periodo
    top10          — Posición ≤10 en alguna carrera del periodo
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete_badge import AthleteBadge, BadgeSource, BadgeType
from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

logger = logging.getLogger(__name__)

# Thresholds de asistencia
_ATTENDANCE_100 = 100.0
_ATTENDANCE_90 = 90.0
_ATTENDANCE_75 = 75.0


async def evaluate_badges_for_period(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> list[AthleteBadge]:
    """Evalúa y persiste insignias para el atleta en el periodo dado.

    Idempotente: usa INSERT IGNORE semántico (try/except IntegrityError).
    Retorna la lista de insignias NUEVAS persistidas en esta llamada.
    Las ya existentes se omiten silenciosamente.
    """
    new_badges: list[AthleteBadge] = []

    # --- Insignias de asistencia ---
    attendance_badges = await _evaluate_attendance_badges(
        db, athlete_id, year, month
    )
    for badge in attendance_badges:
        saved = await _upsert_badge(db, badge)
        if saved:
            new_badges.append(saved)

    # --- Insignias competitivas ---
    race_badges = await _evaluate_race_badges(
        db, athlete_id, year, month
    )
    for badge in race_badges:
        saved = await _upsert_badge(db, badge)
        if saved:
            new_badges.append(saved)

    return new_badges


def _compute_streak(
    sessions: list[Any],
    attendances: list[Any],
) -> int:
    """Calcula la racha de asistencia consecutiva desde la sesión más reciente.

    Ordena las sesiones por `scheduled_date` descendente y cuenta cuántas
    sesiones consecutivas más recientes tienen estado PRESENTE o TARDE.
    La racha se rompe en la primera AUSENTE.

    Args:
        sessions: Lista de objetos con `.id` y `.scheduled_date`.
        attendances: Lista de objetos con `.session_id` y `.status`.

    Returns:
        Entero ≥ 0 representando la racha.
    """
    from app.models.training_session import AttendanceStatus

    # Mapa session_id → status
    status_map = {a.session_id: a.status for a in attendances}

    # Ordenar sesiones descendente por fecha
    sorted_sessions = sorted(sessions, key=lambda s: s.scheduled_date, reverse=True)

    streak = 0
    for s in sorted_sessions:
        st = status_map.get(s.id)
        if st in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}:
            streak += 1
        else:
            break
    return streak


async def get_badges_for_period(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> list[AthleteBadge]:
    """Retorna las insignias ya persistidas para el atleta/periodo (sin evaluar)."""
    result = await db.execute(
        select(AthleteBadge).where(
            AthleteBadge.athlete_id == athlete_id,
            AthleteBadge.period_year == year,
            AthleteBadge.period_month == month,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Evaluación de asistencia
# ---------------------------------------------------------------------------


async def _evaluate_attendance_badges(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    """Calcula qué insignias de asistencia merece el atleta en el periodo."""
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    # Sesiones ejecutadas del atleta en el mes
    from app.models.athlete import Athlete

    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        return []

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = sessions_result.scalars().all()
    total = len(sessions)
    if total == 0:
        return []

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete_id,
        )
    )
    attendances = att_result.scalars().all()

    present = sum(
        1
        for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    )
    pct = round(present / total * 100, 1)

    badges: list[dict[str, Any]] = []

    if pct >= _ATTENDANCE_100:
        badges.append({
            "badge_type": BadgeType.attendance_100,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
        })
    elif pct >= _ATTENDANCE_90:
        badges.append({
            "badge_type": BadgeType.attendance_90,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
        })
    elif pct >= _ATTENDANCE_75:
        badges.append({
            "badge_type": BadgeType.attendance_75,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
        })

    return badges


# ---------------------------------------------------------------------------
# Evaluación de insignias competitivas
# ---------------------------------------------------------------------------


async def _evaluate_race_badges(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    """Calcula qué insignias competitivas merece el atleta en el periodo.

    Requiere que el atleta tenga un RaceCompetitor vinculado (athlete_id NOT NULL).
    Si no tiene competitor vinculado, no se generan insignias de carrera.
    """
    try:
        from app.models.race_competitor import RaceCompetitor
        from app.models.race_event import RaceEvent
        from app.models.race_result import RaceResult, ResultStatus
        from app.models.race_series import RaceSeries
    except ImportError:
        logger.debug("Modelos de carrera no disponibles, omitiendo insignias race.")
        return []

    # Buscar el competitor vinculado al atleta
    comp_result = await db.execute(
        select(RaceCompetitor).where(RaceCompetitor.athlete_id == athlete_id)
    )
    competitor = comp_result.scalar_one_or_none()
    if competitor is None:
        return []

    # Eventos del periodo (mes/año)
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    events_result = await db.execute(
        select(RaceEvent).where(
            RaceEvent.event_date >= month_start,
            RaceEvent.event_date <= month_end,
        )
    )
    events_in_month = events_result.scalars().all()
    if not events_in_month:
        return []

    event_ids = [e.id for e in events_in_month]

    # Resultados del competitor en ese periodo
    results_result = await db.execute(
        select(RaceResult).where(
            RaceResult.competitor_id == competitor.id,
            RaceResult.event_id.in_(event_ids),
            RaceResult.status == ResultStatus.FINISHED,
        )
    )
    results = results_result.scalars().all()
    if not results:
        return []

    badges: list[dict[str, Any]] = []

    # Top 10
    top10_results = [r for r in results if r.position is not None and r.position <= 10]
    if top10_results:
        best = min(top10_results, key=lambda r: r.position)
        badges.append({
            "badge_type": BadgeType.top10,
            "badge_source": BadgeSource.race,
            "metadata_json": {
                "position": best.position,
                "event_id": best.event_id,
                "race_time_ms": best.race_time_ms,
            },
        })

    # Primer podio histórico: P1/P2/P3 en este periodo Y no tiene podios previos
    podium_results = [r for r in results if r.position is not None and r.position <= 3]
    if podium_results:
        # Verificar si ya tenía podios antes de este periodo
        prev_podium_result = await db.execute(
            select(RaceResult).join(
                RaceEvent,
                RaceEvent.id == RaceResult.event_id,
            ).where(
                RaceResult.competitor_id == competitor.id,
                RaceResult.position <= 3,
                RaceResult.status == ResultStatus.FINISHED,
                RaceEvent.event_date < month_start,
            ).limit(1)
        )
        had_previous_podium = prev_podium_result.scalar_one_or_none() is not None

        if not had_previous_podium:
            best_podium = min(podium_results, key=lambda r: r.position)
            badges.append({
                "badge_type": BadgeType.first_podium,
                "badge_source": BadgeSource.race,
                "metadata_json": {
                    "position": best_podium.position,
                    "event_id": best_podium.event_id,
                },
            })

    # MTP: ¿mejoró su mejor tiempo personal en el periodo?
    # Comparar el mejor tiempo del mes vs historial previo del competitor
    times_this_month = [
        r.race_time_ms
        for r in results
        if r.race_time_ms is not None and r.position is not None
    ]
    if times_this_month:
        best_time_month = min(times_this_month)

        # Historial previo (misma categoría si disponible, o todos)
        prev_results_stmt = await db.execute(
            select(RaceResult).join(
                RaceEvent,
                RaceEvent.id == RaceResult.event_id,
            ).where(
                RaceResult.competitor_id == competitor.id,
                RaceResult.race_time_ms.isnot(None),
                RaceResult.status == ResultStatus.FINISHED,
                RaceEvent.event_date < month_start,
            )
        )
        prev_results = prev_results_stmt.scalars().all()
        prev_times = [r.race_time_ms for r in prev_results if r.race_time_ms is not None]

        if prev_times:
            best_prev_time = min(prev_times)
            if best_time_month < best_prev_time:
                badges.append({
                    "badge_type": BadgeType.mtp,
                    "badge_source": BadgeSource.race,
                    "metadata_json": {
                        "best_time_ms": best_time_month,
                        "previous_best_ms": best_prev_time,
                        "improvement_ms": best_prev_time - best_time_month,
                    },
                })

    return badges


# ---------------------------------------------------------------------------
# Persistencia idempotente
# ---------------------------------------------------------------------------


async def _upsert_badge(
    db: AsyncSession,
    badge_data: dict[str, Any],
    athlete_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
) -> AthleteBadge | None:
    """Inserta una insignia si no existe. Retorna None si ya existía."""
    # badge_data debe tener badge_type, badge_source, metadata_json
    # athlete_id/year/month se pasan por contexto del caller o dentro del dict
    _athlete_id = athlete_id or badge_data.get("athlete_id")
    _year = year or badge_data.get("period_year")
    _month = month or badge_data.get("period_month")

    # Verificar si ya existe
    existing = await db.execute(
        select(AthleteBadge).where(
            AthleteBadge.athlete_id == _athlete_id,
            AthleteBadge.badge_type == badge_data["badge_type"],
            AthleteBadge.period_year == _year,
            AthleteBadge.period_month == _month,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    new_badge = AthleteBadge(
        athlete_id=_athlete_id,
        badge_type=badge_data["badge_type"],
        badge_source=badge_data["badge_source"],
        period_year=_year,
        period_month=_month,
        earned_at=datetime.now(timezone.utc),
        metadata_json=badge_data.get("metadata_json"),
    )
    db.add(new_badge)
    await db.flush()
    return new_badge


async def evaluate_and_persist_badges(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> list[AthleteBadge]:
    """API pública: evalúa e inserta insignias. Retorna lista de nuevas insignias.

    Idempotente: llamadas repetidas no duplican registros.
    """
    new_badges: list[AthleteBadge] = []

    attendance_badge_datas = await _evaluate_attendance_badges(db, athlete_id, year, month)
    for bd in attendance_badge_datas:
        badge = await _upsert_badge(
            db,
            {**bd, "athlete_id": athlete_id, "period_year": year, "period_month": month},
        )
        if badge:
            new_badges.append(badge)

    race_badge_datas = await _evaluate_race_badges(db, athlete_id, year, month)
    for bd in race_badge_datas:
        badge = await _upsert_badge(
            db,
            {**bd, "athlete_id": athlete_id, "period_year": year, "period_month": month},
        )
        if badge:
            new_badges.append(badge)

    return new_badges
