"""Nodo 1: ``validate_input`` — valida inputs mínimos del grafo.

Verifica:
- ``athlete_id`` es int positivo.
- ``season`` está en rango razonable (2000..2100).
- El atleta tiene ≥1 ``RaceResult`` confirmado (vía ``queries.athlete_exists``).

Si alguna validación falla, retorna ``{"errors": [...]}`` con el error
agregado. El grafo enruta a END (skip resto del pipeline).
"""

from __future__ import annotations

from typing import Any

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.queries import athlete_exists

NODE_NAME = "validate_input"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def validate_input(state: dict) -> dict[str, Any]:
    """Valida el state inicial.

    Reglas:
        - athlete_id requerido y > 0.
        - season requerida y en [2000, 2100].
        - athlete_exists(db, athlete_id) → True.

    Si alguna falla → agrega a ``errors[]``. El grafo lo enruta a END.
    """
    errors: list[dict] = []
    athlete_id = state.get("athlete_id")
    season = state.get("season")

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

    if not errors:
        async with get_session() as db:
            exists = await athlete_exists(db, athlete_id)
        if not exists:
            errors.append(
                {
                    "node": NODE_NAME,
                    "error": "AthleteNotFound",
                    "message": f"athlete_id={athlete_id} no tiene resultados",
                }
            )

    if errors:
        prior = list(state.get("errors") or [])
        prior.extend(errors)
        return {"errors": prior}

    return {}


__all__ = ["validate_input", "NODE_NAME"]
