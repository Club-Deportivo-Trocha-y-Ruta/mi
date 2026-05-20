"""Helpers compartidos por los agentes (LLM client factory + token extract).

Aislado del agente concreto para facilitar mock en tests: los tests
patchean :func:`build_chat_llm` y se ahorran instanciar la SDK real.

Decisiones:
- ``build_chat_llm`` lee de :data:`app.config.settings` por default; los
  agentes pueden override pasando un ``llm`` ya construido (útil para
  inyección en tests).
- ``extract_usage`` busca ``usage_metadata`` y luego cae al fallback
  declarado en el workflow (§3.2) ``len(text)//4``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings
from app.services.race.agents.pricing import (
    compute_cost_usd,
    estimate_tokens_from_chars,
)

DEFAULT_MODEL = "gemini-2.5-flash-lite"


def build_chat_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
):
    """Construye un ``ChatGoogleGenerativeAI`` con los defaults del proyecto.

    Import lazy para no requerir ``langchain_google_genai`` en tests que
    mockean el LLM antes de tocarlo.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model or settings.ai_model or DEFAULT_MODEL,
        temperature=temperature if temperature is not None else settings.ai_temperature,
        max_output_tokens=max_output_tokens or settings.ai_max_tokens,
        google_api_key=api_key or settings.ai_api_key or None,
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
) -> LLMCallResult:
    """Invoca el LLM con un único system+user message y mide métricas.

    Convención: el ``prompt`` ya viene renderizado. Lo enviamos como
    HumanMessage simple (Gemini no distingue system vs human en cuanto
    a billing). Si en el futuro queremos system message dedicado,
    refactor sin tocar callers.
    """
    from langchain_core.messages import HumanMessage

    start = time.monotonic()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    latency_ms = int((time.monotonic() - start) * 1000)

    text = extract_text(response)
    tokens_in, tokens_out = extract_usage(response, prompt, text)
    cost_usd = compute_cost_usd(tokens_in, tokens_out)

    return LLMCallResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
