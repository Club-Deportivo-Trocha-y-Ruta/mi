"""Tests del adapter `LangChainProvider` (feature 042, T023).

Cubre la traducción `LLMRequest` -> mensajes LangChain, el poblado de
`LLMResponse` (incluido el fallback de conteo de tokens), el mapeo de
excepciones del SDK hacia la jerarquía `LLMError`, la estrategia MVP de
`complete_json` (JSON-en-el-prompt, sin tool calling) y el cumplimiento
estructural del Protocol `LLMProvider`.

Usa `GenericFakeChatModel` (langchain_core) como doble de `BaseChatModel` —
una de las dos únicas ubicaciones permitidas para ese fake en todo el
repositorio (`contracts/llm-transport.md` §7); la otra es `tests/anthro/**`.

Nota de alcance (`contracts/llm-transport.md` §3.1): el mapeo a
`LLMConfigError` ("provider desconocido") ocurre una sola vez, al
construir el provider en `create_llm_provider()` — no en este adapter, que
nunca valida el string de proveedor ni lo recibe. Ese camino se cubre en
`test_ai_factory.py` (T024), no aquí; `complete()`/`complete_json()` de
este archivo solo pueden desembocar en `LLMTimeoutError`,
`LLMUnavailableError` o `LLMSchemaError`, que es lo que se prueba abajo.
"""

from __future__ import annotations

import pytest
from langchain_core.exceptions import ModelError, ModelTimeoutError
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage

from app.services.ai.errors import LLMSchemaError, LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.protocols import LLMProvider
from app.services.ai.providers.langchain_provider import LangChainProvider


