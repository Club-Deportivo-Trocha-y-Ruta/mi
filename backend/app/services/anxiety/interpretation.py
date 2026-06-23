"""Interpretation orchestration: LLM-first with guaranteed rule fallback (US4).

Always returns a valid interpretation in the fixed schema (FR-016). The LLM
path is attempted only when enabled; any failure (disabled, timeout, invalid
JSON, guardrail rejection, config error) falls back to ``rule_interpreter``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.ai.use_cases.anxiety_interpretation import (
    AnxietyInterpretationUseCase,
)
from app.services.anxiety import rule_interpreter

logger = logging.getLogger(__name__)


@dataclass
class InterpretationResult:
    interpretation: dict
    source: str  # "llm" | "rule"
    model: str | None


async def interpret(
    *,
    use_case: AnxietyInterpretationUseCase | None,
    ai_enabled: bool,
    instrument_type: str,
    scores: dict[str, float | None],
    baselines: dict[str, float | None],
    age_group: str,
    event_label: str = "sin evento",
    priority: str | None = None,
    is_partial: bool = False,
) -> InterpretationResult:
    """Produce an interpretation, preferring the LLM and falling back to rules."""
    if ai_enabled and use_case is not None:
        try:
            out = await use_case.run(
                instrument_type=instrument_type,
                scores=scores,
                baselines=baselines,
                age_group=age_group,
                event_label=event_label,
                priority=priority,
                is_partial=is_partial,
            )
            return InterpretationResult(
                interpretation=out["interpretation"],
                source="llm",
                model=out.get("model"),
            )
        except Exception as exc:  # noqa: BLE001 — fallback is the contract (FR-016)
            logger.warning(
                "anxiety.interpretation.llm_fallback type=%s", type(exc).__name__
            )

    interpretation = rule_interpreter.interpret(
        instrument_type=instrument_type,
        scores=scores,
        baseline=baselines,
        event=event_label,
        priority=priority,
    )
    return InterpretationResult(
        interpretation=interpretation, source="rule", model=None
    )
