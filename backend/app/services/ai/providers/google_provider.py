"""Adapter del SDK oficial de Google Gen AI (Gemini Developer API).

El import del SDK es lazy dentro de `__init__` para que la capa entera
funcione sin tener `google-genai` instalado mientras `AI_PROVIDER` sea otro.
Cumple SRP: solo traduce entre `LLMRequest`/`LLMResponse` y la API real.

Usa el SDK unificado `google-genai` (no el deprecado `google-generativeai`).
"""

from __future__ import annotations

import json
import time

from app.services.ai.errors import LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider


class GoogleProvider(_BaseProvider):
    """Provider para `gemini-*` usando `google.genai.Client` (modo async)."""

    name = "google"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        base_url: str | None = None,
    ) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMUnavailableError(
                "Paquete 'google-genai' no instalado. "
                "Añade 'google-genai>=1.0' a requirements.txt."
            ) from exc

        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        # http_options.timeout va en milisegundos.
        http_options = types.HttpOptions(timeout=int(timeout * 1000))
        if base_url:
            http_options = types.HttpOptions(
                timeout=int(timeout * 1000), base_url=base_url
            )
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # Importación lazy para mapear errores del SDK a nuestra jerarquía.
        import httpx
        from google.genai import errors, types

        # Gemini usa el role "model" para respuestas previas del asistente.
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in req.messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=req.system,
            max_output_tokens=req.max_tokens or self._max_tokens,
            temperature=(
                req.temperature if req.temperature is not None
                else self._temperature
            ),
        )

        t0 = time.perf_counter()
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except errors.APIError as exc:
            raise LLMUnavailableError(
                f"Gemini API error {getattr(exc, 'code', '?')}: "
                f"{getattr(exc, 'message', str(exc))}"
            ) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        text = resp.text or ""
        # Si Gemini bloqueó por safety o no devolvió texto, exponemos el motivo.
        if not text:
            cand = resp.candidates[0] if resp.candidates else None
            finish = getattr(cand, "finish_reason", None)
            block = getattr(
                getattr(resp, "prompt_feedback", None), "block_reason", None
            )
            raise LLMUnavailableError(
                f"Gemini devolvió respuesta vacía (finish={finish}, block={block})."
            )

        usage_meta = getattr(resp, "usage_metadata", None)
        usage = TokenUsage(
            input_tokens=getattr(usage_meta, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage_meta, "candidates_token_count", 0) or 0,
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
        # sustituible por response_mime_type='application/json' del SDK.
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
