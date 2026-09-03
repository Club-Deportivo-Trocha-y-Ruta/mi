"""Loaders de contexto por-atleta para el grafo agéntico v3 (feature 037, T103).

Reúnen datos que ya existen en la plataforma pero nunca llegaban al prompt
del analista: antropometría (solo maduración, jamás peso/IMC/estado
nutricional), la ventana de entrenamiento previa a la carrera analizada y el
catálogo del club (plantillas de intervalos) para que las acciones sugeridas
referencien recursos reales.

Todas las funciones son ``async``, reciben una ``AsyncSession`` ya abierta y
son de solo lectura (nunca ``commit``/``flush`` — el caller es dueño de la
transacción). Cada loader documenta explícitamente qué claves NUNCA incluye
por privacidad (peso, IMC, estado nutricional, nombres reales de otros
menores).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, ParentAthlete
from app.models.training_session import SessionAttendance, TrainingSession
from app.models.user import User
from app.services.measurement_alerts import calculate_growth_velocity, detect_approaching_circa
from app.services.intervals import templates as interval_templates_service
from app.services.training.focus_grouping import group_focus_texts

logger = logging.getLogger(__name__)

# Estatus de asistencia considerados "presencia" real vs. ausencia justificada
# vs. ausencia sin justificar (feature 037 data-model.md §TrainingWindow).
_ATTENDED_STATUSES = {"presente", "tarde"}
_EXCUSED_STATUSES = {"justificado", "lesionado"}
_ABSENT_STATUSES = {"ausente"}

_STALE_MEASUREMENT_DAYS = 120
_MAX_COACH_FEEDBACK_ITEMS = 3
_COACH_FEEDBACK_MAX_CHARS = 200
_MAX_TECHNICAL_FOCI = 6


def age_band_from_age(age_decimal: float) -> str:
    """Mapea edad decimal → banda de edad del catálogo (``AgeBand``).

    Regla (data-model.md §037 T103): <10 → ``"7-9"``, 10-12 → ``"10-12"``,
    ≥13 → ``"13-15"``.
    """
    if age_decimal < 10:
        return "7-9"
    if age_decimal < 13:
        return "10-12"
    return "13-15"


async def load_anthro_context(
    db: Any, athlete_id: int, reference_date: date
) -> dict[str, Any] | None:
    """Carga el contexto de maduración del atleta, sin peso/IMC/nutrición.

    Args:
        db: sesión async activa.
        athlete_id: atleta objetivo.
        reference_date: fecha de corte — se prefieren registros con
            ``evaluation_date <= reference_date``; si no existe ninguno, se
            usa el registro POSTERIOR más cercano marcado con el flag
            ``measured_after_event`` y ``days_before_event`` negativo.

    Returns:
        ``None`` cuando el atleta no tiene registros hasta esa fecha (el nodo
        debe listarlo en ``data_gaps``, nunca inventar maduración). En caso
        contrario, el dict ``AnthroContext`` de data-model.md §AnthroContext.
        NUNCA incluye ``weight_kg``, ``bmi``, ``nutritional_status`` ni
        z-scores de peso.
    """
    result = await db.execute(
        select(AnthropometricRecord)
        .where(
            AnthropometricRecord.athlete_id == athlete_id,
            AnthropometricRecord.evaluation_date <= reference_date,
        )
        .order_by(AnthropometricRecord.evaluation_date.desc())
    )
    records = list(result.scalars().all())
    measured_after_event = False
    if not records:
        # Sin medición previa a la carrera: usar la más cercana POSTERIOR como
        # aproximación explícita (flag ``measured_after_event``) en vez de
        # declarar "sin datos" cuando el atleta sí tiene antropometría. Un
        # análisis retrospectivo de enero con la medición de agosto es mejor
        # que ninguna, siempre que se diga que es posterior.
        result = await db.execute(
            select(AnthropometricRecord)
            .where(
                AnthropometricRecord.athlete_id == athlete_id,
                AnthropometricRecord.evaluation_date > reference_date,
            )
            .order_by(AnthropometricRecord.evaluation_date.asc())
            .limit(1)
        )
        after = result.scalar_one_or_none()
        if after is None:
            return None
        records = [after]
        measured_after_event = True

    latest = records[0]
    previous = records[1] if len(records) > 1 else None

    maturity_offset_years = float(latest.maturity_offset)
    days_before_event = (reference_date - latest.evaluation_date).days

    growth_velocity_cm_per_year: float | None = None
    velocity_cm_per_month = calculate_growth_velocity(latest, previous)
    if velocity_cm_per_month is not None:
        growth_velocity_cm_per_year = round(velocity_cm_per_month * 12, 2)

    flags: list[str] = []
    if detect_approaching_circa(maturity_offset_years):
        flags.append("approaching_circa_phv")
    if days_before_event > _STALE_MEASUREMENT_DAYS:
        flags.append("stale_measurement_gt_120d")
    if measured_after_event:
        flags.append("measured_after_event")

    latest_status = latest.maturation_status
    latest_block: dict[str, Any] = {
        "evaluation_date": latest.evaluation_date.isoformat(),
        "days_before_event": days_before_event,
        "maturity_offset_years": maturity_offset_years,
        "age_at_phv": float(latest.age_at_phv),
        "maturation_status": (
            latest_status.value if hasattr(latest_status, "value") else latest_status
        ),
        "height_percentile": (
            float(latest.height_percentile) if latest.height_percentile is not None else None
        ),
    }

    previous_block: dict[str, Any] | None = None
    if previous is not None:
        previous_status = previous.maturation_status
        previous_block = {
            "evaluation_date": previous.evaluation_date.isoformat(),
            "maturity_offset_years": float(previous.maturity_offset),
            "maturation_status": (
                previous_status.value if hasattr(previous_status, "value") else previous_status
            ),
        }

    return {
        "records_count": len(records),
        "latest": latest_block,
        "previous": previous_block,
        "growth_velocity_cm_per_year": growth_velocity_cm_per_year,
        "months_from_phv": round(maturity_offset_years * 12, 1),
        "flags": flags,
    }


def _bucket_attendance_status(status: Any) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    value = (value or "").lower()
    if value in _ATTENDED_STATUSES:
        return "attended"
    if value in _EXCUSED_STATUSES:
        return "excused"
    return "absent"


async def load_training_window(
    db: Any,
    athlete_id: int,
    club_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, Any] | None:
    """Agrega asistencia/RPE/rúbricas/foco técnico en ``[date_from, date_to]``.

    Args:
        db: sesión async activa.
        athlete_id: atleta objetivo.
        club_id: club del atleta — filtra las sesiones (defensa adicional
            contra fugas cross-club).
        date_from / date_to: rango inclusivo de ``scheduled_date``.

    Returns:
        ``None`` cuando el atleta no tiene ninguna fila de asistencia en la
        ventana (el nodo/analista debe listarlo en ``data_gaps``, nunca
        inventar un entrenamiento). En caso contrario, el dict
        ``TrainingWindow`` de data-model.md §TrainingWindow.
    """
    stmt = (
        select(SessionAttendance)
        .join(TrainingSession, SessionAttendance.session_id == TrainingSession.id)
        .where(
            SessionAttendance.athlete_id == athlete_id,
            TrainingSession.club_id == club_id,
            TrainingSession.scheduled_date >= date_from,
            TrainingSession.scheduled_date <= date_to,
        )
        .options(
            selectinload(SessionAttendance.session).selectinload(
                TrainingSession.interval_structure
            ),
        )
        .order_by(TrainingSession.scheduled_date.asc())
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().unique().all())
    if not rows:
        return None

    attended = excused = absent = 0
    attended_minutes = 0
    rpe_values: list[float] = []
    rpe_last7: list[float] = []
    rpe_prev21: list[float] = []
    effort_values: list[float] = []
    attitude_values: list[float] = []
    technique_values: list[float] = []
    focus_texts: list[str] = []
    interval_sessions = 0
    scheduled_dates: list[date] = []
    feedback_candidates: list[tuple[date, str]] = []

    last7_cutoff = date_to - _days_delta(7)

    for row in rows:
        session = row.session
        bucket = _bucket_attendance_status(row.status)
        if bucket == "attended":
            attended += 1
            attended_minutes += session.duration_min or 0
        elif bucket == "excused":
            excused += 1
        else:
            absent += 1

        if session.scheduled_date is not None:
            scheduled_dates.append(session.scheduled_date)

        if row.rpe_omni is not None:
            rpe_values.append(float(row.rpe_omni))
            if session.scheduled_date is not None and session.scheduled_date > last7_cutoff:
                rpe_last7.append(float(row.rpe_omni))
            else:
                rpe_prev21.append(float(row.rpe_omni))
        if row.rubric_effort is not None:
            effort_values.append(float(row.rubric_effort))
        if row.rubric_attitude is not None:
            attitude_values.append(float(row.rubric_attitude))
        if row.rubric_technique is not None:
            technique_values.append(float(row.rubric_technique))

        if session.technical_focus:
            focus_texts.append(session.technical_focus)

        if session.interval_structure is not None:
            interval_sessions += 1

        if row.individual_feedback and session.scheduled_date is not None:
            feedback_candidates.append((session.scheduled_date, row.individual_feedback))

    sessions_in_window = len(rows)
    attendance_pct = (
        round(attended / sessions_in_window * 100, 1) if sessions_in_window else None
    )
    training_hours = round(attended_minutes / 60, 2) if attended_minutes else None

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    focus_groups = group_focus_texts(focus_texts)
    technical_foci = [g.name for g in focus_groups[:_MAX_TECHNICAL_FOCI]]

    days_since_last_session = (
        (date_to - max(scheduled_dates)).days if scheduled_dates else None
    )

    feedback_candidates.sort(key=lambda item: item[0], reverse=True)
    coach_feedback = [
        text[:_COACH_FEEDBACK_MAX_CHARS]
        for _d, text in feedback_candidates[:_MAX_COACH_FEEDBACK_ITEMS]
    ]

    return {
        "window_days": (date_to - date_from).days,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "sessions_in_window": sessions_in_window,
        "attended": attended,
        "absent": absent,
        "excused": excused,
        "attendance_pct": attendance_pct,
        "training_hours": training_hours,
        "rpe_mean": _mean(rpe_values),
        "rpe_last7_mean": _mean(rpe_last7),
        "rpe_prev21_mean": _mean(rpe_prev21),
        "rubric_effort_mean": _mean(effort_values),
        "rubric_attitude_mean": _mean(attitude_values),
        "rubric_technique_mean": _mean(technique_values),
        "technical_foci": technical_foci,
        "interval_sessions": interval_sessions,
        "days_since_last_session": days_since_last_session,
        "days_since_previous_race": None,  # reserva — la puebla el nodo (necesita fechas de carrera)
        "coach_feedback": coach_feedback,
        "strava_load": None,  # reserva (fuera de alcance — spec.md §Out of scope)
    }


def _days_delta(days: int):
    from datetime import timedelta

    return timedelta(days=days)


async def load_catalog_context(
    db: Any, club_id: int, age_band: str | None
) -> dict[str, Any]:
    """Carga el catálogo (plantillas de intervalos) del club.

    ``interval_templates`` es scoped por club, y se filtra adicionalmente por
    ``age_band`` cuando se provee (banda del atleta objetivo).
    """
    templates_age_band = None
    if age_band is not None:
        from app.models.interval_structure import AgeBand

        try:
            templates_age_band = AgeBand(age_band)
        except ValueError:
            templates_age_band = None
    templates, _total_templates = await interval_templates_service.list_templates(
        db, club_id=club_id, age_band=templates_age_band
    )

    return {
        "interval_templates": [
            {
                "id": t.id,
                "name": t.name,
                "age_band": getattr(t.target_age_band, "value", t.target_age_band),
                "mesocycle_phase": t.mesocycle_phase,
            }
            for t in templates
        ],
    }


async def load_club_forbidden_names(db: Any, club_id: int) -> list[str]:
    """Carga los nombres reales a prohibir a nivel de TODO el club.

    Extiende :func:`app.services.race.ai.grounding.load_forbidden_names`
    (que solo cubre al atleta analizado + sus padres) a superset: nombres de
    TODOS los atletas del club y de sus padres/acudientes. Necesario porque
    ``training_window.coach_feedback`` y el texto libre de sesiones pueden
    mencionar a compañeros de equipo, no solo al atleta objetivo.

    Best-effort: si la consulta falla devuelve la lista parcial acumulada (o
    vacía), nunca rompe el lanzamiento. NUNCA se pasa al LLM — solo alimenta
    scrubbing/guardrails post-generación.
    """
    names: list[str] = []
    try:
        athlete_rows = await db.execute(
            select(func.concat(User.first_name, " ", User.last_name), Athlete.id)
            .join(Athlete, Athlete.user_id == User.id)
            .where(Athlete.club_id == club_id)
        )
        athlete_ids: list[int] = []
        for full_name, athlete_id in athlete_rows.all():
            if full_name:
                names.append(str(full_name))
            athlete_ids.append(athlete_id)

        if athlete_ids:
            parent_rows = await db.execute(
                select(func.concat(User.first_name, " ", User.last_name))
                .join(ParentAthlete, User.id == ParentAthlete.parent_id)
                .where(ParentAthlete.athlete_id.in_(athlete_ids))
            )
            for prow in parent_rows.scalars().all():
                if prow:
                    names.append(str(prow))
    except Exception:  # noqa: BLE001
        logger.warning(
            "load_club_forbidden_names: no se pudieron cargar nombres para club %d; "
            "se usa la lista parcial acumulada.",
            club_id,
            exc_info=True,
        )
    return names


__all__ = [
    "age_band_from_age",
    "load_anthro_context",
    "load_training_window",
    "load_catalog_context",
    "load_club_forbidden_names",
]
