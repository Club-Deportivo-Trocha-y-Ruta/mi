"""Fallback determinista — usado si el analyst LLM falla 3x (F4 §4.6).

No invoca LLM. Produce un :class:`AnalysisOutput` mínimo que cumple el
contrato Pydantic y permite al coach decidir si reintenta manualmente
o publica como "análisis no disponible".

Razón:
- Sin esto, un fallo de Gemini (rate limit, timeout, malformed JSON)
  rompe el grafo a mitad de camino → estado huérfano sin output ni
  notificación al coach.
- Con el fallback, el grafo siempre llega a ``notify_coach`` con un
  output válido — UX se mantiene incluso en degradación de servicio.
"""

from __future__ import annotations

from app.services.race.schemas import AnalysisOutput

_FALLBACK_MARKDOWN = (
    "Análisis IA no disponible en este momento. Revisa los datos crudos "
    "en la sección de resultados."
)

_FALLBACK_N1_MARKDOWN = """\
## Qué pasó en esta válida
La deportista participó en una válida durante la temporada.

## Recorrido hasta acá
Con una sola válida disputada aún no es posible establecer una tendencia de progresión.

## Hacia dónde va
Reforzar fundamentos técnicos y mantener disfrute en el entrenamiento (categoría=technique, prioridad=med).\
"""


def deterministic_fallback(pseudonym: str) -> AnalysisOutput:
    """Output mínimo válido cuando el analyst LLM no responde.

    Args:
        pseudonym: pseudónimo del atleta (ya anonimizado upstream).

    Returns:
        :class:`AnalysisOutput` con secciones vacías y mensaje neutral.
    """
    return AnalysisOutput(
        pseudonym=pseudonym,
        sections={},
        citations_used=[],
        recommendations=[],
        risk_flags=[],
        raw_markdown=_FALLBACK_MARKDOWN,
        word_count=len(_FALLBACK_MARKDOWN.split()),
    )


def deterministic_fallback_n1(pseudonym: str) -> AnalysisOutput:
    """Output mínimo válido para el caso N=1 (una sola válida en el set).

    Respeta la regla N=1: no infiere tendencias ni proyecciones. Inicia la
    sección "Recorrido hasta acá" con la frase canónica obligatoria.

    Args:
        pseudonym: pseudónimo del atleta (ya anonimizado upstream).

    Returns:
        :class:`AnalysisOutput` con las 3 secciones v2 mínimas conforme
        a la regla N=1.
    """
    from app.services.race.schemas import Priority, Recommendation, RecommendationCategory

    sections = {
        "what_happened": "La deportista participó en una válida durante la temporada.",
        "journey_so_far": (
            "Con una sola válida disputada aún no es posible establecer "
            "una tendencia de progresión."
        ),
        "next_steps": (
            "Reforzar fundamentos técnicos y mantener disfrute en el entrenamiento "
            "(categoría=technique, prioridad=med)."
        ),
    }
    recommendations = [
        Recommendation(
            text="Reforzar fundamentos técnicos y mantener disfrute en el entrenamiento",
            category=RecommendationCategory("technique"),
            priority=Priority("med"),
        )
    ]
    return AnalysisOutput(
        pseudonym=pseudonym,
        sections=sections,
        citations_used=[],
        recommendations=recommendations,
        risk_flags=[],
        raw_markdown=_FALLBACK_N1_MARKDOWN,
        word_count=len(_FALLBACK_N1_MARKDOWN.split()),
    )


__all__ = ["deterministic_fallback", "deterministic_fallback_n1"]
