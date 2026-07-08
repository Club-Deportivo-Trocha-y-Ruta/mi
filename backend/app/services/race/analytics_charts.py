"""Analíticas para los charts del perfil del atleta (BE-2).

Funciones puras async que producen los payloads de ``GET /evolution`` y
``GET /distribution``. Privacidad-first: NO devuelven nombres ni
``competitor_id`` reales — emiten pseudónimos determinísticos por
temporada. ``display_name`` solo viaja cuando el router activa
``include_display_name=True`` (coach/admin únicamente).

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

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.schemas.athlete_race_analysis import (
    AnalysisConfidence,
    DistributionCurvePoint,
    DistributionPoint,
    DistributionResponse,
    EvolutionMetric,
    EvolutionPoint,
    EvolutionResponse,
    RaceParticipationOption,
    RaceParticipationResponse,
)
from app.services.race.race_labels import build_race_label

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepciones de dominio
# ---------------------------------------------------------------------------


class AthleteDidNotParticipate(Exception):
    """El atleta no tiene ningún race_result para el event_id solicitado
    en la temporada indicada (o fue eliminado por soft-delete).

    El router debe mapear esta excepción a HTTPException(404).
    """


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Tamaños mínimos para confianza estadística.
_EVOLUTION_LOW_MAX = 2   # <3 puntos
_EVOLUTION_HIGH_MIN = 8  # ≥8 puntos
_DISTRIBUTION_MIN_N = 5  # <5 → no fit curva normal, mostrar tabla

# Puntos a generar en la curva normal teórica.
_CURVE_POINTS = 60


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
        EvolutionMetric.PERCENTILE: "pct",
    }[metric]

    # CTE strategy:
    # - ``athlete_results``: una fila por evento donde compitió el atleta.
    # - ``cat_stats``: agregados FINISHED por (event, category) — MIN/MAX/COUNT
    #   sustituye al CTE ``winners`` antiguo (MIN cubre el caso gap al P1).
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
                e.event_date,
                s.kind           AS series_kind,
                s.level          AS series_level,
                e.location       AS location
            FROM race_results rr
            JOIN race_events e   ON e.id = rr.event_id
            JOIN race_series s   ON s.id = e.series_id
            WHERE rr.athlete_id = :athlete_id
              AND rr.deleted_at IS NULL
              AND s.season_year = :season
        ),
        cat_stats AS (
            SELECT
                rr.event_id,
                rr.category_id,
                MIN(rr.race_time_ms) AS time_min_ms,
                MAX(rr.race_time_ms) AS time_max_ms,
                COUNT(*)             AS cat_size
            FROM race_results rr
            WHERE rr.deleted_at IS NULL
              AND rr.status = 'finished'
              AND rr.race_time_ms IS NOT NULL
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
            cs.time_min_ms AS winner_time_ms,
            cs.time_max_ms,
            cs.cat_size,
            ar.series_kind,
            ar.series_level,
            ar.location
        FROM athlete_results ar
        LEFT JOIN cat_stats cs
          ON cs.event_id    = ar.event_id
         AND cs.category_id = ar.category_id
        ORDER BY ar.event_date ASC
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
        time_max_ms = _get("time_max_ms", 7)
        cat_size = _get("cat_size", 8)
        series_kind_raw = _get("series_kind", 9)
        series_level_raw = _get("series_level", 10)
        location_raw = _get("location", 11)

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
        elif metric == EvolutionMetric.PERCENTILE:
            # Percentil por TIEMPO (override coach real 2026-05-25).
            # n<5 → ocultar (consistente con comparador, fila se omite).
            if (
                finished
                and race_time_ms is not None
                and winner_time_ms is not None
                and time_max_ms is not None
                and cat_size is not None
                and int(cat_size) >= 5
            ):
                t = int(race_time_ms)
                t_min = int(winner_time_ms)
                t_max = int(time_max_ms)
                if t_min <= t <= t_max:
                    if t_max == t_min:
                        value = 100.0
                    else:
                        pct = 100.0 * (1.0 - (t - t_min) / (t_max - t_min))
                        value = round(pct)

        # Normalizar series_kind: puede llegar como str ("cup"/"championship")
        # o como RaceSeriesKind enum según el driver DB (MySQL vs aiosqlite).
        kind_str = (
            series_kind_raw.value
            if isinstance(series_kind_raw, RaceSeriesKind)
            else str(series_kind_raw)
        )
        kind_enum = RaceSeriesKind(kind_str)
        # Normalizar series_level: mismo patrón dual-driver que series_kind.
        level_str = (
            series_level_raw.value
            if isinstance(series_level_raw, RaceSeriesLevel)
            else str(series_level_raw)
        )
        level_enum = (
            RaceSeriesLevel(level_str)
            if level_str
            else RaceSeriesLevel.departmental
        )
        location_str: str | None = str(location_raw) if location_raw else None
        event_label = build_race_label(
            kind_enum,
            int(valida_num) if valida_num is not None else 0,
            location_str,
            level=level_enum,
        )

        series.append(
            EvolutionPoint(
                valida_num=int(valida_num) if valida_num is not None else 0,
                event_id=int(event_id),
                event_date=event_date,
                value=value,
                unit=unit,
                series_kind=kind_enum.value,
                label=event_label,
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
    event_id: int,
    include_display_name: bool = False,
) -> DistributionResponse:
    """Distribución de tiempos en la categoría del atleta en un evento específico.

    Args:
        athlete_id: PK del atleta (la verificación de acceso vive en el router).
        season: Año de temporada — filtra vía ``race_series.season_year``.
        event_id: PK de ``race_events.id`` del evento objetivo. Reemplaza el
            antiguo ``valida_num`` (``sequence_number``) — identifica el evento
            de forma inequívoca sin depender del número de válida.
        include_display_name: Si ``True``, popula ``display_name`` en cada
            :class:`DistributionPoint` desde ``race_competitors.display_name``
            (fuente: PDF federativo público). Solo activar para coach/admin.
            Para parent dejar en ``False`` (pseudónimo únicamente).

    Returns:
        :class:`DistributionResponse` con distribución real de la categoría.
        Si ``sample_size < 5`` no se ajusta curva normal (``curve=[]``,
        ``confidence="low"``) — el cliente cae a tabla de tiempos
        pseudonimizados. Los ``points`` siempre vienen poblados para n≥1.

    Raises:
        :class:`AthleteDidNotParticipate`: cuando no existe ningún
            ``race_result`` activo para ``(athlete_id, event_id, season)``.
            El router debe mapear esta excepción a ``HTTPException(404)``.

    Notas SQL:
        - ``target`` (1 fila) localiza ``(category_id, event_id)`` del atleta
          filtrando directamente por ``rr.event_id = :event_id`` — no usa
          ``sequence_number`` (que puede repetirse entre series distintas).
        - SELECT principal trae todos los race_results de esa categoría en
          ese evento (FINISHED only para que la curva tenga sentido).
        - JOIN con ``race_competitors`` para tener id estable (pseudonimizar)
          y ``display_name`` (solo expuesto si ``include_display_name=True``).
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
          AND rr.event_id        = :event_id
        LIMIT 1
        """
    )
    target_result = await db.execute(
        target_sql,
        {
            "athlete_id": athlete_id,
            "season": season,
            "event_id": event_id,
        },
    )
    target_row = (
        target_result.first() if hasattr(target_result, "first") else None
    )
    if target_row is None:
        # El atleta no compitió en este evento en esta temporada.
        # Señalamos al router para que devuelva 404.
        raise AthleteDidNotParticipate(
            f"Sin resultados para event_id={event_id}, season={season}"
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
    # JOIN con race_competitors para tener display_name disponible en memoria;
    # solo se expone al cliente cuando include_display_name=True (coach/admin).
    sample_sql = text(
        """
        SELECT
            rr.competitor_id,
            rr.race_time_ms,
            rr.athlete_id,
            rc.display_name
        FROM race_results rr
        JOIN race_competitors rc ON rc.id = rr.competitor_id
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

    times: list[tuple[int, int, bool, str]] = []
    # (competitor_id, race_time_ms, is_self, display_name)
    for row in sample_rows:
        rm = row._mapping if hasattr(row, "_mapping") else None
        comp_id = int(rm["competitor_id"] if rm else row[0])
        t_ms = int(rm["race_time_ms"] if rm else row[1])
        row_athlete_id = (rm["athlete_id"] if rm else row[2])
        dn = str(rm["display_name"] if rm else row[3]) if (rm["display_name"] if rm else row[3]) is not None else ""
        is_self = (
            row_athlete_id is not None and int(row_athlete_id) == int(athlete_id)
        )
        times.append((comp_id, t_ms, is_self, dn))

    sample_size = len(times)

    # Estadísticos base — siempre que tengamos ≥1 dato hacemos mean.
    mean_ms: Optional[float] = None
    stddev_ms: Optional[float] = None
    athlete_z: Optional[float] = None
    athlete_pct: Optional[float] = None

    if sample_size >= 1:
        only_times = [t for _, t, _, _ in times]
        mean_ms = sum(only_times) / sample_size
    if sample_size >= 2:
        variance = sum((t - mean_ms) ** 2 for t in (x for _, x, _, _ in times)) / (
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
            1 for _, t, _, _ in times if t >= athlete_time_ms
        )
        athlete_pct = round(100.0 * rank_better_or_equal / sample_size, 2)

    # Puntos observados — pseudónimo siempre presente; display_name solo
    # cuando include_display_name=True (coach/admin). Nunca se loguea.
    points = [
        DistributionPoint(
            pseudonym=_build_pseudonym(cid),
            time_ms=t,
            is_self=is_self,
            display_name=dn if include_display_name else None,
        )
        for (cid, t, is_self, dn) in times
    ]

    # Curva normal teórica — solo con n >= MIN_N (=5). Con menos corredores
    # la campana es engañosa porque outliers inflan σ.
    # El rango de la curva es [min(times), max(times)] — no ±3σ teórico
    # (con muestras pequeñas el rango teórico produce límites absurdos).
    curve: list[DistributionCurvePoint] = []
    if (
        sample_size >= _DISTRIBUTION_MIN_N
        and mean_ms is not None
        and stddev_ms
        and stddev_ms > 0
    ):
        all_times_ms = [t for _, t, _, _ in times]
        low_x = float(min(all_times_ms))
        high_x = float(max(all_times_ms))
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

    # Sin curve fit → confidence=low (fuerza al frontend a renderizar tabla).
    confidence = (
        AnalysisConfidence.low
        if sample_size < _DISTRIBUTION_MIN_N
        else _confidence_from_n(sample_size)
    )

    return DistributionResponse(
        season=season,
        event_id=event_id,
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
        confidence=confidence,
    )



