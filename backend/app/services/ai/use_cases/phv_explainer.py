"""Use case: explicar el resultado PHV a los padres.

Recibe un Athlete + última medición + opcionalmente historial. Devuelve un
dict con texto saneado y metadatos del modelo (para la response del router).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from app.services.ai.context_builders import AthleteAIContextBuilder
from app.services.ai.guardrails import Guardrails
from app.services.ai.models import LLMMessage, LLMRequest, LLMResponse
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

    # Feature 040 (R-12): la explicación PHV tiene dos variantes de
    # plantilla según quién la lee. La familia usa `template_id` (el
    # default de la clase, sin cambios); el entrenador usa
    # `phv_explanation_coach` (números explícitos de velocidad/meses que
    # la versión familiar omite a propósito). El caché las distingue por
    # `use_case` en el router (`phv_explainer` vs `phv_explanation_coach`).
    _TEMPLATE_ID_BY_AUDIENCE: dict[str, str] = {
        "family": "phv_explainer",
        "coach": "phv_explanation_coach",
    }

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
        audience: Literal["family", "coach"] = "family",
    ) -> PHVExplanation:
        if latest_record is None:
            raise ValueError(
                "PHVExplainerUseCase requiere al menos una medición antropométrica."
            )
        if audience not in self._TEMPLATE_ID_BY_AUDIENCE:
            raise ValueError(f"audience inválida: {audience!r}")

        context = self._context_builder.build(
            athlete, latest_record, history=history
        )
        # Guardrails específicos al grupo de edad para cubrir reglas como
        # "sin potenciómetro para 10-12". Se construyen como variable local
        # (no como atributo de instancia) para evitar que dos requests
        # concurrentes compartiendo el mismo use case se pisen las reglas.
        guardrails = Guardrails(age_group=context.get("age_group"))

        template_id = self._TEMPLATE_ID_BY_AUDIENCE[audience]
        response = await self._ask_with_template(template_id, context)
        sanitized = self._scrub(response.text, guardrails=guardrails)

        return PHVExplanation(
            text=sanitized,
            model=response.model or self._provider.model,
            provider=response.provider or self._provider.name,
            generated_at=response.generated_at,
            age_group=context["age_group"],
            maturation_status=context.get("maturation_status", ""),
        )

    async def _ask_with_template(self, template_id: str, context: dict) -> LLMResponse:
        """Igual que `BaseUseCase._ask`, pero con la plantilla como parámetro.

        `BaseUseCase._ask` siempre usa `self.template_id`. Aquí necesitamos
        variar la plantilla por `audience` en cada llamada sin mutar
        `self.template_id`: esta instancia puede compartirse entre requests
        concurrentes (mismo razonamiento que los guardrails locales arriba),
        y escribir sobre un atributo compartido dejaría una request de un
        entrenador pisando la plantilla de una request familiar concurrente.
        """
        user_msg = self._registry.render(template_id, context)
        request = LLMRequest(
            system=self._registry.system_prompt(),
            messages=(LLMMessage(role="user", content=user_msg),),
        )
        return await self._provider.complete(request)
