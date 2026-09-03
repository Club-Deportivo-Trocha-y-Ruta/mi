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
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete_badge import AthleteBadge
from app.services.category import compute_age_decimal
from app.services.training.badge_evaluator import (
    _compute_streak,
    evaluate_and_persist_badges,
    get_badges_for_period,
)
from app.services.training.focus_grouping import group_focus_texts

logger = logging.getLogger(__name__)

_PHOTO_SOFT_CAP = 8
_MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def _row_str(row: Any, col: str) -> str | None:
    """Extrae una columna de una fila de DataFrame como str, o None.

    Tolera columnas ausentes (KeyError) y los sentinelas nulos de pandas
    (``NaN``/``NA``/``None``/cadena vacía) que aparecen cuando el merge no
    encontró la serie del evento.
    """
    try:
        val = row[col]
    except (KeyError, IndexError):
        return None
    s = str(val).strip() if val is not None else ""
    if s in ("", "nan", "<NA>", "None", "NaN"):
        return None
    return s


def _race_short_label(
    series_kind: str | None,
    series_level: str | None,
    valida_num: int | None,
) -> str:
    """Etiqueta compacta para el eje X de los gráficos del boletín.

    Los campeonatos llevan ``sequence_number=1`` (spec 014) y no pertenecen a
    la secuencia de válidas; mostrarlos como "V1" los haría colisionar con la
    Válida I real. Por eso el campeonato usa su propia etiqueta:

        - ``championship`` + ``national``     → ``"CN"`` (Campeonato Nacional)
        - ``championship`` + ``departmental`` → ``"CD"`` (Campeonato Departamental)
        - ``cup``                             → ``"V{n}"`` (número de válida)
    """
    if series_kind == "championship":
        return "CN" if series_level == "national" else "CD"
    return f"V{valida_num}" if valida_num is not None else "—"


def _race_readable_label(
    series_kind: str | None,
    series_level: str | None,
    valida_num: int | None,
) -> str:
    """Etiqueta legible para tablas, destacados y email del boletín.

    A diferencia de :func:`_race_short_label` (eje X de gráficos, sin espacio),
    aquí sí cabe la forma completa:

        - ``championship`` + ``national``     → ``"Campeonato Nacional"``
        - ``championship`` + ``departmental`` → ``"Campeonato Departamental"``
        - ``cup``                             → ``"Válida {n}"``
    """
    if series_kind == "championship":
        return "Campeonato Nacional" if series_level == "national" else "Campeonato Departamental"
    return f"Válida {valida_num}" if valida_num is not None else "—"


async def _lookup_category_labels(
    db: AsyncSession, category_codes: set[str]
) -> dict[str, str]:
    """Resuelve ``race_categories.label`` por ``code`` en una sola consulta batch.

    Códigos no mapeados quedan ausentes del dict resultante (el llamador cae
    de vuelta al código crudo).
    """
    if not category_codes:
        return {}

    from app.models.race_category import RaceCategory

    result = await db.execute(
        select(RaceCategory.code, RaceCategory.label).where(
            RaceCategory.code.in_(category_codes)
        )
    )
    return {code: label for code, label in result.all()}


