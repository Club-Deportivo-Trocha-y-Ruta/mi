"""Nodo 4: ``compute_metrics`` — analítica longitudinal del atleta.

Llama a :func:`analytics.athlete_progression` y :func:`analytics.podium_gap`
(capa determinista de v1) y serializa los DataFrames a JSON
(``to_dict("records")``) para que el LLM pueda consumirlos como tablas
markdown.

Privacidad — scrub de PII de terceros menores:
- ``podium_gap`` devuelve filas para TODOS los corredores TyR de la categoría.
  Este nodo filtra para quedarse SOLO con la fila del atleta analizado
  (sin ``competitor_id`` en el output al LLM).
- Se calculan estadísticos anónimos de la distribución de la categoría
  (mediana, p25, p75 de gap_pct) que se exponen como contexto agregado
  sin identificadores individuales.

Si ``competitor_id`` no está disponible (sin resultados), devuelve
``metrics={}`` y los nodos downstream lo gestionan.

Season comparative (T013 — feature 010, reescrito en T033 — feature 039):
- ``season_comparative``: list of dicts, one per PRIOR race of the SAME
  series as the analyzed race, with an earlier ``event_date``, ordered by
  date. Each entry includes position, race_time_ms, field_size,
  delta_position, and delta_time_ms vs. the analyzed race. Deltas use None
  when either time is unavailable (DNF/DNS/minus_laps). All data is sourced
  from state["full_season_results"] — never fabricated.
- ``progression_assessment``: ProgressionAssessment enum value derived from
  position comparisons across prior races. Computed entirely in Python;
  the LLM is never asked to perform this arithmetic.

Grupos de comparación (feature 039):
- ``metrics.progression`` se mantiene plana e intacta (compatibilidad).
- ``metrics.progression_groups`` la reparte en copas (por ``series_id``) y
  campeonatos vía :func:`comparison_groups.split_progression`.
- Un campeonato reúne un pelotón distinto al de una válida de copa: nunca
  entra como antecedente de una copa (ni al revés), así que un campeonato
  analizado devuelve ``([], first_reference)`` — INV-2, un campeonato tiene
  una sola carrera y por tanto jamás tiene un antecedente de su misma serie.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.schemas.race_ai import ProgressionAssessment
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.analytics import athlete_progression, podium_gap
from app.services.race.comparison_groups import split_progression
from app.services.race.field_metrics import compute_field_metrics
from app.services.race.queries import load_categories, load_events, load_results, load_series
from app.services.race.race_labels import build_race_label

NODE_NAME = "compute_metrics"

logger = logging.getLogger(__name__)


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convierte DataFrame a list[dict] JSON-safe (NaT/NaN → None)."""
    if df is None or df.empty:
        return []
    # Convertir tipos pandas nullable a Python nativo.
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


# ---------------------------------------------------------------------------
# Season comparative computation (T013)
# ---------------------------------------------------------------------------


def _series_kind(record: dict[str, Any]) -> RaceSeriesKind:
    """Normaliza el ``series_kind`` de un registro de temporada.

    Acepta el enum o su valor string, y cae a ``cup`` cuando falta o es
    desconocido: los fixtures previos a la feature 039 no traen la clave y
    deben seguir resolviendo la carrera analizada por ``valida_num``.
    """
    raw = record.get("series_kind")
    raw = getattr(raw, "value", raw)
    try:
        return RaceSeriesKind(str(raw)) if raw else RaceSeriesKind.cup
    except ValueError:
        return RaceSeriesKind.cup


def _series_level(record: dict[str, Any]) -> RaceSeriesLevel:
    """Normaliza el ``series_level`` de un registro (default ``departmental``)."""
    raw = record.get("series_level")
    raw = getattr(raw, "value", raw)
    try:
        return RaceSeriesLevel(str(raw)) if raw else RaceSeriesLevel.departmental
    except ValueError:
        return RaceSeriesLevel.departmental


def _event_sort_key(record: dict[str, Any]) -> tuple[str, int]:
    """Clave de orden cronológico: ``event_date`` y, a igualdad, ``valida_num``."""
    return (str(record.get("event_date") or ""), record.get("valida_num") or 0)


