"""Cómputo determinista de confianza por insight (feature 011, US4).

Reemplaza el ``InsightConfidence.medium`` hardcoded por una señal real derivada
del verdicto del critic + la completitud de los datos de grounding. Pura y
determinista (Constitution II: testeable, explicable al coach).

Reglas (primer match gana) — ver data-model.md:

    análisis fallback  OR  verdict.must_block  OR  cualquier issue high  → low
    cualquier issue med  OR  verdict is None (critic deshabilitado)      → medium
    faltan condiciones  OR  falta maduración  OR  season_n <= 1          → medium (cap)
    en otro caso                                                          → high
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.ai.prechecks import PrecheckCategory, PrecheckIssue
from app.services.race.schemas import CriticFeedback, CriticIssueSeverity


@dataclass(frozen=True)
class DataCompleteness:
    """Completitud de los insumos de grounding de una válida."""

    has_conditions: bool
    has_maturation: bool
    season_n: int
    is_fallback: bool = False


def compute_confidence(
    verdict: CriticFeedback | None,
    completeness: DataCompleteness,
) -> InsightConfidence:
    """Mapea (verdicto del critic, completitud) → :class:`InsightConfidence`."""
    # 1) Señales que degradan a baja.
    if completeness.is_fallback:
        return InsightConfidence.low
    if verdict is not None:
        if verdict.must_block or verdict.severity == CriticIssueSeverity.HIGH:
            return InsightConfidence.low

    # 2) Issue medio o critic deshabilitado → media.
    if verdict is None:
        return InsightConfidence.medium
    if verdict.severity == CriticIssueSeverity.MED:
        return InsightConfidence.medium

    # 3) Cap a media por insumos incompletos.
    if (
        not completeness.has_conditions
        or not completeness.has_maturation
        or completeness.season_n <= 1
    ):
        return InsightConfidence.medium

    # 4) Datos completos + verdicto limpio → alta.
    return InsightConfidence.high


def compute_confidence_v3(
    *,
    is_fallback: bool,
    must_block: bool,
    issues: Iterable[PrecheckIssue] | None,
    has_training_window: bool,
    has_anthro: bool,
    season_n: int,
) -> InsightConfidence:
    """Confianza v3 (feature 037, T202) — ver plan.md §Critic v3.

    Reglas (primer match gana):

        fallback OR must_block OR cualquier issue de grounding  → low
        cualquier issue (de cualquier categoría) OR falta
        training_window OR falta anthro OR season_n <= 1        → medium
        en otro caso                                              → high
    """
    issues = list(issues or [])

    if is_fallback or must_block:
        return InsightConfidence.low
    if any(i.category == PrecheckCategory.GROUNDING for i in issues):
        return InsightConfidence.low

    if (
        issues
        or not has_training_window
        or not has_anthro
        or season_n <= 1
    ):
        return InsightConfidence.medium

    return InsightConfidence.high


__all__ = ["compute_confidence", "compute_confidence_v3", "DataCompleteness"]
