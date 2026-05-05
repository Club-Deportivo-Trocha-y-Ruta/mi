"""Datos compartidos por la capa de IA.

Las dataclasses de este módulo viajan entre los `UseCase` y los `Provider`,
de modo que ningún caso de uso depende del SDK concreto de un proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

LLMRole = Literal["user", "assistant"]
"""Roles soportados en mensajes de chat. El `system` se pasa por separado
porque la mayoría de SDKs lo expone como parámetro de alto nivel."""


@dataclass(frozen=True)
class LLMMessage:
    """Un turno de conversación (rol + contenido)."""

    role: LLMRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError(
                f"LLMMessage.role inválido: {self.role!r}. "
                "Debe ser 'user' o 'assistant'."
            )
        if not self.content or not self.content.strip():
            raise ValueError("LLMMessage.content no puede estar vacío.")


@dataclass(frozen=True)
class LLMRequest:
    """Petición independiente del proveedor."""

    system: str
    messages: tuple[LLMMessage, ...]
    max_tokens: int | None = None
    temperature: float | None = None

    def __post_init__(self) -> None:
        if not self.system or not self.system.strip():
            raise ValueError("LLMRequest.system es obligatorio.")
        if not self.messages:
            raise ValueError("LLMRequest.messages no puede estar vacío.")


@dataclass(frozen=True)
class TokenUsage:
    """Conteo de tokens reportado por el proveedor."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMResponse:
    """Respuesta normalizada de cualquier proveedor."""

    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    provider: str = ""
    latency_ms: int = 0
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
