"""Factoría LLM compartida, stack-neutral (feature 042, W1).

Extraída de ``app/services/race/agents/_llm.py`` (lead ruling 2,
``contracts/llm-transport.md`` §1) para servir tanto al pipeline agéntico de
``app/services/race/`` como al stack ``app/services/ai/`` detrás de
``AI_USE_LANGCHAIN`` — un único lugar que sabe construir un chat model
LangChain del proveedor configurado, sin acoplarse a cuál de los dos stacks
lo está pidiendo.

Decisiones:
- ``build_chat_llm`` sigue siendo una **factory** de despacho por proveedor
  (Strategy + Factory, mismo patrón que ``app/services/ai/factory.py``):
  agregar un proveedor nuevo implica solo sumar una entrada a
  ``_LLM_BUILDERS``. ``claude-cli`` es un proveedor SOLO local (Claude Code
  CLI vía suscripción del desarrollador) — ver ``_build_claude_cli_llm``.
- Regla de herencia de una sola vía (CLAUDE.md, ``config-env.md`` §0): el
  stack race PUEDE leer ``AI_*`` como fallback cuando su propia variable
  ``RACE_AI_*`` está vacía; el stack app NUNCA lee una variable ``RACE_AI_*``.
  ``resolve_race_config``/``resolve_app_config`` son los dos únicos puntos
  donde esa regla se aplica — todo lo demás en este módulo es genérico.
- ``build_chat_llm`` es keyword-only en ``stack`` (default ``"race"`` —
  comportamiento preexistente, nada cambia para los ~30 tests/call-sites que
  no pasan ``stack``) y despacha al resolver de config correspondiente antes
  de invocar el builder concreto. Los builders (``_build_*_llm``) no leen
  ``settings`` en absoluto: reciben ``ProviderConfig`` ya resuelto — fix de
  T017 para el acoplamiento latente que tenían ``_build_google_llm``/
  ``_build_openai_llm`` con ``settings.ai_temperature`` (ver docstring de
  ``build_chat_llm`` más abajo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from app.config import settings

DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    # gemini-3.1-flash-lite (GA 2026-05-07) es el modelo Google activo desde
    # 2026-07-14 — mismo dato que documenta con sus tarifas
    # ``app/services/llm/pricing.py``. Feature 036 (T061): este default
    # había quedado en el predecesor "gemini-2.5-flash-lite" después de que
    # pricing.py ya se hubiera actualizado — exactamente la clase de deriva
    # que este módulo (única fuente de verdad para el default por proveedor)
    # existe para evitar. Mantener ambos archivos en sync.
    "google": "gemini-3.1-flash-lite",
    # Default genérico para OpenAI real; en uso local con Ollama la config
    # (RACE_AI_MODEL) elige el modelo instalado, ej. "qwen3.5:latest".
    "openai": "gpt-4o-mini",
    # Claude Code CLI vía suscripción del desarrollador (langchain-claude-cli) —
    # SOLO uso local, ver ``_build_claude_cli_llm``.
    "claude-cli": "claude-sonnet-5",
}


@dataclass(frozen=True)
class ProviderConfig:
    """Configuración ya resuelta para un builder concreto.

    Producida por ``resolve_race_config``/``resolve_app_config`` — los
    builders de ``_LLM_BUILDERS`` no leen ``settings``, todo lo que
    necesitan llega ya resuelto aquí (``contracts/llm-transport.md`` §1).
    ``temperature=None`` significa "el builder la omite por completo" (los
    builders de Anthropic y claude-cli, ver §4 del contrato).
    """

    provider: str
    model: str
    api_key: Optional[str]
    temperature: Optional[float]
    max_output_tokens: int
    timeout: float
    base_url: Optional[str]


def _build_anthropic_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatAnthropic`` — import lazy (no requerido si el provider es otro).

    Nota: NO se envía ``temperature``. claude-sonnet-5 (familia 4.6+)
    rechaza con 400 cualquier valor de temperature/top_p/top_k distinto
    del default — mismo fix aplicado en ``AnthropicProvider.complete()``
    (capa app/services/ai/). El parámetro se acepta para paridad de
    interfaz con el builder de Google, pero se ignora aquí a propósito.
    """
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        api_key=api_key,
        max_tokens=max_output_tokens,
        timeout=timeout,
    )


