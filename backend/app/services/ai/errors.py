"""Jerarquía de errores de la capa de IA.

Los routers traducen estos errores a HTTP (`503` para `LLMUnavailableError`
y `LLMTimeoutError`, `502` para `LLMSchemaError`, `500` para `LLMConfigError`).
Todos descienden de `LLMError` para que un `except` único cubra el módulo.
"""

from __future__ import annotations


class LLMError(Exception):
    """Raíz de la jerarquía. Capturar esta clase neutraliza la capa entera."""


class LLMConfigError(LLMError):
    """Configuración inválida (provider desconocido, api_key faltante, …)."""


class LLMUnavailableError(LLMError):
    """El proveedor falló o `AI_ENABLED=false`."""


class LLMTimeoutError(LLMUnavailableError):
    """Timeout específico — subclase de Unavailable para que un único handler los agrupe."""


class LLMSchemaError(LLMError):
    """La respuesta no cumplió un schema o falló el guardrail post-procesamiento."""
