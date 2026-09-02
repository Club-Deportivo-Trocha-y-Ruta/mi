"""Tests del módulo ``_llm.py`` (helpers compartidos por los agentes)."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.race.agents._llm import (
    build_chat_llm,
    extract_text,
    extract_usage,
    resolve_configured_model,
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
    # 1M tokens input + 1M tokens output → 0.25 + 1.50 = 1.75
    # (Gemini 3.1 Flash Lite, tarifa vigente 2026-07-14).
    assert compute_cost_usd(1_000_000, 1_000_000, provider="google") == 1.75
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
    # role="chat" no tiene override propio (feature 037, T101) — aísla el
    # fallback genérico probado aquí de los defaults por-rol de analyst/critic.
    llm = build_chat_llm(api_key="dummy", role="chat")
    assert llm.model == "claude-sonnet-5"


def test_build_chat_llm_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="no soportado"):
        build_chat_llm(provider="bogus", api_key="x")


def test_build_chat_llm_constructs_openai_instance_with_base_url_without_calling_api():
    """build_chat_llm(provider='openai') no debe hacer red — solo instanciar
    el wrapper ``ChatOpenAI`` con el ``base_url`` config-only (dialecto
    Ollama u OpenAI real)."""
    llm = build_chat_llm(
        provider="openai",
        model="qwen3.5:latest",
        api_key="dummy",
        base_url="http://host.docker.internal:11434/v1",
    )
    assert hasattr(llm, "ainvoke")
    assert llm.model_name == "qwen3.5:latest"
    # langchain_openai expone el base_url configurado como ``openai_api_base``.
    assert llm.openai_api_base == "http://host.docker.internal:11434/v1"


def test_build_chat_llm_openai_defaults_base_url_to_none_when_unset():
    """Sin ``base_url`` explícito ni ``Settings.race_ai_base_url`` → apunta
    a la API real de OpenAI (``base_url=None``, default de ``ChatOpenAI``)."""
    from app.config import settings

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "race_ai_base_url", None)
        llm = build_chat_llm(provider="openai", model="gpt-4o-mini", api_key="dummy")
    assert hasattr(llm, "ainvoke")
    assert llm.model_name == "gpt-4o-mini"


def test_compute_cost_usd_known_values_openai():
    """Ollama local (uso objetivo de 'openai' en race/agents/) = costo 0."""
    assert compute_cost_usd(1_000_000, 1_000_000, provider="openai") == 0.0
    assert compute_cost_usd(0, 0, provider="openai") == 0.0


def test_build_chat_llm_google_default_model_is_gemini_3_1_flash_lite(monkeypatch):
    """T061: el default de Google debía seguir a pricing.py, no quedar en el
    modelo predecesor ("gemini-2.5-flash-lite")."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    llm = build_chat_llm(api_key="dummy", role="chat")
    assert llm.model == "gemini-3.1-flash-lite"


# ---------------------------------------------------------------------------
# resolve_configured_model (feature 036, T060)
# ---------------------------------------------------------------------------


def test_resolve_configured_model_reads_provider_and_model_from_settings(monkeypatch):
    """No debe hardcodear ningún string — lee de Settings en el momento de la
    llamada, igual que build_chat_llm."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "anthropic")
    monkeypatch.setattr(settings, "race_ai_model", "")
    assert resolve_configured_model(role="chat") == "claude-sonnet-5"

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    assert resolve_configured_model(role="chat") == "gemini-3.1-flash-lite"


def test_resolve_configured_model_prefers_explicit_model_override(monkeypatch):
    """Un ``race_ai_model`` explícito (o un override pasado por parámetro)
    gana sobre el default del proveedor — mismo orden que build_chat_llm."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "gemini-custom-pinned")
    assert resolve_configured_model(role="chat") == "gemini-custom-pinned"
    assert resolve_configured_model(model="explicit-override") == "explicit-override"


def test_settings_race_ai_provider_validator_accepts_openai():
    """El validator de ``Settings.race_ai_provider`` acepta 'openai' sin
    lanzar ``ValidationError`` (proveedor sumado para Ollama/OpenAI-compatible)."""
    from app.config import Settings

    s = Settings(race_ai_provider="openai")
    assert s.race_ai_provider == "openai"

    # También normaliza mayúsculas/espacios como los demás proveedores.
    s_upper = Settings(race_ai_provider=" OpenAI ")
    assert s_upper.race_ai_provider == "openai"


# ---------------------------------------------------------------------------
# build_chat_llm(role=...) / resolve_configured_model(role=...) — feature 037, T101
# ---------------------------------------------------------------------------


def test_resolve_configured_model_analyst_role_uses_race_ai_analyst_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-3.8-flash")
    assert resolve_configured_model(role="analyst") == "gemini-3.8-flash"


def test_resolve_configured_model_critic_role_uses_race_ai_critic_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_critic_model", "gemini-3.1-flash-lite")
    assert resolve_configured_model(role="critic") == "gemini-3.1-flash-lite"


def test_resolve_configured_model_chat_role_ignores_role_settings_uses_legacy(monkeypatch):
    """'chat' no tiene variable propia — siempre cae a race_ai_model legacy o
    al default del proveedor, nunca a race_ai_analyst_model/race_ai_critic_model."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-3.8-flash")
    monkeypatch.setattr(settings, "race_ai_critic_model", "gemini-3.5-flash-lite")
    assert resolve_configured_model(role="chat") == "gemini-3.1-flash-lite"


def test_resolve_configured_model_role_model_wins_over_legacy_race_ai_model(monkeypatch):
    """RACE_AI_ANALYST_MODEL/RACE_AI_CRITIC_MODEL, cuando están seteados,
    ganan sobre race_ai_model legacy para su rol."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "gemini-legacy-pinned")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-3.8-flash")
    assert resolve_configured_model(role="analyst") == "gemini-3.8-flash"


def test_resolve_configured_model_falls_back_to_legacy_when_role_model_empty(monkeypatch):
    """RACE_AI_MODEL legacy sigue mandando cuando el override por-rol está vacío."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "gemini-legacy-pinned")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "")
    assert resolve_configured_model(role="analyst") == "gemini-legacy-pinned"


def test_build_chat_llm_analyst_role_uses_race_ai_analyst_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-3.8-flash")
    llm = build_chat_llm(api_key="dummy", role="analyst")
    assert llm.model == "gemini-3.8-flash"


def test_build_chat_llm_critic_role_uses_race_ai_critic_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_critic_model", "gemini-3.1-flash-lite")
    llm = build_chat_llm(api_key="dummy", role="critic")
    assert llm.model == "gemini-3.1-flash-lite"


def test_build_chat_llm_explicit_model_wins_over_role(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-3.8-flash")
    llm = build_chat_llm(api_key="dummy", role="analyst", model="explicit-model")
    assert llm.model == "explicit-model"


def test_compute_cost_usd_uses_model_rate_when_known():
    from app.services.race.agents.pricing import compute_cost_usd

    cost = compute_cost_usd(
        1_000_000, 1_000_000, provider="google", model="gemini-3.8-flash"
    )
    assert cost == 0.75 + 3.75

    cost_critic = compute_cost_usd(
        1_000_000, 1_000_000, provider="google", model="gemini-3.5-flash-lite"
    )
    assert cost_critic == 0.30 + 2.50


def test_compute_cost_usd_falls_back_to_provider_rate_when_model_unknown():
    from app.services.race.agents.pricing import compute_cost_usd

    cost = compute_cost_usd(
        1_000_000, 1_000_000, provider="google", model="gemini-unknown-model"
    )
    assert cost == 0.25 + 1.50