def _build_google_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatGoogleGenerativeAI`` — import lazy (no requerido si el provider es otro).

    ``base_url`` se acepta por paridad de interfaz con el resto de builders
    pero se ignora — Gemini Developer API no soporta override de endpoint
    desde este client.

    ``temperature`` llega ya resuelta por el caller (feature 042, T017): este
    builder ya NO cae a ``settings.ai_temperature`` si es ``None`` — quien
    resuelve el default por-stack es ``resolve_race_config``/
    ``resolve_app_config``, antes de llegar aquí.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        google_api_key=api_key,
        timeout=timeout,
    )


def _build_openai_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatOpenAI`` — import lazy (no requerido si el provider es otro).

    Habilita Ollama (dialecto OpenAI ``/v1``) de forma config-only vía
    ``base_url`` (ej. ``http://host.docker.internal:11434/v1`` desde
    Docker) — ``api_key`` puede ser cualquier string dummy, Ollama no la
    valida. Sirve igual para OpenAI real dejando ``base_url`` vacío.

    ``temperature`` llega ya resuelta por el caller (feature 042, T017): ver
    nota equivalente en ``_build_google_llm``.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url or None,
        temperature=temperature,
        max_tokens=max_output_tokens,
        timeout=timeout,
    )


def _build_claude_cli_llm(
    *, model: str, temperature: Optional[float], max_output_tokens: int,
    api_key: Optional[str], timeout: float, base_url: Optional[str] = None,
):
    """``ChatClaudeCli`` — import lazy (no es dependencia dura del proyecto).

    Proveedor SOLO local: envuelve el Claude Code CLI vía ``claude-agent-sdk``
    y reutiliza el login OAuth de la suscripción del desarrollador (Keychain
    de macOS) — no requiere API key. Producción (Render) no debe instalar
    este paquete; por eso NO está en requirements.txt, solo documentado ahí.

    Parámetros ignorados a propósito (mismo criterio que
    ``_build_anthropic_llm``, documentado aquí porque las razones difieren
    caso por caso):
    - ``temperature``: claude-sonnet-5 (familia 4.6+) rechaza con 400
      cualquier valor de sampling distinto del default — idéntica razón que
      el builder de Anthropic.
    - ``max_output_tokens``: el paquete lo implementa como truncación
      client-side a ``max_tokens*4`` caracteres, lo que rompería a mitad de
      camino el JSON estructurado que espera el analista v3.
    - ``api_key`` / ``base_url``: el paquete neutraliza cualquier
      ``ANTHROPIC_API_KEY`` heredada del entorno y usa el login OAuth del
      CLI — no hay endpoint que sobreescribir.

    ``timeout`` en ``ChatClaudeCli`` aborta la corrida completa del CLI
    (arranque del subproceso incluido), no un request HTTP: los 30 s de
    ``AI_TIMEOUT_SECONDS`` matarían al analista v3 antes de los 120 s con
    los que ``_generate_v3`` lo envuelve, así que se toma el mayor de ambos.
    """
    try:
        from langchain_claude_cli import ChatClaudeCli
    except ImportError as exc:
        raise ImportError(
            "RACE_AI_PROVIDER='claude-cli' requiere `pip install langchain-claude-cli` "
            "(solo uso local; no es dependencia del proyecto)."
        ) from exc

    run_timeout = max(timeout, float(settings.race_ai_v3_timeout_seconds))
    return ChatClaudeCli(model=model, timeout=run_timeout)


