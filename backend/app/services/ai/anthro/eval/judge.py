"""LLM-as-judge del eval golden del análisis antropométrico (feature 042, T045).

Implementa ``specs/042-traceable-growth-ai/contracts/golden-eval-case.md`` §2/§6/§7.
Patrón copiado de ``app/services/race/eval/judge.py`` (misma forma: prompt Jinja2 +
parseo defensivo de JSON + fallback neutral en fallos de runtime) — texto de prompt
propio (``prompts/judge_anthropometry_v1.md``), NO el mismo archivo, porque la
rúbrica de 5 dimensiones es la de FR-035, no la del stack de carreras (`golden-
eval-case.md` §2, tabla "Judge rubric — canonical").

Diferencia deliberada frente al juez de carreras: allá el LLM promedia sus propias
5 sub-notas 0-10 y devuelve un único ``score``; aquí el LLM devuelve una nota
0.0-1.0 POR dimensión (``dimensions.grounding`` etc.) y la ponderación de FR-035
(0.30/0.20/0.20/0.15/0.15) se aplica en Python vía
``app.services.ai.anthro.eval.scorer.weighted_judge_score`` — determinístico,
auditable y testeable sin modelo real, en vez de confiar en que el LLM haga bien
la aritmética ponderada.

Stack: este eval mide el analista de ``app/services/ai/anthro/`` (rol
``"analyst"``/``"critic"`` del stack ``app``, nunca ``RACE_AI_*`` — CLAUDE.md,
"Two separate AI stacks"). El propio juez usa deliberadamente el modelo LEGACY
del stack app (``AI_MODEL``/default del proveedor, sin ``role=`` explícito) para
mantenerse independiente de qué modelo tengan configurado el analista/crítico —
mismo criterio que ``race/eval/judge.py::llm_judge_score`` documenta para su
propio juez.

Skip explícito sin clave de modelo real (spec.md edge case, contrato §6)
=========================================================================
"the developer runs the golden evaluation without a real model key: the run is
skipped with an explicit reason" — a diferencia del resto de fallos de runtime
(timeout, JSON malformado, excepción del SDK), que SÍ degradan a un score
neutral 0.5 por dimensión (mismo criterio que el juez de carreras: un juez caído
no debe ni hundir ni inflar el gate), la AUSENCIA de clave configurada es un
caso distinto a propósito: dejarlo caer al neutral 0.5 por-dimensión arriesgaría
que el eval completo "pase en verde" sin haber corrido nunca un juez real. Por
eso :func:`llm_judge_score` levanta :class:`JudgeModelUnavailableError` en vez
de degradar — el runner del eval (``backend/tests/evals/
test_anthropometry_analyst_eval.py``, T048, otro ownership) debe capturarla y
traducirla a un ``pytest.skip`` EXPLÍCITO, nunca a un ``pass`` silencioso.
:func:`has_configured_model_key` es la única fuente de verdad de esa
comprobación — el runner debe usarla también para su propio ``skipif``
declarativo, en vez de reinventar el chequeo de variables de entorno.

Privacidad (CLAUDE.md / Ley 1581): los doce casos golden son sintéticos
(``golden-eval-case.md`` §5) — el ``context_json``/``insight_json`` que este
módulo serializa hacia el prompt del juez nunca contiene un dato real de un
menor. ``JudgeResult.reasoning`` es texto libre del juez LLM: nunca se persiste
en ninguna tabla de producción, solo vive en el reporte del eval (mismo
tratamiento que el juez de carreras le da al suyo).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.config import settings
from app.services.ai.anthro.eval.scorer import JUDGE_DIMENSION_WEIGHTS, weighted_judge_score
from app.services.llm import observability
from app.services.llm.calls import call_llm
from app.services.llm.factory import build_chat_llm

if TYPE_CHECKING:
    from app.services.ai.anthro.context import AnalysisContext
    from app.services.ai.anthro.schemas import AnthropometryInsightV1

logger = logging.getLogger(__name__)

__all__ = [
    "JUDGE_PROMPT_PATH",
    "NO_MODEL_KEY_REASON",
    "JudgeModelUnavailableError",
    "JudgeResult",
    "build_judge_prompt",
    "has_configured_model_key",
    "llm_judge_score",
    "parse_judge_output",
]

JUDGE_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_anthropometry_v1.md"

# Score neutral por dimensión cuando el juez falla EN TIEMPO DE EJECUCIÓN (no por
# falta de clave — ver el docstring del módulo para la distinción). Mismo
# razonamiento que el juez de carreras: ni castiga ni premia de más un output
# que no se pudo evaluar de verdad.
_NEUTRAL_DIMENSION_SCORE = 0.5
_NEUTRAL_DIMENSION_SCORES: dict[str, float] = dict.fromkeys(
    JUDGE_DIMENSION_WEIGHTS, _NEUTRAL_DIMENSION_SCORE
)

# Fences ```json ... ``` (o ``` ... ```), tolerante a saltos de línea — mismo
# patrón que ``race/eval/judge.py``. No se replica el tercer intento de esa
# implementación (objeto JSON balanceado por regex de un solo nivel): con un
# objeto "dimensions" ANIDADO esa heurística de un solo nivel de llaves no
# funciona de forma confiable, y un falso "parseo exitoso" sobre datos a medias
# es peor que caer limpio al neutral documentado.
_FENCE_RE = re.compile(
    r"```(?:json)?\s*(?P<body>\{.*\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

NO_MODEL_KEY_REASON = (
    "AI_API_KEY (o GOOGLE_API_KEY) no configurada — el juez del eval de "
    "antropometría (stack app, nunca RACE_AI_*) no puede invocar un modelo "
    "real. Ver specs/042-traceable-growth-ai/spec.md, edge case: "
    "\"the developer runs the golden evaluation without a real model key\"."
)


class JudgeModelUnavailableError(RuntimeError):
    """No hay clave de modelo real configurada para correr el juez LLM.

    El runner del eval (T048) debe capturar esta excepción puntual y
    traducirla a un ``pytest.skip`` explícito con :data:`NO_MODEL_KEY_REASON`
    — nunca dejar que la corrida caiga en el score neutral y potencialmente
    reporte un composite ≥ threshold sin haber invocado un modelo real (ver
    el docstring del módulo).
    """


class JudgeResult:
    """Resultado del LLM-as-judge del análisis antropométrico.

    Atributos:
        dimension_scores: las 5 notas 0.0-1.0 devueltas por el LLM, una por
            cada clave de :data:`app.services.ai.anthro.eval.scorer.
            JUDGE_DIMENSION_WEIGHTS`.
        score: ``judge_score`` ya ponderado por FR-035
            (:func:`app.services.ai.anthro.eval.scorer.weighted_judge_score`)
            — el valor que se pasa a ``composite_score``.
        reasoning: explicación textual del juez (puede ser vacía si el parseo
            falló).
        parse_ok: ``True`` si el LLM devolvió JSON válido con las 5
            dimensiones (telemetría, igual que el precedente de carreras).
    """

    __slots__ = ("dimension_scores", "score", "reasoning", "parse_ok")

    def __init__(
        self,
        dimension_scores: dict[str, float],
        reasoning: str,
        parse_ok: bool,
    ) -> None:
        self.dimension_scores = dimension_scores
        self.score = weighted_judge_score(dimension_scores)
        self.reasoning = reasoning
        self.parse_ok = parse_ok

    def __repr__(self) -> str:  # pragma: no cover - solo debug
        return f"JudgeResult(score={self.score:.3f}, parse_ok={self.parse_ok})"


def has_configured_model_key() -> bool:
    """``True`` si hay una clave real configurada para el stack ``app``.

    Este pipeline corre el analista/crítico con ``stack="app"`` (nunca
    ``RACE_AI_*`` — CLAUDE.md, "Two separate AI stacks"): la clave relevante
    es ``AI_API_KEY`` (``Settings.ai_api_key``) o, para el proveedor Google
    por defecto de este stack, ``GOOGLE_API_KEY`` directo del entorno (mismo
    criterio de aceptar cualquiera de las dos que usa
    ``race/eval/judge.py``'s runner para su propio stack, vía
    ``RACE_AI_API_KEY``/``GOOGLE_API_KEY``).

    Es la única fuente de verdad de esta comprobación — tanto
    :func:`llm_judge_score` como el runner del eval (T048) deben usarla en
    vez de reinventar el chequeo de variables de entorno por separado, para
    que ambos concuerden siempre sobre si hay o no un modelo real disponible.
    """
    return bool(settings.ai_api_key or os.getenv("GOOGLE_API_KEY"))


def _render_context_json(context: "AnalysisContext") -> str:
    """Serializa el ``AnalysisContext`` (ya saneado) como JSON legible para el juez."""
    payload = {
        "identity": context.identity,
        "measurement_deltas": context.measurement_deltas,
        "longitudinal_series": context.longitudinal_series,
        "growth_summary": context.growth_summary,
        "training_load_window": context.training_load_window,
        "previous_analysis": context.previous_analysis,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _render_insight_json(insight: "AnthropometryInsightV1") -> str:
    """Serializa el insight final (dict o modelo Pydantic) a JSON legible."""
    dump = getattr(insight, "model_dump", None)
    payload = dump(mode="json") if callable(dump) else insight
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def build_judge_prompt(
    insight: "AnthropometryInsightV1",
    rendered_text: str,
    context: "AnalysisContext",
    case: dict[str, Any],
) -> str:
    """Renderiza ``judge_anthropometry_v1.md`` con el caso golden + el output real.

    Args:
        insight: ``AnthropometryInsightV1`` final que produjo el pipeline
            (analista, revisado por el crítico, o la plantilla de fallback).
        rendered_text: la misma prosa plana ya renderizada por
            ``app/services/ai/anthro/guardrails_step.py::render_markdown_free``
            que efectivamente vería la familia o el entrenador.
        context: el ``AnalysisContext`` que vio el analista para este caso —
            única fuente de verdad de "grounding" para el juez.
        case: dict del ``case_NNN.json`` cargado — usa ``case_id``,
            ``description``, ``expected_themes``, ``forbidden_terms``,
            ``max_words``, ``audience``, ``min_confidence_level``/
            ``max_confidence_level``.

    Returns:
        Prompt renderizado listo para enviar al LLM.

    Notas defensivas:
        Usa ``ChainableUndefined`` (mismo criterio que
        ``race/eval/judge.py::build_judge_prompt``): una clave de caso
        ausente se sustituye por un default vacío en vez de romper el eval
        por un caso golden incompleto.
    """
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(JUDGE_PROMPT_PATH.parent)),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=ChainableUndefined,
    )
    template = env.get_template(JUDGE_PROMPT_PATH.name)
    return template.render(
        case_id=case.get("case_id", "unknown"),
        case_description=case.get("description", ""),
        audience=case.get("audience", insight.audience),
        context_json=_render_context_json(context),
        insight_json=_render_insight_json(insight),
        rendered_text=rendered_text or "(texto vacío)",
        expected_themes=list(case.get("expected_themes") or []),
        forbidden_terms=list(case.get("forbidden_terms") or []),
        max_words=int(case.get("max_words") or 180),
        min_confidence_level=case.get("min_confidence_level"),
        max_confidence_level=case.get("max_confidence_level"),
    )


def parse_judge_output(raw_text: str) -> JudgeResult:
    """Parsea defensivamente el JSON emitido por el juez.

    Estrategia de fallback (en orden):

    1. ``json.loads(raw_text)`` directo.
    2. Buscar ``{...}`` dentro de fences ``` ```json``` ```.
    3. Si todo falla, o si el objeto parseado no trae las 5 claves de
       ``dimensions`` — :data:`_NEUTRAL_DIMENSION_SCORES` + ``parse_ok=False``.

    Returns:
        :class:`JudgeResult`.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("anthro_llm_judge: output vacío — usando neutral 0.5 por dimensión")
        return JudgeResult(dict(_NEUTRAL_DIMENSION_SCORES), reasoning="", parse_ok=False)

    text = raw_text.strip()

    parsed: Optional[dict[str, Any]] = None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if parsed is None:
        m = _FENCE_RE.search(text)
        if m:
            try:
                parsed = json.loads(m.group("body"))
            except (json.JSONDecodeError, ValueError):
                parsed = None

    if not isinstance(parsed, dict) or not isinstance(parsed.get("dimensions"), dict):
        logger.warning(
            "anthro_llm_judge: no se pudo parsear JSON con 'dimensions' (%s chars) — "
            "usando neutral 0.5 por dimensión",
            len(text),
        )
        return JudgeResult(
            dict(_NEUTRAL_DIMENSION_SCORES), reasoning="parse_error", parse_ok=False
        )

    raw_dimensions = parsed["dimensions"]
    dimension_scores: dict[str, float] = {}
    all_present_and_numeric = True
    for dimension in JUDGE_DIMENSION_WEIGHTS:
        value = raw_dimensions.get(dimension)
        try:
            dimension_scores[dimension] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            all_present_and_numeric = False
            dimension_scores[dimension] = _NEUTRAL_DIMENSION_SCORE

    if not all_present_and_numeric:
        logger.warning(
            "anthro_llm_judge: al menos una dimensión ausente o no numérica en el "
            "JSON del juez — sustituida por neutral 0.5, resto conservado"
        )

    reasoning = str(parsed.get("reasoning", "")).strip()
    return JudgeResult(
        dimension_scores, reasoning=reasoning, parse_ok=all_present_and_numeric
    )


