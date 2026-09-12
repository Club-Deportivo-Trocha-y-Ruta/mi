"""Tests de ``app/services/llm/factory.py`` (feature 042, T021).

Cubre, en orden:
1. La matriz de herencia race<->app (``config-env.md`` §0): ``RACE_AI_PROVIDER``
   vacío hereda ``AI_PROVIDER``, explícito desacopla los dos stacks, y el stack
   app NUNCA lee una variable ``RACE_AI_*`` bajo ninguna circunstancia.
2. La regresión "Anthropic/claude-cli nunca reciben temperature" (ambos
   builders la ignoran a propósito — claude-sonnet-5 4.6+ responde 400 a
   cualquier sampling param no-default).
3. El fix de T017: los builders de google/openai toman ``RACE_AI_TEMPERATURE``
   para el stack race y ``AI_TEMPERATURE`` para el stack app, sin cruzarse.
4. El import perezoso de ``claude-cli`` (el paquete NO está instalado — no es
   dependencia del proyecto).
5. ``resolve_configured_model`` como espejo sin-efectos-secundarios de la
   resolución de modelo de ``build_chat_llm``.

Ningún test de este archivo construye un cliente LangChain real contra un
proveedor real (SDKs se stubean donde hace falta) ni toca la red.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from app.config import settings
from app.services.llm import factory as llm_factory
from app.services.llm.factory import (
    DEFAULT_MODEL_BY_PROVIDER,
    build_chat_llm,
    resolve_app_config,
    resolve_configured_model,
    resolve_race_config,
)

# Valor centinela distintivo — nunca debe aparecer en una resolución del
# stack app, si aparece es que alguna lectura cruzó a RACE_AI_*.
_SENTINEL = "qqq-race-only-sentinel-nunca-en-app"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class _SpyBuilder:
    """Doble de un builder de ``_LLM_BUILDERS``: solo registra los kwargs
    recibidos y devuelve un objeto cualquiera — nunca instancia un SDK real.
    Aísla la lógica de resolución/despacho de ``build_chat_llm`` de la
    construcción real de cada cliente LangChain."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return object()


@pytest.fixture
def spy_builders(monkeypatch: pytest.MonkeyPatch) -> dict[str, _SpyBuilder]:
    """Reemplaza los cuatro builders de ``_LLM_BUILDERS`` por espías, para
    poder inspeccionar qué ``ProviderConfig`` resolvió ``build_chat_llm``
    sin depender de los SDKs reales."""
    spies = {name: _SpyBuilder() for name in llm_factory._LLM_BUILDERS}
    monkeypatch.setattr(llm_factory, "_LLM_BUILDERS", spies)
    return spies


def _install_fake_claude_cli(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Inyecta un módulo ``langchain_claude_cli`` falso en ``sys.modules``
    con un ``ChatClaudeCli`` espía — permite ejercer ``_build_claude_cli_llm``
    de verdad (sin patchear el builder) sin que el paquete real esté
    instalado. ``monkeypatch`` revierte el ``sys.modules`` al finalizar el
    test (la clave no existía antes, así que se elimina de nuevo)."""
    captured: dict[str, Any] = {}

    class _SpyChatClaudeCli:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    fake_module = types.ModuleType("langchain_claude_cli")
    fake_module.ChatClaudeCli = _SpyChatClaudeCli  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", fake_module)
    return captured


# ---------------------------------------------------------------------------
# 1. Matriz de herencia race <-> app
# ---------------------------------------------------------------------------


def test_race_provider_empty_inherits_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "")
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert resolve_race_config().provider == "anthropic"


def test_race_provider_explicit_decouples_from_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert resolve_race_config().provider == "google"


def test_app_stack_never_reads_any_race_ai_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se fija CADA variable ``RACE_AI_*`` a un valor centinela distintivo y
    se comprueba que ninguna llega a ``resolve_app_config`` — para los tres
    roles relevantes (``None``, ``analyst``, ``critic``)."""
    monkeypatch.setattr(settings, "race_ai_provider", "openai")  # != ai_provider
    monkeypatch.setattr(settings, "race_ai_model", _SENTINEL)
    monkeypatch.setattr(settings, "race_ai_api_key", _SENTINEL)
    monkeypatch.setattr(settings, "race_ai_base_url", _SENTINEL)
    monkeypatch.setattr(settings, "race_ai_analyst_model", _SENTINEL)
    monkeypatch.setattr(settings, "race_ai_critic_model", _SENTINEL)
    monkeypatch.setattr(settings, "race_ai_temperature", 987654.0)

    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "ai_model", "gemini-app-legacy")
    monkeypatch.setattr(settings, "ai_api_key", "app-real-key")
    monkeypatch.setattr(settings, "ai_base_url", "https://app.example/v1")
    monkeypatch.setattr(settings, "ai_analyst_model", "gemini-app-analyst")
    monkeypatch.setattr(settings, "ai_critic_model", "gemini-app-critic")
    monkeypatch.setattr(settings, "ai_temperature", 0.4)

    for role in (None, "analyst", "critic"):
        config = resolve_app_config(role=role)
        assert config.provider == "google"
        assert config.model != _SENTINEL
        assert config.api_key != _SENTINEL
        assert config.base_url != _SENTINEL
        assert config.temperature != 987654.0
        assert config.temperature == 0.4

    assert resolve_app_config(role=None).model == "gemini-app-legacy"
    assert resolve_app_config(role="analyst").model == "gemini-app-analyst"
    assert resolve_app_config(role="critic").model == "gemini-app-critic"
    assert resolve_app_config().api_key == "app-real-key"
    assert resolve_app_config().base_url == "https://app.example/v1"


