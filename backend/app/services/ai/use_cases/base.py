"""BaseUseCase — orquesta provider, registry, context builder y guardrails.

Cada `UseCase` es una clase pequeña con `run()`. Recibe sus colaboradores
por composición; esto deja el código fácil de testear con `FakeLLMProvider`
y permite cambiar de proveedor sin tocar el caso de uso (DIP).

Concurrencia: las instancias pueden compartirse entre requests (FastAPI DI
no garantiza una nueva instancia por request, y el provider/registry sí son
singletons vía `lru_cache`). Por eso `_scrub` recibe los guardrails como
parámetro local en lugar de leerlos de un atributo de instancia: así dos
requests concurrentes no pueden pisarse mutuamente sus reglas de saneo
(p. ej., un padre de 10-12 con reglas anti-potenciómetro frente a un padre
de 13-15 sin ellas).
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
        # Guardrails por defecto cuando el use case no depende del request.
        # Cada subclase que necesita reglas dinámicas debe construir un
        # `Guardrails` local en `run()` y pasarlo explícitamente a `_scrub`.
        self._default_guardrails = guardrails

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

    def _scrub(self, text: str, guardrails: Guardrails | None = None) -> str:
        """Sanea `text` con los `guardrails` recibidos.

        Si el caller no pasa guardrails se usa `_default_guardrails`. Si ese
        también es `None`, el texto se devuelve sin tocar. Pasar siempre los
        guardrails como argumento es la API recomendada para evitar race
        conditions entre requests concurrentes que compartan instancia.
        """
        effective = guardrails if guardrails is not None else self._default_guardrails
        if effective is None:
            return text
        return effective.scrub(text)
