"""Nodo 1: ``validate_input`` — valida inputs mínimos del grafo.

Verifica:
- ``athlete_id`` es int positivo.
- ``season`` está en rango razonable (2000..2100).
- El atleta tiene ≥1 ``RaceResult`` confirmado **en la temporada solicitada**
  (vía ``queries.fetch_results_for_athlete``), respetando ``valida_nums``.

Si ``athlete_id`` o ``season`` son inválidos → ``errors[]`` + ruta a END.
Si no hay resultados para la temporada → marca ``no_data_for_season=True`` y
puebla ``rendered_markdown`` con un mensaje informativo; el grafo enruta a END
saltando analyst/critic/HITL/render.
"""

from __future__ import annotations

from typing import Any

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.queries import fetch_results_for_athlete

NODE_NAME = "validate_input"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def validate_input(state: dict) -> dict[str, Any]:
    """Valida el state inicial.

    Reglas:
        - athlete_id requerido y > 0.
        - season requerida y en [2000, 2100].
        - El atleta debe tener ≥1 ``RaceResult`` en ``season``
          (respetando ``valida_nums`` si viene).

    Si athlete_id/season son inválidos → ``errors[]`` + ruta a END.
    Si no hay resultados para la temporada → ``no_data_for_season=True``,
    ``rendered_markdown`` informativo y ruta a END (sin análisis LLM).
    """
    errors: list[dict] = []
    athlete_id = state.get("athlete_id")
    season = state.get("season")
    valida_nums = state.get("valida_nums")

    if not isinstance(athlete_id, int) or athlete_id <= 0:
        errors.append(
            {
                "node": NODE_NAME,
                "error": "InvalidAthleteId",
                "message": f"athlete_id inválido: {athlete_id!r}",
            }
        )
    if not isinstance(season, int) or not (2000 <= season <= 2100):
        errors.append(
            {
                "node": NODE_NAME,
                "error": "InvalidSeason",
                "message": f"season fuera de rango: {season!r}",
            }
        )

    if errors:
        prior = list(state.get("errors") or [])
        prior.extend(errors)
        return {"errors": prior}

    async with get_session() as db:
        results = await fetch_results_for_athlete(
            db, athlete_id, season, valida_nums
        )

    if not results:
        message = f"Sin carreras registradas para temporada {season}"
        if valida_nums:
            valida_str = ", ".join(str(v) for v in valida_nums)
            message = (
                f"Sin carreras registradas para temporada {season} "
                f"(válidas: {valida_str})"
            )
        markdown = (
            f"# Análisis de carrera — temporada {season}\n\n"
            f"_{message}._\n"
        )
        return {
            "no_data_for_season": True,
            "rendered_markdown": markdown,
            "status": "no_data",
        }

    return {}


__all__ = ["validate_input", "NODE_NAME"]
