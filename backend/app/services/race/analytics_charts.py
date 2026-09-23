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
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_event import RaceEventPriority
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.schemas.athlete_race_analysis import (
    AnalysisConfidence,
    ComparisonGroupOption,
    DistributionCurvePoint,
    DistributionPoint,
    DistributionResponse,
    EvolutionMetric,
    EvolutionPoint,
    EvolutionResponse,
    RaceParticipationOption,
    RaceParticipationResponse,
)
from app.services.notification.race_event_tier import RaceTier, get_race_tier
from app.services.race.comparison_groups import build_comparison_group, group_label
from app.services.race.course.derived import derive_figures
from app.services.race.field_metrics import MetricSet, compute_category_metrics
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


def _build_comparison_groups(
    group_rows: list[dict[str, Any]], *, season: int
) -> list[ComparisonGroupOption]:
    """Deriva ``groups`` a partir de TODAS las filas de la temporada.

    Se calcula sobre el conjunto completo (antes del filtro opcional
    ``series_id`` de :func:`build_evolution`) — el contrato exige que
    ``groups`` viaje completo incluso cuando ``series`` viene filtrada
    (research D4, ``contracts/evolution-api.md``).

    Orden: copas por la fecha de su válida más temprana, luego campeonatos
    por fecha (research D1/D2 — mismo criterio que
    ``comparison_groups.split_progression``, reimplementado aquí porque
    opera sobre filas de query cruda, no sobre ``athlete_progression``).
    """
    by_group: dict[str, dict[str, Any]] = {}
    for row in group_rows:
        series_id = row["series_id"]
        if series_id is None:
            continue
        cg = build_comparison_group(row["kind"], series_id)
        entry = by_group.get(cg)
        if entry is None:
            entry = {
                "series_id": series_id,
                "series_name": row["series_name"],
                "kind": row["kind"],
                "level": row["level"],
                "location": row["location"],
                "first_event_date": row["event_date"],
                "n_points": 0,
            }
            by_group[cg] = entry
        elif row["event_date"] < entry["first_event_date"]:
            entry["first_event_date"] = row["event_date"]
            entry["location"] = row["location"]
        if row["value"] is not None:
            entry["n_points"] += 1

    cups = sorted(
        (e for e in by_group.values() if e["kind"] == RaceSeriesKind.cup.value),
        key=lambda e: e["first_event_date"],
    )
    championships = sorted(
        (e for e in by_group.values() if e["kind"] == RaceSeriesKind.championship.value),
        key=lambda e: e["first_event_date"],
    )

    options: list[ComparisonGroupOption] = []
    for entry in (*cups, *championships):
        label = group_label(
            kind=entry["kind"],
            level=entry["level"],
            name=entry["series_name"],
            season_year=season,
            location=entry["location"],
        )
        options.append(
            ComparisonGroupOption(
                comparison_group=build_comparison_group(entry["kind"], entry["series_id"]),
                series_id=entry["series_id"],
                kind=entry["kind"],
                level=entry["level"],
                label=label,
                n_points=entry["n_points"],
            )
        )
    return options


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

# Unidad por métrica. ``pct_signed`` (2026-09-23): a diferencia de ``pct``
# (percentil, solo positivo, sin signo), la brecha vs. mediana puede ser
# negativa (más rápido que la mediana) — el formateador del cliente antepone
# "+"/"-".
_EVOLUTION_UNITS: dict[EvolutionMetric, str] = {
    EvolutionMetric.PODIUM_GAP_MS: "ms",
    EvolutionMetric.TIME_MS: "ms",
    EvolutionMetric.RANKING: "position",
    EvolutionMetric.PERCENTILE: "pct",
    EvolutionMetric.GAP_TO_MEDIAN_PCT: "pct_signed",
}