_LLM_BUILDERS: dict[str, Callable[..., Any]] = {
    "anthropic": _build_anthropic_llm,
    "google": _build_google_llm,
    "openai": _build_openai_llm,
    "claude-cli": _build_claude_cli_llm,
}


def _resolve_race_api_key(provider: str, explicit: Optional[str]) -> Optional[str]:
    """Resuelve la API key a usar, con fallback a ``AI_API_KEY``.

    Si ``RACE_AI_API_KEY`` está vacía y el proveedor de race/agents/
    coincide con el de app/services/ai/ (``AI_PROVIDER``), reutiliza
    ``AI_API_KEY`` — evita pedirle al usuario la misma key dos veces
    cuando ambos pipelines apuntan al mismo proveedor.
    """
    if explicit:
        return explicit
    if settings.race_ai_api_key:
        return settings.race_ai_api_key
    if provider == settings.ai_provider:
        return settings.ai_api_key or None
    return None


# Rol → nombre del atributo de Settings que trae el override de modelo
# por-rol, por stack. "chat" no tiene variable propia en ninguno de los dos
# stacks: siempre usa el modelo legacy (``race_ai_model``/``ai_model``) o el
# default del proveedor.
_ROLE_MODEL_SETTING_RACE: dict[str, str] = {
    "analyst": "race_ai_analyst_model",
    "critic": "race_ai_critic_model",
}

# Espejo del mapa de arriba para el stack app (feature 042, §1.1 del
# contrato) — deliberadamente NO reutiliza las variables RACE_AI_* (misma
# razón por la que RACE_AI_* hereda de AI_* y no al revés).
_ROLE_MODEL_SETTING_APP: dict[str, str] = {
    "analyst": "ai_analyst_model",
    "critic": "ai_critic_model",
}


def _resolve_role_model(role: Optional[str], setting_map: dict[str, str]) -> str:
    """Resuelve el override de modelo por-rol, o ``""`` si no aplica.

    Orden: ``Settings.<setting_map[role]>`` (si el rol tiene variable propia
    y no está vacía) → ``""`` (el caller cae al modelo legacy del stack y
    luego al default del proveedor).

    ``role=None`` (default) devuelve siempre ``""`` — preserva el
    comportamiento pre-feature-037 para los callers que NO pasan ``role``
    explícito: sin ``role`` no hay resolución por-rol, solo el modelo legacy
    del stack → default del proveedor.
    """
    if role is None:
        return ""
    setting_name = setting_map.get(role)
    if setting_name is None:
        return ""
    return getattr(settings, setting_name, "") or ""


def resolve_race_config(
    *,
    role: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    base_url: Optional[str] = None,
) -> ProviderConfig:
    """Stack race (``app/services/race/``). Reproduce el comportamiento
    exacto de hoy: ``RACE_AI_PROVIDER`` -> ``AI_PROVIDER`` (herencia de una
    sola vía, race PUEDE leer ``AI_*``), ``RACE_AI_ANALYST_MODEL``/
    ``RACE_AI_CRITIC_MODEL`` por rol, el fallback de ``_resolve_race_api_key``
    a ``AI_API_KEY`` solo cuando el proveedor resuelto coincide con
    ``AI_PROVIDER``, y ahora ``race_ai_temperature`` (feature 042, T017) en
    vez de la ``ai_temperature`` del stack app.
    """
    resolved_provider = (
        provider or settings.race_ai_provider or settings.ai_provider or "anthropic"
    ).lower()
    resolved_model = (
        model
        or _resolve_role_model(role, _ROLE_MODEL_SETTING_RACE)
        or settings.race_ai_model
        or DEFAULT_MODEL_BY_PROVIDER.get(resolved_provider, "")
    )
    resolved_temperature = (
        temperature if temperature is not None else settings.race_ai_temperature
    )
    return ProviderConfig(
        provider=resolved_provider,
        model=resolved_model,
        api_key=_resolve_race_api_key(resolved_provider, api_key),
        temperature=resolved_temperature,
        max_output_tokens=max_output_tokens or settings.ai_max_tokens,
        timeout=settings.ai_timeout_seconds,
        base_url=base_url or settings.race_ai_base_url,
    )


