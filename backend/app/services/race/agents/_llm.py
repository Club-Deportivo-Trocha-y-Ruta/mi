"""Helpers compartidos por los agentes (LLM client factory + token extract).

Aislado del agente concreto para facilitar mock en tests: los tests
patchean :func:`build_chat_llm` y se ahorran instanciar la SDK real.

Decisiones:
- ``build_chat_llm`` es una **factory** (Strategy + Factory, mismo patrón
  que ``app/services/ai/factory.py``): despacha por ``RACE_AI_PROVIDER``
  (``anthropic`` | ``google`` | ``openai``) hacia el builder concreto — agregar un
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
    # gemini-3.1-flash-lite (GA 2026-05-07) es el modelo Google activo desde
    # 2026-07-14 — mismo dato que documenta con sus tarifas
    # ``app/services/race/agents/pricing.py``. Feature 036 (T061): este
    # default había quedado en el predecesor "gemini-2.5-flash-lite" después
    # de que pricing.py ya se hubiera actualizado — exactamente la clase de
    # deriva que este módulo (única fuente de verdad para el default por
    # proveedor) existe para evitar. Mantener ambos archivos en sync.
    "google": "gemini-3.1-flash-lite",
    # Default genérico para OpenAI real; en uso local con Ollama la config
    # (RACE_AI_MODEL) elige el modelo instalado, ej. "qwen3.5:latest".
    "openai": "gpt-4o-mini",
}


def _build_anthropic_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
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
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatGoogleGenerativeAI`` — import lazy (no requerido si el provider es otro).

    ``base_url`` se acepta por paridad de interfaz con el resto de builders
    pero se ignora — Gemini Developer API no soporta override de endpoint
    desde este client.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature if temperature is not None else settings.ai_temperature,
        max_output_tokens=max_output_tokens,
        google_api_key=api_key,
        timeout=timeout,
    )


def _build_openai_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatOpenAI`` — import lazy (no requerido si el provider es otro).

    Habilita Ollama (dialecto OpenAI ``/v1``) de forma config-only vía
    ``base_url`` (ej. ``http://host.docker.internal:11434/v1`` desde
    Docker) — ``api_key`` puede ser cualquier string dummy, Ollama no la
    valida. Sirve igual para OpenAI real dejando ``base_url`` vacío.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url or None,
        temperature=temperature if temperature is not None else settings.ai_temperature,
        max_tokens=max_output_tokens,
        timeout=timeout,
    )


_LLM_BUILDERS: dict[str, Callable[..., Any]] = {
    "anthropic": _build_anthropic_llm,
    "google": _build_google_llm,
    "openai": _build_openai_llm,
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


# Rol → nombre del atributo de Settings que trae el override de modelo
# por-rol (feature 037, T101). "chat" no tiene variable propia: siempre
# usa ``race_ai_model`` (legacy) o el default del proveedor.
_ROLE_MODEL_SETTING: dict[str, str] = {
    "analyst": "race_ai_analyst_model",
    "critic": "race_ai_critic_model",
}


def _resolve_role_model(role: Optional[str]) -> str:
    """Resuelve el override de modelo por-rol, o ``""`` si no aplica.

    Orden: ``Settings.race_ai_<role>_model`` (si el rol tiene variable
    propia y no está vacía) → ``""`` (el caller cae a ``race_ai_model``
    legacy y luego al default del proveedor).

    ``role=None`` (default) devuelve siempre ``""`` — preserva el
    comportamiento pre-feature-037 para los callers que NO pasan ``role``
    explícito (``critic.py``, ``chat.py``, las 3 llamadas de
    ``analyst.py`` no tocadas por T101): sin ``role`` no hay resolución
    por-rol, solo ``race_ai_model`` legacy → default del proveedor.
    """
    if role is None:
        return ""
    setting_name = _ROLE_MODEL_SETTING.get(role)
    if setting_name is None:
        return ""
    return getattr(settings, setting_name, "") or ""


def build_chat_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    role: Optional[str] = None,
):
    """Factory: construye el chat model LangChain del proveedor configurado.

    Args:
        provider: override explícito (``"anthropic"`` | ``"google"`` |
            ``"openai"``). Si ``None``, usa ``Settings.race_ai_provider``.
        model: override explícito. Si ``None``, se resuelve por ``role``
            (ver :func:`resolve_configured_model`).
        base_url: override explícito del endpoint. Si ``None``, usa
            ``Settings.race_ai_base_url``. Solo lo consume el builder
            ``"openai"`` (Ollama u otro dialecto-OpenAI); el resto lo ignora.
        role: ``None`` (default, comportamiento legacy) | ``"analyst"`` |
            ``"critic"`` | ``"chat"`` — feature 037 (T101). Cuando se pasa
            ``"analyst"``/``"critic"`` explícito, consulta primero
            ``RACE_AI_ANALYST_MODEL``/``RACE_AI_CRITIC_MODEL`` antes de caer
            al ``race_ai_model`` legacy. ``"chat"`` y ``None`` se comportan
            igual (sin variable propia): van directo a ``race_ai_model`` →
            default del proveedor. ``max_output_tokens`` NO se ajusta
            automáticamente por rol aquí — el caller de analyst debe pasar
            4096 explícito (ver ``agents/analyst.py``).

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
        model
        or _resolve_role_model(role)
        or settings.race_ai_model
        or DEFAULT_MODEL_BY_PROVIDER[resolved_provider]
    )
    return builder(
        model=resolved_model,
        temperature=temperature,
        max_output_tokens=max_output_tokens or settings.ai_max_tokens,
        api_key=_resolve_race_api_key(resolved_provider, api_key),
        timeout=settings.ai_timeout_seconds,
        base_url=base_url or settings.race_ai_base_url,
    )


