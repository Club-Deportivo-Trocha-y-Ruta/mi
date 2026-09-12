"""Paso 2 del pipeline antropométrico (feature 042): el analista.

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T033 y el contrato
``contracts/prompts/anthropometry_analyst_v1.md``. Firma compatible con un
nodo LangGraph (``async def step(state, config) -> dict``, ``research.md``
R-03) por el mismo motivo que ``context.py`` (T028): este pipeline es un
orquestador plano sin grafo, checkpointer ni HITL, pero mantener la firma
idéntica hace que una futura promoción a ``StateGraph`` sea un envoltorio
mecánico, no una reescritura.

Contrato de entrada de ``state`` (lo puebla ``pipeline.py``, T039, no este
módulo — este paso corre después de ``context.build_context``):

- ``context_blocks``: dict producido por ``context.build_context`` — trae
  las cinco variables de bloque que el prompt espera
  (``measurement_deltas_block``, ``longitudinal_series_block``,
  ``growth_summary_block``, ``training_load_block``,
  ``previous_analysis_block``; también trae ``identity_block``, que este
  paso no usa — el prompt del analista interpola edad/sexo/categoría como
  variables sueltas, no como un bloque de texto).
- ``analysis_context``: la ``AnalysisContext`` de ``context.py`` — solo se
  lee ``.identity`` (``age_decimal``, ``age_group``, ``sex``, ``category``,
  ``audience``), ya saneada por ``sanitize_insight_context`` en el paso 1.
- ``prompt_version`` (opcional): override del prompt a renderizar. Por
  defecto ``Settings.ai_anthro_prompt_version``
  (``AI_ANTHRO_PROMPT_VERSION``, hoy siempre ``"anthropometry_analyst_v1"``
  — ver el validador en ``app/config.py``).

``config`` es el fragmento de ``RunnableConfig`` (callbacks de Langfuse) que
``pipeline.py`` arma dentro de su span raíz (``contracts/trace-metadata-
allowlist.md`` §4.1) — este paso solo lo threadea hacia ``call_llm``, nunca
abre su propio span ni decide nada de tracing por sí mismo.

Retorna una actualización de estado con el prefijo ``analyst_*`` (mismo
patrón de acumulación que ``app/services/race/ai/nodes/analyst_agent.py::
_accumulate_metrics``, adaptado a un pipeline de un solo intento por paso en
vez de un grafo):

    {
        "analyst_draft": AnthropometryInsightV1 | None,   # None solo si fallan los dos intentos
        "analyst_prompt_version": str,
        "analyst_tokens_in": int,
        "analyst_tokens_out": int,
        "analyst_latency_ms": int,
        "analyst_cost_usd": float,   # redondeado a 6 decimales, mismo criterio que compute_cost_usd
        "analyst_failed": bool,
        "analyst_error": str | None,   # resumen corto y no sensible del último fallo, solo si analyst_failed
    }

``pipeline.py`` (T039, fuera de este ownership) es quien decide qué hacer
con ``analyst_failed=True``: FR-013/FR-014 y ``data-model.md`` §3 exigen que
un fallo del analista (dos intentos agotados) vaya DIRECTO al fallback
determinista (``fallback.py``) — el crítico ni siquiera se invoca. Este
módulo no construye ningún fallback: solo reporta el fallo.

Privacidad (CLAUDE.md / Ley 1581): el resumen de error de reintento
(``_validation_error_summary``) solo describe violaciones de forma del
esquema Pydantic (campo, tipo, cardinalidad) — nunca el contenido del
draft ni ningún dato del contexto — así que es seguro de anexar al prompt
de reintento y, si hace falta, de loguear. El propio draft (texto crudo del
modelo) SÍ puede aparecer en el prompt de reintento (para que el modelo
pueda corregirlo) siguiendo el mismo criterio ya usado por
``app/services/race/agents/analyst.py::_v3_repair_prompt`` — el draft del
analista ya está sujeto a las reglas inviolables del prompt (sin nombre
propio, sin fecha absoluta, sin dato clínico), así que reenviárselo al
mismo modelo no amplía la superficie de exposición.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from pydantic import ValidationError

from app.config import settings
from app.services.ai.anthro.prompts.loader import render_prompt
from app.services.ai.anthro.schemas import AnthropometryInsightV1
from app.services.llm.calls import LLMCallResult, call_llm
from app.services.llm.factory import build_chat_llm, resolve_configured_model

logger = logging.getLogger(__name__)

__all__ = ["run_analyst"]

# Uno de estos dos análisis basta y sobra: un intento inicial + un único
# reintento de reparación (FR-013: "at most one revision" — la misma regla
# de "una sola corrección" que aplica al ciclo con el crítico también acota
# el propio parseo del analista, mismo criterio que
# ``race/agents/analyst.py::_generate_v3``).
_MAX_ATTEMPTS = 2

# Recorte del draft anterior que se reinyecta en el prompt de reparación —
# mismo valor que ``race/agents/analyst.py::_V3_REPAIR_EXCERPT_CHARS``, para
# no inflar el prompt de reintento con un draft ya muy largo.
_REPAIR_EXCERPT_CHARS = 1500

_JSON_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\s*")
_JSON_FENCE_CLOSE_RE = re.compile(r"\s*```$")


def _strip_json_fence(text: str) -> str:
    """Quita el ```json ... ``` que algunos modelos agregan pese al prompt.

    Mismo helper que ``race/agents/analyst.py::_strip_json_fence`` — la
    salida del analista debe ser JSON puro (regla de formato del prompt),
    pero varios proveedores envuelven la respuesta en un code fence aunque
    se les pida explícitamente no hacerlo.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _JSON_FENCE_OPEN_RE.sub("", stripped)
        stripped = _JSON_FENCE_CLOSE_RE.sub("", stripped)
    return stripped.strip()


