"""Servicio: construcción del snapshot de métricas para el boletín mensual individual.

Reúne los 10 bloques del boletín y los separa en:
  - email_blocks: asistencia, carga técnica, resultados carreras, narrativa IA,
                  calendario, apoyo desde casa, fotos (links), badges.
  - pdf_only_blocks: antropometría completa + gráficos SVG.

La separación estricta garantiza que NUNCA se incluyan datos antropométricos
en el email (Ley 1581: datos sensibles de menores solo en canal seguro).

Privacidad:
  - Ningún nombre real en logs.
  - Fotos: solo las que tienen consent_ack=True y el atleta está etiquetado.
  - Soft-cap de 8 fotos por boletín (previene PDFs excesivamente grandes).
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete_badge import AthleteBadge
from app.services.training.badge_evaluator import evaluate_and_persist_badges, get_badges_for_period

logger = logging.getLogger(__name__)

_PHOTO_SOFT_CAP = 8
_MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


async def build_newsletter_metrics(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Construye el metrics_snapshot completo del boletín.

    Returns:
        dict con claves 'email_blocks' y 'pdf_only_blocks'.
        'email_blocks' NUNCA contiene antropometría.
        'pdf_only_blocks' contiene antropometría + referencia a gráficos SVG.
    """
    from app.models.athlete import Athlete
    from app.models.training_session import (
        AttendanceStatus,
        SessionAttendance,
        SessionStatus,
        TrainingSession,
    )

    athlete_result = await db.execute(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    athlete = athlete_result.scalar_one_or_none()
    if athlete is None:
        raise ValueError(f"Atleta {athlete_id} no encontrado.")

    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    month_label = f"{_MONTHS_ES[month - 1]} {year}"

    # -----------------------------------------------------------------------
    # Bloque 1: Asistencia y compromiso
    # -----------------------------------------------------------------------
    attendance_block = await _build_attendance_block(
        db, athlete, month_start, month_end, year, month
    )

    # -----------------------------------------------------------------------
    # Bloque 2: Carga y desarrollo técnico
    # -----------------------------------------------------------------------
    technical_block = await _build_technical_block(
        db, athlete, month_start, month_end
    )

    # -----------------------------------------------------------------------
    # Bloque 3: Resultados Copa Valle del mes
    # -----------------------------------------------------------------------
    race_block = await _build_race_block(db, athlete_id, year, month)

    # -----------------------------------------------------------------------
    # Bloque 4: Calendario (próximas sesiones + válidas)
    # -----------------------------------------------------------------------
    calendar_block = await _build_calendar_block(db, athlete, month_end)

    # -----------------------------------------------------------------------
    # Bloque 5: Fotos del mes (consent_ack=True, etiquetado al atleta)
    # -----------------------------------------------------------------------
    photos_block = await _build_photos_block(db, athlete_id, month_start, month_end)

    # -----------------------------------------------------------------------
    # Bloque 6: Badges ganados en el periodo
    # -----------------------------------------------------------------------
    badges = await evaluate_and_persist_badges(db, athlete_id, year, month)
    # También recuperar los que ya existían (evaluate es idempotente)
    all_badges = await get_badges_for_period(db, athlete_id, year, month)
    badges_block = _serialize_badges(all_badges)

    # -----------------------------------------------------------------------
    # Bloque 7: "Cómo apoyar desde casa" (template estático)
    # -----------------------------------------------------------------------
    support_block = _build_support_block()

    # -----------------------------------------------------------------------
    # Bloque 8 (pdf_only): Antropometría completa
    # -----------------------------------------------------------------------
    anthropometry_block = await _build_anthropometry_block(db, athlete_id, year, month)

    # -----------------------------------------------------------------------
    # Bloque 9 (pdf_only): Curvas de percentiles de crecimiento
    # CRÍTICO: NUNCA incluir en email_blocks.
    # -----------------------------------------------------------------------
    # Cargar todos los registros ordenados asc para el builder
    from app.models.anthropometry import AnthropometricRecord

    all_records_result = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.asc())
    )
    all_records = all_records_result.scalars().all()

    percentile_curves_block = await _build_percentile_charts_block(
        db, athlete, list(all_records)
    )

    # -----------------------------------------------------------------------
    # Ensamble final
    # -----------------------------------------------------------------------
    email_blocks: dict[str, Any] = {
        "period": {"year": year, "month": month, "label": month_label},
        "attendance": attendance_block,
        "technical": technical_block,
        "race_results": race_block,
        "calendar": calendar_block,
        "photos": photos_block,
        "badges": badges_block,
        "support_at_home": support_block,
        # La narrativa IA se añade por separado tras correr el use case
        "ai_narrative": None,
    }

    pdf_only_blocks: dict[str, Any] = {
        "anthropometry": anthropometry_block,
        # Los gráficos SVG se generan en render time a partir de race_results
        "charts_context": _build_charts_context(race_block),
    }

    # Inyectar curvas de percentiles solo si hay al menos un indicador con datos
    if percentile_curves_block is not None:
        pdf_only_blocks["percentile_curves"] = percentile_curves_block

    return {
        "email_blocks": email_blocks,
        "pdf_only_blocks": pdf_only_blocks,
    }


