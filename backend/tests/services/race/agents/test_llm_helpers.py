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


def test_compute_cost_usd_known_values():
    # 1M tokens input + 1M tokens output → 0.075 + 0.30 = 0.375.
    assert compute_cost_usd(1_000_000, 1_000_000) == 0.375
    # Zero → zero.
    assert compute_cost_usd(0, 0) == 0.0


def test_estimate_tokens_from_chars_floor_at_zero():
    assert estimate_tokens_from_chars("") == 0
    assert estimate_tokens_from_chars("abc") == 0  # 3 // 4 == 0


def test_build_chat_llm_constructs_instance_without_calling_api():
    """build_chat_llm no debe hacer red — solo instanciar el wrapper."""
    llm = build_chat_llm(model="gemini-2.5-flash-lite", api_key="dummy", temperature=0.1)
    # Sanity: el objeto existe y tiene el método ainvoke.
    assert hasattr(llm, "ainvoke")
