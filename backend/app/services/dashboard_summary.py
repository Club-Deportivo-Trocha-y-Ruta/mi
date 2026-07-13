"""Agregados de solo lectura para el resumen del panel de mando del entrenador.

Backing del endpoint ``GET /api/dashboard/coach-summary``
(``app/routers/dashboard.py``). Cada agregado se calcula sobre tablas ya
existentes (no hay migración nueva) y vive en su propia función con su
propio ``try/except``: un fallo en un agregado no debe afectar a los otros
dos (``research.md`` R2/R4/R5, ``data-model.md`` §1, partial-failure
isolation). Cada función retorna ``None`` cuando su cálculo falla — nunca
``0``, que significa "cero pendientes" de forma legítima.

Privacidad: ningún agregado retorna nombres, fechas de nacimiento ni
contenido de sesiones — solo conteos y sumas de minutos (FR-010). Los logs
de error solo incluyen ids/conteos, nunca PII (misma convención que
``services/race/run_staleness.py``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.athlete import Athlete
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.parental_consent import ParentalConsent
from app.models.training_session import SessionAttendance, SessionStatus, TrainingSession
from app.schemas.dashboard import WeeklyLoadBandOut
from app.services.category import compute_age_decimal
from app.services.privacy import get_active_policy

logger = logging.getLogger(__name__)

# El club opera en horario de Colombia; la semana ISO (lunes-domingo) del
# "carga semanal" se calcula desde "hoy" en esta zona, no desde la fecha
# naive del contenedor — evita cruzar mal el límite domingo-noche/lunes en
# el horario vespertino de Bogotá (UTC-5). Sigue el mismo idiom inline ya
# usado en 17 archivos del backend (p.ej. ``services/calendar/birthdays.py``),
# per research.md R3.
_BOGOTA_TZ = ZoneInfo("America/Bogota")

# Tope fijo por banda = edad mínima de la banda × 60 minutos (CLAUDE.md
# regla no negociable #4: "horas semanales ≤ edad del atleta"). No se deriva
# de la mezcla de edades realmente presente esta semana — un tope
# conservador fijo protege al atleta más joven/vulnerable de la banda
# (research.md R3).
_BAND_CAP_MINUTES: dict[str, int] = {
    "10-12": 600,
    "13-15": 780,
}


def _age_to_band(age_decimal: float) -> str | None:
    """Bandea una edad decimal a "10-12"/"13-15", o None fuera de rango."""
    if 10 <= age_decimal < 13:
        return "10-12"
    if 13 <= age_decimal < 16:
        return "13-15"
    return None


async def compute_consents_pending(
    db: AsyncSession,
    club_ids: set[int] | None,
) -> int | None:
    """Cuenta atletas del club sin consentimiento vigente en la política activa.

    "Vigente" reutiliza la semántica exacta de
    ``get_current_consent_for_athlete`` (``services/privacy.py``)
    vectorizada sobre el roster en vez de por atleta: pendiente = conteo de
    atletas del club menos ``COUNT(DISTINCT athlete_id)`` de
    ``parental_consents`` con ``withdrawn_at IS NULL`` para la política
    activa (``research.md`` R4). ``club_ids=None`` significa sin acotar
    (vista admin sin ``club_id``, mismo precedente que ``alerts.py``).

    Retorna ``None`` (nunca ``0``) si el cálculo falla — ``0`` es una
    respuesta legítima ("cero pendientes"), no un valor de error.
    """
    try:
        athlete_filters = []
        if club_ids is not None:
            athlete_filters.append(Athlete.club_id.in_(club_ids))

        total_athletes = (
            await db.execute(select(func.count(Athlete.id)).where(*athlete_filters))
        ).scalar_one()

        active_policy = await get_active_policy(db)

        consent_filters = [
            ParentalConsent.withdrawn_at.is_(None),
            ParentalConsent.policy_id == active_policy.id,
        ]
        if club_ids is not None:
            consent_filters.append(
                ParentalConsent.athlete_id.in_(
                    select(Athlete.id).where(Athlete.club_id.in_(club_ids))
                )
            )

        consented_athletes = (
            await db.execute(
                select(
                    func.count(func.distinct(ParentalConsent.athlete_id))
                ).where(*consent_filters)
            )
        ).scalar_one()

        return max(total_athletes - consented_athletes, 0)
    except Exception:
        logger.exception(
            "dashboard.consents_pending: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None


async def compute_insights_stale(
    db: AsyncSession,
    club_ids: set[int] | None,
) -> int | None:
    """Cuenta atletas del club cuyo insight activo proviene de un run "stale".

    Un insight activo (``athlete_ai_insights.is_active = 1``) es stale si el
    ``AgentRun`` del que proviene tiene ``stale_since IS NOT NULL``. Esto
    refleja, agregado a nivel de club sin fan-out por atleta, exactamente lo
    que el campo por-atleta ``stale_run_id`` ya expone al frontend
    (``research.md`` R5).

    Retorna ``None`` si el cálculo falla.
    """
    try:
        filters = [
            AthleteAiInsight.is_active == 1,
            AgentRun.stale_since.is_not(None),
        ]
        if club_ids is not None:
            filters.append(
                AthleteAiInsight.athlete_id.in_(
                    select(Athlete.id).where(Athlete.club_id.in_(club_ids))
                )
            )

        stmt = (
            select(func.count(func.distinct(AthleteAiInsight.athlete_id)))
            .select_from(AthleteAiInsight)
            .join(AgentRun, AgentRun.id == AthleteAiInsight.agent_run_id)
            .where(*filters)
        )
        return (await db.execute(stmt)).scalar_one()
    except Exception:
        logger.exception(
            "dashboard.insights_stale: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None


async def compute_weekly_load(
    db: AsyncSession,
    club_ids: set[int] | None,
) -> list[WeeklyLoadBandOut] | None:
    """Suma minutos planificados de la semana ISO actual, por banda de edad.

    Banda = "10-12"/"13-15" vía ``compute_age_decimal``
    (``services/category.py``), calculada sobre "hoy" en
    ``ZoneInfo("America/Bogota")`` (no ``date.today()`` naive — ver
    ``_BOGOTA_TZ`` arriba). Semana = lunes-domingo que contiene esa fecha.

    Atribución: una sesión "planned" atribuye su ``duration_min`` completo a
    cada banda que tenga al menos un convocado (``session_attendances``, ya
    poblado en la creación de la sesión) — una sesión conjunta cuenta hacia
    AMBAS bandas, sin duplicarse dentro de una misma banda si convoca a
    varios atletas de esa banda (dedupe por ``(session_id, band)``,
    ``research.md`` R3).

    Una banda con cero atletas en el club se **omite** del resultado (no se
    incluye con valores en cero) — distingue "nadie que seguir" de
    "seguido, en cero esta semana" (``data-model.md`` §1).

    Retorna ``None`` si el cálculo falla; ``[]`` si el club no tiene
    atletas en ninguna banda 10-15 (respuesta válida, no error).
    """
    try:
        today_bogota = datetime.now(_BOGOTA_TZ).date()
        week_start = today_bogota - timedelta(days=today_bogota.weekday())
        week_end = week_start + timedelta(days=6)

        athlete_filters = []
        if club_ids is not None:
            athlete_filters.append(Athlete.club_id.in_(club_ids))

        athlete_rows = (
            await db.execute(
                select(Athlete.id, Athlete.birth_date).where(*athlete_filters)
            )
        ).all()

        band_by_athlete_id: dict[int, str] = {}
        athlete_count_by_band: dict[str, int] = {"10-12": 0, "13-15": 0}
        for athlete_id, birth_date in athlete_rows:
            age_decimal = compute_age_decimal(birth_date, reference_date=today_bogota)
            band = _age_to_band(age_decimal)
            if band is None:
                continue
            band_by_athlete_id[athlete_id] = band
            athlete_count_by_band[band] += 1

        if not band_by_athlete_id:
            return []

        session_filters = [
            TrainingSession.status == SessionStatus.PLANNED,
            TrainingSession.scheduled_date >= week_start,
            TrainingSession.scheduled_date <= week_end,
            SessionAttendance.athlete_id.in_(list(band_by_athlete_id)),
        ]
        if club_ids is not None:
            session_filters.append(TrainingSession.club_id.in_(club_ids))

        session_rows = (
            await db.execute(
                select(
                    TrainingSession.id,
                    TrainingSession.duration_min,
                    SessionAttendance.athlete_id,
                )
                .join(
                    SessionAttendance,
                    SessionAttendance.session_id == TrainingSession.id,
                )
                .where(*session_filters)
            )
        ).all()

        # DISTINCT (session_id, band) antes de sumar: evita contar dos veces
        # la misma sesión dentro de una misma banda cuando convoca a varios
        # atletas de esa banda (el valor de duration_min es el mismo para
        # cualquier fila de esa sesión, así que sobreescribir es seguro).
        minutes_by_session_band: dict[tuple[int, str], int] = {}
        for session_id, duration_min, athlete_id in session_rows:
            band = band_by_athlete_id.get(athlete_id)
            if band is None:
                continue
            minutes_by_session_band[(session_id, band)] = duration_min

        planned_minutes_by_band: dict[str, int] = {"10-12": 0, "13-15": 0}
        for (_session_id, band), duration_min in minutes_by_session_band.items():
            planned_minutes_by_band[band] += duration_min

        bands: list[WeeklyLoadBandOut] = []
        for band in ("10-12", "13-15"):
            athlete_count = athlete_count_by_band[band]
            if athlete_count == 0:
                continue
            bands.append(
                WeeklyLoadBandOut(
                    age_band=band,  # type: ignore[arg-type]
                    planned_minutes=planned_minutes_by_band[band],
                    cap_minutes=_BAND_CAP_MINUTES[band],
                    athlete_count=athlete_count,
                )
            )
        return bands
    except Exception:
        logger.exception(
            "dashboard.weekly_load: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None
