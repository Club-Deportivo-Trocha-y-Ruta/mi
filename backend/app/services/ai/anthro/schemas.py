"""``AnthropometryInsightV1`` — contrato estructurado del análisis antropométrico (feature 042).

Implementa ``specs/042-traceable-growth-ai/contracts/insight-schema.md`` y
``specs/042-traceable-growth-ai/data-model.md`` §2.1 / §2.4, verbatim.

Colisión de nombres deliberada (data-model.md §0 — LEER ANTES DE TOCAR ESTE ARCHIVO)
=====================================================================================
Este feature usa la palabra "schema_version" para **dos cosas independientes** que
NUNCA deben confundirse, compararse entre sí ni asignarse la una a la otra:

1. **``AnthropometryInsightV1.schema_version``** (este módulo): la versión del
   *payload* JSON del insight — hoy siempre ``Literal["v1"]``. Sólo sube cuando el
   contrato JSON analista/crítico cambia de forma.
2. **``AthleteAIExplanation.schema_version``** (columna DB, ``app/models/ai_explanation.py``):
   el discriminador de *formato de fila* — ``NULL`` (prosa libre heredada) vs
   ``"v2"`` (estructurado, este feature). Una fila ``"v2"`` en la DB contiene un
   ``structured_json`` cuyo campo interno ``schema_version`` es ``"v1"`` — eso es
   correcto, no un bug, y así seguirá hasta que el *shape* del insight tenga una
   segunda revisión.

Cualquier revisión de código que encuentre un ``schema_version == "v1"`` sin un
comentario que aclare a cuál de los dos ejes se refiere debe tratarse como un
defecto (data-model.md §6, invariante 4).

Privacidad (CLAUDE.md / Ley 1581): ninguno de estos campos puede llevar nombre
real, fecha de nacimiento, medida cruda, z-score, percentil ni fecha absoluta —
eso lo garantiza el ``AnalysisContext`` de entrada (T028) y las prechecks (T029),
no este módulo; este módulo sólo define la forma del dato.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConfidenceLevel",
    "Confidence",
    "AnthropometryInsightV1",
    "AnthropometryCriticIssue",
    "AnthropometryCriticVerdict",
    "WORD_BUDGETS",
    "WORD_BUDGET_TOLERANCE_FACTOR",
    "count_words",
    "word_budget_for_audience",
    "exceeds_word_budget",
]


class ConfidenceLevel(str, Enum):
    """Nivel de confianza que el analista (o el pipeline, tras el crítico) asigna al insight."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(BaseModel):
    """Confianza declarada del insight, con una razón breve y no clínica."""

    model_config = ConfigDict(extra="forbid")

    level: ConfidenceLevel
    reason: str = Field(..., min_length=3, max_length=200)


class AnthropometryInsightV1(BaseModel):
    """Insight estructurado producido por el analista (y, si aplica, revisado por el crítico).

    ``schema_version`` aquí es la versión del *payload* del insight (ver el
    docstring del módulo) — **no** confundir con ``AthleteAIExplanation.schema_version``
    (columna DB, discriminador de formato de fila).

    ``word_count`` es telemetría autoreportada por el modelo únicamente: el
    sistema jamás confía en este campo para hacer cumplir el presupuesto de
    palabras (FR-002/FR-011) — ver :func:`count_words` / :func:`exceeds_word_budget`,
    que recalculan sobre el texto renderizado real (``app/services/ai/anthro/prechecks.py``,
    regla R07).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"] = "v1"
    audience: Literal["family", "coach"]
    summary_line: str = Field(..., min_length=3, max_length=140)
    changes: list[str] = Field(..., min_length=1, max_length=4)
    meaning: list[str] = Field(..., min_length=1, max_length=4)
    next_weeks: list[str] = Field(..., min_length=1, max_length=3)
    warning_signs: list[str] = Field(default_factory=list, max_length=2)
    confidence: Confidence
    data_gaps: list[str] = Field(default_factory=list, max_length=3)
    word_count: int = Field(..., ge=0)  # telemetría únicamente, ver docstring de la clase


class AnthropometryCriticIssue(BaseModel):
    """Una observación puntual del crítico, referida a una regla de precheck (R01–R12)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    section: str
    problem: str = Field(..., min_length=3, max_length=200)
    suggested_fix: str = Field(..., min_length=3, max_length=200)


class AnthropometryCriticVerdict(BaseModel):
    """Veredicto crudo del crítico (vocabulario de tres valores, NO lo que se persiste).

    ``verdict`` (``approve | revise | reject``) es lo que el LLM crítico
    devuelve por llamada. El pipeline (``app/services/ai/anthro/pipeline.py``,
    T039) combina este veredicto crudo con el resultado de las prechecks y el
    resultado de la (a lo sumo una) reintento para producir el ``critic_verdict``
    persistido de cinco valores (``approved | revised | flagged | fallback |
    skipped``, data-model.md §3). Los dos vocabularios nunca deben tratarse
    como intercambiables.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approve", "revise", "reject"]
    violations: list[AnthropometryCriticIssue] = Field(default_factory=list)
    revised_output: Optional[AnthropometryInsightV1] = None


# ---------------------------------------------------------------------------
# Presupuesto de palabras (FR-002, contracts/insight-schema.md §3)
# ---------------------------------------------------------------------------
#
# Estos presupuestos son deliberadamente más ajustados que los de la prosa
# libre pre-042 (familia 200/250, coach 120 — analysis-design.md §2): los
# campos estructurados eliminan la prosa conectiva que un párrafo único
# necesitaba.
#
# Se cuentan sobre el texto renderizado (`render_markdown_free`, T038), NUNCA
# sobre `AnthropometryInsightV1.word_count` (autoreportado, sólo telemetría),
# y después del scrubbing de guardrails, para que una frase eliminada por un
# guardrail no cuente contra el presupuesto del que fue removida.
#
# La tolerancia del 10% replica la convención ya usada por el stack de
# carreras para sus límites de sección (`app/services/ai/guardrails.py`,
# `_V2_WORDS_TOLERANCE_FACTOR = 1.10`).

WORD_BUDGETS: dict[Literal["family", "coach"], int] = {
    "family": 180,
    "coach": 110,
}

WORD_BUDGET_TOLERANCE_FACTOR: float = 1.10


def count_words(text: str) -> int:
    """Cuenta palabras separadas por espacio en blanco. Función pura, sin efectos secundarios.

    No es un conteo lingüístico (no distingue puntuación pegada a una
    palabra); coincide a propósito con la heurística ya usada por
    ``app/services/ai/guardrails.py::check_v2_section_word_limits``.
    """

    return len([w for w in text.split() if w])


def word_budget_for_audience(audience: Literal["family", "coach"]) -> int:
    """Presupuesto base (sin tolerancia) de palabras para la audiencia dada."""

    return WORD_BUDGETS[audience]


def exceeds_word_budget(audience: Literal["family", "coach"], rendered_text: str) -> bool:
    """``True`` si ``rendered_text`` excede el presupuesto de ``audience`` (con 10% de tolerancia).

    Recalcula siempre sobre el texto renderizado real — nunca sobre
    ``AnthropometryInsightV1.word_count`` — para que un borrador que
    subreporta su propio conteo (accidental o adversarialmente) igual sea
    detectado. Este es el helper que la regla R07 de
    ``app/services/ai/anthro/prechecks.py`` (T029) usa para decidir si
    degrada la confianza del insight; esta función no decide nada por sí
    misma sobre bloqueo o entrega.
    """

    limit = word_budget_for_audience(audience) * WORD_BUDGET_TOLERANCE_FACTOR
    return count_words(rendered_text) > limit
