"""Protocolos (Strategy + ISP).

`LLMProvider` es la unión de capacidades. Los `UseCase` reciben este Protocol
por composición; nunca importan SDKs concretos. Cumple Dependency Inversion.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.ai.models import LLMRequest, LLMResponse


@runtime_checkable
class ChatCompletion(Protocol):
    """Capacidad mínima: completar un prompt y devolver texto."""

    name: str
    model: str

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class StructuredOutput(Protocol):
    """Capacidad opcional: obtener JSON conforme a un schema."""

    async def complete_json(
        self, req: LLMRequest, schema: dict
    ) -> dict: ...


class LLMProvider(ChatCompletion, StructuredOutput, Protocol):
    """Composición ISP — proveedor que cubre las capacidades requeridas hoy.

    Mantenemos un Protocol único exportable para facilitar la inyección
    en los `UseCase` y en `dependencies.py`. Si en el futuro un proveedor
    no soporta `StructuredOutput`, se puede aceptar solo `ChatCompletion`
    en use cases que no lo requieran (ISP).
    """