def _derive_athlete_reference(athlete_sex: str | None) -> str:
    """Deriva el pronombre de referencia en español para el atleta.

    Mismo criterio que ``_derive_athlete_reference`` del use case de IA
    (``app/services/ai/use_cases/athlete_monthly_newsletter.py``): no se
    importa desde ahí para no acoplar el servicio de training a la capa de IA.
    """
    if athlete_sex == "M":
        return "su hijo"
    if athlete_sex == "F":
        return "su hija"
    return "su hijo/a"


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

    # Fecha de referencia para cálculos de edad decimal (LTAD, banda de apoyo).
    # Se usa "hoy" (no el fin de mes) porque el boletín puede generarse tarde.
    generation_date = date.today()
    _athlete_sex = getattr(athlete, "sex", None)
    athlete_reference = _derive_athlete_reference(
        _athlete_sex.value if hasattr(_athlete_sex, "value") else _athlete_sex
    )

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
        db, athlete, month_start, month_end, generation_date
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
    age_decimal = (
        compute_age_decimal(athlete.birth_date, generation_date)
        if athlete.birth_date
        else None
    )
    support_block = _build_support_block(age_decimal, month, athlete_reference)

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
    # Bloque 10 (feature 038): fecha de la primera sesión histórica del
    # atleta (temporada completa, no solo el mes) — usada por la bitácora
    # de etapa para numerar la "etapa" y para el waypoint "first_session".
    # -----------------------------------------------------------------------
    athlete_first_session_date = await _get_athlete_first_session_date(db, athlete)

    # -----------------------------------------------------------------------
    # Bloque 11 (pdf_only, feature 038): perfil de esfuerzo semanal
    # (fecha/asistencia/RPE por sesión del mes) y focos técnicos planificados
    # en las próximas 4 semanas, agrupados por familia de habilidad (024).
    # -----------------------------------------------------------------------
    weekly_block = await _build_weekly_block(db, athlete, month_start, month_end)
    next_focus_groups_block = await _build_next_focus_groups_block(db, athlete, month_end)

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
        # Feature 038 (bitácora de etapa): fecha ISO o None.
        "athlete_first_session_date": athlete_first_session_date,
        # La narrativa IA se añade por separado tras correr el use case
        "ai_narrative": None,
    }

    # US3 (T024): subtítulos por bloque + resumen del mes deterministas.
    # Se calculan aquí como línea base (sin IA, sin red) a partir de las señales
    # ya disponibles en email_blocks. El router puede sobrescribirlos con la
    # versión IA cuando hay consentimiento; si no, esta versión estática viaja
    # en el snapshot y las plantillas la renderizan igual.
    from app.services.training.newsletter_static_copy import (
        build_static_captions,
        build_static_highlights,
    )

    email_blocks["block_captions"] = build_static_captions(email_blocks)
    email_blocks["month_highlights"] = build_static_highlights(email_blocks)

    pdf_only_blocks: dict[str, Any] = {
        "anthropometry": anthropometry_block,
        # Los gráficos SVG se generan en render time a partir de race_results
        "charts_context": _build_charts_context(race_block),
        # Feature 038 (bitácora de etapa): perfil de esfuerzo semanal y
        # focos técnicos planificados de las próximas 4 semanas.
        "weekly": weekly_block,
        "next_focus_groups": next_focus_groups_block,
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
            "streak_sessions": 0,
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
            "streak_sessions": 0,
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

    # Racha actual (sesiones consecutivas con asistencia PRESENTE/TARDE)
    streak = _compute_streak(convoked_sessions, attendances)

    return {
        "sessions_total": total,
        "sessions_present": present,
        "attendance_pct": pct,
        "attendance_pct_prev_month": prev_pct,
        "streak_sessions": streak,
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


async def _build_technical_block(
    db: AsyncSession,
    athlete: Any,
    month_start: date,
    month_end: date,
    generation_date: date,
) -> dict[str, Any]:
    """Carga y desarrollo técnico: rúbrica, focos, RPE, horas vs LTAD."""
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

    ltad_limit_hours = (
        compute_age_decimal(athlete.birth_date, generation_date)
        if athlete.birth_date
        else None
    )
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]

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
            "focus_groups": [],
            "avg_rpe": None,
            "avg_rubric_effort": None,
            "avg_rubric_attitude": None,
            "avg_rubric_technique": None,
            "total_training_hours": 0.0,
            "weekly_hours_avg": None,
            "ltad_limit_hours": ltad_limit_hours,
            "ltad_status": None,
        }

    session_ids = [s.id for s in sessions]
    focos = list({s.technical_focus for s in sessions if s.technical_focus})
    raw_focus_texts = [s.technical_focus for s in sessions if s.technical_focus]
    focus_groups = [
        {"slug": g.slug, "name": g.name, "session_count": g.session_count}
        for g in group_focus_texts(raw_focus_texts)
    ]

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
    total_hours = round(total_hours, 1)

    weekly_hours_avg = round(total_hours / (days_in_month / 7.0), 1)
    ltad_status = (
        ("ok" if weekly_hours_avg <= ltad_limit_hours else "review")
        if ltad_limit_hours is not None
        else None
    )

    return {
        "focos_tecnicos": focos,
        "focus_groups": focus_groups,
        "avg_rpe": avg_rpe,
        "avg_rubric_effort": avg_effort,
        "avg_rubric_attitude": avg_attitude,
        "avg_rubric_technique": avg_technique,
        "total_training_hours": total_hours,
        "weekly_hours_avg": weekly_hours_avg,
        "ltad_limit_hours": ltad_limit_hours,
        "ltad_status": ltad_status,
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
        from app.services.race.analytics import athlete_progression

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

        category_codes = {
            str(row["category_code"])
            for _, row in month_results.iterrows()
            if row["category_code"]
        }
        category_labels = await _lookup_category_labels(db, category_codes)

        results_serialized = []
        for _, row in month_results.iterrows():
            _valida_num = int(row["valida_num"]) if row["valida_num"] is not None and str(row["valida_num"]) != "<NA>" else None
            _series_kind = _row_str(row, "series_kind") or "cup"
            _series_level = _row_str(row, "series_level") or "departmental"
            _category_code = str(row["category_code"]) if row["category_code"] else None
            results_serialized.append({
                "valida_num": _valida_num,
                "series_kind": _series_kind,
                "series_level": _series_level,
                "label": _race_readable_label(_series_kind, _series_level, _valida_num),
                "short_label": _race_short_label(_series_kind, _series_level, _valida_num),
                "event_date": str(row["event_date"]) if row["event_date"] else None,
                "category_code": _category_code,
                "category_label": category_labels.get(_category_code) if _category_code else None,
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
                valida_num = int(row["valida_num"]) if str(row["valida_num"]) != "<NA>" else None
                series_kind = _row_str(row, "series_kind") or "cup"
                series_level = _row_str(row, "series_level") or "departmental"
                location = _row_str(row, "location")
                all_results.append({
                    "valida_num": valida_num,
                    "event_date": str(row["event_date"]),
                    "position": pos,
                    "points_awarded": pts,
                    "gap_to_winner_pct": gap_pct,
                    "series_kind": series_kind,
                    "series_level": series_level,
                    "location": location,
                    "label": _race_short_label(series_kind, series_level, valida_num),
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


async def _get_athlete_first_session_date(db: AsyncSession, athlete: Any) -> str | None:
    """Fecha ISO de la primera sesión de entrenamiento asistida por el
    atleta (histórico completo de temporada, no solo el mes del boletín).

    Feature 038 (bitácora de etapa): usada por ``stage_log_builder`` para
    numerar la "etapa" (mes 1 = mes de esta sesión) y para el waypoint
    ``first_session`` de la ruta del mes. Consulta liviana e independiente
    del resto del snapshot mensual — se ejecuta siempre, aunque el mes del
    boletín no sea el primero.
    """
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

    result = await db.execute(
        select(TrainingSession.scheduled_date)
        .join(SessionAttendance, SessionAttendance.session_id == TrainingSession.id)
        .where(
            SessionAttendance.athlete_id == athlete.id,
            SessionAttendance.status.in_([AttendanceStatus.PRESENTE, AttendanceStatus.TARDE]),
            TrainingSession.status == SessionStatus.EXECUTED,
        )
        .order_by(TrainingSession.scheduled_date.asc())
        .limit(1)
    )
    rows = result.scalars().all()
    first = rows[0] if rows else None
    return first.isoformat() if first else None


async def _build_weekly_block(
    db: AsyncSession,
    athlete: Any,
    month_start: date,
    month_end: date,
) -> list[dict[str, Any]]:
    """Bloque ``weekly`` (pdf_only, feature 038): una entrada por sesión de
    entrenamiento EJECUTADA del club en el mes, con la asistencia/RPE/
    rúbrica de este atleta puntual.

    Se incluye una fila por cada sesión del club (no solo las asistidas) para
    que ``stage_log_builder.effort_profile`` pueda distinguir "sesiones
    planificadas" de "sesiones asistidas" por semana ISO — el mismo criterio
    que ya usa el bloque ``attendance``. Solo PDF: no aporta nada nuevo al
    email, que ya resume asistencia en el bloque ``attendance``.
    """
    from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

    sessions_result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date >= month_start,
            TrainingSession.scheduled_date <= month_end,
            TrainingSession.status == SessionStatus.EXECUTED,
        )
        .order_by(TrainingSession.scheduled_date)
    )
    sessions = sessions_result.scalars().all()
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete.id,
        )
    )
    attendance_by_session = {a.session_id: a for a in att_result.scalars().all()}

    entries: list[dict[str, Any]] = []
    for s in sessions:
        att = attendance_by_session.get(s.id)
        attended = bool(
            att is not None and att.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
        )
        rpe = att.rpe_omni if (attended and att is not None) else None
        rubric_avg = None
        if attended and att is not None:
            rubric_values = [
                v
                for v in (att.rubric_effort, att.rubric_attitude, att.rubric_technique)
                if v is not None
            ]
            if rubric_values:
                rubric_avg = round(sum(rubric_values) / len(rubric_values), 1)
        entries.append(
            {
                "date": s.scheduled_date.isoformat() if s.scheduled_date else None,
                "attended": attended,
                "rpe": rpe,
                "rubric_avg": rubric_avg,
            }
        )
    return entries


async def _build_next_focus_groups_block(
    db: AsyncSession,
    athlete: Any,
    month_end: date,
) -> list[dict[str, Any]]:
    """Bloque ``next_focus_groups`` (pdf_only, feature 038): focos técnicos
    de sesiones PLANIFICADAS en las próximas 4 semanas, agrupados por
    familia de habilidad (mismo agrupador ``group_focus_texts`` del bloque
    ``technical``, para dar consistencia visual entre "lo que se trabajó" y
    "lo que viene").
    """
    from app.models.training_session import SessionStatus, TrainingSession

    horizon_end = month_end + timedelta(days=28)
    sessions_result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.club_id == athlete.club_id,
            TrainingSession.scheduled_date > month_end,
            TrainingSession.scheduled_date <= horizon_end,
            TrainingSession.status == SessionStatus.PLANNED,
        )
    )
    sessions = sessions_result.scalars().all()
    raw_focus_texts = [s.technical_focus for s in sessions if s.technical_focus]
    groups = group_focus_texts(raw_focus_texts)
    return [{"slug": g.slug, "name": g.name, "session_count": g.session_count} for g in groups]


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


