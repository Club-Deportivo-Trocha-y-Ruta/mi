"""Paso 4 del pipeline antropométrico (feature 042, T036): guardrails + puerta familiar.

Implementa ``specs/042-traceable-growth-ai/tasks.md`` T036,
``specs/042-traceable-growth-ai/data-model.md`` §3 (el párrafo final, "Family delivery
gate") y FR-015/FR-016 de ``specs/042-traceable-growth-ai/spec.md``. Firma compatible
con un nodo LangGraph (``async def step(state, config) -> dict``, ``research.md`` R-03)
por el mismo motivo que ``context.py`` (T028) y ``analyst.py`` (T033): este pipeline es
un orquestador plano sin grafo, checkpointer ni HITL, pero mantener la firma idéntica
hace que una futura promoción a ``StateGraph`` sea un envoltorio mecánico, no una
reescritura. El nombre de la función (``guardrails_step``, no ``run_guardrails_step``)
está fijado por el pseudocódigo literal de ``contracts/trace-metadata-allowlist.md`` §4.1:

    state = await context(state, config)
    state = await analyst(state, config)
    state = await critic(state, config)
    state = await guardrails_step(state, config)
    state = await persist(state, config)

Contrato de entrada de ``state`` (lo puebla ``pipeline.py``, T039, y en la práctica
``critic.py``, T034, no este módulo — este paso corre DESPUÉS de que el ciclo
analista→prechecks→crítico ya resolvió un único insight final y un veredicto
persistido; ver la máquina de estados completa en ``data-model.md`` §3):

- ``insight``: la ``AnthropometryInsightV1`` FINAL ya resuelta por el paso 3 — el
  borrador del analista, el ``revised_output`` del crítico, el segundo intento del
  analista, o la plantilla determinista del fallback (``fallback.py``, T035),
  según a qué fila de la tabla de ``data-model.md`` §3 haya llegado la corrida. Este
  paso NUNCA decide cuál de esas cuatro fuentes es la vigente — solo renderiza y
  sanea la que ya llegó resuelta en ``state``.
- ``critic_verdict``: el veredicto persistido de CINCO valores (``approved | revised |
  flagged | fallback | skipped``, ``data-model.md`` §3) — **no** el vocabulario crudo
  de tres valores del crítico (``AnthropometryCriticVerdict.verdict``,
  ``schemas.py`` §2.4). Este paso solo lee este valor para decidir la entrega
  familiar; jamás lo recalcula ni lo reinterpreta.
- ``analysis_context``: la ``AnalysisContext`` del paso 1 (``context.py``), todavía
  presente en ``state`` por acumulación — se usa solo para leer
  ``identity["age_group"]`` y las dos banderas de contexto que
  ``Guardrails(...)`` necesita para R05/R11 (``measurement_deltas["velocity_confidence"]``
  y ``measurement_deltas["phase_crossing_corroborated"]``); ver el docstring de
  ``app/services/ai/guardrails.py::Guardrails`` para el porqué de cada bandera.

``config`` es el fragmento de ``RunnableConfig`` (callbacks de Langfuse) armado en el
span raíz de ``pipeline.py`` — este paso no hace ninguna llamada al LLM ni abre su
propio span, así que no lo usa; se acepta solo por uniformidad de firma (mismo
criterio que ``context.py``).

Qué hace este paso (FR-015 / FR-016, en ese orden):

1. Renderiza ``insight`` a la prosa plana que se guardará en la columna ``NOT NULL``
   ``AthleteAIExplanation.text`` (:func:`render_markdown_free`, regla exacta de
   ``contracts/insight-schema.md`` §4 — nunca incluye ``confidence.reason`` ni
   ``data_gaps``, que son metadata del análisis, no parte de su narrativa). Corre las
   reglas de guardrails EXISTENTES (``app/services/ai/guardrails.py::Guardrails``,
   ``use_case="anthropometry_insight_v1"``, agregado por T037) sobre ese texto — la
   ÚLTIMA defensa antes de que algo llegue a frontend, PDF o email (FR-015), tanto
   para audiencia familiar como para audiencia entrenador: un guardrail (p. ej. cero
   suplementos) nunca es exclusivo de un destinatario.
2. Si esa defensa final RECHAZA el texto (``GuardrailReport.rejected`` — 3+
   violaciones, o cualquier violación de privacidad propia de
   ``anthropometry_insight_v1``: fecha exacta, edad decimal ligada a PHV, cruce de
   fase presentado como confirmado sin corroborar, o filtración de un dato exclusivo
   del entrenador a una audiencia familiar), este paso levanta la MISMA excepción que
   ``Guardrails.scrub()`` ya usa en el caso de uso legado
   (``app.services.ai.errors.LLMSchemaError``), con el mismo formato de mensaje. El
   router (``app/routers/ai.py``, ya mapea ``LLMSchemaError`` → ``502``) no necesita
   ningún cambio para este paso nuevo — ``contracts/measurement-analysis-api.md`` §5
   documenta explícitamente ese ``502`` como "unchanged mapping; now can also fire
   from guardrails_step.py". Un rechazo aquí NUNCA se degrada a "solo entrenador": es
   un fallo de la corrida completa (nada se persiste), no un estado más del enum de
   cinco valores.
3. Si NO hubo rechazo, aplica la puerta de entrega familiar (FR-016,
   ``data-model.md`` §3 "Family delivery gate" + invariante 2 de §6: "Family delivery
   is critic_verdict ∈ {APPROVED, REVISED} and nothing else, full stop"). Este paso
   se limita a EVALUAR esa pertenencia — no inventa ningún texto de aviso para la
   familia (``flagged``/``fallback``/``skipped`` deben renderizarse IDÉNTICOS a "sin
   análisis todavía" en cualquier superficie familiar, mensaje pasivo compartido que
   vive en el frontend, no aquí).
4. Reporta qué reglas de guardrail dispararon y cuántos scrubs hubo, usando
   EXACTAMENTE los nombres de clave de
   ``app/services/llm/observability_metadata.py::ALLOWED_METADATA_KEYS``
   (``guardrail_rule_ids``, ``guardrail_scrub_count``; también incluye
   ``critic_verdict``, igualmente permitido, como contexto). El objeto devuelto ya
   pasa por :func:`app.services.llm.observability_metadata.build_structural_metadata`,
   que devuelve ``None`` cuando ``LANGFUSE_STRUCTURAL_METADATA`` está apagado (default
   y único valor legal en producción) — ``pipeline.py`` solo necesita adjuntarlo tal
   cual a la observación de Langfuse, sin ramificar sobre el flag. La etiqueta
   ``guardrail:<outcome>`` de ``contracts/trace-metadata-allowlist.md`` §3 (canal de
   tags, no de metadata — nunca pasa por el mask) se arma con ``guardrail_outcome``
   (``"clean" | "scrubbed"``; ``"rejected"`` nunca llega a devolverse porque ese caso
   lanza la excepción del punto 2 antes del ``return``).

Privacidad (CLAUDE.md / Ley 1581): ``report.violations``/``guardrail_rule_ids`` son
SIEMPRE nombres de regla (p. ej. ``"anthro_v1_exact_date"``), nunca el fragmento de
texto que disparó la regla ni ningún dato del atleta — mismo criterio que
``PrecheckViolation.detail`` en ``prechecks.py`` (T029).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import Guardrails
from app.services.llm.observability_metadata import build_structural_metadata

if TYPE_CHECKING:
    from app.services.ai.anthro.context import AnalysisContext
    from app.services.ai.anthro.schemas import AnthropometryInsightV1

logger = logging.getLogger(__name__)

__all__ = [
    "ANTHROPOMETRY_INSIGHT_USE_CASE",
    "FAMILY_DELIVERABLE_VERDICTS",
    "render_markdown_free",
    "guardrails_step",
]


# Use case exacto que ``guardrails.py`` (T037) reconoce para activar las reglas
# R04/R05/R11/R12 de defensa final (bloque "Reglas anthropometry_insight_v1" del
# módulo). Constante única para que ningún caller de este paso pueda desalinearse
# del string literal por un typo.
ANTHROPOMETRY_INSIGHT_USE_CASE = "anthropometry_insight_v1"

# Los CINCO valores persistidos de ``critic_verdict`` (data-model.md §3) — usado
# solo como guarda defensiva (fail loud si ``pipeline.py``/``critic.py`` pasaran
# algún día el vocabulario crudo del crítico de tres valores por error; ver la
# nota de colisión de nombres en ``schemas.py``).
_PERSISTED_CRITIC_VERDICTS = frozenset(
    {"approved", "revised", "flagged", "fallback", "skipped"}
)

# FR-016 / data-model.md §3 "Family delivery gate" / invariante 2 de §6: el
# conjunto entregable a familia es EXACTAMENTE este, sin excepción y sin
# "caveat" alguno para los otros tres valores. Exportado para que cualquier otro
# módulo (routers/ai.py T043, routers/growth.py T067) que necesite la misma
# pertenencia la importe de aquí en vez de reinventar el literal.
FAMILY_DELIVERABLE_VERDICTS = frozenset({"approved", "revised"})


def render_markdown_free(insight: "AnthropometryInsightV1") -> str:
    """Prosa plana sin Markdown para la columna ``NOT NULL`` ``text`` (insight-schema.md §4).

    Orden fijo de secciones — verbatim del contrato, string concatenation pura (cada
    campo de ``AnthropometryInsightV1`` ya es prosa plana por la regla 9 del prompt
    del analista, así que esto no es una conversión Markdown→texto):

        {summary_line}

        {" ".join(changes)}
        {" ".join(meaning)}
        {" ".join(next_weeks)}
        {" ".join(warning_signs) if warning_signs else ""}

    ``confidence.reason`` y ``data_gaps`` NUNCA se renderizan aquí — son metadata del
    análisis, no parte de su narrativa (insight-schema.md §4); siguen accesibles solo
    vía ``structured_json`` / los campos dedicados de la API.

    Reutilizable por ``persist.py`` (T038, fuera de este ownership) — importar esta
    función en vez de reimplementar el renderizado, para que el texto persistido en
    ``text`` sea SIEMPRE el mismo que este paso ya saneó con guardrails (FR-015: la
    defensa final debe cubrir el texto que efectivamente se guarda/muestra, no una
    segunda renderización distinta hecha río abajo).
    """
    lines = [
        insight.summary_line,
        "",
        " ".join(insight.changes),
        " ".join(insight.meaning),
        " ".join(insight.next_weeks),
        " ".join(insight.warning_signs) if insight.warning_signs else "",
    ]
    return "\n".join(lines).rstrip()


def _velocity_reliable(context: "AnalysisContext") -> bool:
    """``True`` solo si el contexto respalda una velocidad de crecimiento confiable.

    Mismo criterio exacto que
    ``prechecks.py::check_r05_unreliable_velocity_claimed_reliable`` — nunca un
    juicio de este módulo, siempre un cruce directo contra
    ``AnalysisContext.measurement_deltas["velocity_confidence"]``. Por defecto
    ``False`` (activa el escaneo R05 de ``Guardrails``) cuando no hay deltas
    (primera medición) o el campo no está presente (semanas insuficientes para
    calcular velocidad) — ver el docstring de ``Guardrails`` para por qué
    ``False`` aquí es "escanea por si acaso", no "hay un problema".
    """
    deltas = context.measurement_deltas or {}
    return deltas.get("velocity_confidence") == "reliable"


def _phase_crossing_corroborated(context: "AnalysisContext") -> bool:
    """``True`` (no-op) salvo que hubo un cruce de fase sin corroborar.

    Mismo criterio exacto que
    ``prechecks.py::check_r11_uncorroborated_phase_crossing``: sin cruce de fase
    (``crossed_phv_phase`` falso o sin deltas) no hay nada que corroborar, así que
    se devuelve ``True`` para que ``Guardrails`` no escanee (no-op, ver su
    docstring). Solo cuando SÍ hubo cruce se refleja el valor real de
    ``phase_crossing_corroborated``.
    """
    deltas = context.measurement_deltas
    if not deltas or not deltas.get("crossed_phv_phase"):
        return True
    return bool(deltas.get("phase_crossing_corroborated"))


async def guardrails_step(state: dict, config: Optional[dict] = None) -> dict[str, Any]:
    """Paso 4: renderiza, sanea con guardrails y evalúa la puerta de entrega familiar.

    Ver el docstring del módulo para el contrato completo de ``state`` y para el
    razonamiento de cada una de las cuatro responsabilidades (render+scrub,
    rechazo→502, puerta familiar, metadata de traza).
    """
    del config  # este paso no llama al LLM ni abre su propio span — ver docstring.

    insight: "AnthropometryInsightV1" = state["insight"]
    critic_verdict: str = state["critic_verdict"]
    analysis_context: "AnalysisContext" = state["analysis_context"]

    if critic_verdict not in _PERSISTED_CRITIC_VERDICTS:
        raise ValueError(
            "guardrails_step recibió un critic_verdict fuera del enum persistido "
            f"de cinco valores: {critic_verdict!r} (¿se pasó por error el "
            "vocabulario crudo de tres valores del crítico? ver schemas.py, nota "
            "de colisión de nombres)."
        )

    rendered_text = render_markdown_free(insight)

    guardrails = Guardrails(
        age_group=analysis_context.identity.get("age_group"),
        use_case=ANTHROPOMETRY_INSIGHT_USE_CASE,
        audience=insight.audience,
        velocity_reliable=_velocity_reliable(analysis_context),
        phase_crossing_corroborated=_phase_crossing_corroborated(analysis_context),
    )
    report = guardrails.scrub_with_report(rendered_text)

    rule_ids = sorted(set(report.violations))
    scrub_count = len(report.violations)

    if report.rejected:
        # Mismo mensaje que ``Guardrails.scrub()`` (la API que usa el caso de uso
        # legado) para que ``contracts/measurement-analysis-api.md`` §5 ("502 —
        # Unchanged mapping; now can also fire from guardrails_step.py") sea
        # literalmente cierto: el router no necesita distinguir de dónde vino el
        # rechazo. Nunca se degrada a un estado "solo entrenador" — un rechazo
        # aquí aborta la corrida completa, no persiste nada.
        logger.error(
            "anthro.guardrails_step: defensa final rechazó el texto renderizado "
            "(critic_verdict=%s, reglas=%s, scrubs=%d)",
            critic_verdict,
            rule_ids,
            scrub_count,
        )
        raise LLMSchemaError(f"Respuesta rechazada por guardrails: {report.violations}")

    guardrail_outcome = "scrubbed" if scrub_count else "clean"

    # FR-016 / data-model.md §3 "Family delivery gate": pertenencia pura al
    # conjunto {approved, revised}, sin caveat para los otros tres valores — este
    # paso NUNCA inventa un texto de aviso para la familia (eso es
    # responsabilidad exclusiva del frontend: mensaje pasivo compartido
    # "sin análisis todavía").
    family_deliverable = critic_verdict in FAMILY_DELIVERABLE_VERDICTS

    trace_metadata = build_structural_metadata(
        guardrail_rule_ids=rule_ids,
        guardrail_scrub_count=scrub_count,
        critic_verdict=critic_verdict,
    )

    return {
        "guardrail_rendered_text": report.text,
        "guardrail_violations": report.violations,
        "guardrail_rule_ids": rule_ids,
        "guardrail_scrub_count": scrub_count,
        "guardrail_outcome": guardrail_outcome,
        "guardrail_trace_metadata": trace_metadata,
        "family_deliverable": family_deliverable,
    }
