"""Use case: explicar una medición antropométrica concreta vs su historial.

Mientras `PHVExplainerUseCase` produce una explicación global de la última
medición del atleta, este caso de uso analiza un registro específico
(`target_record`) y lo contextualiza contra las mediciones previas: deltas
significativos, velocidad de crecimiento, cruce de fase PHV.

Guardrails adicionales (`use_case="anthropometric_record_analysis"`) evitan
sugerencias diagnósticas médicas (RED-S, patología, retraso puberal) que solo
personal de salud autorizado puede emitir sobre menores.
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


USE_CASE_KEY = "anthropometric_record_analysis"


@dataclass(frozen=True)
class AnthropometricRecordExplanation:
    text: str
    model: str
    provider: str
    generated_at: datetime
    age_group: str
    maturation_status: str
    record_id: int
    num_previous_measurements: int
    delta_height_cm: float | None
    delta_weight_kg: float | None


class AnthropometricRecordExplainerUseCase(BaseUseCase):
    """Caso de uso `anthropometric_record_analysis`."""

    template_id = USE_CASE_KEY

    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
        context_builder: AthleteAIContextBuilder | None = None,
    ) -> None:
        super().__init__(provider, registry, guardrails=None)
        self._context_builder = context_builder or AthleteAIContextBuilder()

    async def run(
        self,
        athlete: "Athlete",
        target_record: "AnthropometricRecord",
        prior_records: list["AnthropometricRecord"] | None = None,
    ) -> AnthropometricRecordExplanation:
        if target_record is None:
            raise ValueError(
                "AnthropometricRecordExplainerUseCase requiere un target_record."
            )
        priors = prior_records or []
        context = self._context_builder.build_record_delta(
            athlete, target_record, priors
        )
        # Guardrails con reglas anti-diagnóstico activadas.
        self._guardrails = Guardrails(
            age_group=context.get("age_group"),
            use_case=USE_CASE_KEY,
        )

        response = await self._ask(context)
        sanitized = self._scrub(response.text)

        return AnthropometricRecordExplanation(
            text=sanitized,
            model=response.model or self._provider.model,
            provider=response.provider or self._provider.name,
            generated_at=response.generated_at,
            age_group=context["age_group"],
            maturation_status=context.get("maturation_status", ""),
            record_id=target_record.id,
            num_previous_measurements=context.get("num_previous_measurements", 0),
            delta_height_cm=context.get("delta_height_cm"),
            delta_weight_kg=context.get("delta_weight_kg"),
        )