# Métrica → campo de ``field_metrics.MetricSet`` que la sirve (feature 045,
# R-01). ``build_evolution`` NO calcula ninguna de ellas: reenvía el valor del
# motor único, así Evolución, Historial y Detalle de competencia nunca
# discrepan (SC-002). ``TIME_MS`` no es una métrica derivada: es el tiempo
# oficial del propio resultado, que ya viene en la fila (ver ``_metric_value``).
_ENGINE_FIELD_BY_METRIC: dict[EvolutionMetric, str] = {
    EvolutionMetric.PODIUM_GAP_MS: "gap_to_winner_ms",
    EvolutionMetric.RANKING: "position",
    EvolutionMetric.PERCENTILE: "percentile",
    EvolutionMetric.GAP_TO_MEDIAN_PCT: "gap_to_median_pct",
}

# ``race_series.name`` es NOT NULL hoy, pero ``EvolutionPoint.series_name``
# declara ``min_length=1``: un NULL debe degradar a un placeholder, no romper
# con un 500 (F-10).
_SERIES_NAME_FALLBACK = "Serie"

# Una fila por resultado propio del atleta en la temporada. Los agregados de
# la categoría (tamaño, percentil, brechas) NO viven aquí: los calcula el
# motor único en Python (``field_metrics``). ``ix_race_results_athlete_event``
# evita el full scan; ``deleted_at IS NULL`` aplica siempre.
_ATHLETE_RESULTS_SQL = text(
    """
    SELECT
        rr.id             AS result_id,
        rr.event_id,
        rr.category_id,
        rr.status,
        rr.race_time_ms,
        rr.laps_behind,
        e.sequence_number AS valida_num,
        e.event_date,
        e.location        AS location,
        s.id              AS series_id,
        s.name            AS series_name,
        s.kind            AS series_kind,
        s.level           AS series_level
    FROM race_results rr
    JOIN race_events e ON e.id = rr.event_id
    JOIN race_series s ON s.id = e.series_id
    WHERE rr.athlete_id = :athlete_id
      AND rr.deleted_at IS NULL
      AND s.season_year = :season
    ORDER BY e.event_date ASC, rr.id ASC
    """
)


@dataclass(frozen=True)
class _AthleteRaceRow:
    """Fila cruda ya normalizada de ``_ATHLETE_RESULTS_SQL`` (sin métricas)."""

    # ``None`` solo con dobles de prueba que no traen la columna.
    result_id: Optional[int]
    event_id: int
    valida_num: int
    # ``date`` en MySQL, ``str`` ISO en SQLite (SQL crudo sin tipos): pydantic
    # normaliza ambos al construir ``EvolutionPoint``.
    event_date: date | str
    category_id: Optional[int]
    status: str
    race_time_ms: Optional[int]
    laps_behind: Optional[int]
    series_id: int
    series_name: str
    series_kind: RaceSeriesKind
    series_level: RaceSeriesLevel
    location: Optional[str]


def _optional_int(value: Any) -> Optional[int]:
    return None if value is None else int(value)


def _as_float(value: Optional[float]) -> Optional[float]:
    return None if value is None else float(value)


def _as_series_kind(raw: Any) -> RaceSeriesKind:
    """``RaceSeriesKind`` desde el enum o su valor string (según el driver)."""
    return RaceSeriesKind(raw)


def _as_series_level(raw: Any) -> RaceSeriesLevel:
    """``RaceSeriesLevel`` desde el enum o su valor string; vacío → departamental."""
    return RaceSeriesLevel(raw) if raw else RaceSeriesLevel.departmental


def _parse_athlete_row(row: Any) -> Optional[_AthleteRaceRow]:
    """Normaliza una fila cruda; ``None`` si le falta la identidad del evento
    o de la serie (no se puede construir un punto sin ellas)."""
    m = row._mapping
    if m.get("event_id") is None or m.get("event_date") is None or m.get("series_id") is None:
        return None
    status = m.get("status")
    location = m.get("location")
    series_name = m.get("series_name")
    valida_num = m.get("valida_num")
    return _AthleteRaceRow(
        result_id=_optional_int(m.get("result_id")),
        event_id=int(m["event_id"]),
        valida_num=int(valida_num) if valida_num is not None else 0,
        event_date=m["event_date"],
        category_id=_optional_int(m.get("category_id")),
        status=str(status) if status is not None else "",
        race_time_ms=_optional_int(m.get("race_time_ms")),
        laps_behind=_optional_int(m.get("laps_behind")),
        series_id=int(m["series_id"]),
        series_name=str(series_name) if series_name is not None else _SERIES_NAME_FALLBACK,
        series_kind=_as_series_kind(m.get("series_kind")),
        series_level=_as_series_level(m.get("series_level")),
        location=str(location) if location else None,
    )