def _parse_insight(text: str) -> AnthropometryInsightV1:
    """Parsea el JSON del analista → :class:`AnthropometryInsightV1`.

    Tolera el code fence y texto alrededor del objeto (recorta al primer
    ``{`` y al último ``}``) — mismo criterio de tolerancia que
    ``race/agents/analyst.py::parse_insight_v3``. Cualquier fallo se
    propaga como ``ValueError``/``json.JSONDecodeError``/``ValidationError``
    para que el caller dispare el único reintento permitido.
    """
    candidate = _strip_json_fence(text)
    if not candidate:
        raise ValueError("El analista devolvió una respuesta vacía.")
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("La respuesta del analista no contiene un objeto JSON.")
        candidate = candidate[start : end + 1]
    return AnthropometryInsightV1.model_validate(json.loads(candidate))


def _validation_error_summary(exc: Exception) -> str:
    """Resumen corto y NO sensible del fallo de parseo/validación.

    Para un ``ValidationError`` de Pydantic, lista ``campo: mensaje`` por
    cada violación (nunca el valor recibido — podría ser el propio texto
    generado). Para cualquier otro error (JSON malformado, respuesta
    vacía), usa el mensaje de la excepción tal cual: son mensajes fijos de
    este módulo, nunca contienen contenido del draft.
    """
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "objeto"
            parts.append(f"{loc}: {err['msg']}")
        return "; ".join(parts)
    return str(exc)


def _repair_prompt(original_prompt: str, previous_text: str, error_summary: str) -> str:
    """Prompt de reparación: el original + el error + el intento fallido.

    Mismo patrón que ``race/agents/analyst.py::_v3_repair_prompt`` — el
    draft anterior se reinyecta recortado (``_REPAIR_EXCERPT_CHARS``) para
    que el modelo vea exactamente qué produjo y lo corrija, sin repetir
    todo el contexto original dos veces innecesariamente.
    """
    excerpt = _strip_json_fence(previous_text or "")[:_REPAIR_EXCERPT_CHARS]
    return (
        f"{original_prompt}\n\n"
        "# Corrección obligatoria\n\n"
        "Tu respuesta anterior no fue un objeto JSON válido para el esquema "
        f"pedido. Error del validador: {error_summary}\n\n"
        "Respuesta anterior (recortada):\n\n"
        f"```\n{excerpt}\n```\n\n"
        "Devuelve ÚNICAMENTE el objeto JSON corregido, sin texto alrededor "
        "y sin ```json, respetando las cardinalidades indicadas "
        "(changes 1-4, meaning 1-4, next_weeks 1-3, warning_signs 0-2, "
        "data_gaps 0-3)."
    )


async def _attempt(
    llm: Any,
    prompt_text: str,
    *,
    model_id: str,
    config: Optional[dict[str, Any]],
) -> tuple[Optional[AnthropometryInsightV1], LLMCallResult, Optional[str]]:
    """Un intento de llamada + parseo. Nunca lanza — el fallo viaja en la tupla."""
    call_result = await call_llm(
        llm, prompt_text, model=model_id, config=config, stack="app"
    )
    try:
        insight = _parse_insight(call_result.text)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo/validación dispara el reintento.
        return None, call_result, _validation_error_summary(exc)
    return insight, call_result, None


