"""Adapter del SDK oficial de OpenAI (y cualquier backend dialecto-OpenAI /v1).

El import del SDK es lazy dentro de `__init__` para que la capa entera
funcione sin tener `openai` instalado mientras `AI_PROVIDER` sea otro.
Cumple SRP: solo traduce entre `LLMRequest`/`LLMResponse` y la API real.

Uso principal: habilitar Ollama en modo config-only. Ollama expone un
endpoint compatible con OpenAI Chat Completions en `/v1` — basta con
apuntar `AI_BASE_URL=http://host.docker.internal:11434/v1` (Docker →
host) y usar una `AI_API_KEY` dummy (Ollama no valida la key). Nada de
esto está hardcodeado aquí: el provider es genérico y sirve igual para
OpenAI real.
"""

from __future__ import annotations

import json
import time

from app.services.ai.errors import LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider


class OpenAIProvider(_BaseProvider):
    """Provider para `gpt-*` (u otro modelo dialecto-OpenAI, ej. Ollama)
    usando `openai.AsyncOpenAI` + Chat Completions."""

    name = "openai"

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
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMUnavailableError(
                "Paquete 'openai' no instalado. "
                "Añade 'openai>=1.0,<3' a requirements.txt."
            ) from exc

        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        kwargs = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # Importación lazy para mapear errores del SDK a nuestra jerarquía.
        import openai

        # A diferencia de AnthropicProvider, aquí SÍ se reenvía `temperature`
        # — Chat Completions (OpenAI y dialectos como Ollama) la aceptan sin
        # restricciones especiales.
        messages = [{"role": "system", "content": req.system}]
        messages.extend(
            {"role": m.role, "content": m.content} for m in req.messages
        )

        t0 = time.perf_counter()
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=req.max_tokens or self._max_tokens,
                temperature=(
                    req.temperature if req.temperature is not None
                    else self._temperature
                ),
                messages=messages,
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMUnavailableError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        text = resp.choices[0].message.content or ""
        usage = TokenUsage(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
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
        # sustituible por `response_format={"type": "json_object"}` del SDK
        # (no todos los backends dialecto-OpenAI —ej. Ollama— lo soportan
        # de forma consistente, por eso se mantiene el approach por prompt).
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
