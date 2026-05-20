"""Nodo 8: ``critic_agent`` — revisión defensiva del draft.

Si la feature flag :envvar:`RACE_AGENT_CRITIC_ENABLED` es ``false``,
es un no-op (state sin cambios).

Si está habilitada (default), invoca :class:`RaceCriticAgent` y guarda
``critic_feedback`` en el state + acumula métricas.
"""

from __future__ import annotations

from typing import Any

from app.services.race.agents.critic import RaceCriticAgent
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

NODE_NAME = "critic_agent"


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def critic_agent(state: dict) -> dict[str, Any]:
    if not RaceCriticAgent.is_enabled():
        # No-op explícito: emite eventos start/end pero no toca state.
        return {}

    draft = state.get("draft_analysis")
    if draft is None:
        # Sin draft (fallback ejecutado), no hay nada que criticar.
        return {}

    agent = state.get("_critic_agent") or RaceCriticAgent()
    feedback, run_metrics = await agent.invoke(draft)

    aggregate = dict(state.get("aggregate_metrics") or {})
    aggregate.setdefault("tokens_in", 0)
    aggregate.setdefault("tokens_out", 0)
    aggregate.setdefault("latency_ms", 0)
    aggregate.setdefault("cost_usd", 0.0)
    aggregate["tokens_in"] += run_metrics.tokens_in
    aggregate["tokens_out"] += run_metrics.tokens_out
    aggregate["latency_ms"] += run_metrics.latency_ms
    aggregate["cost_usd"] = round(aggregate["cost_usd"] + run_metrics.cost_usd, 6)
    aggregate["prompt_version_critic"] = run_metrics.prompt_version

    return {
        "critic_feedback": feedback,
        "aggregate_metrics": aggregate,
    }


__all__ = ["critic_agent", "NODE_NAME"]