# ---------------------------------------------------------------------------
# 3. list_athlete_races
# ---------------------------------------------------------------------------


async def list_athlete_races(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: int,
) -> RaceParticipationResponse:
    """Devuelve los eventos en los que el atleta compitió en la temporada.

    Contrato:
        - Una fila por evento (DISTINCT sobre ``e.id``) en el que exista al
          menos un ``race_result`` activo para el atleta, en cualquier estado
          (finished, DNF, DNS, DSQ — participación efectiva).
        - Orden cronológico ascendente por ``e.event_date``.
        - Las etiquetas legibles se construyen en el servidor vía
          ``build_race_label`` — el frontend NO debe recalcularlas.
        - Sin participación → ``items=[]``, nunca error.
        - Fuente de verdad para el selector de evento del análisis de carrera.

    Privacidad:
        - NO incluye ``athlete_id`` ni ``competitor_id`` en la respuesta.
        - ``event_name`` y ``location`` son datos federativos públicos.
        - No loguea PII a nivel INFO.
    """
    sql = text(
        """
        SELECT
            e.id             AS event_id,
            e.sequence_number,
            s.kind           AS series_kind,
            s.level          AS series_level,
            e.event_date,
            e.name           AS event_name,
            e.location
        FROM race_results rr
        JOIN race_events e  ON e.id = rr.event_id
        JOIN race_series s  ON s.id = e.series_id
        WHERE rr.athlete_id  = :athlete_id
          AND rr.deleted_at  IS NULL
          AND s.season_year  = :season
        GROUP BY
            e.id,
            e.sequence_number,
            s.kind,
            s.level,
            e.event_date,
            e.name,
            e.location
        ORDER BY e.event_date ASC
        """
    )

    result = await db.execute(sql, {"athlete_id": athlete_id, "season": season})
    rows = result.fetchall() if hasattr(result, "fetchall") else list(result)

    items: list[RaceParticipationOption] = []
    for row in rows:
        m = row._mapping if hasattr(row, "_mapping") else {}

        def _get(name: str, idx: int):
            if m:
                return m.get(name)
            try:
                return row[idx]
            except Exception:  # noqa: BLE001
                return None

        event_id_raw   = _get("event_id", 0)
        seq_num_raw    = _get("sequence_number", 1)
        series_kind_raw = _get("series_kind", 2)
        series_level_raw = _get("series_level", 3)
        event_date_raw = _get("event_date", 4)
        event_name_raw = _get("event_name", 5)
        location_raw   = _get("location", 6)

        if event_id_raw is None or event_date_raw is None or event_name_raw is None:
            continue

        # Normalizar series_kind: MySQL puede devolver el valor enum como string
        # ("cup"/"championship"); aiosqlite siempre devuelve string.
        kind_str = (
            series_kind_raw.value
            if isinstance(series_kind_raw, RaceSeriesKind)
            else str(series_kind_raw)
        )
        kind_enum = RaceSeriesKind(kind_str)
        level_str = (
            series_level_raw.value
            if isinstance(series_level_raw, RaceSeriesLevel)
            else str(series_level_raw)
        )
        level_enum = (
            RaceSeriesLevel(level_str)
            if level_str
            else RaceSeriesLevel.departmental
        )

        seq_num   = int(seq_num_raw) if seq_num_raw is not None else 1
        location_str: str | None = str(location_raw) if location_raw else None
        label = build_race_label(kind_enum, seq_num, location_str, level=level_enum)

        items.append(
            RaceParticipationOption(
                event_id=int(event_id_raw),
                sequence_number=seq_num,
                series_kind=kind_enum.value,
                event_date=event_date_raw,
                event_name=str(event_name_raw),
                location=location_str,
                label=label,
            )
        )

    return RaceParticipationResponse(season=season, items=items)


__all__ = [
    "build_evolution",
    "build_distribution",
    "list_athlete_races",
    "AthleteDidNotParticipate",
]
