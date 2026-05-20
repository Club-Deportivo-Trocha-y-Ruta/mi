"""Fakes compartidos para tests de la capa agéntica (Fase 3).

Diseño:
- :class:`FakeChatLLM` — stub mínimo de un chat model de LangChain.
  Expone ``ainvoke`` (async) que retorna respuestas pre-grabadas y
  ``bind_tools`` que retorna ``self`` (compatibilidad con el chat agent).
- :class:`StubAIMessage` — emula ``AIMessage`` con ``content`` +
  ``usage_metadata`` opcional + ``tool_calls``.
- :func:`make_principles` — genera lista de Citation reales con
  ``chunk_id`` controlables para verificar trazabilidad.

Convención: NINGÚN test toca red. Si un test parece requerir Gemini
real, marcarlo con ``@pytest.mark.integration`` y skiparlo cuando
``AI_API_KEY`` no esté.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable

import pytest

from app.services.race.rag.retriever import Citation


# ---------------------------------------------------------------------------
# Stub AIMessage-like
# ---------------------------------------------------------------------------


@dataclass
class StubAIMessage:
    """Sustituye ``AIMessage`` en respuestas de FakeChatLLM."""

    content: str
    usage_metadata: dict[str, int] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class FakeChatLLM:
    """Stub de un chat model LangChain.

    Respuestas se entregan en orden — si las llamadas exceden el
    iterable, lanza ``RuntimeError`` (catch bugs de mal mockeo).

    ``bind_tools`` retorna ``self`` — el FakeLLM ignora tools (los tests
    del chat agent verifican tool execution por separado vía
    ``tool_calls`` en la respuesta).
    """

    def __init__(self, responses: Iterable[StubAIMessage]):
        self._responses = list(responses)
        self._cursor = 0
        self.calls: list[list[Any]] = []

    def bind_tools(self, tools: list[Any]) -> "FakeChatLLM":
        return self

    async def ainvoke(self, messages: list[Any], **kwargs: Any) -> StubAIMessage:
        # Sin latencia simulada explícita — el test pasa real time.monotonic()
        # rápido. Si necesitas latency_ms > 0, usa await asyncio.sleep(0.001).
        await asyncio.sleep(0.001)
        self.calls.append(list(messages))
        if self._cursor >= len(self._responses):
            raise RuntimeError(
                f"FakeChatLLM: respuestas agotadas (call #{self._cursor + 1})"
            )
        resp = self._responses[self._cursor]
        self._cursor += 1
        return resp


@pytest.fixture
def make_principles():
    """Genera lista de :class:`Citation` con ids controlables."""

    def _factory(n: int = 3, prefix: str = "chunk") -> list[Citation]:
        return [
            Citation(
                chunk_id=f"{prefix}_{i:02d}",
                source="docs/01-marco-teorico.md",
                content=f"Principio {i}: contenido de prueba.",
                score=0.9 - i * 0.05,
                metadata={"h1": "Capítulo", "h2": f"Sección {i}"},
            )
            for i in range(1, n + 1)
        ]

    return _factory
