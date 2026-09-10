"""Tests de providers.

`FakeLLMProvider` se prueba al detalle (es la base de los tests del resto
de la capa). `AnthropicProvider` se prueba a nivel de construcción y
mapeo de errores; las llamadas reales al SDK quedan fuera del CI.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai.errors import LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.providers.fake import FakeLLMProvider


# ---------------------------------------------------------------------------
# FakeLLMProvider
# ---------------------------------------------------------------------------


def _request(content: str = "explícame el PHV") -> LLMRequest:
    return LLMRequest(
        system="Eres asistente.",
        messages=(LLMMessage(role="user", content=content),),
    )


async def test_fake_complete_returns_canned_text():
    fake = FakeLLMProvider(canned="respuesta fija")
    resp = await fake.complete(_request())
    assert resp.text == "respuesta fija"
    assert resp.provider == "fake"
    assert resp.usage.total > 0


async def test_fake_complete_default_echoes_user():
    fake = FakeLLMProvider()
    resp = await fake.complete(_request("hola"))
    assert "hola" in resp.text


async def test_fake_records_last_request():
    fake = FakeLLMProvider()
    req = _request("ping")
    await fake.complete(req)
    assert fake.last_request is req
    assert fake.call_count == 1


async def test_fake_complete_json_returns_canned_dict():
    fake = FakeLLMProvider(canned_json={"resumen": "ok", "alertas": []})
    out = await fake.complete_json(_request(), schema={})
    assert out == {"resumen": "ok", "alertas": []}


async def test_fake_complete_json_builds_from_schema_when_no_canned():
    fake = FakeLLMProvider(canned_json=None)
    fake._canned_json = None  # forzar fallback
    out = await fake.complete_json(
        _request(), schema={"properties": {"a": {}, "b": {}}}
    )
    assert set(out.keys()) == {"a", "b"}


# ---------------------------------------------------------------------------
# AnthropicProvider — sin red
# ---------------------------------------------------------------------------


def test_anthropic_provider_constructs_client(monkeypatch):
    """Verifica que el provider arma el client del SDK con los kwargs correctos."""
    from app.services.ai.providers import anthropic_provider as ap

    captured = {}

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_module = MagicMock()
    fake_module.AsyncAnthropic = FakeAsyncAnthropic
    monkeypatch.setattr(
        ap, "AsyncAnthropic", FakeAsyncAnthropic, raising=False
    )
    # __init__ hace `from anthropic import AsyncAnthropic` — parchear builtins.
    import sys
    fake_pkg = MagicMock()
    fake_pkg.AsyncAnthropic = FakeAsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_pkg)

    provider = ap.AnthropicProvider(
        api_key="sk-test", model="claude-test", timeout=10.0
    )
    assert captured["api_key"] == "sk-test"
    assert captured["timeout"] == 10.0
    assert provider.model == "claude-test"
    assert provider.name == "anthropic"


def test_anthropic_provider_raises_when_sdk_missing(monkeypatch):
    """Si `anthropic` no está instalado, la construcción debe fallar limpio."""
    import sys
    from app.services.ai.providers import anthropic_provider as ap

    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(LLMUnavailableError, match="anthropic"):
        ap.AnthropicProvider(api_key="x", model="m")


async def test_anthropic_provider_maps_timeout(monkeypatch):
    """Errores de timeout del SDK se mapean a `LLMTimeoutError`."""
    import sys
    from app.services.ai.providers import anthropic_provider as ap

    class FakeAPITimeoutError(Exception):
        pass

    class FakeAPIError(Exception):
        pass

    class FakeMessages:
        async def create(self, **kwargs):
            raise FakeAPITimeoutError("timeout!")

    class FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    fake_pkg = MagicMock()
    fake_pkg.AsyncAnthropic = FakeAsyncAnthropic
    fake_pkg.APITimeoutError = FakeAPITimeoutError
    fake_pkg.APIError = FakeAPIError
    monkeypatch.setitem(sys.modules, "anthropic", fake_pkg)

    provider = ap.AnthropicProvider(api_key="x", model="m")
    with pytest.raises(LLMTimeoutError):
        await provider.complete(_request())


# ---------------------------------------------------------------------------
# ClaudeCliProvider — SOLO local, sin red
# ---------------------------------------------------------------------------


def test_claude_cli_provider_raises_when_package_missing(monkeypatch):
    """Si `langchain-claude-cli` no está instalado, falla limpio (SOLO local,
    no es dependencia dura del proyecto — ver requirements.txt)."""
    import sys

    from app.services.ai.providers import claude_cli_provider as ccp

    monkeypatch.setitem(sys.modules, "langchain_claude_cli", None)
    with pytest.raises(LLMUnavailableError, match="langchain-claude-cli"):
        ccp.ClaudeCliProvider(api_key="", model="claude-sonnet-5")


def test_claude_cli_provider_constructs_client(monkeypatch):
    """Verifica que el provider arma ``ChatClaudeCli`` con model/timeout y
    NO reenvía api_key/base_url (el CLI usa el login OAuth, no un endpoint)."""
    import sys

    from app.services.ai.providers import claude_cli_provider as ccp

    captured = {}

    class FakeChatClaudeCli:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_module = MagicMock()
    fake_module.ChatClaudeCli = FakeChatClaudeCli
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", fake_module)

    provider = ccp.ClaudeCliProvider(
        api_key="ignorada", model="claude-sonnet-5", timeout=10.0
    )
    assert captured == {"model": "claude-sonnet-5", "timeout": 10.0}
    assert provider.model == "claude-sonnet-5"
    assert provider.name == "claude-cli"


async def test_claude_cli_provider_complete_maps_response(monkeypatch):
    import sys

    from app.services.ai.providers import claude_cli_provider as ccp

    class FakeAIMessage:
        content = "Hola desde Claude"
        usage_metadata = {"input_tokens": 12, "output_tokens": 4}

    class FakeChatClaudeCli:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, messages):
            return FakeAIMessage()

    fake_module = MagicMock()
    fake_module.ChatClaudeCli = FakeChatClaudeCli
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", fake_module)

    provider = ccp.ClaudeCliProvider(api_key="", model="claude-sonnet-5")
    resp = await provider.complete(_request())
    assert resp.text == "Hola desde Claude"
    assert resp.provider == "claude-cli"
    assert resp.usage.input_tokens == 12
    assert resp.usage.output_tokens == 4


async def test_claude_cli_provider_complete_maps_unavailable_error(monkeypatch):
    """Errores del paquete (``ClaudeCliError`` y derivados) se mapean a
    ``LLMUnavailableError`` — mismo contrato que el resto de providers."""
    import sys

    from app.services.ai.providers import claude_cli_provider as ccp

    class FakeChatClaudeCli:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, messages):
            raise RuntimeError("cli crashed")

    fake_module = MagicMock()
    fake_module.ChatClaudeCli = FakeChatClaudeCli
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", fake_module)

    provider = ccp.ClaudeCliProvider(api_key="", model="claude-sonnet-5")
    with pytest.raises(LLMUnavailableError):
        await provider.complete(_request())


async def test_claude_cli_provider_complete_json_parses_json_text(monkeypatch):
    """``complete_json`` usa la misma estrategia por-prompt que el resto de
    providers del stack (ver AnthropicProvider/OpenAIProvider) — no el
    structured-output nativo del CLI."""
    import sys

    from app.services.ai.providers import claude_cli_provider as ccp

    class FakeAIMessage:
        content = '{"answer": "ok"}'
        usage_metadata = {"input_tokens": 5, "output_tokens": 3}

    class FakeChatClaudeCli:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, messages):
            return FakeAIMessage()

    fake_module = MagicMock()
    fake_module.ChatClaudeCli = FakeChatClaudeCli
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", fake_module)

    provider = ccp.ClaudeCliProvider(api_key="", model="claude-sonnet-5")
    result = await provider.complete_json(
        _request(), schema={"type": "object", "properties": {"answer": {"type": "string"}}}
    )
    assert result == {"answer": "ok"}
