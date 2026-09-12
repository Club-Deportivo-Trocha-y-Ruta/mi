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


def test_ai_defaults_disabled(monkeypatch):
    # Limpia env vars `AI_*` para que el test sea hermético — en Docker compose
    # se inyectan AI_ENABLED, AI_PROVIDER, etc. y enmascararían los defaults.
    for key in [
        "AI_ENABLED",
        "AI_PROVIDER",
        "AI_MODEL",
        "AI_API_KEY",
        "AI_BASE_URL",
        "AI_MAX_TOKENS",
        "AI_TIMEOUT_SECONDS",
        "AI_TEMPERATURE",
        "AI_LOG_PROMPTS",
    ]:
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.ai_enabled is False
    # Feature 036 (T051): default "google" — coincide con backend/.env real,
    # no con "anthropic" (que nunca corrió en producción pese a ser el
    # default de código previo).
    assert s.ai_provider == "google"
    assert s.ai_model
    assert s.ai_max_tokens == 1024
    assert s.ai_log_prompts is False


# ---------------------------------------------------------------------------
# AI_PROVIDER allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google", "fake", "claude-cli"])
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


# ---------------------------------------------------------------------------
# Race AI — defaults alineados con Gemini (feature 036, T051)
# ---------------------------------------------------------------------------


def test_ai_and_race_ai_defaults_point_to_gemini(monkeypatch):
    """Sin ``RACE_AI_PROVIDER`` fijado, hereda ``AI_PROVIDER`` (que por
    default es Gemini) — un solo lugar para cambiar de proveedor en local,
    en vez de tener que fijar las dos variables en sync a mano.
    """
    for key in ["AI_PROVIDER", "AI_MODEL", "RACE_AI_PROVIDER", "RACE_AI_MODEL"]:
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.ai_provider == "google"
    assert s.ai_model == "gemini-3.1-flash-lite"
    # "" = hereda AI_PROVIDER — ver _llm.py::build_chat_llm y demás lectores
    # (``race_ai_provider or ai_provider``), no un default propio fijo.
    assert s.race_ai_provider == ""
    # race_ai_model se deja vacío a propósito: cae al default por proveedor
    # en _llm.py::DEFAULT_MODEL_BY_PROVIDER (única fuente de verdad, T061).
    assert s.race_ai_model == ""


# ---------------------------------------------------------------------------
# Feature 042 (T007) — defaults de los seis settings nuevos de W1
# (config-env.md §1)
# ---------------------------------------------------------------------------


def test_ai_use_langchain_default_on(monkeypatch):
    """Interruptor de rollback de la migración a LangChain — ENCENDIDO por
    default: el transporte trazable es el camino normal y el interruptor
    sirve para volver al anterior durante la transición
    (contracts/config-env.md §1, quickstart.md §1.2).

    ``delenv`` porque la suite se corre con AI_USE_LANGCHAIN en ambas
    posiciones (SC-006) y BaseSettings lee os.environ: sin esto, la prueba
    del *default* mediría el ambiente, no el default.
    """
    monkeypatch.delenv("AI_USE_LANGCHAIN", raising=False)
    s = Settings(_env_file=None)
    assert s.ai_use_langchain is True


def test_ai_analyst_and_critic_model_default_empty():
    """Vacío → el pipeline de antropometría cae a AI_MODEL; un checkout
    nuevo no necesita configurar overrides por rol."""
    s = Settings(_env_file=None)
    assert s.ai_analyst_model == ""
    assert s.ai_critic_model == ""


def test_ai_anthro_prompt_version_default():
    s = Settings(_env_file=None)
    assert s.ai_anthro_prompt_version == "anthropometry_analyst_v1"


def test_race_ai_temperature_default_matches_ai_temperature_default():
    """El bug fix bundleado en config-env.md §1: `race_ai_temperature` nace
    con el mismo valor que `ai_temperature` para que un despliegue con
    defaults no vea cambio de comportamiento tras la extracción de la
    factoría compartida."""
    s = Settings(_env_file=None)
    assert s.race_ai_temperature == 0.4
    assert s.race_ai_temperature == s.ai_temperature


def test_langfuse_structural_metadata_default_off():
    s = Settings(_env_file=None)
    assert s.langfuse_structural_metadata is False


# ---------------------------------------------------------------------------
# Feature 042 (T006/T007, SC-009) — validators de producción nuevos
# ---------------------------------------------------------------------------


def test_langfuse_enabled_forbidden_in_prod():
    with pytest.raises(ValidationError, match="LANGFUSE_ENABLED"):
        Settings(_env_file=None, **_prod_kwargs(langfuse_enabled=True))


def test_langfuse_enabled_allowed_in_dev():
    s = Settings(_env_file=None, langfuse_enabled=True)
    assert s.langfuse_enabled is True


def test_langfuse_structural_metadata_forbidden_in_prod():
    with pytest.raises(ValidationError, match="LANGFUSE_STRUCTURAL_METADATA"):
        Settings(_env_file=None, **_prod_kwargs(langfuse_structural_metadata=True))


def test_langfuse_structural_metadata_allowed_in_dev():
    s = Settings(_env_file=None, langfuse_structural_metadata=True)
    assert s.langfuse_structural_metadata is True


def test_ai_provider_claude_cli_forbidden_in_prod():
    with pytest.raises(ValidationError, match="AI_PROVIDER"):
        Settings(_env_file=None, **_prod_kwargs(ai_provider="claude-cli"))


def test_ai_provider_claude_cli_allowed_in_dev():
    s = Settings(_env_file=None, ai_provider="claude-cli")
    assert s.ai_provider == "claude-cli"


def test_race_ai_provider_claude_cli_forbidden_in_prod():
    with pytest.raises(ValidationError, match="RACE_AI_PROVIDER"):
        Settings(
            _env_file=None,
            **_prod_kwargs(ai_provider="google", race_ai_provider="claude-cli"),
        )


def test_race_ai_provider_claude_cli_allowed_in_dev():
    s = Settings(_env_file=None, ai_provider="google", race_ai_provider="claude-cli")
    assert s.race_ai_provider == "claude-cli"


def test_ai_provider_claude_cli_forbidden_in_prod_via_race_inheritance():
    """`RACE_AI_PROVIDER` vacío hereda `AI_PROVIDER` (config-env.md §0): un
    `AI_PROVIDER=claude-cli` con `RACE_AI_PROVIDER` vacío debe fallar
    también para el stack race, y el mensaje debe nombrar `AI_PROVIDER`
    (la variable realmente fijada), no `RACE_AI_PROVIDER` (que ni siquiera
    se tocó)."""
    with pytest.raises(ValidationError, match="AI_PROVIDER") as excinfo:
        Settings(
            _env_file=None,
            **_prod_kwargs(ai_provider="claude-cli", race_ai_provider=""),
        )
    assert "RACE_AI_PROVIDER" not in str(excinfo.value)


def test_ai_provider_claude_cli_allowed_in_dev_via_race_inheritance():
    s = Settings(_env_file=None, ai_provider="claude-cli", race_ai_provider="")
    assert s.ai_provider == "claude-cli"
    assert s.race_ai_provider == ""