def _build_support_block(
    age_decimal: float | None,
    month: int,
    athlete_reference: str,
) -> dict[str, Any]:
    """Bloque 'Cómo apoyar desde casa': banda etaria + rotación mensual (R14).

    Selecciona la banda 10-12 vs 13-15 según ``age_decimal`` (< 13 → 10-12;
    ``None`` → 13-15 por defecto) y rota deterministamente entre las 2-3
    variantes de cada categoría según el mes (``month % len(variants)``),
    de modo que regenerar el mismo boletín produzca el mismo texto.
    Todas las variantes preservan los no-negociables: cero suplementos, sin
    conteo calórico, alimentación real como base.
    """
    from app.services.training.newsletter_static_copy import (
        SUPPORT_TIP_TITLES,
        SUPPORT_TIP_VARIANTS,
    )

    age_band = "10-12" if age_decimal is not None and age_decimal < 13 else "13-15"
    variants_by_category = SUPPORT_TIP_VARIANTS[age_band]

    tips = []
    rotation_index = 0
    for category, variants in variants_by_category.items():
        rotation_index = month % len(variants)
        text = variants[rotation_index].format(ref=athlete_reference)
        tips.append({
            "category": category,
            "title": SUPPORT_TIP_TITLES[category],
            "text": text,
        })

    return {
        "tips": tips,
        "age_band": age_band,
        "rotation_index": rotation_index,
    }


