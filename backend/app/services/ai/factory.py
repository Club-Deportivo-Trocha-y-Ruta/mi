"""Factory: instancia el `LLMProvider` correcto a partir de `Settings`.

Es el único lugar donde se decide qué SDK usar. Añadir un proveedor nuevo
implica:
  1. Crear `providers/<provider>.py`.
  2. Añadir su nombre a la allowlist del validator de `config.py`.
  3. Añadir una rama en `_PROVIDERS`.
Cero cambios en `UseCase`, `Router` o tests existentes (OCP).
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


_PROVIDERS: dict[str, Callable[["Settings"], LLMProvider]] = {
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "google": _build_google,
    "fake": _build_fake,
}


def create_llm_provider(settings: "Settings") -> LLMProvider:
    """Devuelve el provider adecuado.

    - `AI_ENABLED=false` → siempre `FakeLLMProvider` (modo apagado seguro).
    - En otro caso, despacha por `AI_PROVIDER`.

    Raises:
        LLMConfigError: si el provider no está soportado.
    """
    if not settings.ai_enabled:
        from app.services.ai.providers.fake import FakeLLMProvider

        return FakeLLMProvider(
            reason="AI_ENABLED=false", model=settings.ai_model
        )

    provider_name = settings.ai_provider.lower()
    builder = _PROVIDERS.get(provider_name)
    if builder is None:
        raise LLMConfigError(
            f"AI_PROVIDER='{provider_name}' no está soportado. "
            f"Permitidos: {sorted(_PROVIDERS)}."
        )
    return builder(settings)
