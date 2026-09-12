"""Orquestador del pipeline antropométrico (feature 042, T039): ``run_analysis()``.

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T039 y la máquina de estados
COMPLETA de ``specs/042-traceable-growth-ai/data-model.md`` §3 — ese documento es la
especificación exacta de lo que este módulo orquesta; no se reproduce aquí más que lo
necesario para justificar cada rama de código.

Sin grafo, sin checkpointer, sin HITL (research.md R-03)
=========================================================
``plan.md`` describe la feature como "small LangGraph graph"; este módulo es
deliberadamente un orquestador PLANO — cinco `await` secuenciales, sin
``StateGraph``, sin ``sqlite`` checkpointer y sin interrupción HITL — porque
ninguna corrida de este pipeline necesita pausar a mitad de camino (a
diferencia del stack de carreras, que sí pausa para revisión humana). Cada
paso (``context.build_context``, ``analyst.run_analyst``, ``critic.run_critic``,
``fallback.build_fallback_insight``/``run_fallback``, ``guardrails_step.
guardrails_step``, ``persist.persist``) mantiene la firma
``async def step(state, config) -> dict`` de un nodo LangGraph precisamente para
que una futura promoción a ``StateGraph`` sea un envoltorio mecánico sobre este
mismo código, no una reescritura (`plan.md` "Post-design re-check": "a
StateGraph without checkpointer can be swapped in mechanically if the owner
prefers the literal reading").

Excepción de presupuesto de latencia (dos llamadas LLM secuenciales)
=====================================================================
Este pipeline puede invocar el LLM hasta CUATRO veces en el peor caso (analista →
crítico → reanálisis del analista → crítico del reanálisis) — normalmente dos
(analista → crítico). ``plan.md`` §Constitution Check (fila IV, Performance) y
§Complexity Tracking documentan explícitamente esta corrida como una EXCEPCIÓN
deliberada al presupuesto general de escritura (p95 ≤ 1500 ms): "Analysis endpoints
exceed the p95 ≤ 1500 ms write budget (two sequential LLM calls, ~20–40 s locally) ...
Single-call without critic rejected by the owner (safety)", con un objetivo local de
**p95 ≤ 45 s** y una salida documentada a un patrón submit-and-poll (como el stack de
carreras) si ese objetivo se excede en producción — decisión del owner, no de este
módulo. ``latency_ms`` (ver ``persist.py``, T038) es precisamente la métrica que
permitiría detectar ese cruce.

Máquina de estados orquestada (data-model.md §3, resumen de las ramas de código)
=================================================================================
1. ``context.build_context`` — siempre corre primero, nunca falla en la práctica
   (no llama a un LLM).
2. ``analyst.run_analyst`` — si ``analyst_failed`` (dos intentos de JSON agotados),
   se salta TODO lo demás (prechecks, crítico) y se va directo a
   ``fallback.build_fallback_insight`` con ``critic_verdict="fallback"`` (FR-013/
   FR-014: "the critic call is skipped to avoid spending a call whose verdict
   cannot change the outcome").
3. Si el analista produjo un borrador, ``prechecks.run_prechecks`` corre sobre él.
   Si ``must_block`` — misma razón que el punto 2 — va directo al fallback SIN
   invocar al crítico.
4. Si no hubo ``must_block``, ``critic.run_critic`` corre una vez. Su
   ``critic_decision`` (vocabulario de CINCO valores propio de ``critic.py``, no
   confundir con el ``verdict`` crudo de tres valores del LLM ni con el
   ``critic_verdict`` persistido de cinco valores — ver la nota de colisión en
   ``critic.py``) se traduce al ``critic_verdict`` persistido:
   - ``"approved"`` → ``APPROVED`` (con el forzado determinista a confianza
     ``"low"`` si las prechecks encontraron alguna violación no bloqueante —
     data-model.md §3, fila "approve, pero con violaciones confidence-only").
   - ``"revised_mechanical"`` → ``REVISED`` (``revised_output`` adoptado directo).
   - ``"rejected"`` → ``FLAGGED`` (sin segunda llamada — FR-013 reserva la única
     revisión permitida para ``"revise"``, no para ``"reject"``).
   - ``"skipped"`` → ``SKIPPED`` (confianza ya forzada a ``"low"`` por
     ``critic.py`` mismo).
   - ``"needs_reanalysis"`` → dispara la ÚNICA reinvocación permitida del
     analista (§5.2 más abajo); su resultado determina ``REVISED`` o
     ``FLAGGED`` — nunca un segundo ciclo.
5. ``guardrails_step.guardrails_step`` — última defensa sobre el ``insight`` YA
   resuelto por los puntos 2-4 (incluida la plantilla de fallback, que también
   pasa por aquí: es un ``AnthropometryInsightV1`` válido como cualquier otro).
   Un rechazo aquí (``LLMSchemaError``) se propaga TAL CUAL — no se convierte en
   ningún estado del enum de cinco valores, aborta la corrida completa (nada se
   persiste), igual que el caso de uso legado.
6. ``persist.persist`` — solo se alcanza si el punto 5 no rechazó.

Privacidad (CLAUDE.md / Ley 1581): este módulo no construye NINGÚN texto ni valor
por su cuenta — solo enruta objetos ya validados/saneados por los pasos que posee
cada tarea. La única excepción es ``_augment_context_blocks_with_critic_feedback``
(§5.2), que reordena texto YA producido por el propio crítico (``problem``/
``suggested_fix``, ya sujeto a las mismas reglas inviolables del prompt) — no
inventa contenido nuevo.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Optional, TypeVar

from app.config import settings
from app.services.ai.anthro.context import build_context
from app.services.ai.anthro.critic import run_critic
from app.services.ai.anthro.fallback import build_fallback_insight
from app.services.ai.anthro.guardrails_step import guardrails_step
from app.services.ai.anthro.analyst import run_analyst
from app.services.ai.anthro.persist import persist
from app.services.ai.anthro.prechecks import PrecheckResult, run_prechecks
from app.services.ai.anthro.schemas import (
    AnthropometryCriticIssue,
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)
from app.services.ai.errors import LLMConfigError
from app.services.llm.factory import resolve_configured_model
from app.services.llm.observability import keyed_session_id, llm_tracing, trace_id_for
from app.services.race.ai.athlete_context import load_club_forbidden_names

logger = logging.getLogger(__name__)

__all__ = ["run_analysis"]

_T = TypeVar("_T")

# FR-013/FR-014, data-model.md §3, fila "approve, pero con violaciones
# confidence-only": razón fija y determinista, nunca el texto del analista
# concatenado — mismo criterio (reemplazo completo, no concatenación) que
# ``critic.py::_apply_skipped_confidence`` para garantizar
# 3 <= len(reason) <= 200 sin truncar con cuidado un texto arbitrario.
_CONFIDENCE_ONLY_OVERRIDE_REASON = (
    "La confianza se redujo automáticamente porque una revisión determinista "
    "encontró una observación menor de estilo o de respaldo de datos."
)


async def _translating_config_errors(awaitable: Awaitable[_T]) -> _T:
    """Traduce un ``ValueError`` de la factoría de LLM a ``LLMConfigError``.

    ``app.services.llm.factory.build_chat_llm`` (invocado dentro de
    ``analyst.run_analyst``/``critic.run_critic``, fuera de este ownership) es el
    único punto de este pipeline que puede lanzar ``ValueError`` por configuración
    inválida (proveedor no soportado) — nunca por un fallo de LA LLAMADA en sí,
    que ambos pasos ya capturan internamente y traducen a ``analyst_failed``/
    ``critic_skipped``. Esta envoltura mantiene vigente, sin tocar
    ``app/routers/ai.py``, el mapeo YA documentado en
    ``contracts/measurement-analysis-api.md`` §5 ("500 | LLMConfigError (bad
    provider config) | Unchanged") para el único tipo de excepción que de otro
    modo escaparía como un ``ValueError`` crudo.
    """
    try:
        return await awaitable
    except ValueError as exc:
        raise LLMConfigError(str(exc)) from exc


def _maturation_status_value(record: Any) -> str:
    """``record.maturation_status`` como ``str`` plano.

    Duplicado deliberado, de dos líneas, de ``context.py::_status_value`` (no
    exportado por ese módulo) — evita depender de un símbolo privado de otra
    tarea por un helper tan pequeño.
    """
    status = record.maturation_status
    return status.value if hasattr(status, "value") else str(status)


def _apply_confidence_low_override(insight: AnthropometryInsightV1) -> AnthropometryInsightV1:
    """FR-013, data-model.md §3: fuerza ``confidence.level="low"`` de forma determinista.

    Reemplazo COMPLETO del objeto ``confidence`` (nunca concatenación) — mismo
    criterio que ``critic.py::_apply_skipped_confidence`` — para garantizar
    determinísticamente los límites de longitud de ``Confidence.reason`` sin
    depender de qué haya escrito el analista.
    """
    return insight.model_copy(
        update={
            "confidence": Confidence(
                level=ConfidenceLevel.LOW, reason=_CONFIDENCE_ONLY_OVERRIDE_REASON
            )
        }
    )


def _augment_context_blocks_with_critic_feedback(
    context_blocks: dict[str, Any],
    violations: list[AnthropometryCriticIssue],
) -> dict[str, Any]:
    """Copia de ``context_blocks`` con las violaciones del crítico inyectadas.

    FR-013 / ``data-model.md`` §3 exige que la ÚNICA reinvocación permitida del
    analista corra "with the violations appended". El contrato del prompt del
    analista (``contracts/prompts/anthropometry_analyst_v1.md``, T031, fuera de
    este ownership) no reserva una variable Jinja dedicada a esto — su único
    bloque de texto libre y opcional pensado para "corrige tu intento anterior"
    es ``previous_analysis_block`` (sección "Análisis anterior (para no
    repetirte)"; la instrucción fija que el template le agrega — "Tu
    ``summary_line`` debe ser distinto del anterior" — sigue siendo válida
    también para una corrección). Reusar ese slot (en vez de inventar un bloque
    nuevo que exigiría tocar el archivo de prompt, fuera de este ownership) es
    la única forma de que el LLM vea el feedback en ESTA reinvocación; el valor
    original de ``previous_analysis_block`` (continuidad con una generación
    ESTRUCTURADA anterior de otra medición, ver ``context.py`` §2.6) se pierde
    solo para este único reintento, nunca para el resto de la corrida.

    ``violations`` ya son ``AnthropometryCriticIssue`` — ``problem``/
    ``suggested_fix`` son texto del crítico LLM, sujeto a las mismas reglas
    inviolables de privacidad que el resto de la corrida (nunca nombre propio,
    fecha exacta, dato clínico); reenviarlos al analista no amplía la
    superficie de exposición (mismo argumento que ``analyst.py`` hace para su
    propio prompt de reparación).
    """
    lines = [
        "El crítico automático encontró observaciones sobre tu intento anterior "
        "que debes corregir en esta nueva versión (no repitas el resto sin razón):"
    ]
    for violation in violations:
        lines.append(f"- ({violation.rule_id}) {violation.problem} — {violation.suggested_fix}")
    updated = dict(context_blocks)
    updated["previous_analysis_block"] = "\n".join(lines)
    return updated


async def _resolve_forbidden_names(state: dict) -> list[str]:
    """Nombres prohibidos del club para R06 (``prechecks.py``), o ``[]`` sin DB/club.

    ``club_id``/``db`` ausentes (tests unitarios sin sesión real) degradan a lista
    vacía — R06 simplemente no puede disparar, nunca un error (mismo criterio de
    "nunca inventar, degradar en vez de fallar" de ``context.py`` para
    ``training_load_window``).
    """
    db = state.get("db")
    club_id = state.get("club_id")
    if db is None or club_id is None:
        return []
    return await load_club_forbidden_names(db, club_id)


async def run_analysis(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Corre el pipeline antropométrico completo y persiste el resultado.

    Ver el docstring del módulo para la máquina de estados completa. ``config``
    se ignora — este punto de entrada abre su PROPIO span raíz de traza (única
    fuente de ``callbacks``/``trace_id`` para los cinco pasos); un ``config``
    entrante existiría solo si otro orquestador (inexistente hoy) quisiera
    anidar esta corrida bajo su propio span, caso no soportado.

    Contrato de entrada de ``state`` (documentado aquí, no en un ``TypedDict``
    compartido — mismo criterio que ``context.py``):

    - ``athlete``, ``target_record``, ``history_records``, ``audience``,
      ``use_case``, ``club_id``, ``db``, ``reference_date``: ver
      ``context.py::build_context``, que los consume tal cual.
    - ``actor``: ``User`` autenticado que pidió la generación — solo lo lee
      ``persist.py`` (T038), threadeado sin cambios por este módulo.

    Returns:
        Un dict con, como mínimo, ``insight`` (``AnthropometryInsightV1`` final),
        ``critic_verdict`` (los cinco valores persistidos),
        ``rendered_text`` (la misma prosa ya escrita en la columna ``text``),
        ``family_deliverable`` (bool, la puerta de FR-016),
        ``persisted_explanation_id``/``persisted_action`` (de ``persist.py``) y
        ``langfuse_trace_id`` — todo lo que un caller (``app/routers/ai.py``,
        T043, fuera de este ownership) necesita para construir la respuesta
        ``v1|v2`` de ``contracts/measurement-analysis-api.md`` §2 sin releer la
        fila recién escrita.

    Raises:
        LLMConfigError: proveedor LLM mal configurado (ver
            :func:`_translating_config_errors`) — mapeada a ``500`` sin cambios
            en el router.
        LLMSchemaError: la defensa final de guardrails rechazó el texto
            renderizado (``guardrails_step.py``) — mapeada a ``502`` sin
            cambios en el router; nada se persiste.
    """
    run_start = time.monotonic()

    athlete = state["athlete"]
    target_record = state["target_record"]
    use_case: str = state["use_case"]
    audience: str = state["audience"]

    # Id de sesión determinístico y NO enumerable (FR-019/FR-024) — mismo
    # dominio de separación que el resto del feature 042
    # (`llm/observability.py::keyed_session_id`). Se reusa como semilla del
    # trace id (mismo criterio que `race/ai/runner.py::_run_graph`: un único
    # valor sirve de `session_id` Y de `trace_seed`, así una corrida siempre
    # produce el mismo trace id que su propio session id determinístico).
    session_seed = f"{use_case}:{athlete.id}:{target_record.id}"
    session_id = keyed_session_id(session_seed)
    trace_tags = [f"use_case:{use_case}", f"audience:{audience}"]

    with llm_tracing(
        trace_name=f"anthro-{use_case}",
        session_id=session_id,
        tags=trace_tags,
        trace_seed=session_id,
    ) as tracing:
        llm_config = tracing or None

        # --- Paso 1: contexto -----------------------------------------
        context_update = await build_context(state, llm_config)
        step_state = {**state, **context_update}
        analysis_context = step_state["analysis_context"]

        total_tokens_in = 0
        total_tokens_out = 0
        total_cost_usd = 0.0

        forbidden_names = await _resolve_forbidden_names(step_state)

        # --- Paso 2: analista -------------------------------------------
        analyst_update = await _translating_config_errors(run_analyst(step_state, llm_config))
        step_state = {**step_state, **analyst_update}
        total_tokens_in += analyst_update["analyst_tokens_in"]
        total_tokens_out += analyst_update["analyst_tokens_out"]
        total_cost_usd = round(total_cost_usd + analyst_update["analyst_cost_usd"], 6)
        prompt_version: str = analyst_update["analyst_prompt_version"]

        insight: Optional[AnthropometryInsightV1] = None
        critic_verdict: Optional[str] = None

        if analyst_update["analyst_failed"]:
            # data-model.md §3: fallo del analista (dos intentos agotados) va
            # DIRECTO al fallback — el crítico ni siquiera se invoca.
            logger.warning(
                "anthro.pipeline: analista falló para use_case=%s; usando fallback",
                use_case,
            )
            insight = build_fallback_insight(analysis_context)
            critic_verdict = "fallback"
        else:
            draft: AnthropometryInsightV1 = analyst_update["analyst_draft"]
            precheck_result: PrecheckResult = run_prechecks(
                draft, analysis_context, forbidden_names=forbidden_names
            )

            if precheck_result.must_block:
                # data-model.md §3: violación must_block va DIRECTO al fallback
                # sin gastar una llamada al crítico (FR-014).
                insight = build_fallback_insight(analysis_context)
                critic_verdict = "fallback"
            else:
                critic_state = {
                    **step_state,
                    "analyst_draft": draft,
                    "precheck_result": precheck_result,
                }
                critic_update = await _translating_config_errors(
                    run_critic(critic_state, llm_config)
                )
                total_tokens_in += critic_update["critic_tokens_in"]
                total_tokens_out += critic_update["critic_tokens_out"]
                total_cost_usd = round(total_cost_usd + critic_update["critic_cost_usd"], 6)

                decision = critic_update["critic_decision"]

                if decision == "approved":
                    critic_verdict = "approved"
                    insight = critic_update["critic_output"]
                    if precheck_result.violations:
                        # data-model.md §3: "approve, pero con una o más
                        # violaciones confidence-only (no bloqueantes)" —
                        # forzado determinista a "low", sin importar lo que
                        # haya reportado el analista.
                        insight = _apply_confidence_low_override(insight)
                elif decision == "revised_mechanical":
                    critic_verdict = "revised"
                    insight = critic_update["critic_output"]
                elif decision == "rejected":
                    # FR-013: "at most one revision" se gasta en "revise", no
                    # en "reject" — sin segunda llamada al analista.
                    critic_verdict = "flagged"
                    insight = critic_update["critic_output"]
                elif decision == "skipped":
                    critic_verdict = "skipped"
                    insight = critic_update["critic_output"]
                else:
                    # decision == "needs_reanalysis": la ÚNICA reinvocación
                    # permitida del analista (FR-013), con las violaciones del
                    # crítico anexadas (§_augment_context_blocks_with_critic_feedback).
                    violations = critic_update["critic_violations"]
                    reanalysis_state = {
                        **step_state,
                        "context_blocks": _augment_context_blocks_with_critic_feedback(
                            step_state["context_blocks"], violations
                        ),
                    }
                    analyst2_update = await _translating_config_errors(
                        run_analyst(reanalysis_state, llm_config)
                    )
                    total_tokens_in += analyst2_update["analyst_tokens_in"]
                    total_tokens_out += analyst2_update["analyst_tokens_out"]
                    total_cost_usd = round(
                        total_cost_usd + analyst2_update["analyst_cost_usd"], 6
                    )

                    if analyst2_update["analyst_failed"]:
                        insight = build_fallback_insight(analysis_context)
                        critic_verdict = "fallback"
                    else:
                        draft2: AnthropometryInsightV1 = analyst2_update["analyst_draft"]
                        precheck2 = run_prechecks(
                            draft2, analysis_context, forbidden_names=forbidden_names
                        )
                        if precheck2.must_block:
                            insight = build_fallback_insight(analysis_context)
                            critic_verdict = "fallback"
                        else:
                            critic2_state = {
                                **step_state,
                                "analyst_draft": draft2,
                                "precheck_result": precheck2,
                            }
                            critic2_update = await _translating_config_errors(
                                run_critic(critic2_state, llm_config)
                            )
                            total_tokens_in += critic2_update["critic_tokens_in"]
                            total_tokens_out += critic2_update["critic_tokens_out"]
                            total_cost_usd = round(
                                total_cost_usd + critic2_update["critic_cost_usd"], 6
                            )
                            decision2 = critic2_update["critic_decision"]

                            if decision2 in ("approved", "revised_mechanical"):
                                # data-model.md §3: la segunda vuelta que llega
                                # a approve o a una revisión mecánica cuenta
                                # como REVISED en conjunto — la corrida completa
                                # sí necesitó una corrección, aunque la última
                                # llamada al crítico la haya aprobado tal cual.
                                critic_verdict = "revised"
                                insight = critic2_update["critic_output"]
                            else:
                                # reject | needs_reanalysis (de nuevo) | skipped
                                # en la segunda vuelta: FR-013 agotó la única
                                # revisión permitida — el borrador del segundo
                                # intento se marca FLAGGED tal cual (NUNCA el
                                # fallback determinista: es contenido real,
                                # aunque imperfecto — data-model.md §3).
                                critic_verdict = "flagged"
                                insight = draft2

        if insight is None or critic_verdict is None:  # pragma: no cover — exhaustividad, ver arriba
            raise RuntimeError(
                "anthro.pipeline: ninguna rama de la máquina de estados resolvió "
                "un insight/critic_verdict final (bug de orquestación, no un "
                "estado de negocio válido)."
            )

        # --- Paso 4: guardrails + puerta familiar ------------------------
        guardrails_state = {
            **step_state,
            "insight": insight,
            "critic_verdict": critic_verdict,
        }
        guardrails_update = await guardrails_step(guardrails_state, llm_config)
        step_state = {**step_state, **guardrails_update}

        latency_ms = int((time.monotonic() - run_start) * 1000)
        langfuse_trace_id = trace_id_for(session_id)

        model = resolve_configured_model(role="analyst", stack="app")
        provider = (settings.ai_provider or "anthropic").lower()

        # --- Paso 5: persistencia -----------------------------------------
        persist_state = {
            **step_state,
            "insight": insight,
            "critic_verdict": critic_verdict,
            "guardrail_rendered_text": guardrails_update["guardrail_rendered_text"],
            "prompt_version": prompt_version,
            "model": model,
            "provider": provider,
            "age_group": analysis_context.identity["age_group"],
            "maturation_status": _maturation_status_value(target_record),
            "generated_at": datetime.now(timezone.utc),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "cost_usd": total_cost_usd,
            "latency_ms": latency_ms,
            "langfuse_trace_id": langfuse_trace_id,
        }
        persist_update = await persist(persist_state, llm_config)

    return {
        "insight": insight,
        "critic_verdict": critic_verdict,
        "rendered_text": guardrails_update["guardrail_rendered_text"],
        "family_deliverable": guardrails_update["family_deliverable"],
        "prompt_version": prompt_version,
        "model": model,
        "provider": provider,
        "tokens_in": total_tokens_in,
        "tokens_out": total_tokens_out,
        "cost_usd": total_cost_usd,
        "latency_ms": latency_ms,
        "langfuse_trace_id": langfuse_trace_id,
        **persist_update,
    }
