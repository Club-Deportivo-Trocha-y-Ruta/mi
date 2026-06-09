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

Season comparative (T013 — feature 010):
- ``season_comparative``: list of dicts, one per PRIOR válida (sequence_number
  < min(valida_nums) for the analyzed set, same season). Each entry includes
  position, race_time_ms, field_size, delta_position, and delta_time_ms vs.
  the analyzed válida. Deltas use None when either time is unavailable
  (DNF/DNS/minus_laps). All data is sourced from state["full_season_results"]
  — never fabricated.
- ``progression_assessment``: ProgressionAssessment enum value derived from
  position comparisons across prior válidas. Computed entirely in Python;
  the LLM is never asked to perform this arithmetic.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from app.schemas.race_ai import ProgressionAssessment
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.analytics import athlete_progression, podium_gap

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


def _event_label(valida_num: int) -> str:
    """Construye un label legible para una válida dado su sequence_number.

    Uses the Copa Valle convention: válidas 1-7 are "Válida N",
    sequence_number 99 is "Cto. Departamental".
    """
    if valida_num == 99:
        return "Cto. Departamental"
    return f"Válida {valida_num}"


def _compute_season_comparative(
    full_season_results: list[dict[str, Any]],
    analyzed_valida_nums: list[int],
) -> tuple[list[dict[str, Any]], str]:
    """Compute season_comparative entries and progression_assessment.

    Args:
        full_season_results: Records from state["full_season_results"]. Each
            record is a dict with keys: result_id, event_id, valida_num,
            position, race_time_ms, gap_to_winner_ms, gap_pct, status.
            This list already excludes DNS/DNF/DSQ (filtered in load_race_data).
        analyzed_valida_nums: The valida_nums being analyzed in this run
            (from state["valida_nums"]). The "current" válida is the
            minimum sequence_number in this set (chronologically first
            of the analyzed set). Prior válidas have sequence_number
            strictly less than this minimum.

    Returns:
        Tuple of (season_comparative, progression_assessment_value).
        - season_comparative: list of dicts, one entry per prior válida,
          sorted by valida_num ascending.
        - progression_assessment_value: string value of ProgressionAssessment.

    Notes:
        - Deltas: analyzed - prior (positive delta_position means position
          number went up, i.e. worse; positive delta_time_ms means slower).
        - The "analyzed" result is the athlete's result for the minimum
          valida_num in analyzed_valida_nums (the focus válida for comparison).
        - field_size is always None here: full_season_results only carries
          the athlete's own row; category-wide count is not available without
          a separate DB query.
        - DNF/minus_laps entries in full_season_results are already excluded
          by load_race_data (only finishers are kept). If the analyzed válida
          itself has no time we still compute delta_time_ms as None.
    """
    if not full_season_results or not analyzed_valida_nums:
        return [], ProgressionAssessment.first_reference.value

    # Use the minimum analyzed valida_num as the "analyzed" reference point.
    analyzed_vn = min(analyzed_valida_nums)

    # Find the analyzed válida's own result in full_season_results.
    analyzed_records = [
        r for r in full_season_results if r.get("valida_num") == analyzed_vn
    ]
    if not analyzed_records:
        # No result for the analyzed válida — no comparatives possible.
        return [], ProgressionAssessment.first_reference.value

    analyzed_record = analyzed_records[0]
    analyzed_position: Optional[int] = analyzed_record.get("position")
    analyzed_time_ms: Optional[int] = analyzed_record.get("race_time_ms")

    # Collect prior válidas: sequence_number strictly less than analyzed_vn.
    prior_records = [
        r for r in full_season_results if r.get("valida_num") is not None
        and r["valida_num"] < analyzed_vn
    ]

    if not prior_records:
        return [], ProgressionAssessment.first_reference.value

    # Group by valida_num and take the first record per válida.
    prior_by_vn: dict[int, dict[str, Any]] = {}
    for r in prior_records:
        vn = r["valida_num"]
        if vn not in prior_by_vn:
            prior_by_vn[vn] = r

    comparative: list[dict[str, Any]] = []
    for vn in sorted(prior_by_vn.keys()):
        prior = prior_by_vn[vn]
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
            "event_label": _event_label(vn),
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

    # --- Season comparative (T013 — feature 010) ---
    # Computed entirely in Python from state["full_season_results"] and
    # state["valida_nums"]. The LLM never performs this arithmetic.
    full_season_results: list[dict[str, Any]] = state.get("full_season_results") or []
    valida_nums: list[int] | None = state.get("valida_nums")

    season_comparative: list[dict[str, Any]] = []
    progression_assessment: str = ProgressionAssessment.first_reference.value

    if full_season_results and valida_nums:
        season_comparative, progression_assessment = _compute_season_comparative(
            full_season_results, valida_nums
        )

    return {
        "metrics": {
            "progression": _df_to_records(progression),
            "podium_gap": podium_self_records,
            "podium_peers_stats": podium_peers_stats,
        },
        "season_comparative": season_comparative,
        "progression_assessment": progression_assessment,
    }


__all__ = ["compute_metrics", "NODE_NAME", "_compute_season_comparative", "_event_label"]
