"""Tests de `OpenAIProvider` — sin red.

Calca el patrón de `test_ai_providers.py::AnthropicProvider`: se parchea
`sys.modules["openai"]` con un stub que expone `AsyncOpenAI`/`APITimeoutError`/
`APIError`, de forma que el import lazy dentro de `__init__`/`complete()`
resuelve al stub sin requerir red ni el paquete real instalado.
"""

from __future__ import annotations

import sys

import pytest
from unittest.mock import MagicMock

from app.services.ai.errors import LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.providers import openai_provider as op


def _request(content: str = "explícame el PHV") -> LLMRequest:
    return LLMRequest(
        system="Eres asistente.",
        messages=(LLMMessage(role="user", content=content),),
    )


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str | None, prompt_tokens=10, completion_tokens=5) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage(prompt_tokens, completion_tokens)


class _FakeCompletions:
    """Doble de `client.chat.completions` que captura kwargs y responde según
    lo configurado (respuesta canned o excepción)."""

    def __init__(self, response=None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeAsyncOpenAI:
    """Doble del cliente `openai.AsyncOpenAI`. Captura los kwargs del
    constructor en un dict compartido y expone `.chat.completions`."""

    last_init_kwargs: dict = {}

    def __init__(self, completions: _FakeCompletions | None = None, **kwargs) -> None:
        _FakeAsyncOpenAI.last_init_kwargs = kwargs
        self.chat = _FakeChat(completions or _FakeCompletions())


def _install_fake_openai_module(
    monkeypatch,
    completions: _FakeCompletions | None = None,
    *,
    timeout_error: type[Exception] = Exception,
    api_error: type[Exception] = Exception,
):
    """Instala un stub de `sys.modules['openai']` con `AsyncOpenAI` ligado a
    `completions`, más `APITimeoutError`/`APIError` para el mapeo de errores."""

    fake_pkg = MagicMock()

    def _factory(**kwargs):
        return _FakeAsyncOpenAI(completions, **kwargs)

    fake_pkg.AsyncOpenAI = _factory
    fake_pkg.APITimeoutError = timeout_error
    fake_pkg.APIError = api_error
    monkeypatch.setitem(sys.modules, "openai", fake_pkg)
    return fake_pkg


# ---------------------------------------------------------------------------
# __init__ — construcción del client
# ---------------------------------------------------------------------------


def test_openai_provider_constructs_client(monkeypatch):
    """Verifica que el provider arma el client del SDK con api_key/model
    correctos y sin `base_url` cuando no se pasa."""
    _install_fake_openai_module(monkeypatch)

    provider = op.OpenAIProvider(api_key="sk-test", model="gpt-4o-mini", timeout=10.0)

    assert _FakeAsyncOpenAI.last_init_kwargs["api_key"] == "sk-test"
    assert _FakeAsyncOpenAI.last_init_kwargs["timeout"] == 10.0
    assert "base_url" not in _FakeAsyncOpenAI.last_init_kwargs
    assert provider.model == "gpt-4o-mini"
    assert provider.name == "openai"


def test_openai_provider_honors_base_url_for_dialect_backends(monkeypatch):
    """Ollama (y otros dialectos OpenAI) se configuran vía `base_url`."""
    _install_fake_openai_module(monkeypatch)

    provider = op.OpenAIProvider(
        api_key="ollama",
        model="llama3.1",
        base_url="http://host.docker.internal:11434/v1",
    )

    assert (
        _FakeAsyncOpenAI.last_init_kwargs["base_url"]
        == "http://host.docker.internal:11434/v1"
    )
    assert provider.model == "llama3.1"


def test_openai_provider_raises_when_sdk_missing(monkeypatch):
    """Si `openai` no está instalado, la construcción debe fallar limpio."""
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(LLMUnavailableError, match="openai"):
        op.OpenAIProvider(api_key="x", model="m")


# ---------------------------------------------------------------------------
# complete() — happy path
# ---------------------------------------------------------------------------


async def test_openai_provider_complete_returns_text_and_usage(monkeypatch):
    completions = _FakeCompletions(
        response=_FakeCompletion("respuesta del modelo", prompt_tokens=12, completion_tokens=8)
    )
    _install_fake_openai_module(monkeypatch, completions)

    provider = op.OpenAIProvider(
        api_key="sk-test", model="gpt-4o-mini", max_tokens=256, temperature=0.2
    )
    resp = await provider.complete(_request("hola"))

    assert resp.text == "respuesta del modelo"
    assert resp.provider == "openai"
    assert resp.model == "gpt-4o-mini"
    assert resp.usage.input_tokens == 12
    assert resp.usage.output_tokens == 8


async def test_openai_provider_complete_builds_call_with_model_temperature_max_tokens_and_messages(
    monkeypatch,
):
    """`complete()` arma la llamada a `chat.completions.create` con
    model/temperature/max_tokens correctos y el mensaje `system` primero."""
    completions = _FakeCompletions(response=_FakeCompletion("ok"))
    _install_fake_openai_module(monkeypatch, completions)

    provider = op.OpenAIProvider(
        api_key="sk-test", model="gpt-4o-mini", max_tokens=256, temperature=0.2
    )
    req = LLMRequest(
        system="Eres asistente.",
        messages=(LLMMessage(role="user", content="hola"),),
        max_tokens=512,
        temperature=0.9,
    )
    await provider.complete(req)

    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    # `req.max_tokens`/`req.temperature` (por-request) tienen prioridad sobre
    # los defaults del constructor.
    assert call["max_tokens"] == 512
    assert call["temperature"] == 0.9
    assert call["messages"][0] == {"role": "system", "content": "Eres asistente."}
    assert call["messages"][1] == {"role": "user", "content": "hola"}


async def test_openai_provider_complete_falls_back_to_constructor_defaults(monkeypatch):
    """Sin `max_tokens`/`temperature` en el request, usa los del constructor."""
    completions = _FakeCompletions(response=_FakeCompletion("ok"))
    _install_fake_openai_module(monkeypatch, completions)

    provider = op.OpenAIProvider(
        api_key="sk-test", model="gpt-4o-mini", max_tokens=333, temperature=0.7
    )
    await provider.complete(_request())

    call = completions.calls[0]
    assert call["max_tokens"] == 333
    assert call["temperature"] == 0.7


# ---------------------------------------------------------------------------
# complete() — casos borde / errores
# ---------------------------------------------------------------------------


async def test_openai_provider_complete_returns_empty_string_when_content_is_none(monkeypatch):
    """Respuesta con `message.content=None` (p.ej. tool-call vacío) no debe
    romper: el provider normaliza a cadena vacía."""
    completions = _FakeCompletions(response=_FakeCompletion(None))
    _install_fake_openai_module(monkeypatch, completions)

    provider = op.OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
    resp = await provider.complete(_request())

    assert resp.text == ""


async def test_openai_provider_maps_timeout(monkeypatch):
    """Errores de timeout del SDK se mapean a `LLMTimeoutError`."""

    class FakeAPITimeoutError(Exception):
        pass

    class FakeAPIError(Exception):
        pass

    completions = _FakeCompletions(exc=FakeAPITimeoutError("timeout!"))
    _install_fake_openai_module(
        monkeypatch,
        completions,
        timeout_error=FakeAPITimeoutError,
        api_error=FakeAPIError,
    )

    provider = op.OpenAIProvider(api_key="x", model="m")
    with pytest.raises(LLMTimeoutError):
        await provider.complete(_request())


async def test_openai_provider_maps_generic_api_error(monkeypatch):
    """Otros errores del SDK (rate limit, 5xx, etc.) se mapean a
    `LLMUnavailableError`."""

    class FakeAPITimeoutError(Exception):
        pass

    class FakeAPIError(Exception):
        pass

    completions = _FakeCompletions(exc=FakeAPIError("boom"))
    _install_fake_openai_module(
        monkeypatch,
        completions,
        timeout_error=FakeAPITimeoutError,
        api_error=FakeAPIError,
    )

    provider = op.OpenAIProvider(api_key="x", model="m")
    with pytest.raises(LLMUnavailableError):
        await provider.complete(_request())
