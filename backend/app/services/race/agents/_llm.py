"""Shim de compatibilidad — la implementación real vive en
``app.services.llm.factory`` y ``app.services.llm.calls`` (feature 042, W1,
``contracts/llm-transport.md`` §1-2).

La factoría LLM (``build_chat_llm`` y sus builders concretos), la resolución
de config por-rol y la invocación normalizada (``call_llm``,
``extract_text``, ``extract_usage``, ``LLMCallResult``) se extrajeron a
``app/services/llm/`` para que ``app/services/ai/`` (detrás de
``AI_USE_LANGCHAIN``) también pueda construir un chat model LangChain sin
depender del paquete ``race``. Este módulo se conserva como shim porque
~30 tests de ``tests/services/race/`` importan y algunos monkeypatchean
símbolos por esta ruta de módulo exacta
(``app.services.race.agents._llm.<símbolo>``), y varios módulos de
producción (``analyst.py``, ``critic.py``, ``chat.py``, ``eval/judge.py``,
``race/ai/nodes/persist_insight.py``) los importan igual. Se retira en una
feature futura, nunca en esta (``plan.md`` Complexity Tracking).

Todo lo reexportado aquí son funciones puras y estructuras de datos
inmutables (o diccionarios de despacho que ningún test/caller reasigna vía
esta ruta de módulo — verificado con
``grep -rn "_llm" backend/tests backend/app`` antes de reducir este
archivo): ninguna otra función de este módulo llama internamente a
``build_chat_llm``/``call_llm``/etc., así que un ``from ... import ...``
directo basta — no hay indirección de módulo que preservar (a diferencia
del cliente Langfuse singleton de ``race/observability.py``, que sí necesita
un ``ModuleType`` delegado por su estado mutable de proceso).

Todos los callers de este módulo (incluidos los ~30 tests) invocan estos
símbolos con el comportamiento **race** de siempre — ninguno pasa
``stack="app"`` — así que el default ``stack="race"`` de
``app.services.llm.factory``/``app.services.llm.calls`` reproduce el
comportamiento preexistente sin cambios.

Excepción: ``_resolve_role_model`` cambió de firma en la factoría
compartida (ahora recibe también el mapa rol→setting, para servir a los dos
stacks). Ningún caller ni test invoca ``_resolve_role_model`` a través de
esta ruta de módulo hoy (verificado con el mismo grep), pero se conserva un
wrapper con la firma original de 1 argumento — fijada al mapa de roles de
race — por si algún código futuro la resuelve dinámicamente por nombre de
módulo.
"""

from __future__ import annotations

from typing import Optional

from app.services.llm.calls import (  # noqa: F401 — reexport público
    LLMCallResult,
    call_llm,
    extract_text,
    extract_usage,
)
from app.services.llm.factory import (  # noqa: F401 — reexport público
    DEFAULT_MODEL_BY_PROVIDER,
    _build_anthropic_llm,
    _build_claude_cli_llm,
    _build_google_llm,
    _build_openai_llm,
    _LLM_BUILDERS,
    _resolve_race_api_key,
    _ROLE_MODEL_SETTING_RACE,
    build_chat_llm,
    resolve_configured_model,
)
from app.services.llm.factory import _resolve_role_model as _resolve_role_model_for_stack


def _resolve_role_model(role: Optional[str]) -> str:
    """Compat: firma original de 1 argumento, fijada al mapa de roles race.

    Ver docstring del módulo — nada la invoca por esta ruta hoy; se conserva
    por si algún código futuro la resuelve dinámicamente.
    """
    return _resolve_role_model_for_stack(role, _ROLE_MODEL_SETTING_RACE)


__all__ = [
    "DEFAULT_MODEL_BY_PROVIDER",
    "LLMCallResult",
    "_LLM_BUILDERS",
    "_build_anthropic_llm",
    "_build_claude_cli_llm",
    "_build_google_llm",
    "_build_openai_llm",
    "_resolve_race_api_key",
    "_resolve_role_model",
    "build_chat_llm",
    "call_llm",
    "extract_text",
    "extract_usage",
    "resolve_configured_model",
]
