"""Nodo 10: ``persist_insight`` — escribe la fila en ``athlete_ai_insights``.

Refactor BE-2
=============
El nodo ahora usa el modelo ORM ``AthleteAiInsight`` (introducido en BE-1)
en vez de SQL crudo. Esto:

1. Centraliza la lógica de versionado en :mod:`app.services.race.insights_history`
   (función :func:`deprecate_previous_active`).
2. Garantiza que el campo ``is_active`` se asigne correctamente al
   sentinel ``1`` (sólo cuando ``coach_approved=True``).
3. Mantiene la cadena ``superseded_by_insight_id`` consistente: se hace
   un UPDATE post-flush sobre la fila previa con la nueva PK.

Convenciones
============
- ``coach_approved=True`` ⇒ deprecar fila previa de la misma terna y
  ``is_active=1`` para la nueva.
- ``coach_approved=False`` (HITL rejected / draft pending) ⇒ insertar con
  ``is_active=NULL`` y no tocar previos.
- ``valida_num=None`` para use_cases agregados se mapea a ``0`` antes de
  persistir (CHECK relax permite ``>=0``).

Si la persistencia falla, registramos el error en ``state.errors`` pero
no rompemos el grafo — ``notify_coach`` aún tiene valor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence
from app.services.race.ai.db import get_session
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.insights_history import deprecate_previous_active

logger = logging.getLogger(__name__)

NODE_NAME = "persist_insight"

_USE_CASE = "race_progression"
_SUMMARY_MAX_CHARS = 5000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serializable(obj: Any) -> Any:
    """Convierte recursivamente Pydantic/dataclass/enum a dict/list JSON-safe."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    return obj


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
    event_id = state.get("event_id")
    # Para use_cases agregados (season_summary, projection) el grafo puede
    # pasar valida_num=None — la columna tiene CHECK relax (>=0) que admite 0
    # como sentinel para "agregado de temporada". Documentado en
    # ``athlete_ai_insight.py`` y migración ``8c1d2e3f4a5b``.
    raw_valida = state.get("valida_num")
    use_case = state.get("use_case") or _USE_CASE
    valida_num_db: int = (
        int(raw_valida)
        if raw_valida is not None
        else (0 if use_case in {"season_summary", "projection"} else 0)
    )

    aggregate = state.get("aggregate_metrics") or {}

    recommendations = _serializable(draft.recommendations or [])
    risks = _serializable(draft.risk_flags or [])
    principles = _serializable(state.get("principles") or [])

    metrics_snapshot = {
        "progression": state.get("metrics", {}).get("progression", []),
        "podium_gap": state.get("metrics", {}).get("podium_gap", []),
        "podium_context": state.get("podium_context", {}),
        "aggregate": aggregate,
        "risks": risks,
    }

    confidence_value = state.get("confidence") or InsightConfidence.medium
    if isinstance(confidence_value, str):
        try:
            confidence_enum = InsightConfidence(confidence_value)
        except ValueError:
            confidence_enum = InsightConfidence.medium
    else:
        confidence_enum = confidence_value

    now = _now()
    summary_text = (getattr(draft, "raw_markdown", None) or "")[:_SUMMARY_MAX_CHARS]
    prompt_version = aggregate.get("prompt_version_analyst", "race_analyst_v1")

    try:
        async with get_session() as db:
            previous_id: Optional[int] = None
            is_active_value: Optional[int] = None

            if approved:
                # Liberar slot UNIQUE antes del INSERT (clave para no chocar
                # con uq_insights_active_terna). new_insight_id se enlaza
                # después del flush con UPDATE puntual.
                previous_id = await deprecate_previous_active(
                    db,
                    athlete_id=athlete_id,
                    season=season,
                    valida_num=valida_num_db,
                    new_insight_id=None,
                )
                is_active_value = 1

            new_row = AthleteAiInsight(
                athlete_id=athlete_id,
                competitor_id=competitor_id,
                event_id=event_id,
                agent_run_id=state.get("agent_run_id"),
                generated_by_user_id=coach_id,
                season=season,
                valida_num=valida_num_db,
                use_case=use_case,
                summary_text=summary_text,
                recommendations_json=recommendations,
                metrics_snapshot_json=metrics_snapshot,
                principles_cited_json=principles,
                confidence=confidence_enum,
                model="gemini-2.5-flash-lite",
                prompt_version=prompt_version,
                coach_approved=approved,
                coach_edits_count=0,
                generated_at=now,
                approved_at=now if approved else None,
                archived_at=now if archived else None,
                deprecated_at=None,
                is_active=is_active_value,
                created_at=now,
                updated_at=now,
            )
            db.add(new_row)
            await db.flush()  # Asigna new_row.id sin commit aún.

            # Enlazar la cadena: el insight previo ahora apunta al nuevo.
            if approved and previous_id is not None:
                from sqlalchemy import update as sa_update

                await db.execute(
                    sa_update(AthleteAiInsight)
                    .where(AthleteAiInsight.id == previous_id)
                    .values(
                        superseded_by_insight_id=new_row.id,
                        updated_at=now,
                    )
                )

            await db.commit()

    except Exception as exc:  # noqa: BLE001
        # Persistencia es importante pero no debe romper el grafo
        # (notify_coach aún tiene valor). Log + sigue.
        logger.error("persist_insight: insert falló: %s", type(exc).__name__)
        return {
            "errors": list(state.get("errors") or [])
            + [
                {
                    "node": NODE_NAME,
                    "error": type(exc).__name__,
                    "message": str(exc)[:200],
                }
            ]
        }

    return {}


__all__ = ["persist_insight", "NODE_NAME"]