def _is_earlier(candidate: dict[str, Any], analyzed: dict[str, Any]) -> bool:
    """¿``candidate`` ocurrió antes que ``analyzed``?

    Compara por ``event_date`` (ISO, comparable como cadena). Si alguno de
    los dos no la trae — fixtures previos a la feature 039 —, cae al
    ``sequence_number``, que dentro de una misma serie sí es monótono.
    """
    candidate_date = candidate.get("event_date")
    analyzed_date = analyzed.get("event_date")
    if candidate_date is not None and analyzed_date is not None:
        return str(candidate_date) < str(analyzed_date)

    candidate_vn = candidate.get("valida_num")
    analyzed_vn = analyzed.get("valida_num")
    return (
        candidate_vn is not None
        and analyzed_vn is not None
        and candidate_vn < analyzed_vn
    )


def _find_analyzed_record(
    full_season_results: list[dict[str, Any]],
    analyzed_valida_nums: list[int],
    anchored_event_id: int | None,
) -> Optional[dict[str, Any]]:
    """Localiza el registro de la carrera analizada.

    Regla 1 del contrato (``contracts/ai-context.md``): si el lanzamiento
    viene anclado a un ``event_id``, esa es la carrera — nunca se resuelve
    por ``valida_num`` a secas. Sin ancla, ``valida_num`` solo puede
    resolverse entre filas de copa: desde spec 014 un campeonato comparte
    ``sequence_number`` con la Válida I y solo puede analizarse anclado.
    """
    if anchored_event_id is not None:
        anchored = next(
            (r for r in full_season_results if r.get("event_id") == anchored_event_id),
            None,
        )
        if anchored is not None:
            return anchored

    if not analyzed_valida_nums:
        return None

    # La carrera "actual" es la primera cronológica del set lanzado.
    analyzed_vn = min(analyzed_valida_nums)
    return next(
        (
            r
            for r in full_season_results
            if r.get("valida_num") == analyzed_vn
            and _series_kind(r) is RaceSeriesKind.cup
        ),
        None,
    )


