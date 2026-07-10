"""Tests del módulo ``_llm.py`` (helpers compartidos por los agentes)."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.race.agents._llm import (
    build_chat_llm,
    extract_text,
    extract_usage,
)
from app.services.race.agents.pricing import (
    compute_cost_usd,
    estimate_tokens_from_chars,
)


@dataclass
class _StubResp:
    content: object = ""
    usage_metadata: object = None


def test_extract_text_handles_str_content():
    assert extract_text(_StubResp(content="hola")) == "hola"


def test_extract_text_handles_list_of_str():
    assert extract_text(_StubResp(content=["a", "b", "c"])) == "abc"


def test_extract_text_handles_list_of_dicts_with_text():
    payload = [{"type": "text", "text": "primero"}, {"type": "text", "text": "segundo"}]
    assert extract_text(_StubResp(content=payload)) == "primerosegundo"


def test_extract_text_handles_list_of_dicts_without_text_key():
    """Items sin 'text' se ignoran (defensa)."""
    payload = [{"type": "image_url"}, {"text": "ok"}]
    assert extract_text(_StubResp(content=payload)) == "ok"


def test_extract_text_handles_raw_string_response():
    """Si el objeto NO tiene .content (raro), str(response)."""
    assert extract_text("respuesta cruda") == "respuesta cruda"


def test_extract_usage_with_metadata_returns_metadata():
    resp = _StubResp(usage_metadata={"input_tokens": 100, "output_tokens": 50})
    ti, to = extract_usage(resp, "prompt", "answer")
    assert (ti, to) == (100, 50)


def test_extract_usage_fallback_when_metadata_missing():
    """Sin usage_metadata → estimate por chars."""
    resp = _StubResp(usage_metadata=None)
    ti, to = extract_usage(resp, "x" * 40, "y" * 20)
    assert ti == 10  # 40 // 4
    assert to == 5  # 20 // 4


def test_extract_usage_fallback_when_both_tokens_zero():
    """Edge: usage_metadata existe pero ambos tokens son 0 → estimate."""
    resp = _StubResp(usage_metadata={"input_tokens": 0, "output_tokens": 0})
    ti, to = extract_usage(resp, "x" * 40, "y" * 20)
    assert ti == 10
    assert to == 5


def test_compute_cost_usd_known_values_google():
    # 1M tokens input + 1M tokens output → 0.075 + 0.30 = 0.375.
    assert compute_cost_usd(1_000_000, 1_000_000, provider="google") == 0.375
    # Zero → zero.
    assert compute_cost_usd(0, 0, provider="google") == 0.0


def test_compute_cost_usd_known_values_anthropic():
    # 1M tokens input + 1M tokens output → 3.00 + 15.00 = 18.0.
    assert compute_cost_usd(1_000_000, 1_000_000, provider="anthropic") == 18.0
    assert compute_cost_usd(0, 0, provider="anthropic") == 0.0


def test_compute_cost_usd_unknown_provider_raises():
    with pytest.raises(KeyError):
        compute_cost_usd(1, 1, provider="bogus")


def test_estimate_tokens_from_chars_floor_at_zero():
    assert estimate_tokens_from_chars("") == 0
    assert estimate_tokens_from_chars("abc") == 0  # 3 // 4 == 0


def test_build_chat_llm_constructs_google_instance_without_calling_api():
    """build_chat_llm no debe hacer red — solo instanciar el wrapper."""
    llm = build_chat_llm(
        provider="google", model="gemini-2.5-flash-lite", api_key="dummy", temperature=0.1
    )
    # Sanity: el objeto existe y tiene el método ainvoke.
    assert hasattr(llm, "ainvoke")


def test_build_chat_llm_constructs_anthropic_instance_without_calling_api():
    llm = build_chat_llm(provider="anthropic", model="claude-sonnet-5", api_key="dummy")
    assert hasattr(llm, "ainvoke")
    assert hasattr(llm, "bind_tools")


def test_build_chat_llm_defaults_to_anthropic_when_unset(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "anthropic")
    monkeypatch.setattr(settings, "race_ai_model", "")
    llm = build_chat_llm(api_key="dummy")
    assert llm.model == "claude-sonnet-5"


def test_build_chat_llm_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="no soportado"):
        build_chat_llm(provider="bogus", api_key="x")