def _prompt_context(state: dict) -> tuple[dict[str, Any], str]:
    """Arma las variables Jinja del prompt del analista desde el ``state``.

    Devuelve ``(prompt_vars, prompt_version)``. Las cinco variables de
    bloque vienen de ``context_blocks`` (paso 1); ``audience``,
    ``age_group``, ``age_decimal``, ``sex`` y ``category`` vienen de
    ``analysis_context.identity`` — el prompt las interpola sueltas, no
    como un bloque pre-formateado (a diferencia de las otras cinco).
    """
    context_blocks: dict[str, Any] = state["context_blocks"]
    identity: dict[str, Any] = state["analysis_context"].identity
    prompt_version: str = state.get("prompt_version") or settings.ai_anthro_prompt_version

    prompt_vars = {
        "audience": identity["audience"],
        "age_group": identity["age_group"],
        "age_decimal": identity["age_decimal"],
        "sex": identity["sex"],
        "category": identity["category"],
        "measurement_deltas_block": context_blocks.get("measurement_deltas_block"),
        "longitudinal_series_block": context_blocks.get("longitudinal_series_block"),
        "growth_summary_block": context_blocks["growth_summary_block"],
        "training_load_block": context_blocks.get("training_load_block"),
        "previous_analysis_block": context_blocks.get("previous_analysis_block"),
    }
    return prompt_vars, prompt_version


async def run_analyst(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Paso 2: renderiza el prompt del analista, invoca el LLM y valida el JSON.

    Ver el docstring del módulo para el contrato completo de ``state`` y de
    la actualización devuelta. Usa ``role="analyst"`` (``AI_ANALYST_MODEL``)
    y ``stack="app"`` en toda llamada a la factoría/transporte compartidos
    (``app/services/llm/factory.py``, ``app/services/llm/calls.py``) — el
    stack app NUNCA lee una variable ``RACE_AI_*`` (regla de herencia de una
    sola vía, CLAUDE.md).
    """
    prompt_vars, prompt_version = _prompt_context(state)
    prompt_text = render_prompt(prompt_version, prompt_vars)

    llm = build_chat_llm(role="analyst", stack="app")
    model_id = resolve_configured_model(role="analyst", stack="app")

    tokens_in = tokens_out = latency_ms = 0
    cost_usd = 0.0
    last_error: Optional[str] = None
    current_prompt = prompt_text

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            insight, call_result, error = await _attempt(
                llm, current_prompt, model_id=model_id, config=config
            )
        except Exception as exc:  # noqa: BLE001 — timeout, error de red/proveedor, etc.
            logger.warning(
                "anthro.analyst: llamada al LLM falló en el intento %s/%s (%s)",
                attempt,
                _MAX_ATTEMPTS,
                type(exc).__name__,
            )
            last_error = f"llamada fallida: {type(exc).__name__}"
            continue

        tokens_in += call_result.tokens_in
        tokens_out += call_result.tokens_out
        latency_ms += call_result.latency_ms
        cost_usd = round(cost_usd + call_result.cost_usd, 6)

        if insight is not None:
            return {
                "analyst_draft": insight,
                "analyst_prompt_version": prompt_version,
                "analyst_tokens_in": tokens_in,
                "analyst_tokens_out": tokens_out,
                "analyst_latency_ms": latency_ms,
                "analyst_cost_usd": cost_usd,
                "analyst_failed": False,
                "analyst_error": None,
            }

        last_error = error
        if attempt < _MAX_ATTEMPTS:
            logger.info(
                "anthro.analyst: JSON inválido en el intento %s/%s (%s); reintentando",
                attempt,
                _MAX_ATTEMPTS,
                error,
            )
            current_prompt = _repair_prompt(prompt_text, call_result.text, error or "")

    logger.warning(
        "anthro.analyst: sin draft válido tras %s intentos (%s)", _MAX_ATTEMPTS, last_error
    )
    return {
        "analyst_draft": None,
        "analyst_prompt_version": prompt_version,
        "analyst_tokens_in": tokens_in,
        "analyst_tokens_out": tokens_out,
        "analyst_latency_ms": latency_ms,
        "analyst_cost_usd": cost_usd,
        "analyst_failed": True,
        "analyst_error": last_error,
    }
