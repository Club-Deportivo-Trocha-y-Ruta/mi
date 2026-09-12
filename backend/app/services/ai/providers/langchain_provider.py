"""Adapter LangChain sobre el Protocol `LLMProvider` (feature 042, T019).

Traduce `LLMRequest`/`LLMResponse` hacia/desde un `BaseChatModel` de
LangChain construido por la factoría compartida
(`app.services.llm.factory.build_chat_llm(stack="app", ...)`), para que los
cinco casos de uso puenteados (clarify/draft de sesión, reporte mensual,
bloques del reporte mensual, newsletter v2) puedan correr detrás de
`AI_USE_LANGCHAIN=true` sin que su semántica cambie ni un bit — mismos
campos poblados en `LLMResponse`, mismos atributos `name`/`model` que los
providers nativos (`contracts/llm-transport.md` §3, FR-025, SC-006).

No confundir con `app/services/ai/anthro/{analyst,critic}.py`: ese pipeline
nuevo llama directo a `app/services/llm/calls.py::call_llm`, sin pasar por
este adapter — ver §0 del contrato. Este módulo es exclusivamente el puente
para los cinco casos de uso legacy.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from app.services.ai.errors import LLMSchemaError, LLMTimeoutError, LLMUnavailableError
from app.services.ai.models import LLMRequest, LLMResponse, TokenUsage
from app.services.ai.providers.base import _BaseProvider
from app.services.llm.calls import extract_text, extract_usage

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class LangChainProvider(_BaseProvider):
    """Implementa `LLMProvider` (`ChatCompletion` + `StructuredOutput`) sobre
    un `BaseChatModel` de LangChain.

    Una instancia por proceso, construida una sola vez por
    `create_llm_provider()` — misma disciplina de singleton que el resto de
    entradas en `app/services/ai/factory.py::_PROVIDERS`.
    """

    def __init__(self, chat_model: "BaseChatModel", *, name: str, model: str) -> None:
        self._chat_model = chat_model
        self.name = name
        self.model = model

    def _to_messages(self, req: LLMRequest) -> list[Any]:
        """Traduce `LLMRequest.system` + `.messages` a mensajes LangChain,
        preservando el orden: `SystemMessage` primero, luego un
        `HumanMessage`/`AIMessage` por cada turno.

        A diferencia de `app.services.llm.calls::call_llm` (que colapsa todo
        en un único `HumanMessage` porque el pipeline de race/ no distingue
        system de human), aquí SÍ usamos `SystemMessage` — los cinco casos de
        uso puenteados ya distinguen system de human hoy y ese comportamiento
        no puede cambiar con la migración de transporte.
        """
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages: list[Any] = [SystemMessage(content=req.system)]
        for m in req.messages:
            if m.role == "assistant":
                messages.append(AIMessage(content=m.content))
            else:
                messages.append(HumanMessage(content=m.content))
        return messages

    async def complete(self, req: LLMRequest) -> LLMResponse:
        from langchain_core.exceptions import ModelError, ModelTimeoutError

        messages = self._to_messages(req)
        t0 = time.perf_counter()
        try:
            # Sin `config=`: los cinco casos de uso puenteados no tienen un
            # scope de Langfuse por-request que enhebrar hoy (a diferencia
            # del pipeline de antropometría, que sí pasa `config` explícito
            # en cada paso — ver `contracts/llm-transport.md` §3).
            response = await self._chat_model.ainvoke(messages)
        except ModelTimeoutError as exc:
            # Subclase de ModelError — debe capturarse antes que el genérico.
            raise LLMTimeoutError(str(exc)) from exc
        except ModelError as exc:
            raise LLMUnavailableError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — nunca dejar escapar el SDK crudo.
            raise LLMUnavailableError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        text = extract_text(response)
        prompt_text = req.system + "".join(m.content for m in req.messages)
        tokens_in, tokens_out = extract_usage(response, prompt_text, text)

        result = LLMResponse(
            text=text,
            usage=TokenUsage(input_tokens=tokens_in, output_tokens=tokens_out),
            model=self.model,
            provider=self.name,
            latency_ms=elapsed_ms,
        )
        self._log_response(result)
        return result

    async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
        # Misma estrategia MVP que los providers nativos (JSON-en-el-prompt +
        # validación) — NO `with_structured_output()` de LangChain: dos de
        # los cuatro proveedores soportados (claude-cli, openai vía Ollama)
        # no tienen soporte confiable de tool-calling (spec.md Assumptions;
        # `contracts/llm-transport.md` §3).
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
