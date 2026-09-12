"""Tests de la factoría — Strategy + Factory.

La idea: cualquier combinación válida de `AI_*` produce un provider que
cumple `LLMProvider`. Combinaciones inválidas explotan en `LLMConfigError`.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services.ai.errors import LLMConfigError
from app.services.ai.factory import create_llm_provider
from app.services.ai.providers.fake import FakeLLMProvider


def _settings(**overrides) -> Settings:
    # ``ai_use_langchain=False`` explícito: sin esto, un AI_USE_LANGCHAIN=true
    # en el entorno del proceso (la suite se corre en ambas posiciones del
    # interruptor, SC-006) se filtra a cada Settings() y los tests de despacho
    # nativo reciben un LangChainProvider. Cada test decide el valor que le
    # importa; ninguno debe depender del ambiente. Los tests del interruptor
    # pasan ``ai_use_langchain=True`` por override y siguen mandando.
    base = dict(_env_file=None, ai_use_langchain=False)
    base.update(overrides)
    return Settings(**base)


def test_factory_returns_fake_when_disabled():
    s = _settings(ai_enabled=False, ai_provider="anthropic")
    p = create_llm_provider(s)
    assert isinstance(p, FakeLLMProvider)


def test_factory_returns_fake_when_provider_is_fake():
    s = _settings(ai_enabled=True, ai_provider="fake")
    p = create_llm_provider(s)
    assert isinstance(p, FakeLLMProvider)


def test_factory_anthropic(monkeypatch):
    """Cuando `AI_ENABLED=true` y `AI_PROVIDER=anthropic` debe instanciar el adapter."""

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_pkg = MagicMock()
    fake_pkg.AsyncAnthropic = FakeAsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_pkg)

    s = _settings(
        ai_enabled=True,
        ai_provider="anthropic",
        ai_api_key="sk-test",
        ai_model="claude-x",
    )
    p = create_llm_provider(s)
    from app.services.ai.providers.anthropic_provider import AnthropicProvider

    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-x"


def test_factory_openai(monkeypatch):
    """Cuando `AI_ENABLED=true` y `AI_PROVIDER=openai` debe instanciar el
    adapter nativo — el provider de OpenAI SÍ está implementado
    (`app/services/ai/providers/openai_provider.py`); esta prueba era antes
    `test_factory_openai_not_implemented` y reflejaba una expectativa
    obsoleta (feature 042, T024)."""

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_pkg = MagicMock()
    fake_pkg.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_pkg)

    s = _settings(
        ai_enabled=True,
        ai_provider="openai",
        ai_api_key="sk-test",
        ai_model="gpt-4o-mini",
    )
    p = create_llm_provider(s)
    from app.services.ai.providers.openai_provider import OpenAIProvider

    assert isinstance(p, OpenAIProvider)
    assert p.model == "gpt-4o-mini"


def test_factory_google(monkeypatch):
    """`AI_PROVIDER=google` instancia GoogleProvider con google-genai mockeado."""

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_genai = MagicMock()
    fake_genai.Client = FakeClient
    fake_types = MagicMock()
    monkeypatch.setitem(sys.modules, "google", MagicMock(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    s = _settings(
        ai_enabled=True,
        ai_provider="google",
        ai_api_key="key",
        ai_model="gemini-2.5-flash-lite",
    )
    p = create_llm_provider(s)
    from app.services.ai.providers.google_provider import GoogleProvider

    assert isinstance(p, GoogleProvider)
    assert p.model == "gemini-2.5-flash-lite"


def test_factory_unknown_provider_caught_by_config_validator():
    """`AI_PROVIDER` desconocido es rechazado en config (no llega a la factory)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _settings(ai_provider="ollama")


# ---------------------------------------------------------------------------
# AI_USE_LANGCHAIN (feature 042, T024) — el short-circuit AI_ENABLED=false
# debe mantenerse PRIMERO y sin cambios bajo ambos valores del switch (FR-038,
# ~40 tests de privacidad leen `FakeLLMProvider.last_request`); con AI
# habilitada, el switch decide si se despacha al SDK nativo o al adapter
# `LangChainProvider` construido sobre la factoría compartida.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("use_langchain", [False, True])
def test_factory_disabled_returns_fake_under_both_langchain_switches(use_langchain):
    """`AI_ENABLED=false` → siempre `FakeLLMProvider`, sin importar
    `AI_USE_LANGCHAIN` — el short-circuit va antes que el switch."""
    s = _settings(
        ai_enabled=False,
        ai_provider="anthropic",
        ai_use_langchain=use_langchain,
    )
    p = create_llm_provider(s)
    assert isinstance(p, FakeLLMProvider)