# ---------------------------------------------------------------------------
# Helpers de construcción de bloques
# ---------------------------------------------------------------------------


async def _build_attendance_block(
    db: AsyncSession,
    athlete: Any,
    month_start: date,
    month_end: date,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Asistencia y compromiso: %, comparativa mes anterior, racha."""
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = sessions_result.scalars().all()

    if not sessions:
        return {
            "sessions_total": 0,
            "sessions_present": 0,
            "attendance_pct": 0.0,
            "attendance_pct_prev_month": None,
            "streak_days": 0,
        }

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete.id,
        )
    )
    attendances = att_result.scalars().all()

    # Solo cuentan sesiones donde el atleta fue convocado (tiene registro)
    convoked_ids = {a.session_id for a in attendances}
    convoked_sessions = [s for s in sessions if s.id in convoked_ids]
    total = len(convoked_sessions)

    if total == 0:
        return {
            "sessions_total": 0,
            "sessions_present": 0,
            "attendance_pct": 0.0,
            "attendance_pct_prev_month": None,
            "streak_days": 0,
        }

    present = sum(
        1 for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    )
    pct = round(present / total * 100, 1)

    # Mes anterior (comparativa)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_pct = await _get_prev_month_attendance(
        db, athlete, prev_year, prev_month
    )

    # Racha actual (días consecutivos con asistencia PRESENTE)
    streak = _compute_streak(convoked_sessions, attendances)

    return {
        "sessions_total": total,
        "sessions_present": present,
        "attendance_pct": pct,
        "attendance_pct_prev_month": prev_pct,
        "streak_days": streak,
    }


async def _get_prev_month_attendance(
    db: AsyncSession,
    athlete: Any,
    year: int,
    month: int,
) -> float | None:
    """Calcula el % de asistencia del mes anterior para comparativa."""
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

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
    if not sessions:
        return None

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete.id,
        )
    )
    attendances = att_result.scalars().all()
    # Solo cuentan sesiones donde el atleta fue convocado
    total = len(attendances)
    if total == 0:
        return None
    present = sum(
        1 for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    )
    return round(present / total * 100, 1)


def _compute_streak(sessions: list, attendances: list) -> int:
    """Calcula la racha de días con asistencia presente (simplificado)."""
    from app.models.training_session import AttendanceStatus

    present_session_ids = {
        a.session_id
        for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    }
    # Ordenar sesiones por fecha desc y contar racha
    sorted_sessions = sorted(sessions, key=lambda s: s.scheduled_date, reverse=True)
    streak = 0
    for s in sorted_sessions:
        if s.id in present_session_ids:
            streak += 1
        else:
            break
    return streak


async def _build_technical_block(
    db: AsyncSession,
    athlete: Any,
    month_start: date,
    month_end: date,
) -> dict[str, Any]:
    """Carga y desarrollo técnico: rúbrica, focos, RPE, horas vs LTAD."""
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
    )
    sessions = sessions_result.scalars().all()
    if not sessions:
        return {
            "focos_tecnicos": [],
            "avg_rpe": None,
            "avg_rubric_effort": None,
            "avg_rubric_attitude": None,
            "avg_rubric_technique": None,
            "total_training_hours": 0.0,
        }

    session_ids = [s.id for s in sessions]
    focos = list({s.technical_focus for s in sessions if s.technical_focus})

    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete.id,
        )
    )
    attendances = att_result.scalars().all()

    def _avg(values: list) -> float | None:
        clean = [v for v in values if v is not None]
        return round(sum(clean) / len(clean), 1) if clean else None

    avg_rpe = _avg([a.rpe_omni for a in attendances])
    avg_effort = _avg([a.rubric_effort for a in attendances])
    avg_attitude = _avg([a.rubric_attitude for a in attendances])
    avg_technique = _avg([a.rubric_technique for a in attendances])

    # Horas totales de entrenamiento (duración de sesiones con asistencia presente)
    from app.models.training_session import AttendanceStatus
    present_session_ids = {
        a.session_id
        for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    }
    total_hours = sum(
        (s.duration_min or 0) / 60.0
        for s in sessions
        if s.id in present_session_ids
    )

    return {
        "focos_tecnicos": focos,
        "avg_rpe": avg_rpe,
        "avg_rubric_effort": avg_effort,
        "avg_rubric_attitude": avg_attitude,
        "avg_rubric_technique": avg_technique,
        "total_training_hours": round(total_hours, 1),
    }


async def _build_race_block(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Resultados de carreras del mes: posición, gap, ranking club, proyección.

    Reutiliza funciones de services/race/analytics.py.
    """
    try:
        import pandas as pd
        from app.models.race_competitor import RaceCompetitor
        from app.services.race.analytics import athlete_progression, podium_gap, projection

        comp_result = await db.execute(
            select(RaceCompetitor).where(RaceCompetitor.athlete_id == athlete_id)
        )
        competitors = comp_result.scalars().all()
        if not competitors:
            return {"has_races": False, "competitor_id": None, "results": [], "projection": None}

        primary_competitor_id = competitors[0].id

        # Historial completo: agrega progression de todos los competitors vinculados
        progression_dfs = []
        for c in competitors:
            df = await athlete_progression(db, c.id)
            if not df.empty:
                progression_dfs.append(df)
        if not progression_dfs:
            return {"has_races": False, "competitor_id": primary_competitor_id, "results": [], "projection": None}

        progression_df = pd.concat(progression_dfs, ignore_index=True)
        # Dedup por event_date: mismo atleta corrió un evento bajo nombres distintos
        progression_df = progression_df.drop_duplicates(subset=["event_date"], keep="first")

        # Filtrar solo el mes actual
        month_start_str = f"{year}-{month:02d}-01"
        month_end_str = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"

        month_results = progression_df[
            (progression_df["event_date"] >= month_start_str)
            & (progression_df["event_date"] <= month_end_str)
        ]

        results_serialized = []
        for _, row in month_results.iterrows():
            results_serialized.append({
                "valida_num": int(row["valida_num"]) if row["valida_num"] is not None and str(row["valida_num"]) != "<NA>" else None,
                "event_date": str(row["event_date"]) if row["event_date"] else None,
                "category_code": str(row["category_code"]) if row["category_code"] else None,
                "position": int(row["position"]) if row["position"] is not None and str(row["position"]) != "<NA>" else None,
                "race_time_ms": int(row["race_time_ms"]) if row["race_time_ms"] is not None and str(row["race_time_ms"]) != "<NA>" else None,
                "points_awarded": int(row["points_awarded"]) if row["points_awarded"] is not None and str(row["points_awarded"]) != "<NA>" else 0,
                "gap_to_winner_ms": int(row["gap_to_winner_ms"]) if row["gap_to_winner_ms"] is not None and str(row["gap_to_winner_ms"]) != "<NA>" else None,
                "gap_to_winner_pct": float(row["gap_to_winner_pct"]) if row["gap_to_winner_pct"] is not None and str(row["gap_to_winner_pct"]) not in ("nan", "None") else None,
            })

        # Historial completo serializado (para gráficos SVG)
        all_results = []
        for _, row in progression_df.iterrows():
            try:
                pos = int(row["position"]) if str(row["position"]) != "<NA>" else None
                pts = int(row["points_awarded"]) if str(row["points_awarded"]) != "<NA>" else 0
                gap = int(row["gap_to_winner_ms"]) if str(row["gap_to_winner_ms"]) != "<NA>" else None
                gap_pct = float(row["gap_to_winner_pct"]) if str(row["gap_to_winner_pct"]) not in ("nan", "<NA>", "None") else None
                all_results.append({
                    "valida_num": int(row["valida_num"]) if str(row["valida_num"]) != "<NA>" else None,
                    "event_date": str(row["event_date"]),
                    "position": pos,
                    "points_awarded": pts,
                    "gap_to_winner_pct": gap_pct,
                })
            except Exception:
                continue

        return {
            "has_races": len(results_serialized) > 0,
            "competitor_id": primary_competitor_id,
            "results": results_serialized,
            "progression_history": all_results,
            "projection": None,  # Se puede completar con next_event_id cuando se conozca
        }

    except Exception as exc:
        logger.warning("Error construyendo bloque de carreras: %s", type(exc).__name__)
        return {"has_races": False, "competitor_id": None, "results": [], "projection": None}


async def _build_calendar_block(
    db: AsyncSession,
    athlete: Any,
    month_end: date,
) -> dict[str, Any]:
    """Próximas sesiones planificadas y válidas."""
    from app.models.training_session import SessionStatus, TrainingSession

    # Próximas 4 sesiones planificadas
    next_sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date > month_end,
            TrainingSession.status.in_([SessionStatus.PLANNED, SessionStatus.EXECUTED]),
        ).order_by(TrainingSession.scheduled_date).limit(4)
    )
    next_sessions = next_sessions_result.scalars().all()

    sessions_out = []
    for s in next_sessions:
        sessions_out.append({
            "date": s.scheduled_date.isoformat() if s.scheduled_date else None,
            "technical_focus": s.technical_focus,
            "location": s.location,
            "duration_min": s.duration_min,
        })

    # Próximos eventos de carrera del calendario (Calendario Copa Valle)
    next_races = _get_upcoming_copa_valle_races(month_end)

    return {
        "next_training_sessions": sessions_out,
        "next_race_events": next_races,
    }