async def _fetch_athlete_race_rows(
    db: AsyncSession, *, athlete_id: int, season: int
) -> list[_AthleteRaceRow]:
    result = await db.execute(_ATHLETE_RESULTS_SQL, {"athlete_id": athlete_id, "season": season})
    parsed = (_parse_athlete_row(row) for row in result.fetchall())
    return [row for row in parsed if row is not None]


def _own_event_category_pairs(rows: list[_AthleteRaceRow]) -> set[tuple[int, int]]:
    """Pares (event_id, category_id) propios del atleta. Delimitan todo lo
    que se carga de terceros: nunca otras categorías/eventos del club."""
    return {(r.event_id, r.category_id) for r in rows if r.category_id is not None}


async def _load_course_setups(
    db: AsyncSession, pairs: set[tuple[int, int]]
) -> dict[tuple[int, int], RaceCourseCategorySetup]:
    """Setups de recorrido (feature 043, R-11) en UNA sola query para toda la
    llamada (nunca por punto), indexados por (event_id, category_id): el
    setup de una categoría es propio de cada válida, no de la temporada.
    ``avg_speed_kmh`` queda ``None`` para todo par sin setup."""
    if not pairs:
        return {}
    event_ids = {event_id for event_id, _ in pairs}
    result = await db.execute(
        select(RaceCourseCategorySetup)
        .options(selectinload(RaceCourseCategorySetup.variant))
        .where(RaceCourseCategorySetup.race_event_id.in_(event_ids))
    )
    return {(s.race_event_id, s.category_id): s for s in result.scalars().all()}


async def _load_engine_metrics(
    db: AsyncSession, pairs: set[tuple[int, int]]
) -> dict[int, MetricSet]:
    """``MetricSet`` del motor único por ``result_id`` (feature 045).

    UNA sola query ORM para toda la llamada: los ``RaceResult`` de cualquier
    competidor restringidos a los pares propios (candado de terceros: nunca
    otras categorías/eventos del club). ``compute_category_metrics`` es puro
    y da un ``MetricSet`` por fila, así que dos resultados del mismo atleta
    en un mismo evento (dos categorías) reciben cada uno los suyos.
    """
    if not pairs:
        return {}
    event_ids = {event_id for event_id, _ in pairs}
    results = await db.execute(
        select(RaceResult).where(
            RaceResult.event_id.in_(event_ids),
            RaceResult.deleted_at.is_(None),
        )
    )
    field_rows = [r for r in results.scalars().all() if (r.event_id, r.category_id) in pairs]

    metrics_by_result: dict[int, MetricSet] = {}
    for event_id, category_id in pairs:
        metrics_by_result.update(compute_category_metrics(field_rows, event_id, category_id))
    return metrics_by_result


def _metric_value(
    metric: EvolutionMetric, row: _AthleteRaceRow, metrics: Mapping[str, Any]
) -> Optional[float]:
    if metric == EvolutionMetric.TIME_MS:
        # Hecho del propio resultado, no una métrica derivada: el CHECK
        # ``ck_race_results_time_consistent_with_status`` garantiza que solo
        # un FINISHED tiene ``race_time_ms`` (DNF/DNS/DSQ/MINUS_LAPS → NULL).
        return _as_float(row.race_time_ms)
    return _as_float(metrics.get(_ENGINE_FIELD_BY_METRIC[metric]))


def _avg_speed_kmh(row: _AthleteRaceRow, setup: Optional[RaceCourseCategorySetup]) -> Optional[float]:
    return derive_figures(setup, row.status, row.race_time_ms, row.laps_behind).avg_speed_kmh


