"""Factory: instancia el `LLMProvider` correcto a partir de `Settings`.

Es el único lugar donde se decide qué SDK usar. Añadir un proveedor nuevo
implica:
  1. Crear `providers/<provider>.py`.
  2. Añadir su nombre a la allowlist del validator de `config.py`.
  3. Añadir una rama en `_PROVIDERS`.
  4. Si el proveedor debe poder correr también detrás de
     `AI_USE_LANGCHAIN=true`, añadir su builder a
     `app.services.llm.factory._LLM_BUILDERS` (stack `"app"`) — no aquí.
Cero cambios en `UseCase`, `Router` o tests existentes (OCP).

`AI_USE_LANGCHAIN=true` (feature 042, T020) desvía cualquier `AI_PROVIDER`
soportado — salvo `"fake"`, que nunca es un transporte real que bridgear —
hacia el adapter `LangChainProvider` en vez del SDK nativo. El short-circuit
`AI_ENABLED=false` → `FakeLLMProvider` de más abajo se mantiene PRIMERO y
sin tocar: ~40 tests de privacidad leen `FakeLLMProvider.last_request` y no
deben verse afectados por este interruptor (FR-038,
`contracts/llm-transport.md` §6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from app.services.ai.errors import LLMConfigError
from app.services.ai.protocols import LLMProvider

if TYPE_CHECKING:
    from app.config import Settings


def _build_anthropic(s: "Settings") -> LLMProvider:
    from app.services.ai.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider(
        api_key=s.ai_api_key,
        model=s.ai_model,
        timeout=s.ai_timeout_seconds,
        max_tokens=s.ai_max_tokens,
        temperature=s.ai_temperature,
        base_url=s.ai_base_url,
    )


def _build_fake(s: "Settings") -> LLMProvider:
    from app.services.ai.providers.fake import FakeLLMProvider

    return FakeLLMProvider(model=s.ai_model)


def _build_openai(s: "Settings") -> LLMProvider:
    from app.services.ai.providers.openai_provider import OpenAIProvider

    return OpenAIProvider(
        api_key=s.ai_api_key,
        model=s.ai_model,
        timeout=s.ai_timeout_seconds,
        max_tokens=s.ai_max_tokens,
        temperature=s.ai_temperature,
        base_url=s.ai_base_url,
    )


def _build_google(s: "Settings") -> LLMProvider:
    from app.services.ai.providers.google_provider import GoogleProvider

    return GoogleProvider(
        api_key=s.ai_api_key,
        model=s.ai_model,
        timeout=s.ai_timeout_seconds,
        max_tokens=s.ai_max_tokens,
        temperature=s.ai_temperature,
        base_url=s.ai_base_url,
    )


def _build_claude_cli(s: "Settings") -> LLMProvider:
    from app.services.ai.providers.claude_cli_provider import ClaudeCliProvider

    return ClaudeCliProvider(
        api_key=s.ai_api_key,
        model=s.ai_model,
        timeout=s.ai_timeout_seconds,
        max_tokens=s.ai_max_tokens,
        temperature=s.ai_temperature,
        base_url=s.ai_base_url,
    )


def _build_langchain(s: "Settings", provider_name: str) -> LLMProvider:
    """Rama `AI_USE_LANGCHAIN=true` (feature 042, T020).

    Bridgea el `AI_PROVIDER` ya resuelto a través del adapter
    `LangChainProvider`, construido sobre el `BaseChatModel` que produce la
    factoría compartida stack-neutral (`app.services.llm.factory`,
    `stack="app"` — nunca lee una variable `RACE_AI_*`, regla de herencia de
    una sola vía de `config-env.md` §0). `role=None`: los cinco casos de uso
    puenteados no tienen concepto de rol propio, igual que hoy.
    """
    from app.services.ai.providers.langchain_provider import LangChainProvider
    from app.services.llm.factory import build_chat_llm, resolve_configured_model

    chat_model = build_chat_llm(stack="app")
    model_name = resolve_configured_model(stack="app")
    return LangChainProvider(chat_model, name=provider_name, model=model_name)


_PROVIDERS: dict[str, Callable[["Settings"], LLMProvider]] = {
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "google": _build_google,
    "fake": _build_fake,
    "claude-cli": _build_claude_cli,
}


def create_llm_provider(settings: "Settings") -> LLMProvider:
    """Devuelve el provider adecuado.

    - `AI_ENABLED=false` → siempre `FakeLLMProvider` (modo apagado seguro).
      Esta rama va SIEMPRE primero y no depende de `AI_USE_LANGCHAIN`.
    - `AI_PROVIDER='fake'` → siempre `FakeLLMProvider`, con o sin
      `AI_USE_LANGCHAIN` — el fake no es un transporte real que bridgear.
    - `AI_USE_LANGCHAIN=true` (y AI habilitada, provider real) → despacha a
      `LangChainProvider` en vez del SDK nativo (feature 042, T020).
    - En otro caso (comportamiento de hoy, sin cambios), despacha por
      `AI_PROVIDER` al provider nativo correspondiente.

    Raises:
        LLMConfigError: si el provider no está soportado.
    """
    if not settings.ai_enabled:
        from app.services.ai.providers.fake import FakeLLMProvider

        return FakeLLMProvider(
            reason="AI_ENABLED=false", model=settings.ai_model
        )

    provider_name = settings.ai_provider.lower()
    if provider_name not in _PROVIDERS:
        raise LLMConfigError(
            f"AI_PROVIDER='{provider_name}' no está soportado. "
            f"Permitidos: {sorted(_PROVIDERS)}."
        )

    if settings.ai_use_langchain and provider_name != "fake":
        return _build_langchain(settings, provider_name)

    return _PROVIDERS[provider_name](settings)