def test_build_chat_llm_app_stack_never_dispatches_to_race_provider(
    monkeypatch: pytest.MonkeyPatch, spy_builders: dict[str, _SpyBuilder]
) -> None:
    """Extremo a extremo vía ``build_chat_llm(stack="app")``: aunque
    ``RACE_AI_PROVIDER`` apunte a otro builder, el stack app solo debe
    invocar el builder de ``AI_PROVIDER``."""
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    build_chat_llm(stack="app", api_key="dummy")
    assert spy_builders["openai"].calls
    assert not spy_builders["google"].calls


# ---------------------------------------------------------------------------
# Herencia: RACE_AI_MODEL vacío -> DEFAULT_MODEL_BY_PROVIDER, nunca AI_MODEL
# ---------------------------------------------------------------------------


def test_race_empty_model_resolves_to_provider_default_not_ai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "")
    monkeypatch.setattr(settings, "race_ai_critic_model", "")
    monkeypatch.setattr(settings, "ai_model", "ai-legacy-nunca-deberia-usarse")
    config = resolve_race_config()
    assert config.model == DEFAULT_MODEL_BY_PROVIDER["google"]
    assert config.model != "ai-legacy-nunca-deberia-usarse"


def test_app_empty_model_resolves_to_provider_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "ai_model", "")
    monkeypatch.setattr(settings, "ai_analyst_model", "")
    monkeypatch.setattr(settings, "ai_critic_model", "")
    config = resolve_app_config()
    assert config.model == DEFAULT_MODEL_BY_PROVIDER["openai"]


# ---------------------------------------------------------------------------
# Fallback de API key: RACE_AI_API_KEY vacío -> AI_API_KEY solo si el
# proveedor resuelto coincide con AI_PROVIDER
# ---------------------------------------------------------------------------


def test_race_api_key_falls_back_to_ai_api_key_when_same_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_api_key", "")
    monkeypatch.setattr(settings, "ai_api_key", "shared-key-123")
    assert resolve_race_config().api_key == "shared-key-123"


def test_race_api_key_does_not_fall_back_when_provider_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "race_ai_api_key", "")
    monkeypatch.setattr(settings, "ai_api_key", "shared-key-123")
    assert resolve_race_config().api_key is None


def test_race_api_key_explicit_wins_over_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_api_key", "race-own-key")
    monkeypatch.setattr(settings, "ai_api_key", "shared-key-123")
    assert resolve_race_config(api_key="explicit-override").api_key == "explicit-override"


def test_race_api_key_own_value_wins_over_ai_api_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_api_key", "race-own-key")
    monkeypatch.setattr(settings, "ai_api_key", "shared-key-123")
    assert resolve_race_config().api_key == "race-own-key"


def test_app_api_key_never_falls_back_to_race_ai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(settings, "race_ai_api_key", "race-key-should-not-leak")
    assert resolve_app_config().api_key is None


# ---------------------------------------------------------------------------
# Resolución de modelo por-rol
# ---------------------------------------------------------------------------


def test_race_role_analyst_uses_race_ai_analyst_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "race-legacy")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "race-analyst-model")
    assert resolve_race_config(role="analyst").model == "race-analyst-model"


def test_race_role_critic_uses_race_ai_critic_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "race-legacy")
    monkeypatch.setattr(settings, "race_ai_critic_model", "race-critic-model")
    assert resolve_race_config(role="critic").model == "race-critic-model"


@pytest.mark.parametrize("role", [None, "chat"])
def test_race_role_none_and_chat_skip_per_role_lookup(
    monkeypatch: pytest.MonkeyPatch, role: str | None
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "race-legacy")
    monkeypatch.setattr(settings, "race_ai_analyst_model", "race-analyst-model")
    monkeypatch.setattr(settings, "race_ai_critic_model", "race-critic-model")
    assert resolve_race_config(role=role).model == "race-legacy"