def resolve_app_config(
    *,
    role: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    base_url: Optional[str] = None,
) -> ProviderConfig:
    """Stack app (``app/services/ai/``, incluyendo ``ai/anthro/``). NUNCA lee
    una variable ``RACE_AI_*`` — regla de herencia de una sola vía
    (CLAUDE.md, ``config-env.md`` §0): solo race puede heredar de app, nunca
    al revés.
    """
    resolved_provider = (provider or settings.ai_provider or "anthropic").lower()
    resolved_model = (
        model
        or _resolve_role_model(role, _ROLE_MODEL_SETTING_APP)
        or settings.ai_model
        or DEFAULT_MODEL_BY_PROVIDER.get(resolved_provider, "")
    )
    resolved_temperature = (
        temperature if temperature is not None else settings.ai_temperature
    )
    return ProviderConfig(
        provider=resolved_provider,
        model=resolved_model,
        api_key=api_key or settings.ai_api_key or None,
        temperature=resolved_temperature,
        max_output_tokens=max_output_tokens or settings.ai_max_tokens,
        timeout=settings.ai_timeout_seconds,
        base_url=base_url or settings.ai_base_url,
    )


_CONFIG_RESOLVERS: dict[str, Callable[..., ProviderConfig]] = {
    "race": resolve_race_config,
    "app": resolve_app_config,
}


def build_chat_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    role: Optional[str] = None,
    *,
    stack: Literal["race", "app"] = "race",
):
    """Factory: construye el chat model LangChain del proveedor configurado.

    Args:
        provider: override explícito (``"anthropic"`` | ``"google"`` |
            ``"openai"`` | ``"claude-cli"``). Si ``None``, se resuelve del
            stack seleccionado (ver ``resolve_race_config``/
            ``resolve_app_config``).
        model: override explícito. Si ``None``, se resuelve por ``role``
            (ver :func:`resolve_configured_model`).
        base_url: override explícito del endpoint. Si ``None``, usa el
            setting del stack correspondiente. Solo lo consume el builder
            ``"openai"`` (Ollama u otro dialecto-OpenAI); el resto lo ignora.
        role: ``None`` (default, comportamiento legacy) | ``"analyst"`` |
            ``"critic"`` | ``"chat"`` — feature 037 (T101), extendido a
            ambos stacks en feature 042. Cuando se pasa ``"analyst"``/
            ``"critic"`` explícito, consulta primero la variable de modelo
            por-rol del stack (``RACE_AI_ANALYST_MODEL``/``RACE_AI_CRITIC_MODEL``
            para race, ``AI_ANALYST_MODEL``/``AI_CRITIC_MODEL`` para app)
            antes de caer al modelo legacy del stack. ``"chat"`` y ``None``
            se comportan igual (sin variable propia): van directo al modelo
            legacy → default del proveedor. ``max_output_tokens`` NO se
            ajusta automáticamente por rol aquí — el caller de analyst debe
            pasar 4096 explícito (ver ``race/agents/analyst.py``).
        stack: ``"race"`` (default — comportamiento preexistente sin cambios
            para todo call-site que no lo pase) | ``"app"``. Selecciona qué
            resolver de configuración aplica (feature 042, W1) — los
            builders concretos no conocen el stack, solo reciben valores ya
            resueltos vía :class:`ProviderConfig`.

    Raises:
        ValueError: proveedor no soportado (no debería ocurrir — el
            validator de ``Settings.race_ai_provider``/``Settings.ai_provider``
            ya lo bloquea salvo que se pase ``provider=`` explícito
            inválido).

    Nota (feature 042, T017 — sin cambio de comportamiento hoy): antes,
    ``_build_google_llm``/``_build_openai_llm`` caían a
    ``settings.ai_temperature`` cuando ``temperature`` era ``None``, sin
    importar si el caller era race/ o app/ (acoplamiento latente). Ahora
    ``resolve_race_config``/``resolve_app_config`` resuelven la temperatura
    efectiva por-stack (``race_ai_temperature``/``ai_temperature``) y se la
    pasan ya lista al builder, que nunca vuelve a leer ``settings``.
    ``RACE_AI_TEMPERATURE`` por defecto es 0.4 — idéntico al valor efectivo
    de hoy — así que este es un refactor sin cambio de comportamiento salvo
    para quien ya hubiera fijado ``AI_TEMPERATURE`` distinto de 0.4 sin
    fijar también ``RACE_AI_TEMPERATURE`` (caso ya señalado como bug en el
    comentario de ``Settings.race_ai_temperature``).
    """
    resolver = _CONFIG_RESOLVERS[stack]
    config = resolver(
        role=role,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        base_url=base_url,
    )
    builder = _LLM_BUILDERS.get(config.provider)
    if builder is None:
        raise ValueError(
            f"Proveedor LLM '{config.provider}' no soportado. "
            f"Permitidos: {sorted(_LLM_BUILDERS)}."
        )
    return builder(
        model=config.model,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        api_key=config.api_key,
        timeout=config.timeout,
        base_url=config.base_url,
    )