def _anthropometry_unavailable_reason(
    *,
    weight_kg: float | None,
    standing_height_cm: float | None,
    bmi: float | None,
    height_z_score: float | None,
    height_percentile: float | None,
    bmi_z_score: float | None,
    bmi_percentile: float | None,
    weight_z_score: float | None,
    weight_percentile: float | None,
) -> dict[str, str]:
    """Devuelve un diccionario con razones pedagógicas (español neutro, sin diagnóstico)
    para cada celda de la tabla que no tiene valor numérico disponible.

    Las razones son breves, informativas, y no implican ningún juicio sobre el atleta.
    Solo se incluyen entradas para campos genuinamente ausentes.
    """
    reasons: dict[str, str] = {}

    has_weight = weight_kg is not None
    has_height = standing_height_cm is not None

    if bmi is None:
        if not has_weight and not has_height:
            reasons["bmi"] = "Se requiere peso y talla para calcularlo"
        elif not has_weight:
            reasons["bmi"] = "Se requiere peso para calcularlo"
        elif not has_height:
            reasons["bmi"] = "Se requiere talla para calcularlo"

    _lms_missing_msg = "Fuera del rango de tablas de referencia para esta edad"

    if height_z_score is None or height_percentile is None:
        if not has_height:
            reasons["height_lms"] = "Se requiere talla para calcularlo"
        else:
            reasons["height_lms"] = _lms_missing_msg

    if bmi_z_score is None or bmi_percentile is None:
        if bmi is None:
            reasons["bmi_lms"] = "Se requiere IMC calculado"
        else:
            reasons["bmi_lms"] = _lms_missing_msg

    if weight_z_score is None or weight_percentile is None:
        if not has_weight:
            reasons["weight_lms"] = "Se requiere peso para calcularlo"
        else:
            reasons["weight_lms"] = _lms_missing_msg

    return reasons


