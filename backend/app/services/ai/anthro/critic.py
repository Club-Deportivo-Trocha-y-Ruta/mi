"""Paso 3 del pipeline antropométrico (feature 042): el crítico.

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T034, el contrato
``contracts/prompts/anthropometry_critic_v1.md`` y la política de revisión
EXACTA de ``data-model.md`` §3 (tabla "Critic-call outcome → persisted
``critic_verdict``"). Firma compatible con un nodo LangGraph (``async def
step(state, config) -> dict``, ``research.md`` R-03) por el mismo motivo que
``context.py``/``analyst.py``: este pipeline es un orquestador plano sin
grafo, checkpointer ni HITL, pero mantener la firma idéntica hace que una
futura promoción a ``StateGraph`` sea un envoltorio mecánico, no una
reescritura.

Colisión de vocabularios (data-model.md §2.4 — LEER ANTES DE TOCAR ESTE
ARCHIVO)
=========================================================================
El crítico LLM devuelve un veredicto de TRES valores
(:class:`~app.services.ai.anthro.schemas.AnthropometryCriticVerdict.verdict`,
``approve|revise|reject``). Eso **no** es lo que se persiste en
``AthleteAIExplanation.critic_verdict`` (CINCO valores: ``approved|revised|
flagged|fallback|skipped``). Este módulo NO produce el valor persistido —
eso es responsabilidad exclusiva de ``pipeline.py`` (T039, fuera de este
ownership), que combina esta salida con el resultado de las prechecks y de
la (a lo sumo una) reinvocación del analista. Para evitar que alguien
confunda los dos vocabularios, este módulo usa un tercer nombre propio,
``critic_decision`` (cinco valores DISTINTOS de ambos: ``approved``,
``revised_mechanical``, ``needs_reanalysis``, ``rejected``, ``skipped``) —
ver su docstring en :func:`run_critic`.

Contrato de entrada de ``state`` (lo puebla ``pipeline.py``, T039, no este
módulo — este paso corre después de ``prechecks.run_prechecks`` (T029) y
solo cuando ``PrecheckResult.must_block`` es falso; FR-014/data-model.md §3:
un ``must_block`` va directo a ``fallback.py`` sin gastar una llamada al
crítico):

- ``analyst_draft``: ``AnthropometryInsightV1`` — el borrador a revisar en
  ESTA llamada (el primer intento del analista, o su segundo y último
  intento si ``pipeline.py`` ya reinvocó por una violación interpretativa).
- ``context_blocks``: el mismo dict que arma ``context.build_context``
  (paso 1) — se reutilizan ``measurement_deltas_block``,
  ``growth_summary_block`` y ``previous_analysis_block``, YA renderizados y
  saneados, como la "verdad de campo" del crítico: es exactamente lo que el
  analista vio, así que la comparación es contra la misma fuente, no una
  releída paralela que podría divergir.
- ``precheck_result``: el ``PrecheckResult`` de ``prechecks.py`` (T029)
  para este borrador (solo violaciones no bloqueantes, por construcción de
  ``pipeline.py`` — ver arriba). Se usa únicamente para render de texto
  (``precheck_summary``); este módulo no reinterpreta sus reglas.
- ``critic_prompt_version`` (opcional): override del prompt a renderizar.
  Por defecto :data:`DEFAULT_CRITIC_PROMPT_VERSION`.

``config`` es el fragmento de ``RunnableConfig`` (callbacks de Langfuse) que
``pipeline.py`` arma dentro de su span raíz — este paso solo lo threadea
hacia ``call_llm``, nunca abre su propio span ni decide nada de tracing por
sí mismo (mismo criterio que ``analyst.py``).

Privacidad (CLAUDE.md / Ley 1581): ``precheck_summary`` solo repite
``PrecheckViolation.detail`` (ya no sensible por construcción de
``prechecks.py`` — "never echoes the offending text verbatim into logs",
data-model.md §2.3) y el propio ``draft_json``/``ground_truth`` ya pasaron
por el allow-list de ``context.py`` y las reglas inviolables del prompt del
analista — reenviarlos al crítico no amplía la superficie de exposición
(mismo argumento que ``analyst.py`` hace para su prompt de reparación).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, Optional

from pydantic import ValidationError

from app.services.ai.anthro.prompts.loader import render_prompt
from app.services.ai.anthro.schemas import (
    AnthropometryCriticIssue,
    AnthropometryCriticVerdict,
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)
from app.services.llm.calls import call_llm
from app.services.llm.factory import build_chat_llm, resolve_configured_model

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_CRITIC_PROMPT_VERSION", "CriticDecision", "run_critic"]

# Único prompt del crítico hoy — a diferencia de ``AI_ANTHRO_PROMPT_VERSION``
# (analista), no existe todavía una variable de entorno propia para este
# rol: no hay más de una versión que seleccionar (si se agrega una segunda,
# el mismo patrón de validación de ``app/config.py::validate_ai_anthro_
# prompt_version`` aplicaría aquí, fuera de este ownership).
DEFAULT_CRITIC_PROMPT_VERSION = "anthropometry_critic_v1"

# Política de revisión (FR-013, data-model.md §3, verbatim de tasks.md T034):
# un ``rule_id`` "mecánico" es corregible sin reinterpretar el dato — el
# crítico puede aplicar el fix directo. Un ``rule_id`` "interpretativo"
# exige que el ANALISTA (no el crítico) vuelva a razonar sobre el contexto,
# así que dispara la única reinvocación permitida por FR-013. Cualquier
# ``rule_id`` que el crítico invente fuera de ambos conjuntos (typo, alucinación)
# se trata como interpretativo — el lado conservador es reintentar con el
# analista, nunca adoptar un ``revised_output`` no clasificable a ciegas.
_MECHANICAL_RULE_IDS: frozenset[str] = frozenset(
    {"R04", "R06", "R07", "R09", "R10", "R12"}
)
_INTERPRETIVE_RULE_IDS: frozenset[str] = frozenset(
    {"R01", "R02", "R03", "R05", "R08", "R11", "CTX01", "CTX02"}
)

# FR-014: mensaje de calibración de confianza cuando el crítico no pudo
# ejecutarse (llamada fallida, timeout o JSON no parseable). Español neutro,
# nunca menciona el proveedor/modelo ni ningún detalle técnico — eso viaja
# aparte, en ``critic_error`` (log/trace interno, nunca hacia la familia o
# el entrenador).
_SKIPPED_CONFIDENCE_REASON = (
    "La revisión automática de este análisis no estuvo disponible; se "
    "muestra el borrador sin revisar, con confianza reducida por precaución."
)

CriticDecision = Literal[
    "approved",
    "revised_mechanical",
    "needs_reanalysis",
    "rejected",
    "skipped",
]

_JSON_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\s*")
_JSON_FENCE_CLOSE_RE = re.compile(r"\s*```$")


def _strip_json_fence(text: str) -> str:
    """Quita el ```json ... ``` que algunos modelos agregan pese al prompt.

    Mismo helper que ``analyst.py::_strip_json_fence`` / ``race/agents/
    critic.py`` — copiado localmente (no importado) para que este módulo no
    dependa de ningún otro paso del pipeline más allá de lo que su ``state``
    documenta.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _JSON_FENCE_OPEN_RE.sub("", stripped)
        stripped = _JSON_FENCE_CLOSE_RE.sub("", stripped)
    return stripped.strip()