def _compute_season_comparative(
    full_season_results: list[dict[str, Any]],
    analyzed_valida_nums: list[int],
    *,
    anchored_event_id: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Compute season_comparative entries and progression_assessment.

    Args:
        full_season_results: Records from state["full_season_results"]. Each
            record is a dict with keys: result_id, event_id, valida_num,
            event_date, series_id, series_kind, series_level, position,
            race_time_ms, gap_to_winner_ms, gap_pct, status.
            This list already excludes DNS/DNF/DSQ (filtered in load_race_data).
        analyzed_valida_nums: The valida_nums being analyzed in this run
            (from state["valida_nums"]). Without an anchor, the analyzed race
            is the CUP round whose sequence_number is the minimum of this set.
        anchored_event_id: ``state["event_id"]`` when the run was launched
            from a concrete competition. Takes precedence over
            ``analyzed_valida_nums``: es el único identificador no ambiguo
            de una carrera dentro de la temporada (spec 014).

    Returns:
        Tuple of (season_comparative, progression_assessment_value).
        - season_comparative: one entry per prior race of the SAME series,
          sorted by event_date ascending.
        - progression_assessment_value: string value of ProgressionAssessment.

    Notes:
        - Deltas: analyzed - prior (positive delta_position means position
          number went up, i.e. worse; positive delta_time_ms means slower).
        - Priors are restricted to the analyzed race's ``series_id``. Un
          campeonato reúne un pelotón distinto: comparar su puesto con el de
          una válida de copa (o el de otra copa) es una comparación inválida.
        - Un campeonato analizado devuelve ``([], first_reference)`` (INV-2:
          una serie de campeonato tiene exactamente una carrera).
        - field_size is always None here: full_season_results only carries
          the athlete's own row; category-wide count is not available without
          a separate DB query.
        - DNF/minus_laps entries in full_season_results are already excluded
          by load_race_data (only finishers are kept). If the analyzed race
          itself has no time we still compute delta_time_ms as None.
    """
    if not full_season_results or (not analyzed_valida_nums and anchored_event_id is None):
        return [], ProgressionAssessment.first_reference.value

    analyzed_record = _find_analyzed_record(
        full_season_results, analyzed_valida_nums, anchored_event_id
    )
    if analyzed_record is None:
        # No result for the analyzed race — no comparatives possible.
        return [], ProgressionAssessment.first_reference.value

    if _series_kind(analyzed_record) is RaceSeriesKind.championship:
        # INV-2: la serie del campeonato tiene una sola carrera, así que no
        # existe ningún antecedente comparable. Nunca se cruza con una copa.
        return [], ProgressionAssessment.first_reference.value

    analyzed_position: Optional[int] = analyzed_record.get("position")
    analyzed_time_ms: Optional[int] = analyzed_record.get("race_time_ms")
    analyzed_series_id = analyzed_record.get("series_id")

    # Antecedentes: misma serie, fecha anterior. Se ordenan por fecha y se
    # deduplica por válida (dentro de una serie, ``sequence_number`` es único).
    prior_records = [
        r
        for r in full_season_results
        if r is not analyzed_record
        and r.get("valida_num") is not None
        and r.get("series_id") == analyzed_series_id
        and _is_earlier(r, analyzed_record)
    ]

    if not prior_records:
        return [], ProgressionAssessment.first_reference.value

    seen_validas: set[int] = set()
    comparative: list[dict[str, Any]] = []
    for prior in sorted(prior_records, key=_event_sort_key):
        vn = prior["valida_num"]
        if vn in seen_validas:
            continue
        seen_validas.add(vn)

        prior_position: Optional[int] = prior.get("position")
        prior_time_ms: Optional[int] = prior.get("race_time_ms")

        # delta = analyzed - prior (None when either value is unavailable).
        delta_position: Optional[int] = (
            analyzed_position - prior_position
            if analyzed_position is not None and prior_position is not None
            else None
        )
        delta_time_ms: Optional[int] = (
            analyzed_time_ms - prior_time_ms
            if analyzed_time_ms is not None and prior_time_ms is not None
            else None
        )

        comparative.append({
            "valida_num": vn,
            "event_label": build_race_label(
                _series_kind(prior), vn, None, level=_series_level(prior)
            ),
            "position": prior_position,
            "race_time_ms": prior_time_ms,
            "field_size": None,  # not available without a category-wide query
            "delta_position": delta_position,
            "delta_time_ms": delta_time_ms,
        })

    # Derive progression_assessment from position comparisons.
    # Lower position number = better result.
    if analyzed_position is None:
        assessment = ProgressionAssessment.first_reference.value
    else:
        prior_positions = [
            c["position"] for c in comparative if c["position"] is not None
        ]
        if not prior_positions:
            # All priors had no position (shouldn't happen after finisher filter).
            assessment = ProgressionAssessment.first_reference.value
        else:
            strictly_better = all(analyzed_position < p for p in prior_positions)
            strictly_worse = all(analyzed_position > p for p in prior_positions)
            all_equal = all(analyzed_position == p for p in prior_positions)

            if strictly_better:
                assessment = ProgressionAssessment.improving.value
            elif strictly_worse:
                assessment = ProgressionAssessment.declining.value
            elif all_equal:
                assessment = ProgressionAssessment.stable.value
            else:
                assessment = ProgressionAssessment.mixed.value

    return comparative, assessment


def _build_progression_groups(
    progression_records: list[dict[str, Any]], season: int | None
) -> dict[str, Any]:
    """Reparte ``metrics.progression`` en copas y campeonatos (feature 039).

    Args:
        progression_records: filas planas de ``athlete_progression``.
        season: año de temporada del lanzamiento. ``athlete_progression`` no
            expone ``season_year`` y ``split_progression`` lo necesita para
            etiquetar la copa, así que se rellena desde el state.

    Returns:
        ``{"cups": {"<series_id>": [filas]}, "championships": [filas]}``.
        Las claves de ``cups`` son ``str`` (JSON no tiene claves enteras;
        ``contracts/ai-context.md`` las documenta como ``"<series_id>"`` —
        F-7). Las filas sin ``series_id`` se omiten (no hay grupo al que
        asignarlas).
    """
    rows: list[dict[str, Any]] = [
        r if r.get("season_year") is not None else {**r, "season_year": season}
        for r in progression_records
        if r.get("series_id") is not None
    ]
    split = split_progression(rows)
    return {
        "cups": {str(cup.series_id): cup.rows for cup in split.cups},
        "championships": split.championships,
    }


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def compute_metrics(state: dict) -> dict[str, Any]:
    competitor_id = state.get("competitor_id")
    category_id = state.get("category_id")
    season = state["season"]

    if competitor_id is None:
        return {"metrics": {}}

    async with get_session() as db:
        progression = await athlete_progression(db, competitor_id)
        podium_full = (
            await podium_gap(db, category_id, season) if category_id is not None else pd.DataFrame()
        )
        # Feature 037: lectura del atleta contra el pelotón (expected-vs-actual).
        results = await load_results(db)
        events = await load_events(db)
        series = await load_series(db)
        categories = await load_categories(db)

    field_context = compute_field_metrics(
        results=results,
        events=events,
        series=series,
        categories=categories,
        competitor_id=competitor_id,
        season=season,
    )

    # --- Scrub PII de terceros: filtrar solo la fila del atleta analizado ---
    # ``podium_full`` contiene filas de TODOS los corredores TyR de la
    # categoría. Solo propagamos la fila del atleta al contexto LLM, y
    # calculamos estadísticos anónimos de los peers.
    podium_self_records: list[dict[str, Any]] = []
    podium_peers_stats: dict[str, Any] = {}

    if not podium_full.empty and "competitor_id" in podium_full.columns:
        podium_self_df = podium_full[
            podium_full["competitor_id"] == competitor_id
        ].drop(columns=["competitor_id"])
        podium_self_records = _df_to_records(podium_self_df)

        # Estadísticos anónimos de la distribución completa (incluye al atleta).
        if "gap_pct" in podium_full.columns:
            gap_series = pd.to_numeric(podium_full["gap_pct"], errors="coerce").dropna()
            if not gap_series.empty:
                podium_peers_stats = {
                    "category_median_gap_pct": round(float(gap_series.median()), 2),
                    "category_p25_gap_pct": round(float(gap_series.quantile(0.25)), 2),
                    "category_p75_gap_pct": round(float(gap_series.quantile(0.75)), 2),
                }
    elif not podium_full.empty:
        # DataFrame sin columna competitor_id (estructura inesperada).
        logger.warning(
            "compute_metrics: podium_full sin columna 'competitor_id'; "
            "no se puede filtrar por atleta. Se omite podium_gap del contexto."
        )

    # --- Season comparative (T013 — feature 010, T033 — feature 039) ---
    # Computed entirely in Python from state["full_season_results"],
    # state["valida_nums"] y state["event_id"] (ancla del lanzamiento).
    # The LLM never performs this arithmetic.
    full_season_results: list[dict[str, Any]] = state.get("full_season_results") or []
    valida_nums: list[int] | None = state.get("valida_nums")
    anchored_event_id: int | None = state.get("event_id")

    season_comparative: list[dict[str, Any]] = []
    progression_assessment: str = ProgressionAssessment.first_reference.value

    if full_season_results and (valida_nums or anchored_event_id is not None):
        season_comparative, progression_assessment = _compute_season_comparative(
            full_season_results,
            valida_nums or [],
            anchored_event_id=anchored_event_id,
        )

    progression_records = _df_to_records(progression)

    return {
        "metrics": {
            "progression": progression_records,
            "progression_groups": _build_progression_groups(progression_records, season),
            "podium_gap": podium_self_records,
            "podium_peers_stats": podium_peers_stats,
            "field": field_context,
        },
        "field_context": field_context,
        "season_comparative": season_comparative,
        "progression_assessment": progression_assessment,
    }


__all__ = ["compute_metrics", "NODE_NAME", "_compute_season_comparative"]