def _build_point(
    row: _AthleteRaceRow,
    metrics: Mapping[str, Any],
    *,
    metric: EvolutionMetric,
    setup: Optional[RaceCourseCategorySetup],
) -> EvolutionPoint:
    """Un punto de la serie. Toda cifra de campo/posición viene de ``metrics``
    (el ``MetricSet`` del motor para ESTE resultado); aquí no se calcula nada.

    ``field_size``/``percentile``/``position``/``gap_pct``/``gap_to_median_pct``
    se exponen SIEMPRE, sea cual sea ``metric`` — la tarjeta de campeonato del
    frontend los necesita aunque la métrica pedida sea otra (feature 039)."""
    return EvolutionPoint(
        valida_num=row.valida_num,
        event_id=row.event_id,
        event_date=row.event_date,
        value=_metric_value(metric, row, metrics),
        unit=_EVOLUTION_UNITS[metric],
        series_kind=row.series_kind.value,
        label=build_race_label(row.series_kind, row.valida_num, row.location, level=row.series_level),
        series_id=row.series_id,
        series_name=row.series_name,
        series_level=row.series_level.value,
        comparison_group=build_comparison_group(row.series_kind, row.series_id),
        field_size=metrics.get("field_size"),
        percentile=metrics.get("percentile"),
        position=metrics.get("position"),
        gap_pct=metrics.get("gap_to_winner_pct"),
        gap_to_median_pct=metrics.get("gap_to_median_pct"),
        avg_speed_kmh=_avg_speed_kmh(row, setup),
    )


def _group_row(row: _AthleteRaceRow, point: EvolutionPoint) -> dict[str, Any]:
    """Insumo de ``_build_comparison_groups`` para un punto."""
    return {
        "series_id": row.series_id,
        "series_name": row.series_name,
        "kind": row.series_kind.value,
        "level": row.series_level.value,
        "location": row.location,
        "event_date": row.event_date,
        "value": point.value,
    }


def _filter_by_series(
    points: list[EvolutionPoint],
    groups: list[ComparisonGroupOption],
    series_id: Optional[int],
) -> tuple[list[EvolutionPoint], Optional[str]]:
    """Aplica el filtro opcional ``series_id`` DESPUÉS de derivar ``groups``
    de la temporada completa (research D4). Devuelve los puntos filtrados y
    el eco del grupo aplicado (``None`` si no hay filtro o no coincide)."""
    if series_id is None:
        return points, None
    matched_group = next((g for g in groups if g.series_id == series_id), None)
    selected_group = matched_group.comparison_group if matched_group is not None else None
    return [p for p in points if p.series_id == series_id], selected_group


