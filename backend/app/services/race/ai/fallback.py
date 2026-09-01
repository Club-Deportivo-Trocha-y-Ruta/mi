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

Discriminador ``is_fallback`` (feature 036, US4, T022)
=======================================================
``deterministic_fallback`` es el *failure path*: se activa cuando el LLM
no responde. ``deterministic_fallback_n1`` NO es una falla — es el
análisis legítimo que exige la regla N=1 (una sola válida en la
temporada). Sólo el primero debe marcar ``AthleteAiInsight.is_fallback``.

En vez de que ``persist_insight`` infiera esto inspeccionando el
markdown o las secciones (frágil: cambia con el wording, y un output
real también puede llegar con ``sections`` vacías si el LLM no usa los
headings esperados), ``deterministic_fallback`` devuelve una subclase
marcadora de :class:`AnalysisOutput` — :class:`_FallbackAnalysisOutput`
— que no agrega ni cambia campos. :func:`is_fallback_output` expone el
chequeo (``isinstance``) para que los nodos downstream (``persist_insight``)
sólo *propaguen* el discriminador, sin duplicar la regla de negocio.
"""

from __future__ import annotations

from app.services.race.schemas import AnalysisOutput

_FALLBACK_MARKDOWN = (
    "Análisis IA no disponible en este momento. Revisa los datos crudos "
    "en la sección de resultados."
)


class _FallbackAnalysisOutput(AnalysisOutput):
    """Marca los ``AnalysisOutput`` producidos por el failure path.

    Subclase sin campos nuevos: se comporta exactamente como
    :class:`AnalysisOutput` en todo lo demás (serialización, acceso a
    atributos). Sólo existe para permitir ``isinstance`` en vez de
    inspeccionar contenido. NUNCA la construye ``deterministic_fallback_n1``.
    """


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

    Failure path: el resultado es una :class:`_FallbackAnalysisOutput`
    (subclase marcadora — ver :func:`is_fallback_output`), para que
    ``persist_insight`` marque ``AthleteAiInsight.is_fallback=True``.

    Args:
        pseudonym: pseudónimo del atleta (ya anonimizado upstream).

    Returns:
        :class:`AnalysisOutput` con secciones vacías y mensaje neutral.
    """
    return _FallbackAnalysisOutput(
        pseudonym=pseudonym,
        sections={},
        citations_used=[],
        recommendations=[],
        risk_flags=[],
        raw_markdown=_FALLBACK_MARKDOWN,
        word_count=len(_FALLBACK_MARKDOWN.split()),
    )


def is_fallback_output(output: AnalysisOutput | None) -> bool:
    """``True`` ⇔ ``output`` lo produjo el failure path (T022).

    Chequeo de identidad de tipo (``isinstance``), no de contenido: no
    inspecciona ``raw_markdown`` ni ``sections``. ``deterministic_fallback_n1``
    devuelve un :class:`AnalysisOutput` plano y por lo tanto siempre
    evalúa ``False`` aquí — es un análisis legítimo bajo la regla N=1,
    no una falla.

    Args:
        output: el ``AnalysisOutput`` a clasificar, o ``None`` (p.ej. no
            hubo draft para esa válida).

    Returns:
        ``True`` sólo para instancias producidas por :func:`deterministic_fallback`.
    """
    return isinstance(output, _FallbackAnalysisOutput)


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


__all__ = [
    "deterministic_fallback",
    "deterministic_fallback_n1",
    "is_fallback_output",
]