# Interpretaciones pedagógicas del estado de maduración — español neutro, sin diagnóstico.
_MATURATION_PEDAGOGY: dict[str, str] = {
    "Pre-PHV": (
        "El deportista se encuentra en la etapa previa al pico de velocidad de crecimiento. "
        "Es un período ideal para consolidar habilidades técnicas y coordinativas."
    ),
    "Circa-PHV": (
        "El deportista está transitando el período de mayor velocidad de crecimiento. "
        "Se recomienda monitorear la carga de entrenamiento y dar prioridad a la técnica "
        "y la movilidad para acompañar los cambios corporales."
    ),
    "Post-PHV": (
        "El deportista ha superado el pico de velocidad de crecimiento. "
        "Este momento es propicio para consolidar la base aeróbica y continuar "
        "el desarrollo técnico con mayor estabilidad física."
    ),
}


async def _build_anthropometry_block(
    db: AsyncSession,
    athlete_id: int,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Antropometría completa: historial + implicaciones pedagógicas (solo PDF).

    NUNCA debe incluirse en email_blocks.

    Cada registro serializado incluye un campo opcional 'unavailable_reasons'
    (dict[str, str]) con explicaciones en español neutro para celdas sin valor.
    El registro 'latest' incluye además 'maturation_pedagogy' si hay estado PHV.
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
        bmi_val = float(r.bmi) if r.bmi is not None else None
        weight_val = float(r.weight_kg) if r.weight_kg is not None else None
        height_val = float(r.standing_height_cm) if r.standing_height_cm is not None else None
        height_z = float(r.height_z_score) if r.height_z_score is not None else None
        height_p = float(r.height_percentile) if r.height_percentile is not None else None
        bmi_z = float(r.bmi_z_score) if r.bmi_z_score is not None else None
        bmi_p = float(r.bmi_percentile) if r.bmi_percentile is not None else None
        weight_z = float(r.weight_z_score) if r.weight_z_score is not None else None
        weight_p = float(r.weight_percentile) if r.weight_percentile is not None else None

        unavailable_reasons = _anthropometry_unavailable_reason(
            weight_kg=weight_val,
            standing_height_cm=height_val,
            bmi=bmi_val,
            height_z_score=height_z,
            height_percentile=height_p,
            bmi_z_score=bmi_z,
            bmi_percentile=bmi_p,
            weight_z_score=weight_z,
            weight_percentile=weight_p,
        )

        serialized.append({
            "evaluation_date": r.evaluation_date.isoformat() if r.evaluation_date else None,
            "weight_kg": weight_val,
            "standing_height_cm": height_val,
            "sitting_height_cm": float(r.sitting_height_cm) if r.sitting_height_cm is not None else None,
            "bmi": bmi_val,
            "height_z_score": height_z,
            "height_percentile": height_p,
            "bmi_z_score": bmi_z,
            "bmi_percentile": bmi_p,
            "weight_z_score": weight_z,
            "weight_percentile": weight_p,
            "maturity_offset": float(r.maturity_offset) if r.maturity_offset is not None else None,
            "age_at_phv": float(r.age_at_phv) if r.age_at_phv is not None else None,
            "maturation_status": r.maturation_status.value if r.maturation_status else None,
            "nutritional_status": r.nutritional_status.value if r.nutritional_status else None,
            "training_implications": r.training_implications,
            # Razones pedagógicas para celdas sin valor — vacío si todo está disponible
            "unavailable_reasons": unavailable_reasons,
        })

    # Registro más reciente para el resumen
    latest = serialized[0]

    # Añadir interpretación pedagógica del estado PHV (español neutro, sin diagnóstico)
    maturation_status = latest.get("maturation_status")
    latest_with_pedagogy = {
        **latest,
        "maturation_pedagogy": _MATURATION_PEDAGOGY.get(maturation_status, ""),
    }

    return {
        "has_records": True,
        "records": serialized,
        "latest": latest_with_pedagogy,
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
    has_championship = any(row.get("series_kind") == "championship" for row in history)
    if not history:
        return {
            "has_data": False,
            "positions": [],
            "gap_pcts": [],
            "points_accumulated": [],
            "has_championship": has_championship,
        }

    positions = []
    gap_pcts = []
    points_acc = []
    acc = 0
    # El eje X usa un índice ordinal cronológico (1..N) — NO el valida_num —
    # para que el campeonato (sequence_number=1, spec 014) no colisione con la
    # Válida I ni se dibuje fuera de orden. La etiqueta visible viene de
    # ``label`` (V1..VN para copas, CD/CN para campeonatos). ``history`` ya
    # llega ordenado cronológicamente por event_date (athlete_progression).
    for idx, row in enumerate(history, start=1):
        v = row.get("valida_num")
        pos = row.get("position")
        gap = row.get("gap_to_winner_pct")
        pts = row.get("points_awarded", 0) or 0
        label = row.get("label") or _race_short_label(
            row.get("series_kind"), row.get("series_level"), v
        )
        acc += pts
        positions.append({"x": idx, "label": label, "y": pos})
        gap_pcts.append({"x": idx, "label": label, "y": gap})
        points_acc.append({"x": idx, "label": label, "y": acc})

    n_samples = len([p for p in positions if p["y"] is not None])

    return {
        "has_data": True,
        "n_samples": n_samples,
        "low_confidence": n_samples < 5,
        "positions": positions,
        "gap_pcts": gap_pcts,
        "points_accumulated": points_acc,
        "has_championship": has_championship,
    }