def resolve_configured_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    role: Optional[str] = None,
) -> str:
    """Resuelve el ``model_id`` configurado, SIN instanciar el cliente LLM.

    Misma resolución de ``model`` que usa internamente :func:`build_chat_llm`
    (explícito → ``RACE_AI_<ROLE>_MODEL`` por rol → ``Settings.race_ai_model``
    legacy → default del proveedor en :data:`DEFAULT_MODEL_BY_PROVIDER`),
    expuesta aparte para quien necesite *saber qué modelo se usaría* sin
    pagar el costo de construir el cliente.

    Feature 036 (T060): ``persist_insight`` la usa para registrar en
    ``AthleteAiInsight.model`` el modelo que realmente generó el análisis.
    Antes de este helper, ese nodo tenía su propio string fijo
    (``"gemini-2.5-flash-lite"``) que quedaba desactualizado cada vez que el
    proveedor/modelo configurado cambiaba — cada insight persistido
    misreportaba su propia procedencia. Con este helper hay un único lugar
    que sabe resolver "el modelo configurado hoy".

    Feature 037 (T101): ``role`` (``"analyst"`` | ``"critic"`` | ``"chat"``)
    permite resolver el modelo específico de cada agente cuando corren con
    modelos distintos (analyst fuerte, critic barato).

    A diferencia de ``build_chat_llm``, nunca lanza por proveedor
    desconocido: degrada a la entrada ``"anthropic"`` de
    :data:`DEFAULT_MODEL_BY_PROVIDER` sólo para tener *algún* nombre que
    persistir — la validación real de proveedores soportados vive en
    ``Settings.race_ai_provider`` y en ``build_chat_llm``.
    """
    resolved_provider = (provider or settings.race_ai_provider or "anthropic").lower()
    default_model = DEFAULT_MODEL_BY_PROVIDER.get(
        resolved_provider, DEFAULT_MODEL_BY_PROVIDER["anthropic"]
    )
    return model or _resolve_role_model(role) or settings.race_ai_model or default_model


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
        model: model_id exacto usado para la tarifa por-modelo (feature 037,
            T101). Opcional — cuando no se pasa, cae a la tarifa por
            proveedor como antes.
    """
    from langchain_core.messages import HumanMessage

    resolved_provider = (provider or settings.race_ai_provider or "anthropic").lower()

    start = time.monotonic()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
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