async def build_evolution(
    db: AsyncSession,
    *,
    athlete_id: int,
    season: int,
    metric: EvolutionMetric,
    series_id: Optional[int] = None,
) -> EvolutionResponse:
    """Serie cronológica de una métrica del atleta en una temporada.

    Args:
        athlete_id: PK ``athletes.id`` (el verificación de acceso vive en el router).
        season: Año de temporada — filtra vía ``race_series.season_year``.
        metric: ``podium_gap_ms`` / ``ranking`` / ``time_ms`` / ``percentile``
            / ``gap_to_median_pct``.
        series_id: filtro opcional de grupo de comparación (feature 039,
            research D4). Restringe ``series`` a esa sola serie —
            ``groups`` sigue viniendo completo (temporada entera) y
            ``confidence`` se recalcula sobre la serie YA filtrada. Un
            ``series_id`` que no corresponde a ninguna serie del atleta en
            la temporada devuelve ``series=[]`` (nunca 404 — contrato
            ``evolution-api.md``).

    Returns:
        :class:`EvolutionResponse` con un punto por evento donde el atleta
        compitió. Valores ``None`` para DNF/DNS/DSQ o cuando el motor no
        puede calcular la cifra (p.ej. percentil con menos de
        ``field_metrics.MIN_FIELD`` finalistas cronometrados). Incluye
        ``groups`` (grupos de comparación derivados, feature 039) y
        ``selected_group`` (eco del filtro aplicado).

    Fuente de las cifras (feature 045, R-01):
        ``field_size``, ``percentile``, ``position``, ``gap_pct``
        (``gap_to_winner_pct``), ``gap_to_median_pct`` y el ``value`` de toda
        métrica salen del ``MetricSet`` de ``field_metrics`` — el motor único
        — de CADA resultado (por ``result_id``, no por evento). Solo
        ``metric=time_ms`` lee el tiempo del propio resultado. Esta función no
        calcula ninguna fórmula propia.

    Notas SQL:
        - Una query cruda para las filas propias (``ix_race_results_athlete_event``
          evita full scan) más, UNA sola vez para todos los ``event_id``
          (nunca por punto): los setups de recorrido (feature 043) y los
          ``RaceResult`` de campo que consume el motor.
        - El filtro ``series_id`` se aplica en Python DESPUÉS de calcular
          ``groups`` sobre el resultado completo — sin segundo roundtrip
          (research D4).
    """
    rows = await _fetch_athlete_race_rows(db, athlete_id=athlete_id, season=season)
    pairs = _own_event_category_pairs(rows)
    setups = await _load_course_setups(db, pairs)
    metrics_by_result = await _load_engine_metrics(db, pairs)

    points: list[EvolutionPoint] = []
    group_rows: list[dict[str, Any]] = []
    for row in rows:
        setup = setups.get((row.event_id, row.category_id)) if row.category_id is not None else None
        point = _build_point(row, metrics_by_result.get(row.result_id, {}), metric=metric, setup=setup)
        points.append(point)
        group_rows.append(_group_row(row, point))

    groups = _build_comparison_groups(group_rows, season=season)
    filtered_points, selected_group = _filter_by_series(points, groups, series_id)

    # Confianza: cuenta puntos con valor no-nulo (los que sirven al usuario),
    # calculada sobre la serie YA filtrada por series_id (research D4).
    n_valid = sum(1 for p in filtered_points if p.value is not None)
    return EvolutionResponse(
        season=season,
        metric=metric,
        series=filtered_points,
        confidence=_confidence_from_n(n_valid),
        groups=groups,
        selected_group=selected_group,
    )


# ---------------------------------------------------------------------------
# 2. build_distribution
# ---------------------------------------------------------------------------