def test_app_role_analyst_uses_ai_analyst_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "ai_model", "app-legacy")
    monkeypatch.setattr(settings, "ai_analyst_model", "app-analyst-model")
    assert resolve_app_config(role="analyst").model == "app-analyst-model"


def test_app_role_critic_uses_ai_critic_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "ai_model", "app-legacy")
    monkeypatch.setattr(settings, "ai_critic_model", "app-critic-model")
    assert resolve_app_config(role="critic").model == "app-critic-model"


@pytest.mark.parametrize("role", [None, "chat"])
def test_app_role_none_and_chat_skip_per_role_lookup(
    monkeypatch: pytest.MonkeyPatch, role: str | None
) -> None:
    monkeypatch.setattr(settings, "ai_provider", "google")
    monkeypatch.setattr(settings, "ai_model", "app-legacy")
    monkeypatch.setattr(settings, "ai_analyst_model", "app-analyst-model")
    monkeypatch.setattr(settings, "ai_critic_model", "app-critic-model")
    assert resolve_app_config(role=role).model == "app-legacy"


# ---------------------------------------------------------------------------
# 2. Anthropic / claude-cli NUNCA reciben temperature (ni top_p/top_k)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stack", ["race", "app"])
@pytest.mark.parametrize(
    "explicit_temperature, race_ai_temperature, ai_temperature",
    [
        (None, 0.4, 0.4),
        (0.9, 0.4, 0.4),
        (None, 1.9, 0.0),
        (0.0, 0.0, 1.9),
    ],
)
def test_anthropic_never_receives_temperature(
    monkeypatch: pytest.MonkeyPatch,
    stack: str,
    explicit_temperature: float | None,
    race_ai_temperature: float,
    ai_temperature: float,
) -> None:
    import langchain_anthropic

    captured: dict[str, Any] = {}

    class _SpyChatAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setattr(settings, "race_ai_provider", "anthropic")
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "race_ai_temperature", race_ai_temperature)
    monkeypatch.setattr(settings, "ai_temperature", ai_temperature)

    build_chat_llm(
        stack=stack, api_key="dummy", model="claude-sonnet-5", temperature=explicit_temperature
    )

    assert "temperature" not in captured
    assert "top_p" not in captured
    assert "top_k" not in captured


@pytest.mark.parametrize("stack", ["race", "app"])
@pytest.mark.parametrize(
    "explicit_temperature, race_ai_temperature, ai_temperature",
    [
        (None, 0.4, 0.4),
        (0.9, 0.4, 0.4),
        (None, 1.9, 0.0),
        (0.0, 0.0, 1.9),
    ],
)
def test_claude_cli_never_receives_temperature(
    monkeypatch: pytest.MonkeyPatch,
    stack: str,
    explicit_temperature: float | None,
    race_ai_temperature: float,
    ai_temperature: float,
) -> None:
    captured = _install_fake_claude_cli(monkeypatch)
    monkeypatch.setattr(settings, "race_ai_provider", "claude-cli")
    monkeypatch.setattr(settings, "ai_provider", "claude-cli")
    monkeypatch.setattr(settings, "race_ai_temperature", race_ai_temperature)
    monkeypatch.setattr(settings, "ai_temperature", ai_temperature)
    monkeypatch.setattr(settings, "race_ai_v3_timeout_seconds", 45.0)

    build_chat_llm(
        stack=stack, model="claude-sonnet-5", temperature=explicit_temperature
    )

    assert "temperature" not in captured
    assert "top_p" not in captured
    assert "top_k" not in captured
    # También ignora max_output_tokens (ver docstring de _build_claude_cli_llm)
    # y nunca reenvía api_key — no forman parte de esta regresión pero
    # confirman que el spy realmente ejerció el builder real, no un stub.
    assert "api_key" not in captured


