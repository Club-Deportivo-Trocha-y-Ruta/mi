"""Nodo 7: ``analyst_agent`` — invoca :class:`RaceAnalystAgent`.

Construye :class:`AnalysisInput` a partir del state (datos ya
anonimizados, métricas, principios, memoria) e invoca el agente. Si el
agente falla con excepción no-retryable, ``with_events`` la propaga y
el grafo enruta a fallback (ver ``graph.py``).

Acumula tokens / cost / latency en ``state["aggregate_metrics"]``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.race.agents.analyst import RaceAnalystAgent
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.schemas import AnalysisInput, LTADGroup

logger = logging.getLogger(__name__)

NODE_NAME = "analyst_agent"


def _resolve_ltad(state: dict) -> LTADGroup:
    raw = state.get("ltad_group")
    if isinstance(raw, LTADGroup):
        return raw
    if isinstance(raw, str):
        try:
            return LTADGroup(raw)
        except ValueError:
            pass
    # Default conservador (10-12 años).
    return LTADGroup.BAMBINO


def _resolve_age(state: dict) -> int:
    age = state.get("athlete_age")
    if isinstance(age, int) and 6 <= age <= 20:
        return age
    return 12  # default razonable para juvenil mid-range


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def analyst_agent(state: dict) -> dict[str, Any]:
    anon = state.get("anonymized_data") or {}
    pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
    metrics = state.get("metrics") or {}
    progression_records = metrics.get("progression", []) or []
    podium_ctx = state.get("podium_context") or {}
    principles = state.get("principles") or []
    memory = state.get("memory") or []

    input_ = AnalysisInput(
        athlete_pseudonym=pseudonym,
        age=_resolve_age(state),
        ltad_group=_resolve_ltad(state),
        progression_df_records=progression_records,
        podium_context=podium_ctx,
        memory_recent_insights=memory[:10],
        principles_citations=principles,
        explain_mode=bool(state.get("explain_mode", False)),
        athlete_id=state["athlete_id"],
        season=state["season"],
    )

    agent = state.get("_analyst_agent") or RaceAnalystAgent()
    output, run_metrics = await agent.invoke(input_)

    aggregate = dict(state.get("aggregate_metrics") or {})
    aggregate.setdefault("tokens_in", 0)
    aggregate.setdefault("tokens_out", 0)
    aggregate.setdefault("latency_ms", 0)
    aggregate.setdefault("cost_usd", 0.0)
    aggregate["tokens_in"] += run_metrics.tokens_in
    aggregate["tokens_out"] += run_metrics.tokens_out
    aggregate["latency_ms"] += run_metrics.latency_ms
    aggregate["cost_usd"] = round(aggregate["cost_usd"] + run_metrics.cost_usd, 6)
    aggregate["prompt_version_analyst"] = run_metrics.prompt_version

    return {
        "draft_analysis": output,
        "aggregate_metrics": aggregate,
    }


__all__ = ["analyst_agent", "NODE_NAME"]
