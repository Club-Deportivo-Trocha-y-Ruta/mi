"""Tests de las dataclasses y errores de la capa de IA.

Verifican validaciones invariantes y la jerarquía de errores.
"""

from __future__ import annotations

import pytest

from app.services.ai.errors import (
    LLMConfigError,
    LLMError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.ai.models import LLMMessage, LLMRequest, LLMResponse, TokenUsage


# ---------------------------------------------------------------------------
# LLMMessage
# ---------------------------------------------------------------------------


def test_llm_message_user_ok():
    msg = LLMMessage(role="user", content="hola")
    assert msg.role == "user"
    assert msg.content == "hola"


def test_llm_message_assistant_ok():
    msg = LLMMessage(role="assistant", content="hola")
    assert msg.role == "assistant"


def test_llm_message_role_system_rejected():
    with pytest.raises(ValueError, match="role inválido"):
        LLMMessage(role="system", content="x")  # type: ignore[arg-type]


def test_llm_message_empty_content_rejected():
    with pytest.raises(ValueError, match="vacío"):
        LLMMessage(role="user", content="   ")


# ---------------------------------------------------------------------------
# LLMRequest
# ---------------------------------------------------------------------------


def test_llm_request_ok():
    req = LLMRequest(
        system="Eres asistente",
        messages=(LLMMessage(role="user", content="hola"),),
        max_tokens=128,
        temperature=0.2,
    )
    assert req.max_tokens == 128
    assert len(req.messages) == 1


def test_llm_request_empty_system_rejected():
    with pytest.raises(ValueError, match="system"):
        LLMRequest(system="", messages=(LLMMessage(role="user", content="x"),))


def test_llm_request_empty_messages_rejected():
    with pytest.raises(ValueError, match="messages"):
        LLMRequest(system="ok", messages=())


# ---------------------------------------------------------------------------
# LLMResponse / TokenUsage
# ---------------------------------------------------------------------------


def test_token_usage_total():
    u = TokenUsage(input_tokens=10, output_tokens=20)
    assert u.total == 30


def test_token_usage_default_zero():
    assert TokenUsage().total == 0


def test_llm_response_defaults():
    r = LLMResponse(text="ok")
    assert r.text == "ok"
    assert r.usage.total == 0
    assert r.model == ""
    assert r.provider == ""


# ---------------------------------------------------------------------------
# Jerarquía de errores
# ---------------------------------------------------------------------------


def test_error_hierarchy():
    # Todos descienden de LLMError → un único except cubre la capa.
    assert issubclass(LLMConfigError, LLMError)
    assert issubclass(LLMUnavailableError, LLMError)
    assert issubclass(LLMTimeoutError, LLMUnavailableError)
    assert issubclass(LLMSchemaError, LLMError)


def test_timeout_is_unavailable():
    # Routers manejan ambos como 503; LLMTimeoutError debe ser subclase.
    e = LLMTimeoutError("timeout")
    assert isinstance(e, LLMUnavailableError)
