"""Agregados de solo lectura para el resumen del panel de mando del entrenador.

Backing del endpoint ``GET /api/dashboard/coach-summary``
(``app/routers/dashboard.py``). Cada agregado se calcula sobre tablas ya
existentes (no hay migración nueva) y vive en su propia función con su
propio ``try/except``: un fallo en un agregado no debe afectar a los otros
(``research.md`` R2/R4/R5, ``data-model.md`` §1, partial-failure isolation).
Cada función retorna ``None`` cuando su cálculo falla — nunca ``0``, que
significa "cero pendientes" de forma legítima.

Feature 045 (US5) suma tres conteos de «Pendientes»: decisiones de identidad,
cargas en curso y análisis por aprobar; FR-033 suma los competidores sin enlazar
(insignia de «Cargas e identidades»). ``insights_stale`` y
``analyses_awaiting_approval`` delegan en
``services/race/pending_analyses.py``, la misma especificación que arma la
lista ``GET /api/race-analysis/pending-analyses`` (SC-005).

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

from app.models.athlete import Athlete
from app.models.club import ClubMember, ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.race_identity_candidate import IdentityCandidateState, RaceIdentityCandidate
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.training_session import SessionAttendance, SessionStatus, TrainingSession
from app.schemas.dashboard import WeeklyLoadBandOut
from app.schemas.race_pending_analyses import PendingAnalysisState
from app.services.category import compute_age_decimal
from app.services.privacy import get_active_policy
from app.services.race.competitor_linking import count_unlinked_competitors
from app.services.race.pending_analyses import count_pending_analyses

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
        athlete_filters = [Athlete.deleted_at.is_(None)]
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
        consent_athlete_filters = [Athlete.deleted_at.is_(None)]
        if club_ids is not None:
            consent_athlete_filters.append(Athlete.club_id.in_(club_ids))
        consent_filters.append(
            ParentalConsent.athlete_id.in_(
                select(Athlete.id).where(*consent_athlete_filters)
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
    """Cuenta los análisis desactualizados (stale) de los atletas del club.

    Un análisis es stale si el ``AgentRun`` del que proviene un insight activo
    (``athlete_ai_insights.is_active = 1``) tiene ``stale_since IS NOT NULL``
    — el mismo concepto que expone por-run ``StaleAnalysisBadge`` en el
    frontend (``services/race/run_staleness.py``).

    Unidad de conteo (feature 045, SC-005): un **run**, no un atleta. Antes
    contaba atletas distintos; un atleta con dos análisis desactualizados (dos
    válidas) sumaba 1 aunque la lista que abre la fila mostrara 2. La cuenta y
    la lista salen ahora de la misma especificación
    (``pending_analyses._membership_stmt``); con un solo análisis stale por
    atleta el valor es idéntico al anterior.

    Retorna ``None`` si el cálculo falla.
    """
    try:
        return await count_pending_analyses(db, PendingAnalysisState.stale, club_ids)
    except Exception:
        logger.exception(
            "dashboard.insights_stale: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None


async def compute_analyses_awaiting_approval(
    db: AsyncSession,
    club_ids: set[int] | None,
) -> int | None:
    """Cuenta los análisis IA que esperan la aprobación del coach (HITL).

    ``AgentRun.status == awaiting_hitl`` de atletas vigentes del club. La lista
    ``GET /api/race-analysis/pending-analyses?state=awaiting_approval`` sale de
    la misma especificación, así que ambas cifras coinciden por construcción.

    Retorna ``None`` si el cálculo falla.
    """
    try:
        return await count_pending_analyses(
            db, PendingAnalysisState.awaiting_approval, club_ids
        )
    except Exception:
        logger.exception(
            "dashboard.analyses_awaiting_approval: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None


async def compute_identity_decisions_pending(db: AsyncSession) -> int | None:
    """Cuenta los candidatos de identidad ``pending`` de la cola.

    Es la cola completa (``data-model.md`` §7), sin acotar por club: los
    candidatos son pares de competidores de carreras de terceros, y el rebuild
    ya descarta los que no involucran a un atleta del club
    (``identity_review.remove_out_of_scope``). Es un conteo del badge del
    inbox; el detalle de los pares no sale de aquí.

    Retorna ``None`` si el cálculo falla.
    """
    try:
        stmt = select(func.count(RaceIdentityCandidate.id)).where(
            RaceIdentityCandidate.state == IdentityCandidateState.pending
        )
        return int((await db.execute(stmt)).scalar_one())
    except Exception:
        logger.exception("dashboard.identity_decisions_pending: fallo calculando agregado")
        return None


async def compute_imports_in_progress(
    db: AsyncSession,
    club_ids: set[int] | None,
) -> int | None:
    """Cuenta las cargas de resultados en curso (``pending`` o ``dry_run``).

    Se cuentan solo esos dos estados de forma explícita — no "todo menos
    committed/failed" — para que un estado nuevo (p. ej. ``discarded``, que el
    coach abandona a propósito) nunca infle el badge.

    Las carreras no tienen ``club_id``: el vínculo con el club es la membresía
    (coach/admin) de quien subió el archivo, la misma regla de alcance del
    listado ``GET /api/race-analysis/imports/`` (``import_club_ids``).
    ``club_ids=None`` no acota (admin sin ``club_id``).

    Retorna ``None`` si el cálculo falla.
    """
    try:
        stmt = select(func.count(RaceImport.id)).where(
            RaceImport.status.in_((RaceImportStatus.pending, RaceImportStatus.dry_run))
        )
        if club_ids is not None:
            stmt = stmt.where(
                RaceImport.imported_by_user_id.in_(
                    select(ClubMember.user_id).where(
                        ClubMember.club_id.in_(club_ids),
                        ClubMember.role_in_club.in_([ClubRole.coach, ClubRole.admin]),
                    )
                )
            )
        return int((await db.execute(stmt)).scalar_one())
    except Exception:
        logger.exception(
            "dashboard.imports_in_progress: fallo calculando agregado (club_ids=%s)",
            club_ids,
        )
        return None


async def compute_unlinked_competitors_pending(db: AsyncSession) -> int | None:
    """Cuenta los competidores sin enlazar que esperan acción del coach.

    Es exactamente el ``total`` que devuelve la lista «Sin enlazar» de
    «Cargas e identidades» (``GET /api/race-competitors/?unlinked=true
    &club_filter=trocha``): ambos parten de
    ``competitor_linking._unlinked_base_stmt`` y del mismo filtro de club, así
    que la insignia y la lista coinciden por construcción (SC-005).

    Los competidores de carreras no tienen ``club_id``; el alcance de club es el
    filtro «Trocha y Ruta» (``club_text``), el mismo default de la lista — por
    eso no depende de ``club_ids``, igual que ``identity_decisions_pending``.

    Retorna ``None`` si el cálculo falla.
    """
    try:
        return await count_unlinked_competitors(db)
    except Exception:
        logger.exception("dashboard.unlinked_competitors_pending: fallo calculando agregado")
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

        athlete_filters = [Athlete.deleted_at.is_(None)]
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
