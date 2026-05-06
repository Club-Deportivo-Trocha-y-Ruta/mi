"""Funciones compartidas por providers concretos.

`_BaseProvider` aporta logging estructurado de tokens/latencia.
Cada subclase implementa la integración con su SDK; este módulo NO importa
SDKs concretos para que `from app.services.ai.providers.base import …`
no arrastre dependencias opcionales (anthropic / openai / google).
"""

from __future__ import annotations

import logging

from app.services.ai.models import LLMResponse

logger = logging.getLogger(__name__)


class _BaseProvider:
    """Mixin con utilidades comunes a los providers."""

    name: str = "base"
    model: str = ""

    def _log_response(self, response: LLMResponse) -> None:
        """Loguea telemetría sin emitir contenido sensible.

        Solo emite proveedor, modelo, tokens y latencia. Nunca el texto del
        prompt o la respuesta — eso requiere `AI_LOG_PROMPTS=true`,
        que está prohibido en producción por validador de config.
        """
        logger.info(
            "ai.complete provider=%s model=%s in=%d out=%d ms=%d",
            response.provider or self.name,
            response.model or self.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.latency_ms,
        )
