"""Validators de configuración de la capa de IA.

Forzamos cada combinación crítica con `Settings(...)` directo para no depender
de variables de entorno reales. El validator de pydantic recorre los campos
en orden de declaración, por lo que en `production` debemos pasar también un
`jwt_secret_key` válido y `email_provider="resend"` con `resend_api_key`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def _prod_kwargs(**overrides):
    """Defaults que pasan los validators previos en `app_env=production`."""
    base = dict(
        app_env="production",
        jwt_secret_key="0" * 64,
        email_provider="resend",
        resend_api_key="re_xxx",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_ai_defaults_disabled():
    s = Settings(_env_file=None)
    assert s.ai_enabled is False
    assert s.ai_provider == "anthropic"
    assert s.ai_model
    assert s.ai_max_tokens == 1024
    assert s.ai_log_prompts is False


# ---------------------------------------------------------------------------
# AI_PROVIDER allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google", "fake"])
def test_ai_provider_allowed(provider):
    s = Settings(_env_file=None, ai_provider=provider)
    assert s.ai_provider == provider


def test_ai_provider_normalizes_case():
    s = Settings(_env_file=None, ai_provider="Anthropic")
    assert s.ai_provider == "anthropic"


def test_ai_provider_invalid():
    with pytest.raises(ValidationError, match="AI_PROVIDER"):
        Settings(_env_file=None, ai_provider="ollama")


# ---------------------------------------------------------------------------
# AI_API_KEY en producción
# ---------------------------------------------------------------------------


def test_ai_api_key_required_in_prod_when_enabled():
    with pytest.raises(ValidationError, match="AI_API_KEY"):
        Settings(
            _env_file=None,
            **_prod_kwargs(ai_enabled=True, ai_provider="anthropic", ai_api_key=""),
        )


def test_ai_api_key_not_required_when_disabled_in_prod():
    s = Settings(
        _env_file=None,
        **_prod_kwargs(ai_enabled=False, ai_api_key=""),
    )
    assert s.ai_enabled is False


def test_ai_api_key_not_required_for_fake_provider_in_prod():
    s = Settings(
        _env_file=None,
        **_prod_kwargs(ai_enabled=True, ai_provider="fake", ai_api_key=""),
    )
    assert s.ai_provider == "fake"


def test_ai_api_key_optional_in_dev():
    s = Settings(_env_file=None, ai_enabled=True, ai_api_key="")
    assert s.ai_enabled is True


# ---------------------------------------------------------------------------
# AI_LOG_PROMPTS prohibido en prod
# ---------------------------------------------------------------------------


def test_ai_log_prompts_forbidden_in_prod():
    with pytest.raises(ValidationError, match="AI_LOG_PROMPTS"):
        Settings(_env_file=None, **_prod_kwargs(ai_log_prompts=True))


def test_ai_log_prompts_allowed_in_dev():
    s = Settings(_env_file=None, ai_log_prompts=True)
    assert s.ai_log_prompts is True
