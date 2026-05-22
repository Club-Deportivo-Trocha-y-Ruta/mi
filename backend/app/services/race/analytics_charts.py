"""Analíticas para los charts del perfil del atleta (BE-2).

Funciones puras async que producen los payloads de ``GET /evolution`` y
``GET /distribution``. Privacidad-first: NO devuelven nombres ni
``competitor_id`` reales — emiten pseudónimos determinísticos por
temporada.

Patrón de queries (sql-pro):
    Usamos CTEs explícitos en lugar de cargar tablas completas con
    pandas. La carga de un atleta en una temporada es de O(decenas) y
    cabe en una sola query con índices existentes:

    - ``ix_race_results_athlete_event`` (athlete_id, event_id) acelera
      ``build_evolution`` que filtra por atleta+season.
    - ``ix_race_results_event_category_position`` permite el podium
      lookup en el mismo evento.

``confidence``:
    - ``low``    si ``n_points < 3`` en evolution o ``sample_size < 5`` en distribution.
    - ``medium`` si 3..7 puntos.
    - ``high``   si ≥8.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.athlete_race_analysis import (
    AnalysisConfidence,
    DistributionCurvePoint,
    DistributionPoint,
    DistributionResponse,
    EvolutionMetric,
    EvolutionPoint,
    EvolutionResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Tamaños mínimos para confianza estadística.
_EVOLUTION_LOW_MAX = 2   # <3 puntos
_EVOLUTION_HIGH_MIN = 8  # ≥8 puntos
_DISTRIBUTION_MIN_N = 5  # <5 → no fit curva normal

# Puntos a generar en la curva normal teórica.
_CURVE_POINTS = 60
# Cuántas sigmas a cada lado del mean para barrer la curva.
_CURVE_SIGMA_WIDTH = 3.0


def _confidence_from_n(n: int) -> AnalysisConfidence:
    if n < _EVOLUTION_LOW_MAX + 1:
        return AnalysisConfidence.low
    if n >= _EVOLUTION_HIGH_MIN:
        return AnalysisConfidence.high
    return AnalysisConfidence.medium


def _build_pseudonym(competitor_id: int) -> str:
    """Pseudónimo determinístico por competidor.

    Forma ``C{id % 10000:04d}`` — colisiones son posibles si el dataset
    crece >10k competitors, pero como el cliente sólo ve la distribución
    de una válida (decenas de filas) el colisión visible es marginal.
    """
    return f"C{(competitor_id % 10000):04d}"


def _normal_pdf(x: float, mu: float, sigma: float) -> float:
    """PDF normal — sin scipy. Pura matemática stdlib."""
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


# ---------------------------------------------------------------------------
# 1. build_evolution
# ---------------------------------------------------------------------------


async def build_evolution(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: int,
    metric: EvolutionMetric,
) -> EvolutionResponse:
    """Serie cronológica de una métrica del atleta en una temporada.

    Args:
        athlete_id: PK ``athletes.id`` (el verificación de acceso vive en el router).
        season: Año de temporada — filtra vía ``race_series.season_year``.
        metric: ``podium_gap_ms`` / ``ranking`` / ``time_ms``.

    Returns:
        :class:`EvolutionResponse` con un punto por evento donde el atleta
        compitió. Valores ``None`` para DNF/DNS/DSQ o cuando no se puede
        calcular gap (p.ej. el atleta es P1 → gap=0 explícito).

    Notas SQL:
        - ``ix_race_results_athlete_event`` evita full scan.
        - JOIN con ``race_events`` + ``race_series`` para filtrar season.
        - Subquery ``cat_stats`` calcula tiempo de P1 por (event, category)
          para podium_gap.
        - Filtro ``rr.deleted_at IS NULL`` aplica siempre.
    """
    unit = {
        EvolutionMetric.PODIUM_GAP_MS: "ms",
        EvolutionMetric.TIME_MS: "ms",
        EvolutionMetric.RANKING: "position",
    }[metric]

    # CTE strategy:
    # - ``athlete_results``: una fila por evento donde compitió el atleta.
    # - ``winners``: tiempo del P1 por (event, category) usado en gap.
    # Las dos se hacen LEFT JOIN para que un P1 propio aparezca con gap=0.
    sql = text(
        """
        WITH athlete_results AS (
            SELECT
                rr.id            AS result_id,
                rr.event_id,
                rr.category_id,
                rr.position,
                rr.status,
                rr.race_time_ms,
                e.sequence_number AS valida_num,
                e.event_date
            FROM race_results rr
            JOIN race_events e   ON e.id = rr.event_id
            JOIN race_series s   ON s.id = e.series_id
            WHERE rr.athlete_id = :athlete_id
              AND rr.deleted_at IS NULL
              AND s.season_year = :season
        ),
        winners AS (
            SELECT
                rr.event_id,
                rr.category_id,
                MIN(rr.race_time_ms) AS winner_time_ms
            FROM race_results rr
            WHERE rr.deleted_at IS NULL
              AND rr.status = 'finished'
              AND rr.position = 1
              AND rr.event_id IN (SELECT event_id FROM athlete_results)
            GROUP BY rr.event_id, rr.category_id
        )
        SELECT
            ar.event_id,
            ar.valida_num,
            ar.event_date,
            ar.status,
            ar.position,
            ar.race_time_ms,
            w.winner_time_ms
        FROM athlete_results ar
        LEFT JOIN winners w
          ON w.event_id    = ar.event_id
         AND w.category_id = ar.category_id
        ORDER BY ar.valida_num ASC, ar.event_date ASC
        """
    )

    result = await db.execute(sql, {"athlete_id": athlete_id, "season": season})
    rows = result.fetchall() if hasattr(result, "fetchall") else list(result)

    series: list[EvolutionPoint] = []
    for row in rows:
        m = row._mapping if hasattr(row, "_mapping") else {}

        def _get(name: str, idx: int):
            if m:
                return m.get(name)
            try:
                return row[idx]
            except Exception:  # noqa: BLE001
                return None

        event_id = _get("event_id", 0)
        valida_num = _get("valida_num", 1)
        event_date = _get("event_date", 2)
        status = _get("status", 3)
        position = _get("position", 4)
        race_time_ms = _get("race_time_ms", 5)
        winner_time_ms = _get("winner_time_ms", 6)

        if event_id is None or event_date is None:
            continue

        value: Optional[float] = None
        finished = (str(status) == "finished") if status is not None else False

        if metric == EvolutionMetric.RANKING:
            if finished and position is not None:
                value = float(int(position))
        elif metric == EvolutionMetric.TIME_MS:
            if finished and race_time_ms is not None:
                value = float(int(race_time_ms))
        elif metric == EvolutionMetric.PODIUM_GAP_MS:
            if (
                finished
                and race_time_ms is not None
                and winner_time_ms is not None
            ):
                gap = int(race_time_ms) - int(winner_time_ms)
                # Atleta es P1 → gap=0. No es None.
                value = float(max(gap, 0))

        series.append(
            EvolutionPoint(
                valida_num=int(valida_num) if valida_num is not None else 0,
                event_id=int(event_id),
                event_date=event_date,
                value=value,
                unit=unit,
            )
        )

    # Confianza: cuenta puntos con valor no-nulo (los que sirven al usuario).
    n_valid = sum(1 for p in series if p.value is not None)
    return EvolutionResponse(
        season=season,
        metric=metric,
        series=series,
        confidence=_confidence_from_n(n_valid),
    )


# ---------------------------------------------------------------------------
# 2. build_distribution
# ---------------------------------------------------------------------------


async def build_distribution(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: int,
    valida_num: int,
) -> DistributionResponse:
    """Distribución de tiempos en la categoría del atleta en una válida.

    Args:
        athlete_id: PK del atleta.
        season: Año de temporada.
        valida_num: ``sequence_number`` del evento (1..7 / 99 / 0=agregada).

    Returns:
        :class:`DistributionResponse`. Si ``sample_size < 5`` la respuesta
        es informativa pero ``points=[]`` y ``curve=[]`` — no entregamos
        estadísticas poco confiables sobre grupos chicos de menores.

    Notas SQL:
        - ``target`` (1 fila) localiza (category_id, event_id) del atleta.
        - SELECT principal trae todos los race_results de esa categoría en
          ese evento (FINISHED only para que la curva tenga sentido).
        - JOIN con ``race_competitors`` solo para tener un id estable que
          pseudonimizar — el ``display_name`` NUNCA viaja al cliente.
    """
    # Step 1: localizar el target del atleta (category + event).
    target_sql = text(
        """
        SELECT
            rr.category_id,
            rr.event_id,
            rr.race_time_ms     AS athlete_time_ms,
            rr.status           AS athlete_status,
            rc.code             AS category_code
        FROM race_results rr
        JOIN race_events e   ON e.id = rr.event_id
        JOIN race_series s   ON s.id = e.series_id
        JOIN race_categories rc ON rc.id = rr.category_id
        WHERE rr.athlete_id      = :athlete_id
          AND rr.deleted_at      IS NULL
          AND s.season_year      = :season
          AND e.sequence_number  = :valida_num
        LIMIT 1
        """
    )
    target_result = await db.execute(
        target_sql,
        {
            "athlete_id": athlete_id,
            "season": season,
            "valida_num": valida_num,
        },
    )
    target_row = (
        target_result.first() if hasattr(target_result, "first") else None
    )
    if target_row is None:
        # El atleta no compitió esa válida o no hay datos — respuesta vacía pero válida.
        return DistributionResponse(
            season=season,
            valida_num=valida_num,
            category_id=0,
            category_code="",
            sample_size=0,
            mean_ms=None,
            stddev_ms=None,
            athlete_time_ms=None,
            athlete_z_score=None,
            athlete_percentile=None,
            points=[],
            curve=[],
            confidence=AnalysisConfidence.low,
        )

    tm = target_row._mapping if hasattr(target_row, "_mapping") else None
    category_id = int(tm["category_id"] if tm else target_row[0])
    event_id = int(tm["event_id"] if tm else target_row[1])
    athlete_time_raw = (tm["athlete_time_ms"] if tm else target_row[2])
    athlete_status = (tm["athlete_status"] if tm else target_row[3])
    category_code = str(tm["category_code"] if tm else target_row[4])
    athlete_time_ms: Optional[int] = (
        int(athlete_time_raw)
        if athlete_time_raw is not None and str(athlete_status) == "finished"
        else None
    )

    # Step 2: todos los corredores FINISHED de esa categoría en ese evento.
    sample_sql = text(
        """
        SELECT
            rr.competitor_id,
            rr.race_time_ms,
            rr.athlete_id
        FROM race_results rr
        WHERE rr.event_id    = :event_id
          AND rr.category_id = :category_id
          AND rr.status      = 'finished'
          AND rr.race_time_ms IS NOT NULL
          AND rr.deleted_at  IS NULL
        ORDER BY rr.race_time_ms ASC
        """
    )
    sample_result = await db.execute(
        sample_sql,
        {"event_id": event_id, "category_id": category_id},
    )
    sample_rows = (
        sample_result.fetchall()
        if hasattr(sample_result, "fetchall")
        else list(sample_result)
    )

    times: list[tuple[int, int, bool]] = []
    # (competitor_id, race_time_ms, is_self)
    for row in sample_rows:
        rm = row._mapping if hasattr(row, "_mapping") else None
        comp_id = int(rm["competitor_id"] if rm else row[0])
        t_ms = int(rm["race_time_ms"] if rm else row[1])
        row_athlete_id = (rm["athlete_id"] if rm else row[2])
        is_self = (
            row_athlete_id is not None and int(row_athlete_id) == int(athlete_id)
        )
        times.append((comp_id, t_ms, is_self))

    sample_size = len(times)

    # Estadísticos base — siempre que tengamos ≥1 dato hacemos mean.
    mean_ms: Optional[float] = None
    stddev_ms: Optional[float] = None
    athlete_z: Optional[float] = None
    athlete_pct: Optional[float] = None

    if sample_size >= 1:
        only_times = [t for _, t, _ in times]
        mean_ms = sum(only_times) / sample_size
    if sample_size >= 2:
        variance = sum((t - mean_ms) ** 2 for t in (x for _, x, _ in times)) / (
            sample_size - 1
        )
        stddev_ms = math.sqrt(variance)

    if (
        athlete_time_ms is not None
        and mean_ms is not None
        and stddev_ms is not None
        and stddev_ms > 0
    ):
        athlete_z = (athlete_time_ms - mean_ms) / stddev_ms

    # Percentil: posición del atleta entre n (más bajo = mejor en tiempo,
    # pero el percentil reportado es "qué % es peor o igual" → mejor tiempo
    # da percentil más alto). Convención reporte deportivo.
    if athlete_time_ms is not None and sample_size >= 2:
        rank_better_or_equal = sum(
            1 for _, t, _ in times if t >= athlete_time_ms
        )
        athlete_pct = round(100.0 * rank_better_or_equal / sample_size, 2)

    # Si n<5 no devolvemos puntos ni curva — privacidad estadística.
    if sample_size < _DISTRIBUTION_MIN_N:
        return DistributionResponse(
            season=season,
            valida_num=valida_num,
            category_id=category_id,
            category_code=category_code,
            sample_size=sample_size,
            mean_ms=mean_ms,
            stddev_ms=stddev_ms,
            athlete_time_ms=athlete_time_ms,
            athlete_z_score=athlete_z,
            athlete_percentile=athlete_pct,
            points=[],
            curve=[],
            confidence=AnalysisConfidence.low,
        )

    # Puntos observados (pseudonimizados).
    points = [
        DistributionPoint(
            pseudonym=_build_pseudonym(cid),
            time_ms=t,
            is_self=is_self,
        )
        for (cid, t, is_self) in times
    ]

    # Curva normal teórica.
    curve: list[DistributionCurvePoint] = []
    if mean_ms is not None and stddev_ms and stddev_ms > 0:
        low_x = max(0.0, mean_ms - _CURVE_SIGMA_WIDTH * stddev_ms)
        high_x = mean_ms + _CURVE_SIGMA_WIDTH * stddev_ms
        if high_x > low_x:
            step = (high_x - low_x) / (_CURVE_POINTS - 1)
            for i in range(_CURVE_POINTS):
                x = low_x + step * i
                curve.append(
                    DistributionCurvePoint(
                        x_ms=round(x, 2),
                        density=_normal_pdf(x, mean_ms, stddev_ms),
                    )
                )

    return DistributionResponse(
        season=season,
        valida_num=valida_num,
        category_id=category_id,
        category_code=category_code,
        sample_size=sample_size,
        mean_ms=mean_ms,
        stddev_ms=stddev_ms,
        athlete_time_ms=athlete_time_ms,
        athlete_z_score=athlete_z,
        athlete_percentile=athlete_pct,
        points=points,
        curve=curve,
        confidence=_confidence_from_n(sample_size),
    )


__all__ = ["build_evolution", "build_distribution"]
