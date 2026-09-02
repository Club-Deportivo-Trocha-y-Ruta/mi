"""``compute_field_metrics`` — lectura del atleta contra el pelotón (feature 037).

Implementa el contrato de ``specs/037-ai-insights-v3-causal/data-model.md``
§FieldMetrics y la regla "Expected-vs-actual" de ``plan.md``.

Entrada: colecciones ORM ya cargadas (``RaceResult``/``RaceEvent``/
``RaceSeries``/``RaceCategory``) vía :mod:`app.services.race.queries`
(``load_results``/``load_events``/``load_series``/``load_categories``).
Es una función **pura y síncrona**: no hace I/O, solo pandas/Python puro
sobre listas de objetos ORM ya en memoria — sigue el patrón de
``analytics.athlete_progression`` (joins en Python, no en SQL).

Salida: ``dict[int, dict]`` keyed por ``event_id`` — una entrada por cada
válida de la temporada en la que ``competitor_id`` tiene un ``RaceResult``
(cualquier estado; los campos derivados de tiempo/posición quedan en
``None`` cuando el estado no es ``finished``). Cada valor es un dict
JSON-serializable con las claves de ``FieldMetrics`` del data-model,
redondeadas a 1 decimal, sin exponer ids de otros corredores.

Privacidad (CLAUDE.md): la salida nunca incluye ``competitor_id`` de
terceros — solo agregados (``field_size``, ``field_strength``,
``category_median_time_ms``) y los valores propios del atleta analizado.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean, median
from typing import Any, Optional

from app.models.race_category import RaceCategory
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries

__all__ = ["compute_field_metrics"]


def _round1(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 1)


def compute_field_metrics(
    results: list[RaceResult],
    events: list[RaceEvent],
    series: list[RaceSeries],
    categories: list[RaceCategory],
    competitor_id: int,
    season: int,
) -> dict[int, dict[str, Any]]:
    """Calcula ``FieldMetrics`` por válida para ``competitor_id`` en ``season``.

    Args:
        results: ``RaceResult`` ya filtrados de ``deleted_at`` (o no —
            se filtran de nuevo aquí por seguridad, igual que
            ``queries.load_results``).
        events: ``RaceEvent`` de cualquier temporada (se filtra por
            ``season`` internamente vía ``series``).
        series: ``RaceSeries`` de cualquier temporada.
        categories: ``RaceCategory`` (catálogo; usado solo si se necesita
            enriquecer en el futuro — hoy no se expone en la salida).
        competitor_id: PK de ``RaceCompetitor`` del atleta analizado.
        season: año de temporada (``RaceSeries.season_year``).

    Returns:
        ``{event_id: {..FieldMetrics..}}``. Vacío si el competidor no
        tiene ningún ``RaceResult`` en eventos de esa temporada.
    """
    del categories  # reservado — no se usa hoy, mantenido por firma estable.

    live_results = [r for r in results if getattr(r, "deleted_at", None) is None]

    events_by_id: dict[int, RaceEvent] = {e.id: e for e in events}
    series_by_id: dict[int, RaceSeries] = {s.id: s for s in series}

    season_event_ids = {
        eid
        for eid, e in events_by_id.items()
        if series_by_id.get(e.series_id) is not None
        and series_by_id[e.series_id].season_year == season
    }
    if not season_event_ids:
        return {}

    # --- Agrupa resultados FINISHED de la temporada por (event_id, category_id) ---
    finished_in_season = [
        r
        for r in live_results
        if r.event_id in season_event_ids and r.status == ResultStatus.FINISHED
    ]
    by_event_category: dict[tuple[int, int], list[RaceResult]] = defaultdict(list)
    for r in finished_in_season:
        by_event_category[(r.event_id, r.category_id)].append(r)

    # --- gap_pct por resultado, relativo al ganador (position==1) de su (evento, categoría) ---
    gap_pct_by_result: dict[int, float] = {}
    for (_eid, _cid), rows in by_event_category.items():
        winner = next((r for r in rows if r.position == 1), None)
        if winner is None or winner.race_time_ms in (None, 0):
            continue
        wt = winner.race_time_ms
        for r in rows:
            if r.race_time_ms is not None:
                gap_pct_by_result[r.id] = 100.0 * (r.race_time_ms - wt) / wt

    # --- índice histórico por competidor: [(event_date, gap_pct), ...] ---
    history_by_competitor: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for (eid, _cid), rows in by_event_category.items():
        ev = events_by_id.get(eid)
        if ev is None or ev.event_date is None:
            continue
        for r in rows:
            g = gap_pct_by_result.get(r.id)
            if g is not None:
                history_by_competitor[r.competitor_id].append((ev.event_date, g))

    def _prior_index(comp_id: int, before: date) -> Optional[float]:
        vals = [g for d, g in history_by_competitor.get(comp_id, []) if d < before]
        return mean(vals) if vals else None

    # --- Resultados propios del atleta en eventos de la temporada (cualquier estado) ---
    own_results = [
        r
        for r in live_results
        if r.competitor_id == competitor_id and r.event_id in season_event_ids
    ]

    out: dict[int, dict[str, Any]] = {}
    for r in own_results:
        event = events_by_id.get(r.event_id)
        if event is None:
            continue
        s = series_by_id.get(event.series_id)
        rows = by_event_category.get((r.event_id, r.category_id), [])
        n = len(rows)

        is_finished = r.status == ResultStatus.FINISHED
        position = r.position if is_finished else None

        percentile: Optional[float] = None
        if position is not None:
            percentile = 100.0 if n <= 1 else 100.0 * (1 - (position - 1) / (n - 1))
            percentile = _round1(percentile)

        winner_row = next((x for x in rows if x.position == 1), None)
        p3_row = next((x for x in rows if x.position == 3), None)

        gap_to_p1_ms: Optional[int] = None
        gap_pct: Optional[float] = None
        if winner_row is not None and r.race_time_ms is not None and winner_row.race_time_ms is not None:
            gap_to_p1_ms = r.race_time_ms - winner_row.race_time_ms
            gap_pct = _round1(gap_pct_by_result.get(r.id))

        gap_to_p3_ms: Optional[int] = None
        if p3_row is not None and r.race_time_ms is not None and p3_row.race_time_ms is not None:
            gap_to_p3_ms = r.race_time_ms - p3_row.race_time_ms

        times = [x.race_time_ms for x in rows if x.race_time_ms is not None]
        category_median_time_ms: Optional[int] = None
        gap_to_median_pct: Optional[float] = None
        if times:
            med = median(times)
            category_median_time_ms = int(round(med))
            if r.race_time_ms is not None and med:
                gap_to_median_pct = _round1(100.0 * (r.race_time_ms - med) / med)

        # --- prior_index / expected_position / delta / field_strength ---
        own_prior_index = _prior_index(competitor_id, event.event_date) if event.event_date else None

        priors_by_result: dict[int, float] = {}
        if event.event_date is not None:
            for x in rows:
                pv = _prior_index(x.competitor_id, event.event_date)
                if pv is not None:
                    priors_by_result[x.id] = pv

        coverage_with_prior = (len(priors_by_result) / n) if n else 0.0

        expected_position: Optional[int] = None
        delta_vs_expected: Optional[int] = None
        field_strength: Optional[float] = None

        if n > 0 and coverage_with_prior >= 0.5:
            field_strength = _round1(mean(priors_by_result.values()))
            if r.id in priors_by_result:
                # Menor gap_pct histórico = mejor desempeño esperado.
                ranked = sorted(priors_by_result.items(), key=lambda kv: kv[1])
                rank_among_with_prior = next(
                    idx for idx, (rid, _v) in enumerate(ranked) if rid == r.id
                )
                m = len(ranked)
                expected_position = round(
                    1 + rank_among_with_prior * (n - 1) / max(m - 1, 1)
                )
                if position is not None:
                    delta_vs_expected = expected_position - position

        is_championship = bool(getattr(event, "is_championship", False))
        series_kind = s.kind.value if s is not None and hasattr(s.kind, "value") else (str(s.kind) if s else None)
        series_level = (
            s.level.value if s is not None and hasattr(s.level, "value") else (str(s.level) if s else None)
        )

        out[r.event_id] = {
            "event_id": r.event_id,
            "valida_num": event.sequence_number,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "series_kind": series_kind,
            "series_level": series_level,
            "is_championship": is_championship,
            "field_size": n,
            "position": position,
            "percentile": percentile,
            "race_time_ms": r.race_time_ms if is_finished else None,
            "gap_to_p1_ms": gap_to_p1_ms,
            "gap_pct": gap_pct,
            "gap_to_p3_ms": gap_to_p3_ms,
            "category_median_time_ms": category_median_time_ms,
            "gap_to_median_pct": gap_to_median_pct,
            "laps_behind": r.laps_behind,
            "prior_index": _round1(own_prior_index),
            "expected_position": expected_position,
            "delta_vs_expected": delta_vs_expected,
            "field_strength": field_strength,
            "coverage_with_prior": _round1(coverage_with_prior),
        }

    return out