class _RecordingFakeChatModel(GenericFakeChatModel):
    """`GenericFakeChatModel` que además recuerda los mensajes recibidos.

    `GenericFakeChatModel` no distingue tipos de mensaje de entrada —
    siempre devuelve el próximo elemento de su iterador canned — así que
    para poder asertar CÓMO tradujo el adapter la petición interceptamos
    `_generate` y guardamos la lista de `BaseMessage` tal como llegó.
    """

    last_messages: list[BaseMessage] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.last_messages = list(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class _RaisingFakeChatModel(GenericFakeChatModel):
    """Doble que levanta una excepción del SDK en vez de responder."""

    to_raise: BaseException = None

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise self.to_raise


def _provider(chat_model, *, name: str = "google", model: str = "gemini-3.1-flash-lite"):
    return LangChainProvider(chat_model, name=name, model=model)


def _request(**overrides) -> LLMRequest:
    defaults: dict = dict(
        system="Eres un asistente del club.",
        messages=(LLMMessage(role="user", content="Hola"),),
    )
    defaults.update(overrides)
    return LLMRequest(**defaults)


# ---------------------------------------------------------------------------
# 1. Traducción LLMRequest -> mensajes LangChain
# ---------------------------------------------------------------------------


async def test_translates_system_first_and_preserves_message_order():
    """`system` se traduce a un `SystemMessage` en cabeza (nunca colapsado
    dentro de un `HumanMessage`), y el orden user/assistant/user se
    preserva exactamente, con el contenido intacto en cada turno."""
    chat_model = _RecordingFakeChatModel(messages=iter([AIMessage(content="ok")]))
    provider = _provider(chat_model)

    req = _request(
        system="Instrucciones del sistema.",
        messages=(
            LLMMessage(role="user", content="primer turno"),
            LLMMessage(role="assistant", content="segundo turno"),
            LLMMessage(role="user", content="tercer turno"),
        ),
    )

    await provider.complete(req)

    sent = chat_model.last_messages
    assert len(sent) == 4

    first = sent[0]
    assert type(first).__name__ == "SystemMessage"
    assert first.content == "Instrucciones del sistema."

    kinds = [type(m).__name__ for m in sent[1:]]
    assert kinds == ["HumanMessage", "AIMessage", "HumanMessage"]

    contents = [m.content for m in sent[1:]]
    assert contents == ["primer turno", "segundo turno", "tercer turno"]

    # El system prompt no debe reaparecer colapsado en el primer HumanMessage.
    assert sent[1].content == "primer turno"


# ---------------------------------------------------------------------------
# 2. Poblado de LLMResponse (texto, modelo, usage) + fallback de conteo
# ---------------------------------------------------------------------------


async def test_response_carries_text_model_and_usage_from_metadata():
    reply = AIMessage(
        content="Respuesta generada.",
        usage_metadata={"input_tokens": 42, "output_tokens": 7, "total_tokens": 49},
    )
    chat_model = GenericFakeChatModel(messages=iter([reply]))
    provider = _provider(chat_model, name="anthropic", model="claude-sonnet-5")

    resp = await provider.complete(_request())

    assert resp.text == "Respuesta generada."
    assert resp.model == "claude-sonnet-5"
    assert resp.provider == "anthropic"
    assert resp.usage.input_tokens == 42
    assert resp.usage.output_tokens == 7
    assert resp.latency_ms >= 0


async def test_response_usage_falls_back_to_char_count_without_usage_metadata():
    """Sin `usage_metadata` (mock sin ese campo), cae al fallback documentado
    `len(text) // 4` sobre el prompt y sobre el texto de respuesta."""
    reply = AIMessage(content="1234567890")  # sin usage_metadata
    chat_model = GenericFakeChatModel(messages=iter([reply]))
    provider = _provider(chat_model)

    req = _request(system="sistema", messages=(LLMMessage(role="user", content="ab"),))
    resp = await provider.complete(req)

    prompt_text = req.system + "ab"
    assert resp.usage.input_tokens == len(prompt_text) // 4
    assert resp.usage.output_tokens == len("1234567890") // 4


# ---------------------------------------------------------------------------
# 3. Mapeo de excepciones — ninguna excepción cruda del SDK debe escapar
# ---------------------------------------------------------------------------


async def test_timeout_becomes_llm_timeout_error():
    chat_model = _RaisingFakeChatModel(
        messages=iter([]), to_raise=ModelTimeoutError("tiempo agotado")
    )
    provider = _provider(chat_model)

    with pytest.raises(LLMTimeoutError):
        await provider.complete(_request())


async def test_connection_or_provider_failure_becomes_llm_unavailable_error():
    """Un error de conexión/proveedor genérico (`ModelError`, la clase base
    que LangChain estandariza sobre las excepciones nativas de cada SDK) se
    traduce a `LLMUnavailableError` — nunca escapa como `ModelError` crudo."""
    chat_model = _RaisingFakeChatModel(
        messages=iter([]), to_raise=ModelError("el proveedor no respondió")
    )
    provider = _provider(chat_model)

    with pytest.raises(LLMUnavailableError) as excinfo:
        await provider.complete(_request())
    assert not isinstance(excinfo.value, LLMTimeoutError)


async def test_unmapped_sdk_exception_still_becomes_llm_unavailable_error():
    """Cualquier otra excepción cruda del SDK (no `ModelError`/`ModelTimeoutError`)
    tampoco debe escapar del adapter: cae en el `except Exception` genérico."""
    chat_model = _RaisingFakeChatModel(
        messages=iter([]), to_raise=ConnectionError("socket cerrado")
    )
    provider = _provider(chat_model)

    with pytest.raises(LLMUnavailableError):
        await provider.complete(_request())


async def test_complete_json_unparseable_response_becomes_llm_schema_error():
    reply = AIMessage(content="esto no es JSON válido {")
    chat_model = GenericFakeChatModel(messages=iter([reply]))
    provider = _provider(chat_model)

    with pytest.raises(LLMSchemaError):
        await provider.complete_json(_request(), schema={"type": "object"})


# ---------------------------------------------------------------------------
# 4. complete_json: JSON-en-el-prompt, nunca tool calling
# ---------------------------------------------------------------------------


async def test_complete_json_returns_valid_payload_without_tool_calling():
    schema = {
        "type": "object",
        "properties": {"resumen": {"type": "string"}},
        "required": ["resumen"],
    }
    reply = AIMessage(content='{"resumen": "todo bien"}')
    chat_model = _RecordingFakeChatModel(messages=iter([reply]))
    provider = _provider(chat_model)

    result = await provider.complete_json(_request(), schema=schema)

    assert result == {"resumen": "todo bien"}

    # Estrategia MVP: el schema viaja embebido en el system prompt como
    # texto, no vía tool_calls/bind_tools — el fake nunca expone
    # `tool_calls` en el mensaje enviado y el adapter no los usa.
    sent = chat_model.last_messages
    assert type(sent[0]).__name__ == "SystemMessage"
    assert "resumen" in sent[0].content
    assert "JSON" in sent[0].content
    # bind_tools/with_structured_output no fueron ejercitados: el fake no
    # define esos métodos con comportamiento propio, así que si el adapter
    # los hubiera invocado sin existir, la llamada habría fallado antes de
    # llegar aquí. Confirmamos además que el texto crudo del modelo es JSON
    # plano, no una envoltura de tool call.
    assert reply.tool_calls == []


# ---------------------------------------------------------------------------
# 5. Cumplimiento estructural del Protocol LLMProvider
# ---------------------------------------------------------------------------


async def test_adapter_satisfies_llm_provider_protocol_and_exposes_identity():
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    provider = _provider(chat_model, name="google", model="gemini-3.1-flash-lite")

    assert isinstance(provider, LLMProvider)
    assert provider.name == "google"
    assert provider.model == "gemini-3.1-flash-lite"