def _get_upcoming_copa_valle_races(after_date: date) -> list[dict[str, Any]]:
    """Retorna las próximas válidas de la Copa Valle 2026 tras la fecha dada."""
    calendar_copa_valle_2026 = [
        {"valida": "IV", "date": "2026-05-17", "location": "Cali", "priority": "A"},
        {"valida": "CD", "date": "2026-06-12", "location": "Ginebra", "priority": "A"},
        {"valida": "V", "date": "2026-08-01", "location": "Palmira", "priority": "B"},
        {"valida": "VI", "date": "2026-09-12", "location": "Roldanillo", "priority": "A"},
        {"valida": "VII", "date": "2026-10-18", "location": "Yumbo", "priority": "B"},
    ]
    result = []
    for event in calendar_copa_valle_2026:
        try:
            event_date = date.fromisoformat(event["date"])
            if event_date > after_date:
                result.append(event)
        except ValueError:
            continue
    return result[:3]  # máximo 3 próximas


async def _build_photos_block(
    db: AsyncSession,
    athlete_id: int,
    month_start: date,
    month_end: date,
) -> dict[str, Any]:
    """Fotos del mes etiquetadas al atleta con consent_ack=True."""
    try:
        from app.models.session_media import SessionMedia, SessionMediaAthlete
        from app.models.training_session import TrainingSession

        # Sessions del mes
        sessions_result = await db.execute(
            select(TrainingSession).where(
                TrainingSession.scheduled_date >= month_start,
                TrainingSession.scheduled_date <= month_end,
            )
        )
        sessions = sessions_result.scalars().all()
        if not sessions:
            return {"count": 0, "items": []}

        session_ids = [s.id for s in sessions]

        # Medias con consent_ack y el atleta etiquetado
        media_result = await db.execute(
            select(SessionMedia)
            .join(
                SessionMediaAthlete,
                SessionMediaAthlete.media_id == SessionMedia.id,
            )
            .where(
                SessionMedia.session_id.in_(session_ids),
                SessionMedia.consent_ack.is_(True),
                SessionMedia.deleted_at.is_(None),
                SessionMediaAthlete.athlete_id == athlete_id,
            )
            .order_by(SessionMedia.uploaded_at.desc())
            .limit(_PHOTO_SOFT_CAP)
        )
        medias = media_result.scalars().all()

        items = []
        for m in medias:
            items.append({
                "media_id": m.id,
                "thumbnail_url": m.thumbnail_url,
                "storage_url": m.storage_url,
                "caption": m.caption,
                "media_type": m.media_type.value if m.media_type else None,
            })

        return {
            "count": len(items),
            "items": items,
            "soft_cap_reached": len(medias) >= _PHOTO_SOFT_CAP,
        }

    except Exception as exc:
        logger.warning("Error construyendo bloque de fotos: %s", type(exc).__name__)
        return {"count": 0, "items": []}


