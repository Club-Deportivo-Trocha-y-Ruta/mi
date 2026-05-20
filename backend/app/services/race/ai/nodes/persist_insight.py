"""Nodo 10: ``persist_insight`` — inserta fila en ``athlete_ai_insights``.

Tabla creada en F0 (migración 7a8b9c0d1e2f). Sin modelo SQLAlchemy aún
→ usamos SQL crudo con ``text()`` (mismo patrón que chat.py F3 y
recall_memory).

Campos persistidos:
- ``summary_text``: ``raw_markdown`` del draft (truncado a 5000 chars).
- ``recommendations_json``: list[dict] de recomendaciones.
- ``metrics_snapshot_json``: dict con ``progression``, ``podium_gap``.
- ``principles_cited_json``: list[dict] de citations.
- ``model`` / ``prompt_version``: del aggregate_metrics.
- ``coach_approved``: ``True`` si ``hitl_decision.decision == "approve"``.
- ``langfuse_trace_id``: ``NULL`` (Langfuse difería a F8B opcional).

Si HITL fue rejected → marca ``archived_at`` y ``coach_approved=False``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

logger = logging.getLogger(__name__)

NODE_NAME = "persist_insight"

_USE_CASE = "race_progression"
_SUMMARY_MAX_CHARS = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def persist_insight(state: dict) -> dict[str, Any]:
    draft = state.get("draft_analysis")
    if draft is None:
        return {}

    decision = (state.get("hitl_decision") or {}).get("decision", "auto-approve")
    approved = decision in {"approve", "auto-approve"}
    archived = decision == "reject"

    athlete_id = state["athlete_id"]
    season = state["season"]
    coach_id = state.get("coach_id") or 0
    competitor_id = state.get("competitor_id")
    aggregate = state.get("aggregate_metrics") or {}

    recommendations = [
        r.model_dump() if hasattr(r, "model_dump") else dict(r)
        for r in (draft.recommendations or [])
    ]
    risks = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in (draft.risk_flags or [])]
    principles = [
        c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in (state.get("principles") or [])
    ]

    metrics_snapshot = {
        "progression": state.get("metrics", {}).get("progression", []),
        "podium_gap": state.get("metrics", {}).get("podium_gap", []),
        "podium_context": state.get("podium_context", {}),
        "aggregate": aggregate,
        "risks": risks,
    }

    params = {
        "athlete_id": athlete_id,
        "competitor_id": competitor_id,
        "season": season,
        "use_case": _USE_CASE,
        "summary_text": (draft.raw_markdown or "")[:_SUMMARY_MAX_CHARS],
        "recommendations_json": _dumps(recommendations),
        "metrics_snapshot_json": _dumps(metrics_snapshot),
        "principles_cited_json": _dumps(principles),
        "confidence": "medium",
        "model": "gemini-2.5-flash-lite",
        "prompt_version": aggregate.get("prompt_version_analyst", "race_analyst_v1"),
        "coach_approved": 1 if approved else 0,
        "generated_at": _now(),
        "approved_at": _now() if approved else None,
        "generated_by_user_id": coach_id,
        "archived_at": _now() if archived else None,
    }

    try:
        async with get_session() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO athlete_ai_insights (
                        athlete_id, competitor_id, season, use_case,
                        summary_text, recommendations_json, metrics_snapshot_json,
                        principles_cited_json, confidence, model, prompt_version,
                        coach_approved, coach_edits_count, generated_at, approved_at,
                        generated_by_user_id, archived_at
                    ) VALUES (
                        :athlete_id, :competitor_id, :season, :use_case,
                        :summary_text, :recommendations_json, :metrics_snapshot_json,
                        :principles_cited_json, :confidence, :model, :prompt_version,
                        :coach_approved, 0, :generated_at, :approved_at,
                        :generated_by_user_id, :archived_at
                    )
                    """
                ),
                params,
            )
    except Exception as exc:
        # Persistencia es importante pero no debe romper el grafo
        # (notify_coach aún tiene valor). Log + sigue.
        logger.error("persist_insight: insert falló: %s", type(exc).__name__)
        return {"errors": list(state.get("errors") or []) + [{"node": NODE_NAME, "error": type(exc).__name__, "message": str(exc)[:200]}]}

    return {}


__all__ = ["persist_insight", "NODE_NAME"]