async def _engine_percentile(
    db: AsyncSession,
    *,
    event_id: int,
    category_id: int,
    result_id: int,
) -> Optional[float]:
    """Percentil del resultado ``result_id`` según el motor único.

    Carga los ``RaceResult`` de la (evento, categoría) en una sola query y
    delega en ``compute_category_metrics`` — no aplica fórmula ni puerta
    propias (MIN_FIELD, empates y estados viven en el motor)."""
    result = await db.execute(
        select(RaceResult).where(
            RaceResult.event_id == event_id,
            RaceResult.category_id == category_id,
            RaceResult.deleted_at.is_(None),
        )
    )
    metrics = compute_category_metrics(list(result.scalars().all()), event_id, category_id)
    metric_set = metrics.get(result_id)
    return metric_set["percentile"] if metric_set is not None else None


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
        ``athlete_percentile`` es el percentil por TIEMPO del motor único
        (``field_metrics``, feature 045): ``None`` con menos de
        ``MIN_FIELD`` finalistas cronometrados o si el atleta no finalizó.
        Media, desviación y z-score son estadística propia de la distribución
        y se calculan aquí sobre la muestra.

    Raises:
        :class:`AthleteDidNotParticipate`: cuando no existe ningún
            ``race_result`` activo para ``(athlete_id, event_id, season)``.
            El router debe mapear esta excepción a ``HTTPException(404)``.

    Notas SQL:
        - ``target`` (1 fila) localiza ``(category_id, event_id)`` y el
          ``result_id`` del atleta filtrando directamente por
          ``rr.event_id = :event_id`` — no usa ``sequence_number`` (que puede
          repetirse entre series distintas).
        - SELECT principal trae todos los race_results de esa categoría en
          ese evento (FINISHED only para que la curva tenga sentido).
        - JOIN con ``race_competitors`` para tener id estable (pseudonimizar)
          y ``display_name`` (solo expuesto si ``include_display_name=True``).
        - Una query ORM adicional (``_engine_percentile``) carga los
          ``RaceResult`` de la categoría para el percentil del motor único.
    """
    # Step 1: localizar el target del atleta (category + event).
    target_sql = text(
        """
        SELECT
            rr.category_id,
            rr.event_id,
            rr.race_time_ms     AS athlete_time_ms,
            rr.status           AS athlete_status,
            rc.code             AS category_code,
            rr.id               AS result_id
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
    athlete_result_id = int(tm["result_id"] if tm else target_row[5])
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

    # Percentil (feature 045, R-01): lo entrega el motor único
    # (``field_metrics``), por TIEMPO y con la puerta MIN_FIELD — mismo valor
    # que Evolución, Historial y Detalle de competencia (SC-002).
    athlete_pct = await _engine_percentile(
        db,
        event_id=event_id,
        category_id=category_id,
        result_id=athlete_result_id,
    )

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
            s.id             AS series_id,
            s.name           AS series_name,
            s.kind           AS series_kind,
            s.level          AS series_level,
            e.event_date,
            e.name           AS event_name,
            e.location,
            e.is_championship,
            e.priority
        FROM race_results rr
        JOIN race_events e  ON e.id = rr.event_id
        JOIN race_series s  ON s.id = e.series_id
        WHERE rr.athlete_id  = :athlete_id
          AND rr.deleted_at  IS NULL
          AND s.season_year  = :season
        GROUP BY
            e.id,
            e.sequence_number,
            s.id,
            s.name,
            s.kind,
            s.level,
            e.event_date,
            e.name,
            e.location,
            e.is_championship,
            e.priority
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
        series_id_raw  = _get("series_id", 2)
        series_name_raw = _get("series_name", 3)
        series_kind_raw = _get("series_kind", 4)
        series_level_raw = _get("series_level", 5)
        event_date_raw = _get("event_date", 6)
        event_name_raw = _get("event_name", 7)
        location_raw   = _get("location", 8)
        is_championship_raw = _get("is_championship", 9)
        priority_raw   = _get("priority", 10)

        if (
            event_id_raw is None
            or event_date_raw is None
            or event_name_raw is None
            or series_id_raw is None
        ):
            continue

        # MySQL puede devolver el enum o su string; aiosqlite siempre string.
        kind_enum = _as_series_kind(series_kind_raw)
        level_enum = _as_series_level(series_level_raw)

        seq_num   = int(seq_num_raw) if seq_num_raw is not None else 1
        location_str: str | None = str(location_raw) if location_raw else None
        label = build_race_label(kind_enum, seq_num, location_str, level=level_enum)

        # Tier expuesto: reutiliza race_event_tier.get_race_tier (no
        # duplicar la regla "campeonato ⇒ CD aunque priority sea NULL").
        # La query es raw SQL (no ORM RaceEvent) — un SimpleNamespace con
        # los 3 atributos que get_race_tier lee basta, sin query adicional.
        priority_enum: RaceEventPriority | None = None
        if priority_raw is not None:
            priority_str = (
                priority_raw.value
                if isinstance(priority_raw, RaceEventPriority)
                else str(priority_raw)
            )
            if priority_str:
                priority_enum = RaceEventPriority(priority_str)
        tier = get_race_tier(
            SimpleNamespace(
                id=int(event_id_raw),
                is_championship=bool(is_championship_raw),
                sequence_number=seq_num,
                priority=priority_enum,
            )
        )
        exposed_priority = None if tier is RaceTier.UNKNOWN else tier.value

        items.append(
            RaceParticipationOption(
                event_id=int(event_id_raw),
                sequence_number=seq_num,
                series_kind=kind_enum.value,
                event_date=event_date_raw,
                event_name=str(event_name_raw),
                location=location_str,
                label=label,
                series_id=int(series_id_raw),
                # F-10: mismo fallback que build_evolution — RaceParticipationOption
                # también declara min_length=1.
                series_name=str(series_name_raw) if series_name_raw is not None else "Serie",
                series_level=level_enum.value,
                priority=exposed_priority,
            )
        )

    return RaceParticipationResponse(season=season, items=items)


__all__ = [
    "build_evolution",
    "build_distribution",
    "list_athlete_races",
    "AthleteDidNotParticipate",
]