def resolve_configured_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    role: Optional[str] = None,
    *,
    stack: Literal["race", "app"] = "race",
) -> str:
    """Resuelve el ``model_id`` configurado, SIN instanciar el cliente LLM.

    Misma resolución de ``model`` que usa internamente :func:`build_chat_llm`
    para el stack seleccionado (explícito → variable de modelo por-rol del
    stack → modelo legacy del stack → default del proveedor en
    :data:`DEFAULT_MODEL_BY_PROVIDER`), expuesta aparte para quien necesite
    *saber qué modelo se usaría* sin pagar el costo de construir el cliente.

    Feature 036 (T060): ``persist_insight`` la usa para registrar en
    ``AthleteAiInsight.model`` el modelo que realmente generó el análisis.
    Antes de este helper, ese nodo tenía su propio string fijo
    (``"gemini-2.5-flash-lite"``) que quedaba desactualizado cada vez que el
    proveedor/modelo configurado cambiaba — cada insight persistido
    misreportaba su propia procedencia. Con este helper hay un único lugar
    que sabe resolver "el modelo configurado hoy".

    Feature 037 (T101): ``role`` (``"analyst"`` | ``"critic"`` | ``"chat"``)
    permite resolver el modelo específico de cada agente cuando corren con
    modelos distintos (analyst fuerte, critic barato).

    Feature 042 (W1): ``stack`` (``"race"`` default | ``"app"``) selecciona
    qué precedence chain aplica — ver :func:`resolve_race_config`/
    :func:`resolve_app_config`.

    A diferencia de ``build_chat_llm``, nunca lanza por proveedor
    desconocido: degrada a la entrada ``"anthropic"`` de
    :data:`DEFAULT_MODEL_BY_PROVIDER` sólo para tener *algún* nombre que
    persistir — la validación real de proveedores soportados vive en
    ``Settings.race_ai_provider``/``Settings.ai_provider`` y en
    ``build_chat_llm``.
    """
    if stack == "app":
        resolved_provider = (provider or settings.ai_provider or "anthropic").lower()
        role_model = _resolve_role_model(role, _ROLE_MODEL_SETTING_APP)
        legacy_model = settings.ai_model
    else:
        resolved_provider = (
            provider or settings.race_ai_provider or settings.ai_provider or "anthropic"
        ).lower()
        role_model = _resolve_role_model(role, _ROLE_MODEL_SETTING_RACE)
        legacy_model = settings.race_ai_model
    default_model = DEFAULT_MODEL_BY_PROVIDER.get(
        resolved_provider, DEFAULT_MODEL_BY_PROVIDER["anthropic"]
    )
    return model or role_model or legacy_model or default_model
