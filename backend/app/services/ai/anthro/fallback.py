"""Plantilla determinística de reserva del pipeline antropométrico (feature 042).

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T035 y
``data-model.md`` §3, fila "Deterministic-fallback path": el resultado que
``pipeline.py`` (T039, fuera de este ownership) entrega cuando

1. el analista falla dos intentos seguidos (``analyst.py::run_analyst`` ⇒
   ``analyst_failed=True``) — el crítico ni siquiera se invoca; o
2. las prechecks deterministas (``prechecks.py``, T029) encuentran una
   violación ``must_block`` — por la misma razón: "the critic call is
   skipped to avoid spending a call whose verdict cannot change the
   outcome" (FR-014).

Invariante NO negociable (data-model.md §3 y §6, invariante 3): el fallback
debe ser ÉL MISMO un :class:`AnthropometryInsightV1` válido —
``confidence.level="low"``, ``data_gaps=["análisis automático no disponible
para esta medición"]`` — NUNCA una cadena suelta fuera del esquema. Eso es
lo que le permite al renderizador v2 del frontend tratar una fila
``critic_verdict="fallback"`` con cero casos especiales: es una fila
``schema_version="v2"`` más, con ``structured_json`` poblado como cualquier
otra.

Por la misma razón (FR-013: "never a hand-written string outside the
schema", y CLAUDE.md: nunca inventar contenido), este módulo construye su
texto ÚNICAMENTE a partir de las dos señales deterministas ya disponibles
en ``AnalysisContext`` (``context.py``, T028) — jamás del LLM:

- los deltas significativos de talla/peso (``measurement_deltas``, los
  mismos números en cm/kg que el prompt del analista ya permite mostrarle
  a la familia — regla 7 de ``anthropometry_analyst_v1.md``); y
- la PRESENCIA (no el código crudo) de fase de maduración y de alertas del
  resumen de crecimiento (``growth_summary``).

Deliberadamente NO se echa ningún código crudo de ``growth_summary``
(``stage``, ``height_band``, ``weight_band``, ``nutritional_status``,
``alerts``) verbatim en el texto: varios de esos códigos son etiquetas con
connotación clínica (``NutritionalStatus``, ej. "delgadez"/"obesidad"/
"retraso_talla" — ``app/models/anthropometry.py``) y el catálogo de reglas
R01–R12 (``contracts/golden-eval-case.md`` §3, regla R02) trata justamente
la fuga de una etiqueta diagnóstica como violación ``must_block`` para
texto generado por LLM. Esta plantilla es determinística, no LLM, pero
aplica el mismo criterio por precaución: usa la PRESENCIA de esos campos
solo para decidir qué frase genérica incluir, nunca su valor literal.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.schemas import (
    Confidence,
    ConfidenceLevel,
    AnthropometryInsightV1,
    count_words,
)

__all__ = ["FALLBACK_DATA_GAP", "build_fallback_insight", "run_fallback"]

# Verbatim de data-model.md §3 — el mismo string exacto en cada fila
# ``critic_verdict="fallback"``, para que un consumidor (frontend, golden
# eval) pueda reconocer una fila de fallback por este marcador sin tener
# que inspeccionar ``critic_verdict`` aparte.
FALLBACK_DATA_GAP = "análisis automático no disponible para esta medición"

_CONFIDENCE_REASON = (
    "Este contenido es una plantilla generada automáticamente mientras el "
    "análisis con inteligencia artificial no está disponible para esta "
    "medición."
)


def _person_ref(audience: str) -> str:
    """Referencia al deportista sin nombre propio (regla inviolable #3 del
    prompt del analista — la misma restricción aplica aquí por consistencia
    de producto, aunque este texto nunca pasa por un LLM)."""
    return "su hijo o hija" if audience == "family" else "tu deportista"


def _summary_line(audience: str) -> str:
    return (
        f"No fue posible generar automáticamente el análisis de esta "
        f"medición de {_person_ref(audience)}."
    )


def _delta_change_lines(deltas: Optional[dict[str, Any]]) -> list[str]:
    """Frases de ``changes`` a partir SOLO de los deltas significativos.

    Reutiliza los mismos números (cm/kg) que el prompt del analista ya
    considera seguros para la familia (regla 7) — nunca inventa un valor
    que no esté en ``deltas``.
    """
    if deltas is None:
        return ["No hay una medición anterior con la cual comparar esta lectura."]

    lines: list[str] = []
    if deltas.get("delta_height_significant"):
        lines.append(
            "La talla cambió {:+.1f} cm desde la medición anterior.".format(
                deltas["delta_height_cm"]
            )
        )
    if deltas.get("delta_weight_significant"):
        lines.append(
            "El peso cambió {:+.1f} kg desde la medición anterior.".format(
                deltas["delta_weight_kg"]
            )
        )
    if not lines:
        lines.append(
            "El cambio de talla y peso se mantiene dentro de la variación "
            "esperada entre mediciones."
        )
    return lines[:4]


def _meaning_lines(audience: str, growth_summary: dict[str, Any]) -> list[str]:
    """Frases de ``meaning`` a partir SOLO de la presencia (no el valor) de
    campos de ``growth_summary`` — ver el docstring del módulo."""
    lines: list[str] = [
        "El resumen de crecimiento y las bandas de talla, peso y estado "
        "nutricional ya registrados quedan disponibles para que el "
        "entrenador los revise manualmente."
    ]
    if growth_summary.get("stage"):
        lines.append(
            "La fase de maduración actual queda documentada en el resumen "
            "de crecimiento, sin una interpretación automática por ahora."
        )
    if growth_summary.get("alerts"):
        lines.append(
            "El resumen de crecimiento tiene una o más alertas activas que "
            "el entrenador revisará con prioridad."
        )
    return lines[:4]


def _next_weeks_lines(audience: str) -> list[str]:
    if audience == "family":
        return [
            "El entrenador del club revisará esta medición manualmente en "
            "los próximos días y se pondrá en contacto si hace falta algo."
        ]
    return [
        "Revisa esta medición manualmente mientras se resuelve la "
        "generación automática; se reintentará en la próxima carga."
    ]


def _rendered_word_count(*text_groups: list[str]) -> int:
    """Cuenta palabras sobre el texto realmente producido — mismo criterio
    (``count_words``) que usan las prechecks para el presupuesto real; aquí
    solo alimenta el campo telemétrico ``word_count``, nunca decide nada."""
    joined = " ".join(line for group in text_groups for line in group)
    return count_words(joined)


def build_fallback_insight(context: AnalysisContext) -> AnthropometryInsightV1:
    """Construye la plantilla determinística de reserva para ``context``.

    Válida siempre para ambas audiencias (``context.identity["audience"]``
    decide la redacción) — nunca lanza, nunca llama a un LLM. Es responsa-
    bilidad de ``pipeline.py`` invocar esta función tanto en el camino de
    fallo del analista como en el de ``must_block`` de las prechecks
    (data-model.md §3) y persistir su resultado con
    ``critic_verdict="fallback"``.
    """
    audience = context.identity["audience"]

    changes = _delta_change_lines(context.measurement_deltas)
    meaning = _meaning_lines(audience, context.growth_summary)
    next_weeks = _next_weeks_lines(audience)

    return AnthropometryInsightV1(
        audience=audience,
        summary_line=_summary_line(audience),
        changes=changes,
        meaning=meaning,
        next_weeks=next_weeks,
        warning_signs=[],
        confidence=Confidence(level=ConfidenceLevel.LOW, reason=_CONFIDENCE_REASON),
        data_gaps=[FALLBACK_DATA_GAP],
        word_count=_rendered_word_count(changes, meaning, next_weeks),
    )


async def run_fallback(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Envoltorio ``(state, config) -> dict`` de :func:`build_fallback_insight`.

    Mismo motivo de firma que ``context.py``/``analyst.py``/``critic.py``
    (paridad con un futuro nodo LangGraph) aunque este paso no invoque
    ningún LLM y por eso no use ``config`` en absoluto — se acepta solo
    para uniformidad con los demás pasos del pipeline.
    """
    del config  # no usado — ver docstring.
    context: AnalysisContext = state["analysis_context"]
    return {"fallback_output": build_fallback_insight(context)}
