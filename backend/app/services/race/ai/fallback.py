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

from typing import Any

from app.services.race.insight_v3 import (
    ActionCategory,
    ActionV3,
    EvidenceDomain,
    Horizon,
    InsightV3,
    Observation,
    Priority as PriorityV3,
)
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


def is_fallback_output(output: Any | None) -> bool:
    """``True`` ⇔ ``output`` lo produjo el failure path (T022).

    Chequeo de identidad de tipo (``isinstance``), no de contenido: no
    inspecciona ``raw_markdown`` ni ``sections``. ``deterministic_fallback_n1``
    devuelve un :class:`AnalysisOutput` plano y por lo tanto siempre
    evalúa ``False`` aquí — es un análisis legítimo bajo la regla N=1,
    no una falla.

    Feature 037 (T201): acepta también el draft estructurado v3 y reconoce
    el marcador de :func:`deterministic_fallback_v3`. Así ``persist_insight``
    marca ``is_fallback=True`` aunque el fan-out v3 haya sido el que falló,
    sin duplicar la regla de negocio en el nodo.

    Args:
        output: el ``AnalysisOutput`` o ``InsightV3`` a clasificar, o
            ``None`` (p.ej. no hubo draft para esa válida).

    Returns:
        ``True`` sólo para instancias producidas por
        :func:`deterministic_fallback` o :func:`deterministic_fallback_v3`.
    """
    return isinstance(output, (_FallbackAnalysisOutput, _FallbackInsightV3))


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


class _FallbackInsightV3(InsightV3):
    """Marca los :class:`InsightV3` producidos por el failure path v3.

    Mismo patrón que :class:`_FallbackAnalysisOutput`: subclase sin campos
    nuevos, para que :func:`is_fallback_output` decida por ``isinstance`` y
    no inspeccionando el ``headline`` (que cambia con el wording).
    """


_FALLBACK_V3_HEADLINE = "Análisis no disponible"


def deterministic_fallback_v3(*, analysis_kind: str = "valida") -> InsightV3:
    """``InsightV3`` mínimo y honesto cuando el analista v3 no responde.

    Cumple el esquema (2 observaciones, 2 acciones, una pregunta) **sin
    inventar un solo número**: ninguna evidencia contiene cifras, así que el
    precheck de grounding (T202) no encuentra violaciones que no existan y
    la confianza queda en ``low`` por la vía del discriminador
    ``is_fallback``, no por un falso positivo.

    Las dos acciones son deliberadamente conservadoras: ante la ausencia de
    análisis, la recomendación segura es no cambiar la carga.

    Args:
        analysis_kind: ``"valida"`` (default) | ``"season"`` — solo ajusta el
            wording ("esta carrera" vs. "esta temporada").

    Returns:
        :class:`InsightV3` marcado (ver :func:`is_fallback_output`).
    """
    subject = "esta temporada" if analysis_kind == "season" else "esta carrera"
    return _FallbackInsightV3(
        headline=_FALLBACK_V3_HEADLINE,
        field_reading=None,
        trend="first_reference",
        observations=[
            Observation(
                claim=(
                    f"El sistema no pudo generar el análisis automático de {subject}."
                ),
                evidence=["Sin respuesta válida del modelo de lenguaje"],
                domain=EvidenceDomain.RACE,
                confidence="low",
            ),
            Observation(
                claim=(
                    "Los datos oficiales siguen disponibles en la plataforma para "
                    "revisarlos manualmente."
                ),
                evidence=["Resultados y asistencia cargados en la plataforma"],
                domain=EvidenceDomain.RACE,
                confidence="low",
            ),
        ],
        actions=[
            ActionV3(
                text=(
                    "Mantener el plan de entrenamiento sin cambios hasta contar con "
                    "un análisis validado."
                ),
                category=ActionCategory.VOLUME,
                priority=PriorityV3.LOW,
                horizon=Horizon.NEXT_WEEK,
                catalog_ref=None,
                derived_from=0,
            ),
            ActionV3(
                text=(
                    "Sostener los días de descanso habituales mientras se repite el "
                    "análisis."
                ),
                category=ActionCategory.RECOVERY,
                priority=PriorityV3.LOW,
                horizon=Horizon.NEXT_WEEK,
                catalog_ref=None,
                derived_from=1,
            ),
        ],
        watch_signals=[],
        coach_question="¿Quieres reintentar el análisis con IA cuando el servicio esté disponible?",
        data_gaps=[
            "El modelo de IA no devolvió un análisis válido; no hay lectura de "
            "pelotón ni de entrenamiento en este registro."
        ],
        principles_cited=[],
    )


__all__ = [
    "deterministic_fallback",
    "deterministic_fallback_n1",
    "deterministic_fallback_v3",
    "is_fallback_output",
]
