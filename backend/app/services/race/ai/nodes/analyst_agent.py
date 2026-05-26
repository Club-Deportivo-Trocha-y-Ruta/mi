"""Nodo 7: ``analyst_agent`` — invoca :class:`RaceAnalystAgent`.

Construye :class:`AnalysisInput` a partir del state (datos ya
anonimizados, métricas, principios, memoria) e invoca el agente. Si el
agente falla con excepción no-retryable, ``with_events`` la propaga y
el grafo enruta a fallback (ver ``graph.py``).

Acumula tokens / cost / latency en ``state["aggregate_metrics"]``.

v2 (``state["prompt_version"] == "race_analyst_v2"``)
======================================================
En vez de un único análisis agregado, lanza ``asyncio.gather`` con una
llamada por cada válida en ``state["valida_nums"]`` (cap=4). Emite
``state["per_valida_drafts"]: dict[int, AnalysisOutput]`` en lugar del
campo singular ``draft_analysis``.

``state["forbidden_names"]`` se carga upstream (nodo load_race_data o
validate_input) y se pasa a los guardrails; NUNCA va al prompt del LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V2,
    RaceAnalystAgent,
)
from app.services.race.ai.events import with_events
from app.services.race.ai.retry import with_retry
from app.services.race.schemas import AnalysisInput, LTADGroup

logger = logging.getLogger(__name__)

NODE_NAME = "analyst_agent"

# Cap de válidas por run v2 (debe coincidir con RaceAnalystAgent._V2_CAP).
_V2_CAP = 4


def _resolve_ltad(state: dict) -> LTADGroup:
    raw = state.get("ltad_group")
    if isinstance(raw, LTADGroup):
        return raw
    if isinstance(raw, str):
        try:
            return LTADGroup(raw)
        except ValueError:
            pass
    return LTADGroup.BAMBINO


def _resolve_age(state: dict) -> int:
    age = state.get("athlete_age")
    if isinstance(age, int) and 6 <= age <= 20:
        return age
    logger.warning(
        "analyst_agent: athlete_age ausente o fuera de rango en state "
        "(valor=%r); usando fallback=12. Verificar que el router inyecta "
        "'athlete_age' en initial_state (Fix 1).",
        age,
    )
    return 12


def _build_input(state: dict, progression_records: list | None = None) -> AnalysisInput:
    """Construye AnalysisInput desde el state del grafo."""
    anon = state.get("anonymized_data") or {}
    pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
    metrics = state.get("metrics") or {}
    records = progression_records if progression_records is not None else (
        metrics.get("progression", []) or []
    )
    podium_ctx = state.get("podium_context") or {}
    principles = state.get("principles") or []
    memory = state.get("memory") or []

    return AnalysisInput(
        athlete_pseudonym=pseudonym,
        age=_resolve_age(state),
        ltad_group=_resolve_ltad(state),
        progression_df_records=records,
        podium_context=podium_ctx,
        memory_recent_insights=memory[:10],
        principles_citations=principles,
        explain_mode=bool(state.get("explain_mode", False)),
        athlete_id=state["athlete_id"],
        season=state["season"],
    )


def _accumulate_metrics(aggregate: dict, run_metrics: Any) -> dict:
    """Suma métricas de un RunMetrics al dict acumulado del state."""
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
    aggregate["prompt_version_analyst"] = run_metrics.prompt_version
    return aggregate


@with_events(NODE_NAME)
@with_retry(max_attempts=3, backoff=0)
async def analyst_agent(state: dict) -> dict[str, Any]:
    prompt_version: str = state.get("prompt_version") or "race_analyst_v1"

    # ------------------------------------------------------------------ v2
    if prompt_version == PROMPT_VERSION_ANALYST_V2:
        return await _analyst_agent_v2(state)

    # ------------------------------------------------------------------ v1
    input_ = _build_input(state)
    agent = state.get("_analyst_agent") or RaceAnalystAgent()
    output, run_metrics = await agent.invoke(input_)

    aggregate = _accumulate_metrics(dict(state.get("aggregate_metrics") or {}), run_metrics)

    return {
        "draft_analysis": output,
        "aggregate_metrics": aggregate,
    }


async def _analyst_agent_v2(state: dict) -> dict[str, Any]:
    """Implementación v2: gather por válida con cap=4.

    Emite ``per_valida_drafts`` además de ``draft_analysis`` (el primero
    en la lista) para compatibilidad con nodos downstream que leen
    ``draft_analysis``.

    La regla N=1 se basa en ``is_first_in_season`` (toda la temporada)
    en vez del tamaño del set lanzado. ``full_season_results`` alimenta
    el contexto de la sección "Recorrido hasta acá".
    """
    valida_nums: list[int] = list(state.get("valida_nums") or [])

    if len(valida_nums) > _V2_CAP:
        raise ValueError(
            f"Cap v2: máximo {_V2_CAP} válidas por análisis. "
            "Genera resumen temporada para visión global."
        )

    forbidden_names: list[str] = list(state.get("forbidden_names") or [])
    agent: RaceAnalystAgent = state.get("_analyst_agent") or RaceAnalystAgent(
        prompt_version=PROMPT_VERSION_ANALYST_V2
    )

    # is_first_in_season desde state (cargado en load_race_data).
    is_first_in_season: bool = bool(state.get("is_first_in_season", False))
    season_validas_count: int = int(state.get("season_validas_count", 0))

    # Progresión del set lanzado (para "Qué pasó").
    metrics_base = state.get("metrics") or {}
    progression_all: list[dict] = metrics_base.get("progression", []) or []

    # Progresión completa de la temporada (para "Recorrido hasta acá").
    full_season_results: list[dict] | None = state.get("full_season_results")

    # Construir pares (valida_num, AnalysisInput) filtrando por válida.
    pairs: list[tuple[int, AnalysisInput]] = []
    for vn in valida_nums:
        records_for_vn = [
            r for r in progression_all
            if r.get("valida_num") == vn or vn == 0
        ]
        inp = _build_input(state, progression_records=records_for_vn)
        pairs.append((vn, inp))

    if not pairs:
        # Sin datos: emitir fallback por cada válida solicitada.
        from app.services.race.ai.fallback import (
            deterministic_fallback,
            deterministic_fallback_n1,
        )
        anon = state.get("anonymized_data") or {}
        pseudonym = anon.get("pseudonym") or "AtletaAnonimo"
        fallback = (
            deterministic_fallback_n1(pseudonym)
            if is_first_in_season
            else deterministic_fallback(pseudonym)
        )
        per_valida = {vn: fallback for vn in (valida_nums or [0])}
        return {"per_valida_drafts": per_valida, "draft_analysis": fallback}

    results: dict[int, tuple] = await agent.invoke_per_valida(
        pairs,
        forbidden_names=forbidden_names,
        is_first_in_season=is_first_in_season,
        full_season_records=full_season_results,
        athlete_age=state.get("athlete_age"),
    )

    aggregate = dict(state.get("aggregate_metrics") or {})
    per_valida_drafts: dict[int, Any] = {}
    first_output = None
    for vn, (out, met) in results.items():
        per_valida_drafts[vn] = out
        aggregate = _accumulate_metrics(aggregate, met)
        if first_output is None:
            first_output = out

    aggregate["is_first_in_season"] = is_first_in_season
    aggregate["season_validas_count"] = season_validas_count

    return {
        "per_valida_drafts": per_valida_drafts,
        "draft_analysis": first_output,  # compat con nodos v1 downstream
        "aggregate_metrics": aggregate,
    }


__all__ = ["analyst_agent", "NODE_NAME"]