async def llm_judge_score(
    insight: "AnthropometryInsightV1",
    rendered_text: str,
    context: "AnalysisContext",
    case: dict[str, Any],
    llm_factory: Optional[Callable[[], Any]] = None,
) -> JudgeResult:
    """Invoca el LLM-as-judge contra un insight del pipeline antropométrico.

    Args:
        insight: ``AnthropometryInsightV1`` final a evaluar.
        rendered_text: la prosa plana final (``render_markdown_free``).
        context: el ``AnalysisContext`` del caso — grounding del juez.
        case: dict del caso golden cargado de ``case_NNN.json``.
        llm_factory: callable ``() -> chat_model``. Si ``None`` usa
            :func:`app.services.llm.factory.build_chat_llm` con
            ``stack="app"`` (requiere ``AI_API_KEY``/``GOOGLE_API_KEY`` —
            ver :func:`has_configured_model_key`). Para tests, pasar
            ``llm_factory=lambda: GenericFakeChatModel(...)``.

    Returns:
        :class:`JudgeResult`.

    Raises:
        JudgeModelUnavailableError: ``llm_factory`` es ``None`` y
            :func:`has_configured_model_key` devuelve ``False`` — el runner
            (T048) debe traducir esto a un ``pytest.skip`` explícito, nunca
            dejar que la corrida siga y caiga en un score neutral (ver el
            docstring del módulo).
    """
    if llm_factory is None:
        if not has_configured_model_key():
            raise JudgeModelUnavailableError(NO_MODEL_KEY_REASON)
        # Deliberadamente el modelo LEGACY del stack app (sin ``role=``
        # explícito) — el juez debe permanecer independiente de qué modelo
        # tengan configurado el analista/crítico (ver docstring del módulo).
        llm = build_chat_llm(temperature=0.0, stack="app")
    else:
        llm = llm_factory()

    prompt = build_judge_prompt(insight, rendered_text, context, case)

    try:
        with observability.llm_tracing(
            trace_name="anthro-eval-judge",
            session_id=observability.keyed_session_id(
                f"anthro-eval:{case.get('case_id', 'unknown')}"
            ),
            tags=["anthro-judge-v1"],
        ) as tracing:
            call = await call_llm(llm, prompt, config=tracing, stack="app")
    except Exception as exc:  # noqa: BLE001 — un juez caído nunca debe tumbar el eval.
        logger.warning(
            "anthro_llm_judge: llamada al LLM falló (%s) — neutral 0.5 por dimensión", exc
        )
        return JudgeResult(
            dict(_NEUTRAL_DIMENSION_SCORES), reasoning="llm_error", parse_ok=False
        )

    return parse_judge_output(call.text)