def _extract_balanced_json(text: str) -> Optional[dict[str, Any]]:
    """Extrae el primer ``{ ... }`` balanceado del texto (defensivo).

    Mismo algoritmo que ``race/agents/critic.py::_extract_json_block``
    (camina llaves contando profundidad, respeta strings/escapes) — más
    robusto que "primer { al último }" porque ``revised_output`` es un
    objeto anidado y ``problem``/``suggested_fix`` pueden contener llaves
    literales dentro de un string.
    """
    cleaned = _strip_json_fence(text)
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    candidate = cleaned[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_verdict(text: str) -> AnthropometryCriticVerdict:
    """Parsea el JSON del crítico → :class:`AnthropometryCriticVerdict`.

    Cualquier fallo (sin JSON balanceado, JSON inválido, o violación del
    esquema Pydantic — incluido un ``revised_output`` mal formado, que
    ``AnthropometryCriticVerdict`` valida como campo anidado) se propaga
    como ``ValueError``/``ValidationError``: el caller lo trata como
    "crítico no disponible" (FR-014, verdict ``skipped``), sin reintento —
    a diferencia del analista, el crítico no tiene un ciclo de reparación
    propio (FR-013 reserva la única corrección permitida para el analista).
    """
    obj = _extract_balanced_json(text)
    if obj is None:
        raise ValueError("El crítico no produjo un objeto JSON balanceado.")
    return AnthropometryCriticVerdict.model_validate(obj)


def _render_ground_truth(context_blocks: dict[str, Any]) -> str:
    """Verdad de campo del crítico: los MISMOS bloques ya renderizados que
    vio el analista (``context_blocks``, paso 1) — nunca una relectura
    paralela del contexto que podría divergir con el tiempo.
    """
    sections: list[str] = []
    if context_blocks.get("measurement_deltas_block"):
        sections.append(
            "## Cambios desde la medición anterior\n"
            f"{context_blocks['measurement_deltas_block']}"
        )
    sections.append(
        f"## Resumen de crecimiento\n{context_blocks['growth_summary_block']}"
    )
    if context_blocks.get("previous_analysis_block"):
        sections.append(
            f"## Análisis anterior\n{context_blocks['previous_analysis_block']}"
        )
    return "\n\n".join(sections)


def _render_precheck_summary(precheck_result: Any) -> str:
    """Resumen textual, español neutro, de las violaciones NO bloqueantes.

    ``precheck_result`` llega con el shape de ``PrecheckResult``
    (data-model.md §2.3: ``violations: tuple[PrecheckViolation, ...]``,
    cada una con ``rule_id``/``category``/``detail``) pero se lee por
    duck-typing (``getattr``), no por import de ``prechecks.py`` — ese
    módulo es ownership de otra tarea (T029) desarrollada en paralelo a
    esta; acoplarse a su tipo concreto en tiempo de import arriesgaría un
    ``ImportError`` si este archivo se ejecuta antes de que exista. El
    ``detail`` de cada violación ya es, por contrato de ``prechecks.py``,
    "corto y nunca repite el texto ofensor verbatim" — seguro de reenviar
    al prompt del crítico.
    """
    violations = tuple(getattr(precheck_result, "violations", ()) or ())
    if not violations:
        return "Los prechecks deterministas no encontraron violaciones no bloqueantes."
    lines = [
        f"- {getattr(v, 'rule_id', '?')} ({getattr(v, 'category', '?')}): "
        f"{getattr(v, 'detail', '(sin detalle)')}"
        for v in violations
    ]
    return (
        "Violaciones NO bloqueantes ya detectadas por los prechecks "
        "deterministas (no las repitas, solo tenlas en cuenta):\n"
        + "\n".join(lines)
    )


def _all_mechanical(violations: list[AnthropometryCriticIssue]) -> bool:
    """``True`` si CADA violación reportada por el crítico es mecánica.

    Vacuamente ``True`` para una lista vacía — un ``verdict="revise"`` sin
    violaciones listadas es una inconsistencia del propio crítico, pero no
    hay nada interpretativo que reinterpretar; si además trae
    ``revised_output`` se adopta, si no, cae a reanálisis por el chequeo de
    ``revised_output is None`` en :func:`run_critic` (lado conservador).
    """
    return all(v.rule_id in _MECHANICAL_RULE_IDS for v in violations)


def _apply_skipped_confidence(draft: AnthropometryInsightV1) -> AnthropometryInsightV1:
    """FR-014: confianza forzada a ``low`` + razón de indisponibilidad.

    Reemplaza ``confidence`` por completo (no concatena la razón original)
    para garantizar determinísticamente ``3 <= len(reason) <= 200`` sin
    tener que truncar con cuidado un texto arbitrario del analista —
    ``_SKIPPED_CONFIDENCE_REASON`` ya está dentro del presupuesto y en
    español neutro (FR-014: "in español neutro").
    """
    return draft.model_copy(
        update={
            "confidence": Confidence(
                level=ConfidenceLevel.LOW, reason=_SKIPPED_CONFIDENCE_REASON
            )
        }
    )


def _base_result(
    *,
    critic_raw_verdict: Optional[AnthropometryCriticVerdict],
    critic_decision: CriticDecision,
    critic_output: AnthropometryInsightV1,
    critic_violations: list[AnthropometryCriticIssue],
    critic_prompt_version: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cost_usd: float,
    critic_skipped: bool,
    critic_error: Optional[str],
) -> dict[str, Any]:
    return {
        "critic_raw_verdict": critic_raw_verdict,
        "critic_decision": critic_decision,
        "critic_output": critic_output,
        "critic_violations": critic_violations,
        "critic_prompt_version": critic_prompt_version,
        "critic_tokens_in": tokens_in,
        "critic_tokens_out": tokens_out,
        "critic_latency_ms": latency_ms,
        "critic_cost_usd": cost_usd,
        "critic_skipped": critic_skipped,
        "critic_error": critic_error,
    }


async def run_critic(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Paso 3: renderiza el prompt del crítico, invoca el LLM y aplica la
    política de revisión de ``data-model.md`` §3.

    Usa ``role="critic"`` (``AI_CRITIC_MODEL``) y ``stack="app"`` en toda
    llamada a la factoría/transporte compartidos — el stack app NUNCA lee
    una variable ``RACE_AI_*`` (regla de herencia de una sola vía,
    CLAUDE.md).

    Precondición del caller (``pipeline.py``, T039): ``PrecheckResult.
    must_block`` ya es ``False`` para ``state["analyst_draft"]`` — un
    ``must_block`` NUNCA llega hasta aquí, va directo a ``fallback.py``
    (FR-014, "the critic call is skipped to avoid spending a call whose
    verdict cannot change the outcome"). Este módulo no reverifica esa
    precondición: confía en el orquestador, igual que ``analyst.py`` confía
    en que ``context_blocks``/``analysis_context`` ya llegan saneados.

    Returns:
        Un dict de actualización de estado con prefijo ``critic_*``:

        - ``critic_raw_verdict``: :class:`AnthropometryCriticVerdict` tal
          cual la devolvió el LLM, o ``None`` si ``critic_skipped``.
        - ``critic_decision`` (:data:`CriticDecision`, **NO** el
          ``critic_verdict`` persistido de 5 valores — ver el docstring del
          módulo):

          - ``"approved"``: ``verdict="approve"``. ``critic_output`` es el
            borrador de entrada sin tocar. ``pipeline.py`` lo mapea a
            ``APPROVED`` (aplicando además, si corresponde, el
            forzado-a-``low`` por violación de precheck confidence-only —
            esa decisión cruza precheck+critic y es de ``pipeline.py``, no
            de este módulo).
          - ``"revised_mechanical"``: ``verdict="revise"``, TODAS las
            violaciones son mecánicas (R04/R06/R07/R09/R10/R12) y el
            crítico entregó ``revised_output`` (ya validado contra el
            esquema por Pydantic al parsear — "schema-valid" es una
            garantía automática de haber llegado a esta rama).
            ``critic_output`` es ``revised_output``, adoptado DIRECTO, sin
            una segunda llamada al analista. ``pipeline.py`` lo mapea a
            ``REVISED``.
          - ``"needs_reanalysis"``: ``verdict="revise"`` con AL MENOS una
            violación interpretativa (R01/R02/R03/R05/R08/R11/CTX01/CTX02),
            o mecánicas sin ``revised_output`` utilizable (lado
            conservador). ``critic_output`` es el borrador de entrada
            (referencia, no un resultado final) — es ``pipeline.py`` quien
            reinvoca al analista UNA vez con ``critic_violations``
            adjuntas (FR-013) y decide, según el segundo intento, si el
            resultado final es ``REVISED`` o ``FLAGGED``. Este módulo
            nunca hace esa segunda llamada.
          - ``"rejected"``: ``verdict="reject"``. Sin segunda llamada al
            analista (FR-013: "at most one revision" se gasta en
            ``revise``, no en ``reject``). ``critic_output`` es el
            borrador de entrada (el "último draft producido", que en este
            caso es siempre el único). ``pipeline.py`` lo mapea a
            ``FLAGGED``.
          - ``"skipped"``: la llamada al crítico falló, expiró o el JSON
            fue imposible de parsear/validar (FR-014). ``critic_output``
            es el borrador de entrada con ``confidence`` reemplazada
            (:func:`_apply_skipped_confidence`). ``pipeline.py`` lo mapea
            a ``SKIPPED``.
        - ``critic_output``: ver cada rama arriba — siempre un
          ``AnthropometryInsightV1`` válido.
        - ``critic_violations``: lista de ``AnthropometryCriticIssue`` (
          vacía si ``approved``/``skipped``) — para que ``pipeline.py`` las
          adjunte al prompt de reintento del analista o las registre.
        - ``critic_prompt_version``, ``critic_tokens_in/out``,
          ``critic_latency_ms``, ``critic_cost_usd``: cero-cero-cero-cero
          si ``critic_skipped`` fue por fallo de llamada ANTES de recibir
          respuesta; poblados con lo gastado si el fallo fue de parseo
          (la llamada sí costó tokens).
        - ``critic_skipped``: ``bool`` espejo de ``critic_decision ==
          "skipped"`` — conveniencia para callers que no quieren comparar
          contra el ``Literal``.
        - ``critic_error``: resumen corto y NO sensible del fallo (tipo de
          excepción o "JSON del crítico no parseable/inválido"), ``None``
          si no hubo fallo. Nunca contiene el texto del draft ni del
          contexto.
    """
    draft: AnthropometryInsightV1 = state["analyst_draft"]
    context_blocks: dict[str, Any] = state["context_blocks"]
    precheck_result: Any = state.get("precheck_result")
    prompt_version: str = state.get("critic_prompt_version") or DEFAULT_CRITIC_PROMPT_VERSION

    prompt_vars = {
        "draft_json": json.dumps(
            draft.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        ),
        "ground_truth": _render_ground_truth(context_blocks),
        "precheck_summary": _render_precheck_summary(precheck_result),
    }
    prompt_text = render_prompt(prompt_version, prompt_vars)

    llm = build_chat_llm(role="critic", stack="app")
    model_id = resolve_configured_model(role="critic", stack="app")

    try:
        call_result = await call_llm(
            llm, prompt_text, model=model_id, config=config, stack="app"
        )
    except Exception as exc:  # noqa: BLE001 — timeout, error de red/proveedor, etc.
        logger.warning("anthro.critic: llamada al LLM falló (%s)", type(exc).__name__)
        return _base_result(
            critic_raw_verdict=None,
            critic_decision="skipped",
            critic_output=_apply_skipped_confidence(draft),
            critic_violations=[],
            critic_prompt_version=prompt_version,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            cost_usd=0.0,
            critic_skipped=True,
            critic_error=f"llamada fallida: {type(exc).__name__}",
        )

    try:
        verdict = _parse_verdict(call_result.text)
    except (ValueError, ValidationError) as exc:
        logger.warning(
            "anthro.critic: JSON del crítico no parseable/inválido (%s)",
            type(exc).__name__,
        )
        return _base_result(
            critic_raw_verdict=None,
            critic_decision="skipped",
            critic_output=_apply_skipped_confidence(draft),
            critic_violations=[],
            critic_prompt_version=prompt_version,
            tokens_in=call_result.tokens_in,
            tokens_out=call_result.tokens_out,
            latency_ms=call_result.latency_ms,
            cost_usd=call_result.cost_usd,
            critic_skipped=True,
            critic_error="JSON del crítico no parseable/inválido",
        )

    common_kwargs = dict(
        critic_raw_verdict=verdict,
        critic_prompt_version=prompt_version,
        tokens_in=call_result.tokens_in,
        tokens_out=call_result.tokens_out,
        latency_ms=call_result.latency_ms,
        cost_usd=call_result.cost_usd,
        critic_skipped=False,
        critic_error=None,
    )

    if verdict.verdict == "approve":
        return _base_result(
            critic_decision="approved",
            critic_output=draft,
            critic_violations=[],
            **common_kwargs,
        )

    if verdict.verdict == "reject":
        # FR-013: "at most one revision" se gasta en "revise", no en
        # "reject" — nunca se reinvoca al analista aquí.
        return _base_result(
            critic_decision="rejected",
            critic_output=draft,
            critic_violations=verdict.violations,
            **common_kwargs,
        )

    # verdict.verdict == "revise"
    if _all_mechanical(verdict.violations) and verdict.revised_output is not None:
        return _base_result(
            critic_decision="revised_mechanical",
            critic_output=verdict.revised_output,
            critic_violations=verdict.violations,
            **common_kwargs,
        )

    return _base_result(
        critic_decision="needs_reanalysis",
        critic_output=draft,
        critic_violations=verdict.violations,
        **common_kwargs,
    )