@pytest.mark.parametrize(
    ("provider", "sdk_module", "sdk_client_attr", "provider_module", "provider_class"),
    [
        (
            "anthropic",
            "anthropic",
            "AsyncAnthropic",
            "app.services.ai.providers.anthropic_provider",
            "AnthropicProvider",
        ),
        (
            "openai",
            "openai",
            "AsyncOpenAI",
            "app.services.ai.providers.openai_provider",
            "OpenAIProvider",
        ),
        (
            "google",
            "google.genai",
            "Client",
            "app.services.ai.providers.google_provider",
            "GoogleProvider",
        ),
    ],
)
def test_factory_native_provider_when_langchain_disabled(
    monkeypatch, provider, sdk_module, sdk_client_attr, provider_module, provider_class
):
    """`AI_ENABLED=true` + `AI_USE_LANGCHAIN=false` → el SDK nativo de
    siempre, sin pasar por el adapter (comportamiento preexistente,
    inalterado por el switch)."""

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_pkg = MagicMock()
    setattr(fake_pkg, sdk_client_attr, _FakeClient)
    monkeypatch.setitem(sys.modules, sdk_module, fake_pkg)
    if sdk_module == "google.genai":
        # `google_provider.py` importa `from google import genai` — el paquete
        # padre `google` también debe resolver el submódulo mockeado.
        monkeypatch.setitem(sys.modules, "google", MagicMock(genai=fake_pkg))
        monkeypatch.setitem(sys.modules, "google.genai.types", MagicMock())

    s = _settings(
        ai_enabled=True,
        ai_use_langchain=False,
        ai_provider=provider,
        ai_api_key="key",
        ai_model="modelo-test",
    )
    p = create_llm_provider(s)

    import importlib

    mod = importlib.import_module(provider_module)
    expected_cls = getattr(mod, provider_class)
    assert isinstance(p, expected_cls)
    assert p.model == "modelo-test"


@pytest.mark.parametrize(
    ("provider", "lc_module", "lc_class_attr"),
    [
        ("anthropic", "langchain_anthropic", "ChatAnthropic"),
        ("openai", "langchain_openai", "ChatOpenAI"),
        ("google", "langchain_google_genai", "ChatGoogleGenerativeAI"),
    ],
)
def test_factory_langchain_provider_when_switch_on(monkeypatch, provider, lc_module, lc_class_attr):
    """`AI_ENABLED=true` + `AI_USE_LANGCHAIN=true` → `LangChainProvider`
    construido sobre el `BaseChatModel` de la factoría compartida, SIN
    instanciar un cliente SDK real — se parchea el import lazy del builder
    LangChain concreto (`app/services/llm/factory.py::_build_*_llm`).

    La rama `AI_USE_LANGCHAIN=true` de `create_llm_provider`
    (`_build_langchain`) resuelve el chat model y el modelo configurado a
    través de `app.services.llm.factory`, que lee el singleton global
    `app.config.settings` (no el argumento `Settings` recibido) — igual que
    en producción, donde `dependencies.py::get_llm_provider` siempre le pasa
    ese mismo singleton (`create_llm_provider(settings)`). Por eso aquí se
    parchea el singleton en vez de construir un `Settings()` aislado."""
    from app.config import settings as global_settings
    from app.services.ai.providers.langchain_provider import LangChainProvider

    class _FakeChatModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_lc_pkg = MagicMock()
    setattr(fake_lc_pkg, lc_class_attr, _FakeChatModel)
    monkeypatch.setitem(sys.modules, lc_module, fake_lc_pkg)

    monkeypatch.setattr(global_settings, "ai_enabled", True)
    monkeypatch.setattr(global_settings, "ai_use_langchain", True)
    monkeypatch.setattr(global_settings, "ai_provider", provider)
    monkeypatch.setattr(global_settings, "ai_api_key", "key")
    monkeypatch.setattr(global_settings, "ai_model", "modelo-test")
    monkeypatch.setattr(global_settings, "ai_analyst_model", "")
    monkeypatch.setattr(global_settings, "ai_critic_model", "")

    p = create_llm_provider(global_settings)

    assert isinstance(p, LangChainProvider)
    assert p.name == provider
    assert p.model == "modelo-test"
    assert isinstance(p._chat_model, _FakeChatModel)


def test_factory_fake_provider_ignores_langchain_switch():
    """`AI_PROVIDER=fake` nunca se bridgea al adapter — no es un transporte
    real, con o sin `AI_USE_LANGCHAIN`."""
    s = _settings(ai_enabled=True, ai_provider="fake", ai_use_langchain=True)
    p = create_llm_provider(s)
    assert isinstance(p, FakeLLMProvider)


@pytest.mark.parametrize("use_langchain", [False, True])
def test_factory_unknown_provider_raises_under_both_langchain_switches(use_langchain):
    """Un `AI_PROVIDER` no soportado explota en `LLMConfigError` bajo
    cualquier valor del switch — el chequeo de la allowlist ocurre antes de
    despachar al SDK nativo o al adapter."""
    s = _settings(ai_enabled=True, ai_provider="anthropic", ai_use_langchain=use_langchain)
    # Se fuerza un provider no soportado sin pasar por el validator de
    # `Settings.ai_provider` (que ya rechaza valores fuera de la allowlist),
    # para ejercitar el chequeo propio de la factory.
    s.ai_provider = "ollama"
    with pytest.raises(LLMConfigError, match="ollama"):
        create_llm_provider(s)