def _serialize_badges(badges: list[AthleteBadge]) -> dict[str, Any]:
    """Serializa las insignias para almacenar en el snapshot."""
    items = []
    for b in badges:
        items.append({
            "badge_type": b.badge_type.value,
            "badge_source": b.badge_source.value,
            "earned_at": b.earned_at.isoformat() if b.earned_at else None,
            "metadata": b.metadata_json,
        })
    return {"count": len(items), "items": items}


def _build_support_block() -> dict[str, Any]:
    """Bloque estático 'Cómo apoyar desde casa' (sin calorías ni suplementos)."""
    return {
        "tips": [
            {
                "category": "hidratacion",
                "title": "Hidratación",
                "text": (
                    "Asegúrate de que tu hijo/a llegue al entrenamiento bien hidratado/a. "
                    "Durante el día: agua o bebida de fruta natural. "
                    "Antes del entreno: 500ml en la hora previa. "
                    "Durante: sorbos cada 15-20 min según la sed."
                ),
            },
            {
                "category": "sueno",
                "title": "Sueño",
                "text": (
                    "Los atletas de 10-12 años necesitan 9-11 horas por noche; "
                    "los de 13-15 años, 8-10 horas. "
                    "El sueño es cuando el cuerpo crece y se recupera. "
                    "Mantén horarios regulares, especialmente antes de competencia."
                ),
            },
            {
                "category": "descanso",
                "title": "Descanso activo",
                "text": (
                    "Los días sin entrenamiento son parte del plan. "
                    "Un paseo en familia, nadar o jugar libremente es ideal. "
                    "Evitar actividades extenuantes el día antes de competencia."
                ),
            },
            {
                "category": "nutricion",
                "title": "Alimentación",
                "text": (
                    "Tres comidas principales + snack post-entreno balanceado. "
                    "Fruta, lácteos, proteína de alimentos naturales. "
                    "Sin suplementos: a esta edad, la comida real es suficiente. "
                    "El entrenador no realiza seguimiento calórico — la familia es la guía."
                ),
            },
        ]
    }


