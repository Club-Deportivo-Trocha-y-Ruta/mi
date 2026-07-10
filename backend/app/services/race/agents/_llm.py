"""Helpers compartidos por los agentes (LLM client factory + token extract).

Aislado del agente concreto para facilitar mock en tests: los tests
patchean :func:`build_chat_llm` y se ahorran instanciar la SDK real.

Decisiones:
- ``build_chat_llm`` es una **factory** (Strategy + Factory, mismo patrón
  que ``app/services/ai/factory.py``): despacha por ``RACE_AI_PROVIDER``
  (``anthropic`` | ``google``) hacia el builder concreto — agregar un
  proveedor nuevo implica solo sumar una entrada a ``_LLM_BUILDERS``. Los
  agentes (analyst/critic/chat/judge) consumen el chat model resultante
  vía la interfaz genérica de LangChain (``ainvoke``/``bind_tools``); no
  conocen el proveedor concreto.
- Lee de :data:`app.config.settings` por default; los agentes pueden
  override pasando un ``llm`` ya construido (útil para inyección en tests).
- ``extract_usage`` busca ``usage_metadata`` y luego cae al fallback
  declarado en el workflow (§3.2) ``len(text)//4``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.config import settings
from app.services.race.agents.pricing import (
    compute_cost_usd,
    estimate_tokens_from_chars,
)

DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    "google": "gemini-2.5-flash-lite",
}


def _build_anthropic_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float,
):
    """``ChatAnthropic`` — import lazy (no requerido si el provider es otro).

    Nota: NO se envía ``temperature``. claude-sonnet-5 (familia 4.6+)
    rechaza con 400 cualquier valor de temperature/top_p/top_k distinto
    del default — mismo fix aplicado en ``AnthropicProvider.complete()``
    (capa app/services/ai/). El parámetro se acepta para paridad de
    interfaz con el builder de Google, pero se ignora aquí a propósito.
    """
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        api_key=api_key,
        max_tokens=max_output_tokens,
        timeout=timeout,
    )


def _build_google_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float,
):
    """``ChatGoogleGenerativeAI`` — import lazy (no requerido si el provider es otro)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature if temperature is not None else settings.ai_temperature,
        max_output_tokens=max_output_tokens,
        google_api_key=api_key,
        timeout=timeout,
    )


_LLM_BUILDERS: dict[str, Callable[..., Any]] = {
    "anthropic": _build_anthropic_llm,
    "google": _build_google_llm,
}


def _resolve_race_api_key(provider: str, explicit: Optional[str]) -> Optional[str]:
    """Resuelve la API key a usar, con fallback a ``AI_API_KEY``.

    Si ``RACE_AI_API_KEY`` está vacía y el proveedor de race/agents/
    coincide con el de app/services/ai/ (``AI_PROVIDER``), reutiliza
    ``AI_API_KEY`` — evita pedirle al usuario la misma key dos veces
    cuando ambos pipelines apuntan al mismo proveedor.
    """
    if explicit:
        return explicit
    if settings.race_ai_api_key:
        return settings.race_ai_api_key
    if provider == settings.ai_provider:
        return settings.ai_api_key or None
    return None


def build_chat_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
):
    """Factory: construye el chat model LangChain del proveedor configurado.

    Args:
        provider: override explícito (``"anthropic"`` | ``"google"``). Si
            ``None``, usa ``Settings.race_ai_provider``.
        model: override explícito. Si ``None``, usa ``Settings.race_ai_model``
            o el default del proveedor (:data:`DEFAULT_MODEL_BY_PROVIDER`).

    Raises:
        ValueError: proveedor no soportado (no debería ocurrir — el
            validator de ``Settings.race_ai_provider`` ya lo bloquea salvo
            que se pase ``provider=`` explícito inválido).
    """
    resolved_provider = (provider or settings.race_ai_provider or "anthropic").lower()
    builder = _LLM_BUILDERS.get(resolved_provider)
    if builder is None:
        raise ValueError(
            f"RACE_AI_PROVIDER='{resolved_provider}' no soportado. "
            f"Permitidos: {sorted(_LLM_BUILDERS)}."
        )
    resolved_model = (
        model or settings.race_ai_model or DEFAULT_MODEL_BY_PROVIDER[resolved_provider]
    )
    return builder(
        model=resolved_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens or settings.ai_max_tokens,
        api_key=_resolve_race_api_key(resolved_provider, api_key),
        timeout=settings.ai_timeout_seconds,
    )


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
) -> LLMCallResult:
    """Invoca el LLM con un único mensaje y mide métricas.

    Convención: el ``prompt`` ya viene renderizado. Lo enviamos como
    HumanMessage simple — ni Gemini ni el uso actual de Anthropic aquí
    distinguen system vs human en cuanto a billing/comportamiento. Si en
    el futuro queremos system message dedicado, refactor sin tocar callers.

    Args:
        provider: usado solo para elegir la tarifa de :func:`compute_cost_usd`.
            Si ``None``, se resuelve de ``Settings.race_ai_provider`` — el
            caso común, ya que ``llm`` normalmente viene de
            :func:`build_chat_llm` con el mismo proveedor configurado.
    """
    from langchain_core.messages import HumanMessage

    resolved_provider = (provider or settings.race_ai_provider or "anthropic").lower()

    start = time.monotonic()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    latency_ms = int((time.monotonic() - start) * 1000)

    text = extract_text(response)
    tokens_in, tokens_out = extract_usage(response, prompt, text)
    cost_usd = compute_cost_usd(tokens_in, tokens_out, provider=resolved_provider)

    return LLMCallResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
