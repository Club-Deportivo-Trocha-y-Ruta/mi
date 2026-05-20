"""Nodo 4: ``compute_metrics`` — analítica longitudinal del atleta.

Llama a :func:`analytics.athlete_progression` y :func:`analytics.podium_gap`
(capa determinista de v1) y serializa los DataFrames a JSON
(``to_dict("records")``) para que el LLM pueda consumirlos como tablas
markdown.

Si ``competitor_id`` no está disponible (sin resultados), devuelve
``metrics={}`` y los nodos downstream lo gestionan.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.analytics import athlete_progression, podium_gap

NODE_NAME = "compute_metrics"


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
        podium = (
            await podium_gap(db, category_id, season) if category_id is not None else pd.DataFrame()
        )

    return {
        "metrics": {
            "progression": _df_to_records(progression),
            "podium_gap": _df_to_records(podium),
        }
    }


__all__ = ["compute_metrics", "NODE_NAME"]