async def _build_anthropometry_block(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Antropometría completa: historial + implicaciones pedagógicas (solo PDF).

    NUNCA debe incluirse en email_blocks.
    """
    from app.models.anthropometry import AnthropometricRecord

    results = await db.execute(
        select(AnthropometricRecord)
        .where(AnthropometricRecord.athlete_id == athlete_id)
        .order_by(AnthropometricRecord.evaluation_date.desc())
        .limit(6)  # últimas 6 mediciones para tendencia longitudinal
    )
    records = results.scalars().all()

    if not records:
        return {"has_records": False, "records": []}

    serialized = []
    for r in records:
        serialized.append({
            "evaluation_date": r.evaluation_date.isoformat() if r.evaluation_date else None,
            "weight_kg": float(r.weight_kg) if r.weight_kg is not None else None,
            "standing_height_cm": float(r.standing_height_cm) if r.standing_height_cm is not None else None,
            "sitting_height_cm": float(r.sitting_height_cm) if r.sitting_height_cm is not None else None,
            "bmi": float(r.bmi) if r.bmi is not None else None,
            "height_z_score": float(r.height_z_score) if r.height_z_score is not None else None,
            "height_percentile": float(r.height_percentile) if r.height_percentile is not None else None,
            "bmi_z_score": float(r.bmi_z_score) if r.bmi_z_score is not None else None,
            "bmi_percentile": float(r.bmi_percentile) if r.bmi_percentile is not None else None,
            "weight_z_score": float(r.weight_z_score) if r.weight_z_score is not None else None,
            "weight_percentile": float(r.weight_percentile) if r.weight_percentile is not None else None,
            "maturity_offset": float(r.maturity_offset) if r.maturity_offset is not None else None,
            "age_at_phv": float(r.age_at_phv) if r.age_at_phv is not None else None,
            "maturation_status": r.maturation_status.value if r.maturation_status else None,
            "nutritional_status": r.nutritional_status.value if r.nutritional_status else None,
            "training_implications": r.training_implications,
        })

    # Registro más reciente para el resumen
    latest = serialized[0]

    return {
        "has_records": True,
        "records": serialized,
        "latest": latest,
    }


async def _build_percentile_charts_block(
    db: AsyncSession,
    athlete: Any,
    records: list,
) -> dict[str, Any] | None:
    """Construye los 3 gráficos de percentiles de crecimiento para el PDF.

    Retorna dict con claves "height", "bmi", "weight" (los que tengan datos),
    o None si los 3 indicadores carecen de datos suficientes.

    PRIVACIDAD: el dict resultante no contiene nombre, DOB ni z-scores.
    Solo va a pdf_only_blocks — NUNCA a email_blocks.
    """
    from app.services.training.growth_chart_builder import build_percentile_chart_ctx

    sex_attr = getattr(athlete, "sex", None)
    if sex_attr is None:
        return None
    sex: str = sex_attr.value if hasattr(sex_attr, "value") else str(sex_attr)
    birth_date = getattr(athlete, "birth_date", None)
    if birth_date is None:
        return None

    # PHV: extraer del registro más reciente que tenga age_at_phv
    phv_age: float | None = None
    for r in reversed(records):
        if r.age_at_phv is not None:
            phv_age = float(r.age_at_phv)
            break

    charts: dict[str, Any] = {}
    has_any_data = False

    for indicator in ("height", "bmi", "weight"):
        try:
            ctx = await build_percentile_chart_ctx(
                db=db,
                athlete_id=athlete.id,
                birth_date=birth_date,
                sex=sex,
                records=records,
                indicator=indicator,
                phv_age_decimal=phv_age,
            )
        except Exception:
            logger.error(
                "growth_chart_unavailable athlete_id=%s indicator=%s",
                athlete.id,
                indicator,
            )
            charts[indicator] = {
                "enough_data": False,
                "reason_no_data": "growth_chart_unavailable",
                "indicator": indicator,
                "indicator_label_es": {
                    "height": "Talla (cm)",
                    "bmi": "IMC (kg/m²)",
                    "weight": "Peso (kg)",
                }.get(indicator, indicator),
            }
            continue

        charts[indicator] = dict(ctx)
        if ctx["enough_data"]:
            has_any_data = True

    if not has_any_data:
        return None

    return charts


def _build_charts_context(race_block: dict[str, Any]) -> dict[str, Any]:
    """Prepara el contexto para los macros SVG de gráficos.

    Los gráficos se renderizan en el template PDF a partir de estos datos.
    """
    history = race_block.get("progression_history", [])
    if not history:
        return {"has_data": False, "positions": [], "gap_pcts": [], "points_accumulated": []}

    positions = []
    gap_pcts = []
    points_acc = []
    acc = 0
    for row in history:
        v = row.get("valida_num")
        pos = row.get("position")
        gap = row.get("gap_to_winner_pct")
        pts = row.get("points_awarded", 0) or 0
        acc += pts
        positions.append({"x": v, "y": pos})
        gap_pcts.append({"x": v, "y": gap})
        points_acc.append({"x": v, "y": acc})

    n_samples = len([p for p in positions if p["y"] is not None])

    return {
        "has_data": True,
        "n_samples": n_samples,
        "low_confidence": n_samples < 5,
        "positions": positions,
        "gap_pcts": gap_pcts,
        "points_accumulated": points_acc,
    }
