"""Nodo 6: ``recall_memory`` — últimos 3 insights aprobados del atleta.

Query plana a ``athlete_ai_insights`` (SQL crudo con ``text()`` — mismo
patrón que :mod:`app.services.race.agents.chat`). Retorna lista de
``summary_text`` truncados a 500 chars cada uno.

Si la tabla está vacía o el atleta no tiene insights aún, retorna
``memory=[]`` (analyst funciona OK sin memoria).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "recall_memory"

_MEMORY_LIMIT = 3
_SUMMARY_MAX_CHARS = 500


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def recall_memory(state: dict) -> dict[str, Any]:
    athlete_id = state["athlete_id"]

    try:
        async with get_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT summary_text
                    FROM athlete_ai_insights
                    WHERE athlete_id = :aid
                      AND coach_approved = 1
                      AND archived_at IS NULL
                    ORDER BY generated_at DESC
                    LIMIT :n
                    """
                ),
                {"aid": athlete_id, "n": _MEMORY_LIMIT},
            )
            rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
    except Exception as exc:
        # Degrada silenciosamente — la memoria es enriquecimiento, no
        # requisito. No queremos romper análisis por falla DB transitoria
        # en lectura opcional.
        logger.warning("recall_memory: query falló (%s) — sin memoria", type(exc).__name__)
        return {"memory": []}

    summaries: list[str] = []
    for r in rows or []:
        # Soportamos Row, dict y tuple defensivamente (varios fakes).
        if hasattr(r, "summary_text"):
            text_val = r.summary_text
        elif isinstance(r, dict):
            text_val = r.get("summary_text", "")
        else:
            text_val = r[0] if r else ""
        if text_val:
            summaries.append(str(text_val)[:_SUMMARY_MAX_CHARS])

    return {"memory": summaries}


__all__ = ["recall_memory", "NODE_NAME"]
