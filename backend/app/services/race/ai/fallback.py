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


__all__ = ["deterministic_fallback"]
