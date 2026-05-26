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
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

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

    return {
        "metrics": {
            "progression": _df_to_records(progression),
            "podium_gap": podium_self_records,
            "podium_peers_stats": podium_peers_stats,
        }
    }


__all__ = ["compute_metrics", "NODE_NAME"]
