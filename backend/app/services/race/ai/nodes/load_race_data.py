"""Nodo 2: ``load_race_data`` — carga raw data del atleta + contexto podio.

Llama a :func:`queries.fetch_results_for_athlete` para traer los results
de la temporada y a :func:`queries.fetch_podium_context` para el evento
foco (el más reciente). Identifica ``competitor_id`` y ``category_id``
desde el primer resultado.

Si no hay resultados → no es error fatal (validate_input ya verificó
``athlete_exists``), pero el state queda con ``raw_data=[]`` y nodos
downstream lo gestionan.
"""

from __future__ import annotations

from typing import Any

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.queries import fetch_podium_context, fetch_results_for_athlete

NODE_NAME = "load_race_data"


def _serialize_result(r: Any) -> dict[str, Any]:
    """Convierte un RaceResult ORM a dict JSON-serializable."""
    return {
        "result_id": getattr(r, "id", None),
        "event_id": getattr(r, "event_id", None),
        "category_id": getattr(r, "category_id", None),
        "competitor_id": getattr(r, "competitor_id", None),
        "athlete_id": getattr(r, "athlete_id", None),
        "position": getattr(r, "position", None),
        "race_time_ms": getattr(r, "race_time_ms", None),
        "points_awarded": getattr(r, "points_awarded", None),
        "status": getattr(r.status, "value", None) if getattr(r, "status", None) else None,
    }


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def load_race_data(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]
    season = state["season"]
    valida_nums = state.get("valida_nums")

    async with get_session() as db:
        results = await fetch_results_for_athlete(db, athlete_id, season, valida_nums)
        serialized = [_serialize_result(r) for r in results]

        if not serialized:
            return {
                "raw_data": [],
                "competitor_id": None,
                "category_id": None,
                "podium_context": {},
            }

        first = serialized[0]
        competitor_id = first.get("competitor_id")
        category_id = first.get("category_id")

        # Evento foco: el último cronológico (results ya viene ordenado asc).
        focus_event_id = serialized[-1].get("event_id")
        podium_ctx: dict[str, Any] = {}
        if focus_event_id is not None and category_id is not None:
            podium_ctx = await fetch_podium_context(db, category_id, focus_event_id)

    return {
        "raw_data": serialized,
        "competitor_id": competitor_id,
        "category_id": category_id,
        "podium_context": podium_ctx,
    }


__all__ = ["load_race_data", "NODE_NAME"]
