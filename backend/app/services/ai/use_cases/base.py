"""BaseUseCase — orquesta provider, registry, context builder y guardrails.

Cada `UseCase` es una clase pequeña con `run()`. Recibe sus colaboradores
por composición; esto deja el código fácil de testear con `FakeLLMProvider`
y permite cambiar de proveedor sin tocar el caso de uso (DIP).
"""

from __future__ import annotations

from app.services.ai.guardrails import Guardrails
from app.services.ai.models import LLMMessage, LLMRequest, LLMResponse
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider


class BaseUseCase:
    """Composición común a todos los use cases."""

    template_id: str = ""

    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
        guardrails: Guardrails | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._guardrails = guardrails

    async def _ask(self, context: dict) -> LLMResponse:
        """Renderiza la plantilla, hace la llamada y devuelve la respuesta cruda."""
        if not self.template_id:
            raise NotImplementedError(
                "Cada subclase debe declarar `template_id`."
            )
        user_msg = self._registry.render(self.template_id, context)
        request = LLMRequest(
            system=self._registry.system_prompt(),
            messages=(LLMMessage(role="user", content=user_msg),),
        )
        return await self._provider.complete(request)

    def _scrub(self, text: str) -> str:
        if self._guardrails is None:
            return text
        return self._guardrails.scrub(text)
