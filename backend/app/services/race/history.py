"""Progresión histórica de un atleta a través de temporadas (feature 044, US6/US7).

Contrato: ``specs/044-race-history-backfill/contracts/history-progression-api.md``
(ver también ``research.md`` R-08/R-09 y ``data-model.md`` §9). Función pura y
síncrona sobre colecciones ORM ya cargadas — mismo patrón que
``field_metrics.compute_field_metrics``, al que ``build_history_points``
llama una vez por temporada en la que el atleta compitió, sin modificarlo
(feature 037/AI contract intactos).

Candado de terceros (T034, ``third_party_guard.py``)
======================================================
A propósito, **ninguna función pública de este módulo recibe
``competitor_id`` como parámetro**: el barrido estructural de
``third_party_guard.py`` marcaría un candidato nuevo y rompería
``tests/privacy/test_third_party_lock.py::test_expected_candidates_matches_current_surface``
(el contrato original de esta feature, línea 40, sí mostraba ``competitor_id``
en la firma — se corrigió aquí, ver nota de desviación en el contrato). En su
lugar, ``build_history_points`` recibe ``athlete_id`` — coherente con "el
historial se indexa por athlete_id, no por competitor_id" (instrucción de
reparto de esta ronda) — y resuelve el ``competitor_id`` de cada temporada
leyéndolo de las filas propias ya cargadas (``own_result.competitor_id``),
nunca como argumento de función. El candado de ``compute_field_metrics``
sigue vigente porque su único llamador aquí (esta función) solo le pasa
``competitor_id`` valores leídos de resultados que YA vienen filtrados por
``athlete_id`` en el cargador del router (T072) — nunca un id crudo de
tercero.

Gate de familia (FR-040/041, R-09)
===================================
``withhold_before`` es el filtro puro; la decisión de aplicarlo (rol
``parent`` + ``RACE_HISTORY_FAMILY_POLICY_VERSION`` no vigente según
``app/services/privacy.py``) vive en el router (``get_history``). Se aplica
a los resultados ANTES de construir puntos y temporadas, de modo que
``category_changed``/``seasons`` se calculan como si lo retirado nunca
hubiera existido — ninguna señal de lo omitido (data-model §10 inv. 6).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.models.race_category import RaceCategory
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.schemas.athlete_race_analysis import HistoryPoint, SeasonCompletion
from app.services.race.field_metrics import compute_field_metrics
from app.services.race.race_labels import build_race_label

__all__ = [
    "MIN_FIELD",
    "HISTORY_CAVEATS",
    "build_history_points",
    "build_season_completions",
    "withhold_before",
]

#: Umbral mínimo de campo para publicar percentil (FR-032) y de finalistas
#: cronometrados para publicar el gap a la mediana (FR-031).
MIN_FIELD = 5

#: Advertencias permanentes (FR-038) — siempre las mismas cinco, en ese orden,
#: nunca condicionales. Única fuente de verdad; el router las expone tal cual.
HISTORY_CAVEATS: tuple[str, ...] = (
    "different_courses",
    "weather_surface",
    "small_fields",
    "non_finishers_excluded",
    "three_rider_categories",
)

#: DNS no cuenta como "salida" (FR-035).
_NOT_STARTED = ResultStatus.DNS
#: FINISHED y MINUS_LAPS cuentan como "terminó" (FR-035, mismo criterio que
#: ``field_metrics._FIELD_MEMBER_STATUSES``).
_FINISHED_STATUSES = (ResultStatus.FINISHED, ResultStatus.MINUS_LAPS)


def _status_value(status: ResultStatus) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _category_change_kind(
    previous: Optional[RaceCategory], new: Optional[RaceCategory]
) -> str:
    """``promotion`` solo con evidencia de catálogo: mismo sexo y ``age_min``
    conocido y mayor en la nueva. Todo lo demás es ``other`` (FR-042)."""
    if (
        previous is not None
        and new is not None
        and previous.sex == new.sex
        and previous.age_min is not None
        and new.age_min is not None
        and new.age_min > previous.age_min
    ):
        return "promotion"
    return "other"


def withhold_before(
    results: list[RaceResult], events: list[RaceEvent], cutoff: date
) -> list[RaceResult]:
    """Descarta TODAS las filas (propias y de campo) de válidas con
    ``event_date < cutoff``.

    Las métricas de campo son por válida (``compute_field_metrics``), así
    que las válidas restantes conservan exactamente sus cifras. Una válida
    sin fecha se descarta también: no se puede demostrar que sea posterior.
    """
    kept_event_ids = {
        e.id for e in events if e.event_date is not None and e.event_date >= cutoff
    }
    return [r for r in results if r.event_id in kept_event_ids]


def build_history_points(
    results: list[RaceResult],
    events: list[RaceEvent],
    series: list[RaceSeries],
    categories: list[RaceCategory],
    athlete_id: int,
    *,
    series_kind: str = "cup",
) -> list[HistoryPoint]:
    """Serie continua multi-temporada de un atleta (FR-030..039).

    Args:
        results: TODOS los ``RaceResult`` relevantes ya cargados — las
            filas propias del atleta (cualquier temporada, cualquier
            estado) MÁS las filas de campo (mismos pares
            ``(event_id, category_id)``, cualquier competidor) que
            ``compute_field_metrics`` necesita para calcular tamaño de
            campo, percentil y mediana. El cargador del router (T072) es
            responsable de restringir esa segunda mitad a los pares del
            propio atleta — este módulo no vuelve a filtrar por privacidad,
            solo agrupa.
        events / series / categories: catálogo ya cargado (no hace falta
            que cubra toda la BD, solo lo que aparece en ``results``).
        athlete_id: PK de ``Athlete`` — identifica las filas "propias" vía
            ``RaceResult.athlete_id`` (nunca ``competitor_id``, ver
            docstring del módulo).
        series_kind: ``"cup" | "championship" | "all"`` (default ``"cup"``,
            contrato). Filtra las filas propias ANTES de calcular
            ``category_changed``/``seasons`` — la continuidad se evalúa
            sobre la vista solicitada, no sobre el histórico completo con
            eventos ocultos de por medio.

    Returns:
        Una lista de :class:`HistoryPoint`, en orden cronológico ascendente.
    """
    events_by_id: dict[int, RaceEvent] = {e.id: e for e in events}
    series_by_id: dict[int, RaceSeries] = {s.id: s for s in series}
    categories_by_id: dict[int, RaceCategory] = {c.id: c for c in categories}

    live_results = [r for r in results if getattr(r, "deleted_at", None) is None]

    own_rows: list[RaceResult] = []
    for r in live_results:
        if r.athlete_id != athlete_id:
            continue
        event = events_by_id.get(r.event_id)
        if event is None:
            continue
        s = series_by_id.get(event.series_id)
        if s is None or event.event_date is None:
            continue
        if series_kind != "all":
            kind_str = s.kind.value if hasattr(s.kind, "value") else str(s.kind)
            if kind_str != series_kind:
                continue
        own_rows.append(r)

    own_rows.sort(key=lambda r: (events_by_id[r.event_id].event_date, r.event_id))

    if not own_rows:
        return []

    # --- timed_finishers por (event_id, category_id) — mismo criterio que
    # ``compute_field_metrics`` (FINISHED estricto, con tiempo), pero expuesto
    # aquí porque ``compute_field_metrics`` no lo devuelve (contrato 037 fijo).
    timed_finishers_by_pair: dict[tuple[int, int], int] = {}
    for r in live_results:
        if r.status == ResultStatus.FINISHED and r.race_time_ms is not None:
            key = (r.event_id, r.category_id)
            timed_finishers_by_pair[key] = timed_finishers_by_pair.get(key, 0) + 1

    # --- métricas de campo por temporada — UNA llamada por (season, competitor_id)
    # presente entre las filas propias filtradas; se fusionan por event_id.
    seasons_with_competitor: dict[int, set[int]] = {}
    for r in own_rows:
        event = events_by_id[r.event_id]
        s = series_by_id[event.series_id]
        seasons_with_competitor.setdefault(s.season_year, set()).add(r.competitor_id)

    metrics_by_event: dict[int, dict] = {}
    for season, competitor_ids in seasons_with_competitor.items():
        for competitor_id in competitor_ids:
            per_event = compute_field_metrics(
                results=results,
                events=events,
                series=series,
                categories=categories,
                competitor_id=competitor_id,
                season=season,
            )
            metrics_by_event.update(per_event)

    points: list[HistoryPoint] = []
    previous_category_id: Optional[int] = None
    previous_category_label: Optional[str] = None

    for r in own_rows:
        event = events_by_id[r.event_id]
        s = series_by_id[event.series_id]
        category = categories_by_id.get(r.category_id)

        frozen_label = getattr(r, "category_label_raw", None)
        category_label = frozen_label or (category.label if category else "")
        category_code = category.code if category else ""

        category_changed = previous_category_id is not None and r.category_id != previous_category_id
        prev_label_for_point = previous_category_label if category_changed else None
        change_kind = (
            _category_change_kind(categories_by_id.get(previous_category_id), category)
            if category_changed
            else None
        )

        m = metrics_by_event.get(r.event_id, {})
        field_size = m.get("field_size")
        timed_finishers = timed_finishers_by_pair.get((r.event_id, r.category_id))

        percentile = m.get("percentile")
        if field_size is None or field_size < MIN_FIELD:
            percentile = None

        gap_to_median_pct = m.get("gap_to_median_pct")
        if timed_finishers is None or timed_finishers < MIN_FIELD:
            gap_to_median_pct = None

        kind_str = s.kind.value if hasattr(s.kind, "value") else str(s.kind)

        status_str = _status_value(r.status)

        label = build_race_label(
            s.kind,
            event.sequence_number,
            event.location,
            level=s.level,
        )

        points.append(
            HistoryPoint(
                event_id=r.event_id,
                event_date=event.event_date,
                season=s.season_year,
                label=label,
                series_id=s.id,
                series_name=s.name,
                series_kind=kind_str,  # type: ignore[arg-type]
                category_code=category_code,
                category_label=category_label,
                category_changed=category_changed,
                previous_category_label=prev_label_for_point,
                category_change_kind=change_kind,  # type: ignore[arg-type]
                status=status_str,  # type: ignore[arg-type]
                position=m.get("position"),
                field_size=field_size,
                timed_finishers=timed_finishers,
                percentile=percentile,
                gap_to_median_pct=gap_to_median_pct,
                gap_to_winner_pct=m.get("gap_pct"),
                points_awarded=r.points_awarded or 0,
            )
        )

        previous_category_id = r.category_id
        previous_category_label = category_label

    return points


def build_season_completions(
    results: list[RaceResult],
    events: list[RaceEvent],
    series: list[RaceSeries],
    athlete_id: int,
    *,
    series_kind: str = "cup",
) -> list[SeasonCompletion]:
    """Resumen "N de M" por temporada (FR-035) — mismas filas que alimentan
    :func:`build_history_points`, filtradas igual por ``series_kind``.
    """
    events_by_id: dict[int, RaceEvent] = {e.id: e for e in events}
    series_by_id: dict[int, RaceSeries] = {s.id: s for s in series}

    counts: dict[int, dict[str, int]] = {}
    for r in results:
        if getattr(r, "deleted_at", None) is not None or r.athlete_id != athlete_id:
            continue
        event = events_by_id.get(r.event_id)
        if event is None:
            continue
        s = series_by_id.get(event.series_id)
        if s is None:
            continue
        if series_kind != "all":
            kind_str = s.kind.value if hasattr(s.kind, "value") else str(s.kind)
            if kind_str != series_kind:
                continue
        entry = counts.setdefault(s.season_year, {"started": 0, "finished": 0})
        if r.status != _NOT_STARTED:
            entry["started"] += 1
        if r.status in _FINISHED_STATUSES:
            entry["finished"] += 1

    return [
        SeasonCompletion(season=season, started=v["started"], finished=v["finished"])
        for season, v in sorted(counts.items())
    ]
