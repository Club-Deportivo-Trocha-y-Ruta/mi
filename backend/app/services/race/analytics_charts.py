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
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_event import RaceEvent, RaceEventPriority
from app.models.race_result import RaceResult, ResultStatus
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
from app.services.race.field_metrics import compute_field_metrics
from app.services.race.history import MIN_FIELD
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
        metric: ``podium_gap_ms`` / ``ranking`` / ``time_ms``.
        series_id: filtro opcional de grupo de comparación (feature 039,
            research D4). Restringe ``series`` a esa sola serie —
            ``groups`` sigue viniendo completo (temporada entera) y
            ``confidence`` se recalcula sobre la serie YA filtrada. Un
            ``series_id`` que no corresponde a ninguna serie del atleta en
            la temporada devuelve ``series=[]`` (nunca 404 — contrato
            ``evolution-api.md``).

    Returns:
        :class:`EvolutionResponse` con un punto por evento donde el atleta
        compitió. Valores ``None`` para DNF/DNS/DSQ o cuando no se puede
        calcular gap (p.ej. el atleta es P1 → gap=0 explícito). Incluye
        ``groups`` (grupos de comparación derivados, feature 039) y
        ``selected_group`` (eco del filtro aplicado).

    Notas SQL:
        - ``ix_race_results_athlete_event`` evita full scan.
        - JOIN con ``race_events`` + ``race_series`` para filtrar season.
        - Subquery ``cat_stats`` calcula tiempo de P1 por (event, category)
          para podium_gap — sus agregados FINISHED-only también sirven de
          ``field_size`` (research D3, mismo criterio que
          ``field_metrics.compute_field_metrics``).
        - Filtro ``rr.deleted_at IS NULL`` aplica siempre.
        - Una sola query: el filtro ``series_id`` se aplica en Python
          DESPUÉS de calcular ``groups`` sobre el resultado completo — no
          hay un segundo roundtrip a la base de datos (research D4).
        - ``category_id``/``laps_behind`` viajan en esta misma query
          (feature 043, R-11) porque ``derive_figures`` los necesita junto a
          ``status``/``race_time_ms`` (ya seleccionados) para
          ``avg_speed_kmh`` — evita un segundo roundtrip por fila. Las
          queries adicionales de esta función (setups de recorrido, y desde
          2026-09-23 los RaceResult/RaceEvent de campo para
          ``gap_to_median_pct`` vía ``compute_field_metrics``) corren UNA
          sola vez para todos los ``event_id`` presentes en el resultado,
          nunca por punto.
    """
    unit = {
        EvolutionMetric.PODIUM_GAP_MS: "ms",
        EvolutionMetric.TIME_MS: "ms",
        EvolutionMetric.RANKING: "position",
        EvolutionMetric.PERCENTILE: "pct",
        # "pct_signed" (2026-09-23): a diferencia de "pct" (percentil, solo
        # positivo, sin signo), esta brecha puede ser negativa (más rápido
        # que la mediana) — el formateador del cliente antepone "+"/"-".
        EvolutionMetric.GAP_TO_MEDIAN_PCT: "pct_signed",
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
                rr.competitor_id,
                rr.position,
                rr.status,
                rr.race_time_ms,
                rr.laps_behind,
                e.sequence_number AS valida_num,
                e.event_date,
                s.id             AS series_id,
                s.name           AS series_name,
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
                MIN(rr.race_time_ms)   AS time_min_ms,
                MAX(rr.race_time_ms)   AS time_max_ms,
                COUNT(*)               AS cat_size,
                COUNT(rr.race_time_ms) AS cat_size_with_time
            FROM race_results rr
            WHERE rr.deleted_at IS NULL
              AND rr.status = 'finished'
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
            ar.category_id,
            ar.laps_behind,
            cs.time_min_ms AS winner_time_ms,
            cs.time_max_ms,
            cs.cat_size,
            cs.cat_size_with_time,
            ar.series_id,
            ar.series_name,
            ar.series_kind,
            ar.series_level,
            ar.location,
            ar.competitor_id
        FROM athlete_results ar
        LEFT JOIN cat_stats cs
          ON cs.event_id    = ar.event_id
         AND cs.category_id = ar.category_id
        ORDER BY ar.event_date ASC
        """
    )

    result = await db.execute(sql, {"athlete_id": athlete_id, "season": season})
    rows = result.fetchall() if hasattr(result, "fetchall") else list(result)

    # Course setups (feature 043, R-11): ONE extra query for the whole call
    # (never per point) — keyed by (event_id, category_id) because a
    # category's course setup is válida-specific, not season-wide. Skipped
    # entirely when there are no rows. ``avg_speed_kmh`` stays None for any
    # (event, category) pair without a matching setup — expected for most
    # events for a long while; no aggregate of speed is computed anywhere.
    #
    # El mismo barrido recolecta, para "brecha vs. mediana" (2026-09-23):
    # los pares (event_id, category_id) propios del atleta y su
    # competitor_id por evento — insumo de compute_field_metrics más abajo.
    event_ids: set[int] = set()
    own_pairs: set[tuple[int, int]] = set()
    competitor_id_by_event: dict[int, int] = {}
    for row in rows:
        rm = row._mapping if hasattr(row, "_mapping") else None
        raw_event_id = rm.get("event_id") if rm else (row[0] if len(row) > 0 else None)
        raw_category_id = rm.get("category_id") if rm else (row[6] if len(row) > 6 else None)
        raw_competitor_id = rm.get("competitor_id") if rm else None
        if raw_event_id is not None:
            event_ids.add(int(raw_event_id))
            if raw_category_id is not None:
                own_pairs.add((int(raw_event_id), int(raw_category_id)))
            if raw_competitor_id is not None:
                competitor_id_by_event[int(raw_event_id)] = int(raw_competitor_id)

    setup_by_event_category: dict[tuple[int, int], Any] = {}
    if event_ids:
        setup_result = await db.execute(
            select(RaceCourseCategorySetup)
            .options(selectinload(RaceCourseCategorySetup.variant))
            .where(RaceCourseCategorySetup.race_event_id.in_(event_ids))
        )
        # Defensive hasattr: unit tests exercise build_evolution against a
        # bare-bones fake AsyncSession (see _FakeDbNullSeriesName below) that
        # only implements the raw-SQL ``execute`` contract used by the main
        # query above, not the ORM ``select(...)`` one — degrade to "no
        # course data" rather than raise for that fake.
        setup_rows = (
            setup_result.scalars().all() if hasattr(setup_result, "scalars") else []
        )
        setup_by_event_category = {
            (s.race_event_id, s.category_id): s for s in setup_rows
        }

    # "Brecha vs. mediana" (gap_to_median_pct, 2026-09-23): reutiliza
    # compute_field_metrics (app/services/race/field_metrics.py) — MISMA
    # función que services/race/history.py, nunca una cuarta fórmula. Dos
    # queries ORM adicionales, UNA sola vez para toda la llamada (nunca por
    # punto, mismo patrón que el setup de recorrido arriba):
    #   1. RaceResult de cualquier competidor, restringidos a los pares
    #      exactos (event_id, category_id) propios del atleta (candado de
    #      terceros: nunca se cargan otras categorías/eventos del club).
    #   2. RaceEvent + su RaceSeries (season_year/kind/level) de esos mismos
    #      event_ids — compute_field_metrics necesita objetos ORM reales
    #      (``event_date`` como ``date``, no el string crudo de una fila SQL).
    # Mismo umbral que history.py: MIN_FIELD (5) finalistas CON tiempo
    # registrado, no field_size (que cuenta también minus_laps).
    metrics_by_event: dict[int, dict[str, Any]] = {}
    timed_finishers_by_pair: dict[tuple[int, int], int] = {}
    if event_ids:
        field_result = await db.execute(
            select(RaceResult).where(
                RaceResult.event_id.in_(event_ids),
                RaceResult.deleted_at.is_(None),
            )
        )
        # Defensive hasattr: mismo motivo que el setup de recorrido arriba —
        # degrada a "sin campo" para el fake bare-bones de build_evolution.
        field_rows_all = (
            field_result.scalars().all() if hasattr(field_result, "scalars") else []
        )
        field_rows = [
            r for r in field_rows_all if (r.event_id, r.category_id) in own_pairs
        ]

        events_result = await db.execute(
            select(RaceEvent)
            .options(selectinload(RaceEvent.series))
            .where(RaceEvent.id.in_(event_ids))
        )
        events_orm = (
            events_result.scalars().all() if hasattr(events_result, "scalars") else []
        )
        series_orm = [e.series for e in events_orm if e.series is not None]

        for r in field_rows:
            if r.status == ResultStatus.FINISHED and r.race_time_ms is not None:
                key = (r.event_id, r.category_id)
                timed_finishers_by_pair[key] = timed_finishers_by_pair.get(key, 0) + 1

        for competitor_id in set(competitor_id_by_event.values()):
            per_event = compute_field_metrics(
                results=field_rows,
                events=list(events_orm),
                series=series_orm,
                categories=[],
                competitor_id=competitor_id,
                season=season,
            )
            metrics_by_event.update(per_event)

    series: list[EvolutionPoint] = []
    group_rows: list[dict[str, Any]] = []
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
        category_id_raw = _get("category_id", 6)
        laps_behind_raw = _get("laps_behind", 7)
        winner_time_ms = _get("winner_time_ms", 8)
        time_max_ms = _get("time_max_ms", 9)
        cat_size = _get("cat_size", 10)
        cat_size_with_time = _get("cat_size_with_time", 11)
        series_id_raw = _get("series_id", 12)
        series_name_raw = _get("series_name", 13)
        series_kind_raw = _get("series_kind", 14)
        series_level_raw = _get("series_level", 15)
        location_raw = _get("location", 16)

        if event_id is None or event_date is None or series_id_raw is None:
            continue

        # "Brecha vs. mediana" (2026-09-23) — poblada para CUALQUIER
        # métrica solicitada, igual que gap_pct/position/field_size más
        # abajo. Umbral: MIN_FIELD (5) finalistas CON tiempo registrado en
        # la (evento, categoría), mismo criterio que history.py — nunca
        # field_size (que también cuenta minus_laps).
        gap_to_median_val: Optional[float] = None
        if category_id_raw is not None:
            timed = timed_finishers_by_pair.get((int(event_id), int(category_id_raw)))
            if timed is not None and timed >= MIN_FIELD:
                candidate = metrics_by_event.get(int(event_id), {}).get(
                    "gap_to_median_pct"
                )
                if candidate is not None:
                    gap_to_median_val = float(candidate)

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
            # F-8: el umbral de 5 se mide sobre filas CON tiempo registrado
            # (``cat_size_with_time``), no sobre el total de finishers
            # (``cat_size``) — un finisher sin tiempo no aporta al percentil.
            if (
                finished
                and race_time_ms is not None
                and winner_time_ms is not None
                and time_max_ms is not None
                and cat_size_with_time is not None
                and int(cat_size_with_time) >= 5
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
        elif metric == EvolutionMetric.GAP_TO_MEDIAN_PCT:
            # Ya calculado arriba (mismo umbral MIN_FIELD que el campo
            # gap_to_median_pct expuesto para cualquier métrica).
            value = gap_to_median_val

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

        series_id_val = int(series_id_raw)
        # F-10: EvolutionPoint.series_name declara min_length=1 — un NULL de
        # BD (race_series.name es NOT NULL hoy, pero el fallback degrada en
        # vez de romper con un 500 si eso cambia) no puede convertirse en "".
        series_name_val = str(series_name_raw) if series_name_raw is not None else "Serie"
        comparison_group_val = build_comparison_group(kind_enum, series_id_val)

        # field_size / percentile posicional (research D3, F-8): mismo
        # criterio que field_metrics.compute_field_metrics — field_size
        # cuenta TODOS los FINISHED del (evento, categoría), tengan o no
        # tiempo registrado (cs.cat_size ya excluye DNF/DNS/DSQ vía el
        # filtro status='finished' del CTE, sin exigir race_time_ms IS NOT
        # NULL); percentile solo se calcula si el atleta terminó y hay
        # pelotón. El guard de ≥5 del percentil por TIEMPO usa
        # cat_size_with_time en su lugar (arriba) — no confundir ambos.
        field_size: Optional[int] = int(cat_size) if cat_size is not None else None
        percentile: Optional[float] = None
        if finished and position is not None and cat_size is not None:
            n_field = int(cat_size)
            pct = (
                100.0
                if n_field <= 1
                else 100.0 * (1.0 - (int(position) - 1) / (n_field - 1))
            )
            percentile = round(pct, 1)

        # position/gap_pct (feature 039, F-1 / B-2): expuestos siempre,
        # independiente de la métrica solicitada — la tarjeta de campeonato
        # del frontend los necesita aunque ``metric`` sea otra cosa.
        position_val: Optional[int] = (
            int(position) if (finished and position is not None) else None
        )
        gap_pct_val: Optional[float] = None
        if (
            finished
            and race_time_ms is not None
            and winner_time_ms is not None
            and int(winner_time_ms) > 0
        ):
            gap_pct_val = round(
                100.0 * (int(race_time_ms) - int(winner_time_ms)) / int(winner_time_ms),
                1,
            )

        # avg_speed_kmh (feature 043, R-11): per-válida only, no aggregate.
        course_setup = (
            setup_by_event_category.get((int(event_id), int(category_id_raw)))
            if category_id_raw is not None
            else None
        )
        avg_speed_kmh_val = derive_figures(
            course_setup,
            str(status) if status is not None else "",
            int(race_time_ms) if race_time_ms is not None else None,
            int(laps_behind_raw) if laps_behind_raw is not None else None,
        ).avg_speed_kmh

        series.append(
            EvolutionPoint(
                valida_num=int(valida_num) if valida_num is not None else 0,
                event_id=int(event_id),
                event_date=event_date,
                value=value,
                unit=unit,
                series_kind=kind_enum.value,
                label=event_label,
                series_id=series_id_val,
                series_name=series_name_val,
                series_level=level_enum.value,
                comparison_group=comparison_group_val,
                field_size=field_size,
                percentile=percentile,
                position=position_val,
                gap_pct=gap_pct_val,
                gap_to_median_pct=gap_to_median_val,
                avg_speed_kmh=avg_speed_kmh_val,
            )
        )
        group_rows.append(
            {
                "series_id": series_id_val,
                "series_name": series_name_val,
                "kind": kind_enum.value,
                "level": level_enum.value,
                "location": location_str,
                "event_date": event_date,
                "value": value,
            }
        )

    groups = _build_comparison_groups(group_rows, season=season)

    filtered_series = series
    selected_group: Optional[str] = None
    if series_id is not None:
        filtered_series = [p for p in series if p.series_id == series_id]
        matched_group = next((g for g in groups if g.series_id == series_id), None)
        if matched_group is not None:
            selected_group = matched_group.comparison_group

    # Confianza: cuenta puntos con valor no-nulo (los que sirven al usuario),
    # calculada sobre la serie YA filtrada por series_id (research D4).
    n_valid = sum(1 for p in filtered_series if p.value is not None)
    return EvolutionResponse(
        season=season,
        metric=metric,
        series=filtered_series,
        confidence=_confidence_from_n(n_valid),
        groups=groups,
        selected_group=selected_group,
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
