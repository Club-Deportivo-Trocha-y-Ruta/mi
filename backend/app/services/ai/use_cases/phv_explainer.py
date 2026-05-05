"""Use case: explicar el resultado PHV a los padres.

Recibe un Athlete + última medición + opcionalmente historial. Devuelve un
dict con texto saneado y metadatos del modelo (para la response del router).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.services.ai.context_builders import AthleteAIContextBuilder
from app.services.ai.guardrails import Guardrails
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.protocols import LLMProvider
from app.services.ai.use_cases.base import BaseUseCase

if TYPE_CHECKING:
    from app.models.anthropometry import AnthropometricRecord
    from app.models.athlete import Athlete


@dataclass(frozen=True)
class PHVExplanation:
    text: str
    model: str
    provider: str
    generated_at: datetime
    age_group: str
    maturation_status: str


class PHVExplainerUseCase(BaseUseCase):
    """Caso de uso `phv_explainer`."""

    template_id = "phv_explainer"

    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
        context_builder: AthleteAIContextBuilder | None = None,
    ) -> None:
        # Guardrails por edad: instanciaremos uno específico al construir el
        # contexto (ver `run`). El guardrail por defecto del padre cubre las
        # reglas globales como cero suplementos.
        super().__init__(provider, registry, guardrails=None)
        self._context_builder = context_builder or AthleteAIContextBuilder()

    async def run(
        self,
        athlete: "Athlete",
        latest_record: "AnthropometricRecord",
        history: list["AnthropometricRecord"] | None = None,
    ) -> PHVExplanation:
        if latest_record is None:
            raise ValueError(
                "PHVExplainerUseCase requiere al menos una medición antropométrica."
            )

        context = self._context_builder.build(
            athlete, latest_record, history=history
        )
        # Guardrails específicos al grupo de edad para cubrir reglas como
        # "sin potenciómetro para 10-12".
        self._guardrails = Guardrails(age_group=context.get("age_group"))

        response = await self._ask(context)
        sanitized = self._scrub(response.text)

        return PHVExplanation(
            text=sanitized,
            model=response.model or self._provider.model,
            provider=response.provider or self._provider.name,
            generated_at=response.generated_at,
            age_group=context["age_group"],
            maturation_status=context.get("maturation_status", ""),
        )
