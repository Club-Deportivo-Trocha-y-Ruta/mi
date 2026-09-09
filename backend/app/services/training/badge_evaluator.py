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
    first_podium   — Primer podio real (posición ≤3) histórico del atleta, y
                     solo si esa posición es creíble contra la parrilla real
                     (ver `_is_credible_position`). Copa Valle XCO juvenil
                     premia hasta el puesto 5 en puntos, pero el boletín
                     familiar usa el podio clásico (1-3): con parrillas de
                     5-7 corredoras (ver abajo), "Top 5" solo significaba "no
                     llegar último" — decisión del entrenador, 2026-09-08.
    mtp            — Mejor Tiempo Personal en una carrera del periodo
    top10          — Posición ≤10 en alguna carrera del periodo, y solo si la
                     parrilla misma es lo bastante grande para que la
                     ETIQUETA "Top 10" tenga sentido (ver
                     `_min_credible_field_size`) — no basta con que la
                     posición sea relativamente buena.

Insignias de posición usan DOS criterios distintos, porque el defecto que
reportó el entrenador tenía dos caras (posición vacía Y etiqueta absurda):

  - `first_podium` (posición ≤3): exige que la posición sea creíble CONTRA
    LA PARRILLA REAL de esa carrera (``_is_credible_position``, percentil —
    "mitad delantera"). La etiqueta ("Primer podio") no promete un tamaño de
    parrilla, así que un P2 o P3 en una categoría de 6 corredoras sigue
    siendo un podio real y se otorga.
  - `top10` (posición ≤10): la etiqueta SÍ promete un tamaño ("10"), y esa
    promesa es falsa si la parrilla real es de 6-7 corredoras — no importa
    qué tan buena haya sido la posición relativa. Por eso exige que la
    parrilla ABSOLUTA sea lo bastante grande (``_min_credible_field_size``),
    en vez del criterio relativo de `first_podium`. Con las parrillas reales
    del club (5-13, ver `_min_credible_field_size`) esto significa que
    `top10` prácticamente nunca se otorga — es el comportamiento correcto,
    no un defecto: la insignia queda reservada para categorías/eventos con
    pelotones genuinamente grandes.

