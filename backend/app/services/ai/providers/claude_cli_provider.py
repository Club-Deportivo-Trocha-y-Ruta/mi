"""Adapter del Claude Code CLI (suscripción del desarrollador) — SOLO local.

Reusa el mismo paquete que ``app/services/race/agents/_llm.py::_build_claude_cli_llm``
(``langchain_claude_cli.ChatClaudeCli``) para no duplicar la lógica de invocar
el CLI, pero traduce entre ``LLMRequest``/``LLMResponse`` y LangChain en vez de
exponer un ``BaseChatModel`` — este stack (``app/services/ai/``) es Protocol-
based, no LangChain-based.

Import del paquete lazy: no es dependencia dura del proyecto (no está en
requirements.txt — ver comentario ahí) y el resto de la capa debe seguir
funcionando sin él mientras ``AI_PROVIDER`` sea otro.
"""

from __future__ import annotations

import json
import time

from app.services.ai.errors import LLMSchemaError, LLMUnavailableError
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider


class ClaudeCliProvider(_BaseProvider):
    """Provider SOLO local: Claude Code CLI vía la suscripción del desarrollador.

    Los términos de consumo de Anthropic prohíben usar una suscripción
    personal para servir usuarios finales — nunca activar en Render (mismo
    criterio que el builder gemelo de ``race/agents/_llm.py``).
    """

    name = "claude-cli"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        max_tokens: int = 1024,
        temperature: float = 0.4,  # aceptado por paridad de interfaz; ignorado — ver abajo
        base_url: str | None = None,  # aceptado por paridad de interfaz; ignorado — ver abajo
    ) -> None:
        try:
            from langchain_claude_cli import ChatClaudeCli
        except ImportError as exc:
            raise LLMUnavailableError(
                "Paquete 'langchain-claude-cli' no instalado. SOLO uso local: "
                "`pip install langchain-claude-cli` (requiere `claude` logueado "
                "en la máquina — ver `claude setup-token` para contenedores)."
            ) from exc

        self.model = model
        self._max_tokens = max_tokens
        # api_key y base_url se ignoran a propósito: el paquete neutraliza
        # cualquier ANTHROPIC_API_KEY heredada y usa el login OAuth del CLI,
        # no hay endpoint que sobreescribir (idéntico a _build_claude_cli_llm).
        self._client = ChatClaudeCli(model=model, timeout=timeout)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        role_to_message = {"user": HumanMessage, "assistant": AIMessage}
        messages = [SystemMessage(content=req.system)] + [
            role_to_message[m.role](content=m.content) for m in req.messages
        ]

        t0 = time.perf_counter()
        try:
            response = await self._client.ainvoke(messages)
        except Exception as exc:  # el paquete tipa sus propios errores (ClaudeCliError)
            raise LLMUnavailableError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        content = response.content
        text = content if isinstance(content, str) else str(content)
        usage_meta = getattr(response, "usage_metadata", None) or {}
        usage = TokenUsage(
            input_tokens=int(usage_meta.get("input_tokens", 0) or 0),
            output_tokens=int(usage_meta.get("output_tokens", 0) or 0),
        )
        result = LLMResponse(
            text=text,
            usage=usage,
            model=self.model,
            provider=self.name,
            latency_ms=elapsed_ms,
        )
        self._log_response(result)
        return result

    async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
        # Misma estrategia por prompt que el resto de providers del stack
        # (ver AnthropicProvider/OpenAIProvider) — consistencia entre
        # providers por encima de usar el structured-output nativo del CLI.
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
            raise LLMSchemaError("Respuesta del modelo no es JSON válido.") from exc
