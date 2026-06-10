"""Nodo 8: ``critic_agent`` — revisión defensiva del/los draft(s).

Si la feature flag :envvar:`RACE_AGENT_CRITIC_ENABLED` es ``false``,
es un no-op (state sin cambios).

v1: invoca :class:`RaceCriticAgent.invoke` sobre ``draft_analysis`` y guarda
``critic_feedback``.

v2 (feature 011): cuando hay ``per_valida_drafts``, itera TODOS los drafts
(cap=4), construye la verdad de campo (condiciones registradas + fila de
resultado + podio) de cada válida y la pasa a ``invoke_v2``. Emite
``per_valida_verdicts: dict[int, CriticFeedback]`` y mantiene ``critic_feedback``
(verdicto de la primera válida) para compatibilidad con nodos v1 downstream.
"""

from __future__ import annotations

from typing import Any

from app.services.race.agents.analyst import _format_ms_hhmmss, format_race_meta
from app.services.race.agents.critic import RaceCriticAgent
from app.services.race.ai.confidence import DataCompleteness, compute_confidence
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry

NODE_NAME = "critic_agent"

# Cap de válidas revisadas por run (coincide con el cap del analyst v2).
_V2_CAP = 4


def _accumulate(aggregate: dict, run_metrics: Any, *, prompt_key: str) -> dict:
    aggregate.setdefault("tokens_in_total", 0)
    aggregate.setdefault("tokens_out_total", 0)
    aggregate.setdefault("latency_ms_total", 0)
    aggregate.setdefault("cost_usd_total", 0.0)
    aggregate["tokens_in_total"] += run_metrics.tokens_in
    aggregate["tokens_out_total"] += run_metrics.tokens_out
    aggregate["latency_ms_total"] += run_metrics.latency_ms
    aggregate["cost_usd_total"] = round(
        aggregate["cost_usd_total"] + run_metrics.cost_usd, 6
    )
    aggregate[prompt_key] = run_metrics.prompt_version
    return aggregate


def _build_ground_truth(state: dict, valida_num: int) -> str:
    """Construye el bloque de verdad de campo para una válida (feature 011).

    Incluye: condiciones registradas (o "sin condiciones registradas"), la fila
    de resultado del atleta (posición, tiempo, gap al líder) y los tiempos de
    podio del evento foco. Sirve para que el critic detecte contradicciones.
    """
    event_conditions: dict[int, dict] = state.get("event_conditions") or {}
    conditions_block = format_race_meta(event_conditions.get(valida_num))

    lines: list[str] = ["### Condiciones registradas"]
    lines.append(conditions_block if conditions_block else "sin condiciones registradas")

    # Fila de resultado del atleta para esta válida (desde full_season_results).
    full_season: list[dict] = state.get("full_season_results") or []
    row = next(
        (r for r in full_season if r.get("valida_num") == valida_num), None
    )
    lines.append("")
    lines.append(f"### Resultado del atleta (Válida {valida_num})")
    if row:
        lines.append(f"- Posición: {row.get('position', '—')}")
        lines.append(f"- Tiempo: {_format_ms_hhmmss(row.get('race_time_ms'))}")
        lines.append(
            f"- Gap al líder: {_format_ms_hhmmss(row.get('gap_to_winner_ms'))}"
        )
    else:
        lines.append("- (sin fila de resultado registrada para esta válida)")

    # Maduración real (o sin registro).
    maturation = state.get("maturation_status")
    lines.append("")
    lines.append("### Maduración")
    lines.append(maturation if maturation else "sin registro de maduración")

    # Podio del evento foco (tiempos P1-P3).
    podium_ctx = state.get("podium_context") or {}
    podium_rows = podium_ctx.get("podium") or []
    lines.append("")
    lines.append("### Podio (evento foco)")
    if podium_rows:
        for p in podium_rows:
            lines.append(
                f"- P{p.get('position')}: {_format_ms_hhmmss(p.get('race_time_ms'))}"
            )
    else:
        lines.append("- (sin datos de podio)")

    return "\n".join(lines)


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def critic_agent(state: dict) -> dict[str, Any]:
    if not RaceCriticAgent.is_enabled():
        # No-op explícito: emite eventos start/end pero no toca state.
        return {}

    agent = state.get("_critic_agent") or RaceCriticAgent()
    aggregate = dict(state.get("aggregate_metrics") or {})

    per_valida_drafts: dict[int, Any] | None = state.get("per_valida_drafts")

    # ------------------------------------------------------------------ v2
    if per_valida_drafts:
        event_conditions: dict[int, dict] = state.get("event_conditions") or {}
        has_maturation = bool(state.get("maturation_status"))
        season_n = int(state.get("season_validas_count", 0))

        verdicts: dict[int, Any] = {}
        confidence: dict[int, Any] = {}
        first_feedback = None
        for vn in list(per_valida_drafts.keys())[:_V2_CAP]:
            draft = per_valida_drafts[vn]
            if draft is None:
                continue
            ground_truth = _build_ground_truth(state, vn)
            feedback, run_metrics = await agent.invoke_v2(draft, ground_truth)
            verdicts[vn] = feedback
            aggregate = _accumulate(
                aggregate, run_metrics, prompt_key="prompt_version_critic"
            )
            if first_feedback is None:
                first_feedback = feedback

            # Confianza determinista por válida (feature 011, US4).
            cond = event_conditions.get(vn) or {}
            has_conditions = any(v is not None for v in cond.values())
            # El fallback de falla (no N=1) trae sections vacías.
            is_fallback = not getattr(draft, "sections", None)
            confidence[vn] = compute_confidence(
                feedback,
                DataCompleteness(
                    has_conditions=has_conditions,
                    has_maturation=has_maturation,
                    season_n=season_n,
                    is_fallback=is_fallback,
                ),
            )

        out: dict[str, Any] = {
            "per_valida_verdicts": verdicts,
            "confidence": confidence,
            "aggregate_metrics": aggregate,
        }
        if first_feedback is not None:
            out["critic_feedback"] = first_feedback
        return out

    # ------------------------------------------------------------------ v1
    draft = state.get("draft_analysis")
    if draft is None:
        # Sin draft (fallback ejecutado), no hay nada que criticar.
        return {}

    feedback, run_metrics = await agent.invoke(draft)
    aggregate = _accumulate(aggregate, run_metrics, prompt_key="prompt_version_critic")

    return {
        "critic_feedback": feedback,
        "aggregate_metrics": aggregate,
    }


__all__ = ["critic_agent", "NODE_NAME"]