Ambos criterios usan `field_size` = corredores FINISHED en esa
categoría/válida (mismo criterio que ``app/services/race/field_metrics.py``
y ``analytics_charts.py``).
"""

from __future__ import annotations

import calendar
import logging
import math
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete_badge import AthleteBadge, BadgeSource, BadgeType
from app.models.training_session import AttendanceStatus, SessionAttendance, SessionStatus, TrainingSession

logger = logging.getLogger(__name__)

# Thresholds de asistencia
_ATTENDANCE_100 = 100.0
_ATTENDANCE_90 = 90.0
_ATTENDANCE_75 = 75.0


# Mínimo absoluto de corredores en la parrilla para evaluar cualquier
# insignia de posición — evita casos degenerados (parrilla de 2-3, donde
# "medio pelotón" no dice nada). Ninguna carrera real del club ha bajado de
# 5, así que este piso no debería activarse en la práctica: es una red de
# seguridad para datos atípicos, no el criterio principal.
_MIN_ABSOLUTE_FIELD_SIZE = 4


def _is_credible_position(position: int, field_size: int) -> bool:
    """¿La `position` obtenida es creíble frente a la `field_size` real?

    Usada SOLO por `first_podium` (podio real, posición ≤3 — ver
    `_evaluate_race_badges` y `_min_credible_field_size` para el criterio de
    `top10`, que es distinto a propósito).

    Regla: la posición debe caer en la mitad delantera de la parrilla real
    (``position <= field_size / 2``, comparado sin división para evitar
    ambigüedad de redondeo: ``position * 2 <= field_size``), con un piso
    absoluto de `_MIN_ABSOLUTE_FIELD_SIZE` corredores. La etiqueta "Primer
    podio" no promete un tamaño de parrilla — solo que el atleta quedó
    genuinamente por delante de una porción real del pelotón — así que un
    umbral relativo (percentil) es lo correcto acá, a diferencia de `top10`
    (ver `_min_credible_field_size`), cuya etiqueta sí promete un tamaño y
    por eso exige un umbral absoluto de parrilla en vez de este.

    Para el podio (peor caso, posición 3) esto exige parrilla ≥6 —
    "suficientemente mayor que 3" en los términos que pidió el entrenador.
    Validado contra los 7 resultados reales de una temporada 2026 completa:

        P4/7, P4/6, P4/5, P11/13  → no creíble (quedó en la mitad trasera)
        P3/6, P2/6                → creíble (mitad delantera) → podio real
        P5/7 (caso reportado por el entrenador, recibió "Top 10" indebido)
                                   → no creíble — 2 corredoras detrás de 6
                                     rivales no sostiene ni siquiera el podio
        P3/3 ("podio de 3 en parrilla de 3", ejemplo del entrenador)
                                   → no creíble — bajo el piso absoluto,
                                     3er puesto de 3 es simplemente el último

    Si `field_size` es 0 (desconocida, ver `_field_size` en el llamador) o
    menor al piso absoluto, se retiene la insignia (conservador): es
    preferible no otorgarla a que la familia la lea como inflada.
    """
    if field_size < _MIN_ABSOLUTE_FIELD_SIZE:
        return False
    return position * 2 <= field_size


def _min_credible_field_size(n: int) -> int:
    """Tamaño mínimo de parrilla para que la ETIQUETA "Top N" no sea falsa.

    Usada SOLO por `top10` (ver `_is_credible_position` para el criterio de
    `first_podium`, que es distinto a propósito). A diferencia del podio, la
    etiqueta "Top 10" promete literalmente un tamaño de parrilla — decirlo
    en una categoría de 6-7 corredoras es una afirmación falsa sin importar
    qué tan buena haya sido la posición relativa (el entrenador reportó
    justo eso: un P2 de 6, aunque sea un resultado excelente, no sostiene la
    palabra "10"). Por eso este criterio NO mira la posición obtenida, solo
    si la parrilla en sí es lo bastante grande.

    Regla: la parrilla debe ser al menos 1.5× N, con un colchón mínimo
    absoluto de 3 corredores adicionales a N:

        top10 (N=10) → parrilla ≥ 15

    Con las parrillas reales del club (5-13 corredoras, hasta ~13 en un
    campeonato nacional — ver `_is_credible_position`) esto significa que
    `top10` prácticamente nunca se otorga. Es la consecuencia esperada, no
    un defecto: verificado contra los 7 resultados reales de una temporada
    2026 completa, ninguno alcanza parrilla ≥15, así que `top10` no aparece
    en ninguno — incluido el Campeonato Nacional (parrilla 13).
    """
    return n + max(math.ceil(n / 2), 3)


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
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]
    att_result = await db.execute(
        select(SessionAttendance).where(
            SessionAttendance.session_id.in_(session_ids),
            SessionAttendance.athlete_id == athlete_id,
        )
    )
    attendances = att_result.scalars().all()

    # Solo cuentan sesiones donde el atleta fue convocado (tiene registro).
    # Si no fue convocado, no debe penalizar su % asistencia.
    total = len(attendances)
    if total == 0:
        return []

    present = sum(
        1
        for a in attendances
        if a.status in {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
    )
    pct = round(present / total * 100, 1)

    # Fecha de cumplimiento del criterio (no "ahora"): la última sesión en la
    # que el atleta fue convocado dentro del periodo — el mismo conjunto de
    # sesiones que compone el denominador de `pct` arriba. El % de asistencia
    # del mes solo queda determinado una vez ocurrida esa sesión, así que es
    # la fecha real en que se ganó el badge, no la fecha en que se generó el
    # boletín. Determinística: reevaluar el mismo periodo con los mismos
    # datos siempre produce la misma fecha (ver `_upsert_badge`).
    session_dates_by_id = {s.id: s.scheduled_date for s in sessions}
    earned_date = max(session_dates_by_id[a.session_id] for a in attendances)

    badges: list[dict[str, Any]] = []

    if pct >= _ATTENDANCE_100:
        badges.append({
            "badge_type": BadgeType.attendance_100,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
            "earned_date": earned_date,
        })
    elif pct >= _ATTENDANCE_90:
        badges.append({
            "badge_type": BadgeType.attendance_90,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
            "earned_date": earned_date,
        })
    elif pct >= _ATTENDANCE_75:
        badges.append({
            "badge_type": BadgeType.attendance_75,
            "badge_source": BadgeSource.attendance,
            "metadata_json": {"attendance_pct": pct, "sessions_present": present, "sessions_total": total},
            "earned_date": earned_date,
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

    # Buscar todos los competitors vinculados al atleta (athlete_id no tiene UNIQUE)
    comp_result = await db.execute(
        select(RaceCompetitor).where(RaceCompetitor.athlete_id == athlete_id)
    )
    competitors = comp_result.scalars().all()
    if not competitors:
        return []
    competitor_ids = [c.id for c in competitors]

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
    # event_id → fecha real de la válida — usado para que `earned_at` refleje
    # el día de la carrera que disparó el criterio, no el día en que se
    # (re)evaluó el boletín (ver `_upsert_badge`).
    events_by_id: dict[int, date] = {e.id: e.event_date for e in events_in_month}

    # Resultados de todos los competitors del atleta en ese periodo
    results_result = await db.execute(
        select(RaceResult).where(
            RaceResult.competitor_id.in_(competitor_ids),
            RaceResult.event_id.in_(event_ids),
            RaceResult.status == ResultStatus.FINISHED,
        )
    )
    results = results_result.scalars().all()
    if not results:
        return []

    # Tamaño de parrilla por (evento, categoría): mismo criterio de
    # `field_size` que field_metrics.py/analytics_charts.py — corredores con
    # resultado FINISHED en esa categoría/válida, contando también a
    # corredores de otros clubes/competitors (no solo los del atleta). Solo
    # se consulta para las (evento, categoría) donde el atleta tiene
    # resultado este periodo, no para todas las del mes.
    field_size_by_event_category: dict[tuple[int, int], int] = {}
    result_event_category_pairs = {(r.event_id, r.category_id) for r in results}
    if result_event_category_pairs:
        field_size_stmt = await db.execute(
            select(
                RaceResult.event_id,
                RaceResult.category_id,
                func.count(RaceResult.id),
            )
            .where(
                RaceResult.event_id.in_(event_ids),
                RaceResult.status == ResultStatus.FINISHED,
            )
            .group_by(RaceResult.event_id, RaceResult.category_id)
        )
        field_size_by_event_category = {
            (eid, cid): count for eid, cid, count in field_size_stmt.all()
        }

    def _field_size(r: Any) -> int:
        # Parrilla desconocida → 0 → nunca alcanza el umbral (conservador).
        return field_size_by_event_category.get((r.event_id, r.category_id), 0)

    badges: list[dict[str, Any]] = []

    # Top 10: solo si la parrilla ABSOLUTA es lo bastante grande para que la
    # etiqueta "Top 10" no sea una promesa falsa (ver
    # `_min_credible_field_size`) — no basta con que la posición sea buena
    # relativamente: un P2 de 6 es un resultado real, pero "Top 10" en una
    # categoría de 6 corredores es una afirmación falsa igual.
    min_field_top10 = _min_credible_field_size(10)
    top10_results = [
        r
        for r in results
        if r.position is not None
        and r.position <= 10
        and _field_size(r) >= min_field_top10
    ]
    if top10_results:
        best = min(top10_results, key=lambda r: r.position)
        badges.append({
            "badge_type": BadgeType.top10,
            "badge_source": BadgeSource.race,
            "metadata_json": {
                "position": best.position,
                "event_id": best.event_id,
                "race_time_ms": best.race_time_ms,
                "field_size": _field_size(best),
            },
            "earned_date": events_by_id.get(best.event_id),
        })

    # Primer podio real histórico: posición ≤3 (1º-2º-3º clásico, decisión
    # del entrenador 2026-09-08 — ver docstring del módulo) en este periodo,
    # creíble contra la parrilla real (ver `_is_credible_position`), Y no
    # tiene podio previo.
    podium_results = [
        r
        for r in results
        if r.position is not None
        and r.position <= 3
        and _is_credible_position(r.position, _field_size(r))
    ]
    if podium_results:
        # Verificar si ya tenía un podio CREÍBLE (≤3 y `_is_credible_position`)
        # antes de este periodo. No basta con `position <= 3`: un podio
        # pasado que en su momento no habría sido creíble (p. ej. 3º de una
        # parrilla de 3) no debe bloquear el primer podio real de verdad. Se
        # trae todo el historial candidato (normalmente pocas carreras por
        # temporada) y se recalcula su parrilla — no hay forma simple de
        # expresar `_is_credible_position` como filtro SQL.
        prev_podium_candidates_stmt = await db.execute(
            select(RaceResult).join(
                RaceEvent,
                RaceEvent.id == RaceResult.event_id,
            ).where(
                RaceResult.competitor_id.in_(competitor_ids),
                RaceResult.position <= 3,
                RaceResult.status == ResultStatus.FINISHED,
                RaceEvent.event_date < month_start,
            )
        )
        prev_podium_candidates = prev_podium_candidates_stmt.scalars().all()

        had_previous_podium = False
        if prev_podium_candidates:
            prev_event_ids = list({r.event_id for r in prev_podium_candidates})
            prev_field_size_stmt = await db.execute(
                select(
                    RaceResult.event_id,
                    RaceResult.category_id,
                    func.count(RaceResult.id),
                )
                .where(
                    RaceResult.event_id.in_(prev_event_ids),
                    RaceResult.status == ResultStatus.FINISHED,
                )
                .group_by(RaceResult.event_id, RaceResult.category_id)
            )
            prev_field_size_by_event_category = {
                (eid, cid): count for eid, cid, count in prev_field_size_stmt.all()
            }
            had_previous_podium = any(
                _is_credible_position(
                    r.position,
                    prev_field_size_by_event_category.get((r.event_id, r.category_id), 0),
                )
                for r in prev_podium_candidates
            )

        if not had_previous_podium:
            best_podium = min(podium_results, key=lambda r: r.position)
            badges.append({
                "badge_type": BadgeType.first_podium,
                "badge_source": BadgeSource.race,
                "metadata_json": {
                    "position": best_podium.position,
                    "event_id": best_podium.event_id,
                    "field_size": _field_size(best_podium),
                },
                "earned_date": events_by_id.get(best_podium.event_id),
            })

    # MTP: ¿mejoró su mejor tiempo personal en el periodo?
    # Comparar el mejor tiempo del mes vs historial previo del competitor.
    # Se conserva el RaceResult completo (no solo el tiempo) para poder fechar
    # el badge con el event_date de la carrera que lo produjo.
    results_with_time = [
        r for r in results if r.race_time_ms is not None and r.position is not None
    ]
    if results_with_time:
        best_result_month = min(results_with_time, key=lambda r: r.race_time_ms)
        best_time_month = best_result_month.race_time_ms

        # Historial previo (misma categoría si disponible, o todos)
        prev_results_stmt = await db.execute(
            select(RaceResult).join(
                RaceEvent,
                RaceEvent.id == RaceResult.event_id,
            ).where(
                RaceResult.competitor_id.in_(competitor_ids),
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
                    "earned_date": events_by_id.get(best_result_month.event_id),
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
    """Inserta una insignia si no existe. Retorna None si ya existía.

    `earned_at` refleja el día real en que se cumplió el criterio — la fecha
    de la última sesión (asistencia) o de la carrera (insignias
    competitivas) que lo disparó, provista por el caller en
    `badge_data["earned_date"]` — y NO el instante en que corre el
    evaluador. Si esa fecha no es recuperable (badge_data sin
    "earned_date", o algún caller legado que no la provea), se usa como
    mínimo el último día del periodo evaluado, nunca "ahora": un boletín de
    agosto no debe mostrar insignias fechadas en septiembre solo porque se
    regeneró ese día.

    Idempotencia: como `earned_date` es una función determinística de los
    datos del periodo (sesión/carrera reales), no del reloj, reevaluar el
    mismo periodo con los mismos datos siempre produce el mismo `earned_at`
    — regenerar el boletín no mueve la fecha de una insignia ya otorgada.
    """
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

    earned_date = badge_data.get("earned_date")
    if earned_date is None:
        # Fallback conservador: último día del periodo evaluado, no "ahora".
        last_day = calendar.monthrange(_year, _month)[1]
        earned_date = date(_year, _month, last_day)
    earned_at = datetime.combine(earned_date, datetime.min.time(), tzinfo=timezone.utc)

    new_badge = AthleteBadge(
        athlete_id=_athlete_id,
        badge_type=badge_data["badge_type"],
        badge_source=badge_data["badge_source"],
        period_year=_year,
        period_month=_month,
        earned_at=earned_at,
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
    """API pública: re-evalúa e inserta insignias para el atleta/periodo.

    Borra los badges existentes del periodo antes de reinsertar para que el
    estado refleje siempre las métricas actuales (e.g. si al regenerar el
    boletín la asistencia subió de 94% a 100%, se reemplaza attendance_90 por
    attendance_100). Los badges automáticos (source: attendance/race) son
    derivados de datos, no aportes manuales.
    """
    # Borrar badges previos del periodo para reflejar métricas actuales.
    await db.execute(
        delete(AthleteBadge).where(
            AthleteBadge.athlete_id == athlete_id,
            AthleteBadge.period_year == year,
            AthleteBadge.period_month == month,
        )
    )
    await db.flush()

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
