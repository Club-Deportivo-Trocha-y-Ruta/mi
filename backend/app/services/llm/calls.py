"""Invocación de LLM + extracción de métricas normalizadas, stack-neutral
(feature 042, W1).

Extraído de ``app/services/race/agents/_llm.py`` (lead ruling 2,
``contracts/llm-transport.md`` §2) — mismo código, mismos nombres públicos,
nueva ruta de import. Aislado del agente concreto para facilitar mock en
tests: los tests patchean estos símbolos y se ahorran instanciar la SDK real.

- ``extract_usage`` busca ``usage_metadata`` y luego cae al fallback
  declarado en el workflow (§3.2) ``len(text)//4``.
- ``call_llm`` añade un parámetro ``stack`` (feature 042) para que el stack
  app resuelva su tarifa de proveedor desde ``AI_PROVIDER`` en vez de
  ``RACE_AI_PROVIDER`` — mismo criterio de herencia de una sola vía que
  ``app.services.llm.factory``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.config import settings
from app.services.llm.pricing import compute_cost_usd, estimate_tokens_from_chars


@dataclass(frozen=True)
class LLMCallResult:
    """Resultado normalizado de una llamada al LLM."""

    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float


def extract_usage(response: Any, prompt_text: str, fallback_text: str) -> tuple[int, int]:
    """Extrae (tokens_in, tokens_out) del response LangChain.

    LangChain >=0.3 expone ``response.usage_metadata = {"input_tokens": N,
    "output_tokens": M, ...}``. Si no está disponible (mocks o providers
    legacy), cae al fallback declarado: ``len(text) // 4``.
    """
    meta = getattr(response, "usage_metadata", None)
    if isinstance(meta, dict):
        ti = int(meta.get("input_tokens", 0) or 0)
        to = int(meta.get("output_tokens", 0) or 0)
        if ti or to:
            return ti, to

    return estimate_tokens_from_chars(prompt_text), estimate_tokens_from_chars(fallback_text)


def extract_text(response: Any) -> str:
    """Extrae el texto de la respuesta LangChain.

    LangChain ``AIMessage.content`` es ``str`` o ``list[dict|str]`` (multi-
    modal). Cubrimos ambos.
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                t = c.get("text")
                if t:
                    parts.append(str(t))
        return "".join(parts)
    return str(content)


async def call_llm(
    llm: Any,
    prompt: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[dict[str, Any]] = None,
    stack: Literal["race", "app"] = "race",
) -> LLMCallResult:
    """Invoca el LLM con un único mensaje y mide métricas.

    Convención: el ``prompt`` ya viene renderizado. Lo enviamos como
    HumanMessage simple — ni Gemini ni el uso actual de Anthropic aquí
    distinguen system vs human en cuanto a billing/comportamiento. Si en
    el futuro queremos system message dedicado, refactor sin tocar callers.

    Args:
        provider: usado solo para elegir la tarifa de :func:`compute_cost_usd`.
            Si ``None``, se resuelve del stack seleccionado — el caso común,
            ya que ``llm`` normalmente viene de :func:`build_chat_llm` con el
            mismo proveedor configurado y el mismo ``stack``.
        model: model_id exacto usado para la tarifa por-modelo (feature 037,
            T101). Opcional — cuando no se pasa, cae a la tarifa por
            proveedor como antes.
        config: ``RunnableConfig`` opcional (callbacks de Langfuse). Solo lo
            pasan callers fuera del grafo (juez); dentro del grafo los
            callbacks ya se heredan del config de la corrida.
        stack: ``"race"`` (default, comportamiento preexistente) | ``"app"``
            — selecciona si el proveedor de fallback (cuando ``provider`` es
            ``None``) se resuelve de ``RACE_AI_PROVIDER`` (con herencia a
            ``AI_PROVIDER``) o directo de ``AI_PROVIDER`` (feature 042, la
            regla de herencia de una sola vía: el stack app nunca lee
            ``RACE_AI_*``).
    """
    from langchain_core.messages import HumanMessage

    if stack == "app":
        resolved_provider = (provider or settings.ai_provider or "anthropic").lower()
    else:
        resolved_provider = (
            provider or settings.race_ai_provider or settings.ai_provider or "anthropic"
        ).lower()

    messages = [HumanMessage(content=prompt)]
    start = time.monotonic()
    response = await (llm.ainvoke(messages, config=config) if config else llm.ainvoke(messages))
    latency_ms = int((time.monotonic() - start) * 1000)

    text = extract_text(response)
    tokens_in, tokens_out = extract_usage(response, prompt, text)
    cost_usd = compute_cost_usd(
        tokens_in, tokens_out, provider=resolved_provider, model=model
    )

    return LLMCallResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