# ---------------------------------------------------------------------------
# 3. T017: google/openai toman RACE_AI_TEMPERATURE (race) / AI_TEMPERATURE
#    (app), y nunca se cruzan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["google", "openai"])
def test_race_stack_temperature_uses_race_ai_temperature_not_ai_temperature(
    monkeypatch: pytest.MonkeyPatch, spy_builders: dict[str, _SpyBuilder], provider: str
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", provider)
    monkeypatch.setattr(settings, "race_ai_temperature", 0.11)
    monkeypatch.setattr(settings, "ai_temperature", 0.99)
    build_chat_llm(stack="race", api_key="dummy")
    assert spy_builders[provider].calls[-1]["temperature"] == 0.11


@pytest.mark.parametrize("provider", ["google", "openai"])
def test_app_stack_temperature_uses_ai_temperature_not_race_ai_temperature(
    monkeypatch: pytest.MonkeyPatch, spy_builders: dict[str, _SpyBuilder], provider: str
) -> None:
    monkeypatch.setattr(settings, "ai_provider", provider)
    monkeypatch.setattr(settings, "ai_temperature", 0.22)
    monkeypatch.setattr(settings, "race_ai_temperature", 0.88)
    build_chat_llm(stack="app", api_key="dummy")
    assert spy_builders[provider].calls[-1]["temperature"] == 0.22


def test_explicit_temperature_argument_wins_over_stack_setting_for_google(
    monkeypatch: pytest.MonkeyPatch, spy_builders: dict[str, _SpyBuilder]
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_temperature", 0.11)
    build_chat_llm(stack="race", api_key="dummy", temperature=0.77)
    assert spy_builders["google"].calls[-1]["temperature"] == 0.77


# ---------------------------------------------------------------------------
# 4. claude-cli: import perezoso, solo local
# ---------------------------------------------------------------------------


def test_factory_module_does_not_import_claude_cli_package_eagerly() -> None:
    """El módulo ya está importado (arriba, a nivel de archivo de test) — si
    ``langchain_claude_cli`` (paquete deliberadamente ausente de
    requirements.txt) apareciera en ``sys.modules`` sería porque algo lo
    importó a nivel de módulo en vez de perezosamente dentro del builder."""
    assert "langchain_claude_cli" not in sys.modules


def test_claude_cli_missing_package_raises_documented_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "langchain_claude_cli", None)
    with pytest.raises(ImportError, match="pip install langchain-claude-cli"):
        build_chat_llm(provider="claude-cli")


def test_claude_cli_builds_successfully_once_lazy_import_is_stubbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contraparte positiva del test anterior: con el módulo stubeado, el
    builder real (no un espía del dict ``_LLM_BUILDERS``) sí construye un
    cliente — prueba que el ``try/except ImportError`` no esconde ningún
    otro fallo del builder."""
    captured = _install_fake_claude_cli(monkeypatch)
    llm = build_chat_llm(provider="claude-cli", model="claude-sonnet-5")
    assert llm is not None
    assert captured["model"] == "claude-sonnet-5"


# ---------------------------------------------------------------------------
# 5. resolve_configured_model — espejo sin construir cliente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stack", ["race", "app"])
@pytest.mark.parametrize("role", [None, "chat", "analyst", "critic"])
def test_resolve_configured_model_matches_build_chat_llm_model(
    monkeypatch: pytest.MonkeyPatch,
    spy_builders: dict[str, _SpyBuilder],
    stack: str,
    role: str | None,
) -> None:
    if stack == "race":
        monkeypatch.setattr(settings, "race_ai_provider", "google")
        monkeypatch.setattr(settings, "race_ai_model", "legacy-model")
        monkeypatch.setattr(settings, "race_ai_analyst_model", "role-analyst-model")
        monkeypatch.setattr(settings, "race_ai_critic_model", "role-critic-model")
    else:
        monkeypatch.setattr(settings, "ai_provider", "google")
        monkeypatch.setattr(settings, "ai_model", "legacy-model")
        monkeypatch.setattr(settings, "ai_analyst_model", "role-analyst-model")
        monkeypatch.setattr(settings, "ai_critic_model", "role-critic-model")

    expected = resolve_configured_model(role=role, stack=stack)
    build_chat_llm(role=role, stack=stack, api_key="dummy")
    assert spy_builders["google"].calls[-1]["model"] == expected


def test_resolve_configured_model_does_not_build_a_client(
    monkeypatch: pytest.MonkeyPatch, spy_builders: dict[str, _SpyBuilder]
) -> None:
    monkeypatch.setattr(settings, "race_ai_provider", "google")
    resolve_configured_model(stack="race")
    assert not spy_builders["google"].calls
    assert not spy_builders["anthropic"].calls
    assert not spy_builders["openai"].calls
    assert not spy_builders["claude-cli"].calls


def test_resolve_configured_model_unknown_provider_degrades_to_anthropic_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "race_ai_model", "")
    assert (
        resolve_configured_model(provider="proveedor-totalmente-desconocido")
        == DEFAULT_MODEL_BY_PROVIDER["anthropic"]
    )


def test_resolve_configured_model_unknown_provider_for_app_stack_also_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Aísla el fallback de proveedor desconocido del modelo legacy
    # (``AI_MODEL`` trae un default no-vacío en Settings y ganaría antes de
    # llegar a ``DEFAULT_MODEL_BY_PROVIDER`` si no se vacía aquí).
    monkeypatch.setattr(settings, "ai_model", "")
    assert (
        resolve_configured_model(provider="otro-desconocido", stack="app")
        == DEFAULT_MODEL_BY_PROVIDER["anthropic"]
    )
