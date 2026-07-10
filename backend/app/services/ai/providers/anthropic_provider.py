"""Adapter del SDK oficial de Anthropic.

El import del SDK es lazy dentro de `__init__` para que la capa entera
funcione sin tener `anthropic` instalado mientras `AI_PROVIDER` sea otro.
Cumple SRP: solo traduce entre `LLMRequest`/`LLMResponse` y la API real.
"""

from __future__ import annotations

import json
import time

from app.services.ai.errors import LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider


class AnthropicProvider(_BaseProvider):
    """Provider para `claude-*` usando `anthropic.AsyncAnthropic`."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_tokens: int = 1024,
        temperature: float = 0.4,  # aceptado por paridad de interfaz con
        # otros providers (ver factory.py); no se reenvía al SDK — ver
        # comentario en `complete()`.
        base_url: str | None = None,
    ) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise LLMUnavailableError(
                "Paquete 'anthropic' no instalado. "
                "Añade 'anthropic>=0.40' a requirements.txt."
            ) from exc

        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        kwargs = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # Importación lazy para mapear errores del SDK a nuestra jerarquía.
        import anthropic

        t0 = time.perf_counter()
        try:
            # Nota: `temperature` NO se envía. En claude-sonnet-5 (y el resto
            # de la familia 4.6+) el SDK rechaza con 400 cualquier valor de
            # temperature/top_p/top_k distinto del default — se omite el
            # parámetro entero en vez de intentar pasar `self._temperature`.
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=req.max_tokens or self._max_tokens,
                system=req.system,
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
            )
        except anthropic.APITimeoutError as exc:  # type: ignore[attr-defined]
            raise LLMTimeoutError(str(exc)) from exc
        except anthropic.APIError as exc:  # type: ignore[attr-defined]
            raise LLMUnavailableError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = TokenUsage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
        )
        response = LLMResponse(
            text=text,
            usage=usage,
            model=self.model,
            provider=self.name,
            latency_ms=elapsed_ms,
        )
        self._log_response(response)
        return response

    async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
        # Estrategia simple para MVP: añadimos al system una instrucción
        # explícita de devolver JSON conforme al schema. Para producción
        # sustituible por tool-use estructurado del SDK sin tocar consumidores.
        json_system = (
            f"{req.system}\n\nDebes responder ÚNICAMENTE con JSON válido "
            f"que cumpla el siguiente schema (sin comentarios, sin texto extra):\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        json_req = LLMRequest(
            system=json_system,
            messages=req.messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
        resp = await self.complete(json_req)
        try:
            return json.loads(resp.text)
        except json.JSONDecodeError as exc:
            from app.services.ai.errors import LLMSchemaError

            raise LLMSchemaError(
                "Respuesta del modelo no es JSON válido."
            ) from exc
