"""Provider determinístico para tests y modo `AI_ENABLED=false`.

`FakeLLMProvider` registra el último request recibido (`last_request`) para
que los tests puedan inspeccionar qué se envió al "modelo" sin hacer red.
También sirve como fallback seguro cuando la capa de IA está apagada.
"""

from __future__ import annotations

import json
import time

from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider


class FakeLLMProvider(_BaseProvider):
    """Implementación trivial del Protocol `LLMProvider`.

    Args:
        canned: Texto que devolverá `complete()`. Si es None se construye
            uno determinístico a partir del último mensaje del request.
        canned_json: Dict que devolverá `complete_json()`.
        reason: Etiqueta opcional (ej: "AI_ENABLED=false") que se incluye
            en logs para distinguir usos del Fake en producción.
    """

    name = "fake"

    def __init__(
        self,
        *,
        canned: str | None = None,
        canned_json: dict | None = None,
        reason: str = "",
        model: str = "fake-model",
    ) -> None:
        self.model = model
        self._canned = canned
        self._canned_json = canned_json or {"ok": True}
        self._reason = reason
        # Inspeccionable por los tests:
        self.last_request: LLMRequest | None = None
        self.call_count: int = 0

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.last_request = req
        self.call_count += 1
        text = self._canned if self._canned is not None else (
            f"[fake] {req.messages[-1].content[:80]}"
        )
        usage = TokenUsage(
            input_tokens=sum(len(m.content) for m in req.messages),
            output_tokens=len(text),
        )
        response = LLMResponse(
            text=text,
            usage=usage,
            model=self.model,
            provider=self.name,
            latency_ms=0,
        )
        self._log_response(response)
        return response

    async def complete_json(
        self, req: LLMRequest, schema: dict
    ) -> dict:
        self.last_request = req
        self.call_count += 1
        # Si el caller pasó un dict cannedo lo devuelve. Si no, intenta
        # construir un objeto vacío con las claves de top-level del schema.
        if self._canned_json is not None:
            return dict(self._canned_json)
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        return {key: None for key in props}
