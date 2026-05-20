"""Nodo 3: ``anonymize`` — sustituye nombres reales por pseudónimos estables.

Estrategia (F4 §4.2 nodo 3):

1. Computa el ``pseudonym`` del atleta principal vía
   :func:`anonymizer.make_pseudonym`.
2. Persiste el mapping en ``anonymization_mappings`` (tabla F0) usando
   SQL crudo con ``text()`` — patrón consistente con chat.py de F3.
3. Construye ``state["anonymized_data"]`` con:
   - ``pseudonym``
   - ``raw_data`` filtrado (sin athlete_id real — solo pseudonym y
     competitor_id, que el LLM no puede mapear a nombre sin contexto).
4. Guarda ``state["mapping"]`` (pseudonym → athlete_id real) — NUNCA
   se serializa hacia el LLM.

Privacidad:
- El LLM solo ve ``pseudonym``. ``athlete_id`` viaja en el state para
  audit pero no se inyecta al prompt (ver schemas.AnalysisInput).
- El nodo final ``rehydrate_names`` revierte para mostrar al coach.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.services.race.ai.anonymizer import make_pseudonym
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "anonymize"

_DEFAULT_SALT = "tyr-race-v2"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def anonymize(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]
    competitor_id = state.get("competitor_id")
    run_id = state.get("run_id", "no-run")

    pseudonym = make_pseudonym(athlete_id, salt=_DEFAULT_SALT)
    mapping: dict[str, int] = {pseudonym: athlete_id}

    # Persist mapping (best-effort: si falla, log warning pero el grafo
    # sigue — el pseudonym es estable por hash, así que el coach puede
    # re-mapearlo si fuera necesario).
    try:
        async with get_session() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO anonymization_mappings
                        (run_id, pseudonym, real_competitor_id, real_athlete_id,
                         salt_used, created_at)
                    VALUES (
                        (SELECT id FROM agent_runs WHERE external_run_id = :rid),
                        :pseudo, :comp_id, :ath_id, :salt, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "rid": run_id,
                    "pseudo": pseudonym,
                    "comp_id": competitor_id,
                    "ath_id": athlete_id,
                    "salt": _DEFAULT_SALT,
                },
            )
    except Exception as exc:  # pragma: no cover - best-effort persist
        logger.warning(
            "anonymize: persist mapping falló (run_id=%s): %s — continuo con state-only",
            run_id,
            type(exc).__name__,
        )

    # Anonimiza raw_data: filtra athlete_id real, pseudónimo se aplica
    # solo al atleta objetivo. competitor_id se mantiene (es un opaque ID
    # que no permite identificación sin acceso a la DB).
    raw_data = state.get("raw_data", []) or []
    anonymized_rows = []
    for row in raw_data:
        cleaned = {k: v for k, v in row.items() if k != "athlete_id"}
        # Inyectamos pseudonym SOLO en filas del atleta target — competitors
        # de podio mantienen su competitor_id opaco.
        if row.get("athlete_id") == athlete_id:
            cleaned["pseudonym"] = pseudonym
        anonymized_rows.append(cleaned)

    return {
        "anonymized_data": {
            "pseudonym": pseudonym,
            "rows": anonymized_rows,
        },
        "mapping": mapping,
    }


__all__ = ["anonymize", "NODE_NAME"]
