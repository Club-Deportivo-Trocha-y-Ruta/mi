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
    base = dict(_env_file=None)
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


def test_factory_openai_not_implemented():
    s = _settings(ai_enabled=True, ai_provider="openai", ai_api_key="x")
    with pytest.raises(LLMConfigError, match="OpenAI"):
        create_llm_provider(s)


def test_factory_google_not_implemented():
    s = _settings(ai_enabled=True, ai_provider="google", ai_api_key="x")
    with pytest.raises(LLMConfigError, match="Google"):
        create_llm_provider(s)


def test_factory_unknown_provider_caught_by_config_validator():
    """`AI_PROVIDER` desconocido es rechazado en config (no llega a la factory)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _settings(ai_provider="ollama")
