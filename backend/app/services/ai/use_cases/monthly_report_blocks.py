"""Use case: generación de bloques de narrativa para el Informe Técnico Mensual.

Produce UN borrador de texto por bloque (objetivo, desarrollo, resultados,
conclusiones, apoyos_materiales, analisis_grupo). Reutiliza el mecanismo de
privacidad de MonthlyReportUseCase: anonimización de atletas con pseudónimos
deterministas, guardrails sin nombres reales ni términos médicos/suplementos.

PRIVACIDAD: la IA NUNCA recibe ni emite nombres reales de atletas.
Los nombres solo aparecen en CompetitionResultItem (campo estructurado curado
por el coach/admin), que no se envía al LLM.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.ai.use_cases.monthly_report import (
    MonthlyReportContext,
    MonthlyReportGuardrails,
    MonthlyReportLLMTimeout,
    MonthlyReportUseCase,
)

logger = logging.getLogger(__name__)

# Límite de palabras por bloque — balanceo entre completitud y concisión.
# Ajustado para encajar en una página A4 con márgenes del template técnico.
_BLOCK_MAX_WORDS: dict[str, int] = {
    "objetivo": 150,
    "desarrollo": 200,
    "resultados": 180,
    "conclusiones": 150,
    "apoyos_materiales": 120,
    "analisis_grupo": 220,
}

# Títulos legibles para cada bloque (español)
_BLOCK_TITLES: dict[str, str] = {
    "objetivo": "Objetivo del período",
    "desarrollo": "Desarrollo de actividades",
    "resultados": "Resultados obtenidos",
    "conclusiones": "Conclusiones y recomendaciones",
    "apoyos_materiales": "Apoyos y recursos materiales",
    "analisis_grupo": "Análisis cualitativo del grupo de alto rendimiento",
}

# Instrucción específica por bloque — contextualiza qué debe redactar la IA
_BLOCK_PROMPTS: dict[str, str] = {
    "objetivo": (
        "Describe en 2-3 oraciones el objetivo central trabajado durante el mes "
        "con el grupo de alto rendimiento: focos técnicos planificados, propósito "
        "formativo y alineación con el plan de temporada. Sin detallar individuos."
    ),
    "desarrollo": (
        "Describe el desarrollo de las sesiones del mes: número de sesiones "
        "ejecutadas vs planificadas, tipos de actividades trabajadas (focos "
        "técnicos), volumen general y dinámica del grupo. Mantén tono de "
        "informe de gestión."
    ),
    "resultados": (
        "Describe los resultados del mes en términos de indicadores agregados: "
        "porcentaje de asistencia del grupo, nivel de ejecución técnica (rúbricas "
        "agregadas), adherencia al plan. Sin mencionar resultados competitivos "
        "(esos van en el bloque de competencia). Sin juicios individuales."
    ),
    "conclusiones": (
        "Redacta las conclusiones del período: logros del grupo, áreas a reforzar "
        "en el próximo ciclo, y una o dos recomendaciones concretas para el equipo "
        "técnico. Tono propositivo, agregado, sin mencionar atletas individuales."
    ),
    "apoyos_materiales": (
        "Describe brevemente los apoyos y recursos materiales utilizados durante "
        "el mes (instalaciones, equipamiento, materiales didácticos, escenarios de "
        "competencia). Si no hay información específica disponible, redacta con "
        "base en el tipo de actividades ejecutadas (sesiones de entrenamiento XCO)."
    ),
    "analisis_grupo": (
        "Redacta un análisis cualitativo del grupo de alto rendimiento como conjunto: "
        "tendencias de asistencia y compromiso, evolución técnica observable en la "
        "rúbrica agregada (esfuerzo, actitud, técnica), focos dominantes del período "
        "y dinámica grupal general. Tono del entrenador, reflexivo. SIN juicios "
        "individuales. SIN mencionar pseudónimos de atletas."
    ),
}


@dataclass
class BlockDraft:
    """Borrador de un bloque generado por la IA."""

    block_key: str
    ai_draft: str | None
    ai_model: str | None
    generated_at: datetime | None
    error: str | None = None  # None si la generación fue exitosa


class MonthlyReportBlocksUseCase(MonthlyReportUseCase):
    """Genera borradores de narrativa bloque a bloque.

    Hereda de MonthlyReportUseCase para reutilizar:
    - build_context_from_metrics (anonimización)
    - MonthlyReportGuardrails (sin nombres reales, sin términos médicos)
    - _ask / _scrub / _LLM_TIMEOUT_SECONDS
    El template_id se sobreescribe en cada llamada vía _ask_block().
    """

    template_id = "monthly_report_blocks"  # registrado en registry.py

    async def run_block(
        self,
        ctx: MonthlyReportContext,
        block_key: str,
    ) -> BlockDraft:
        """Genera el borrador de UN bloque.

        Si el LLM falla (timeout, error de red, guardrail) retorna un
        BlockDraft con ai_draft=None y error descriptivo — NO lanza excepción.
        El caller (servicio) puede continuar con los demás bloques.
        """
        title = _BLOCK_TITLES.get(block_key, block_key)
        prompt = _BLOCK_PROMPTS.get(block_key, f"Redacta el bloque '{block_key}'.")
        max_words = _BLOCK_MAX_WORDS.get(block_key, 180)

        guardrails = MonthlyReportGuardrails(forbidden_names=ctx.forbidden_names)

        context_dict = ctx.model_dump(exclude={"forbidden_names"})
        context_dict["attendance_stats"] = [
            s.model_dump() for s in ctx.attendance_stats
        ]
        context_dict["block_key"] = block_key
        context_dict["block_title"] = title
        context_dict["block_prompt"] = prompt
        context_dict["block_max_words"] = max_words

        try:
            response = await asyncio.wait_for(
                self._ask(context_dict),
                timeout=self._LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "monthly_report_blocks: timeout en bloque '%s' tras %.0fs",
                block_key,
                self._LLM_TIMEOUT_SECONDS,
            )
            return BlockDraft(
                block_key=block_key,
                ai_draft=None,
                ai_model=None,
                generated_at=None,
                error="timeout",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "monthly_report_blocks: error en bloque '%s': %s",
                block_key,
                type(exc).__name__,
            )
            return BlockDraft(
                block_key=block_key,
                ai_draft=None,
                ai_model=None,
                generated_at=None,
                error=type(exc).__name__,
            )

        try:
            sanitized = self._scrub(response.text, guardrails=guardrails)
        except Exception as exc:  # noqa: BLE001 — guardrail reject
            logger.warning(
                "monthly_report_blocks: guardrail rechazó bloque '%s': %s",
                block_key,
                exc,
            )
            return BlockDraft(
                block_key=block_key,
                ai_draft=None,
                ai_model=response.model or self._provider.model,
                generated_at=response.generated_at,
                error=f"guardrail: {exc}",
            )

        return BlockDraft(
            block_key=block_key,
            ai_draft=sanitized,
            ai_model=response.model or self._provider.model,
            generated_at=response.generated_at,
        )

    async def run_all_blocks(
        self,
        ctx: MonthlyReportContext,
        block_keys: list[str] | None = None,
    ) -> list[BlockDraft]:
        """Genera borradores para todos los bloques en paralelo.

        Si `block_keys` es None, genera los 6 bloques estándar (excluye
        'competencia' — ese bloque es estructurado, no narrativo).

        Cada bloque falla de forma independiente: un timeout en un bloque
        no afecta los demás. El caller debe comprobar BlockDraft.error.
        """
        keys = block_keys or list(_BLOCK_MAX_WORDS.keys())
        tasks = [self.run_block(ctx, key) for key in keys]
        return list(await asyncio.gather(*tasks))
