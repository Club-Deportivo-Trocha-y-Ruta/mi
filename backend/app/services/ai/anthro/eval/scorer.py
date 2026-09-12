"""Scorer del eval golden del análisis antropométrico (feature 042, T044).

Implementa ``specs/042-traceable-growth-ai/contracts/golden-eval-case.md`` §2 y
reusa, sin reimplementarla, la fórmula de composición del eval de carreras
(``app/services/race/eval/scorer.py::composite_score``,
``composite = 0.4 * rule + 0.6 * judge``) — el contrato es explícito
("Composite formula — reused verbatim, not re-derived") y ambos evals deben
poder cambiar de threshold o de peso rule/judge en un único lugar sin que uno
se desincronice del otro.

Dos piezas independientes viven aquí, correspondientes a las dos mitades del
``composite_score`` de arriba:

1. :func:`rule_based_score` — el ``rule`` determinista (§2 del contrato):
   "the deterministic R01–R12 pass/fail rate (§3) plus the case-level
   expected_themes/forbidden_terms/max_words checks". Corre
   ``app/services/ai/anthro/prechecks.py::run_prechecks`` (T029, catálogo
   R01-R12) sobre el borrador y combina esa tasa de aprobación con los tres
   chequeos de caso — mismo estilo "todo o nada por sub-rúbrica, pesos que
   suman 1.0" que el precedente de carreras, para que ambos scorers se lean
   igual a quien ya conoce uno.
2. :data:`JUDGE_DIMENSION_WEIGHTS` / :func:`weighted_judge_score` — los
   pesos de las 5 dimensiones del juez LLM que exige FR-035 (§2 del
   contrato, tabla "Judge rubric — canonical"): grounding 0.30, uncertainty
   calibration 0.20, privacy/developmental safety 0.20, tone/format 0.15,
   actionability 0.15. A diferencia del juez de carreras (que le pide al
   propio LLM que promedie sus 5 sub-notas 0-10 y devuelva un único
   ``score``), aquí el LLM devuelve una nota 0.0-1.0 POR dimensión
   (``app/services/ai/anthro/eval/judge.py``, T045) y la ponderación FR-035
   se aplica en Python — determinística, auditable y testeable sin
   necesidad de un modelo real (a diferencia de confiar en que el LLM haga
   bien la aritmética ponderada él mismo).

Decisión de diseño — pesos de :data:`RULE_WEIGHTS`: el contrato fija el
CATÁLOGO de reglas (R01-R12, "must_block" vs "degrade", §3) y la fórmula de
composición (§2), pero no fija un desglose numérico de cuánto pesa "la tasa
R01-R12" frente a cada chequeo de caso individual — eso queda, como en el
precedente de carreras, a discreción del scorer. Se eligió 0.70 para la tasa
de aprobación de las doce reglas (es la defensa determinista central de
privacidad/seguridad de desarrollo y grounding: debe dominar el ``rule``
score) y 0.10 para cada uno de los tres chequeos de caso restantes
(``expected_themes``/``forbidden_terms``/``max_words``, mismo peso relativo
entre sí que el precedente de carreras les da a sus propias sub-rúbricas de
contenido).

No hay estado ni I/O en este módulo — funciones puras sobre los objetos ya
resueltos por el pipeline (T026-T039) y el dict del caso golden cargado por
el runner (T048, otro ownership).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Mapping

from app.services.ai.anthro.guardrails_step import render_markdown_free
from app.services.ai.anthro.prechecks import PrecheckResult, run_prechecks
from app.services.race.eval.scorer import composite_score

if TYPE_CHECKING:
    from app.services.ai.anthro.context import AnalysisContext
    from app.services.ai.anthro.schemas import AnthropometryInsightV1

__all__ = [
    "COMPOSITE_THRESHOLD",
    "RULE_WEIGHTS",
    "JUDGE_DIMENSION_WEIGHTS",
    "composite_score",
    "precheck_pass_rate",
    "rule_based_score",
    "weighted_judge_score",
]


# Threshold único del eval — verbatim de ``golden-eval-case.md`` §2/§6: "matching
# the race analyst's bar exactly (lead ruling 12)". Exportado para que el runner
# (T048) y el workflow de CI (T049) lean el mismo valor en vez de repetir el
# literal en tres lugares.
COMPOSITE_THRESHOLD: float = 0.75

# Número total de reglas del catálogo (data-model.md §2.3 / golden-eval-case.md §3).
_TOTAL_PRECHECK_RULES: int = 12

# Pesos del ``rule`` score (deben sumar 1.0) — ver la nota de diseño del
# docstring del módulo para el porqué del reparto 0.70/0.10/0.10/0.10.
RULE_WEIGHTS: dict[str, float] = {
    "prechecks": 0.70,
    "expected_themes": 0.10,
    "forbidden_terms": 0.10,
    "max_words": 0.10,
}

# Pesos canónicos de la rúbrica del juez LLM — verbatim de FR-035 /
# ``golden-eval-case.md`` §2 ("Judge rubric — canonical"). NO usar la tabla
# alternativa de ``architecture.md`` §4.7 (schema/grounding/forbidden/
# no_diagnosis/headline/word_limits/coach_question) — está redactada contra un
# ``coach_question`` que ``AnthropometryInsightV1`` no tiene; el contrato es
# explícito en descartarla.
JUDGE_DIMENSION_WEIGHTS: dict[str, float] = {
    "grounding": 0.30,
    "uncertainty_calibration": 0.20,
    "privacy_developmental_safety": 0.20,
    "tone_and_format": 0.15,
    "actionability": 0.15,
}


def _normalize(text: str) -> str:
    """Lowercase + colapso de espacios, para matching case-insensitive.

    Mismo criterio que ``race/eval/scorer.py::_normalize`` — duplicado
    deliberado de dos líneas en vez de importar un símbolo privado (``_``)
    de otro módulo.
    """
    return re.sub(r"\s+", " ", text.lower()).strip()


def _all_themes_present(rendered_text: str, themes: list[str]) -> bool:
    """``True`` si todos los ``expected_themes`` aparecen como substring.

    ``themes`` vacío → ``True`` (nada que validar), mismo criterio que el
    precedente de carreras.
    """
    if not themes:
        return True
    norm = _normalize(rendered_text)
    return all(_normalize(t) in norm for t in themes)


def _no_forbidden_terms(rendered_text: str, forbidden: list[str]) -> bool:
    """``True`` si NINGÚN ``forbidden_term`` aparece (substring case-insensitive)."""
    if not forbidden:
        return True
    norm = _normalize(rendered_text)
    return all(_normalize(t) not in norm for t in forbidden)


def _within_case_word_limit(rendered_text: str, max_words: int | None) -> bool:
    """``True`` si el conteo de palabras del texto renderizado respeta ``max_words``.

    ``max_words`` ausente/``0``/negativo en el caso golden → ``True`` (nada que
    validar a este nivel; R07 ya cubre el presupuesto por audiencia sobre el
    MISMO texto renderizado, con su propia tolerancia del 10%). Cuando el caso
    sí declara un límite, se le aplica la misma tolerancia del 10% que R07
    (``app/services/ai/anthro/schemas.py::WORD_BUDGET_TOLERANCE_FACTOR``) para
    no penalizar dos veces con criterios de redondeo distintos el mismo tipo
    de desborde.
    """
    if not max_words or max_words <= 0:
        return True
    from app.services.ai.anthro.schemas import WORD_BUDGET_TOLERANCE_FACTOR, count_words

    return count_words(rendered_text) <= max_words * WORD_BUDGET_TOLERANCE_FACTOR


def precheck_pass_rate(result: PrecheckResult) -> float:
    """Fracción de las doce reglas R01-R12 SIN violación, en ``[0.0, 1.0]``.

    Cada regla pesa lo mismo dentro de esta sub-tasa — el catálogo mismo ya
    distingue severidad vía ``must_block`` (data-model.md §2.3); esta función
    no lo vuelve a ponderar, solo mide cuántas reglas dispararon en total.
    """
    passed = _TOTAL_PRECHECK_RULES - len(result.violations)
    return max(0.0, min(1.0, passed / _TOTAL_PRECHECK_RULES))


def rule_based_score(
    insight: "AnthropometryInsightV1",
    context: "AnalysisContext",
    case: Mapping[str, Any],
    *,
    forbidden_names: tuple[str, ...] = (),
) -> float:
    """Calcula el ``rule`` determinista de un insight contra un caso golden.

    Args:
        insight: borrador (o insight final) del analista/crítico a evaluar —
            un ``AnthropometryInsightV1`` válido.
        context: el mismo ``AnalysisContext`` que vio el analista para este
            caso (necesario para R03/R05/R08/R11, que cruzan contra el
            contexto en vez de ser un juicio del LLM crítico).
        case: dict del ``case_NNN.json`` cargado — usa ``expected_themes``,
            ``forbidden_terms`` y ``max_words`` (``golden-eval-case.md`` §1).
        forbidden_names: nombres prohibidos del club para R06 — vacío por
            defecto (los doce casos golden son sintéticos, sin roster real
            que cargar; ver ``golden-eval-case.md`` §5).

    Returns:
        Score en ``[0.0, 1.0]``. ``1.0`` solo si las doce reglas pasan y los
        tres chequeos de caso también.

    Notas defensivas:
        Si el caso no trae alguna clave esperada, se asume el default
        permisivo (lista vacía / sin límite) — evita que un caso golden
        incompleto tumbe el scorer con un ``KeyError``; la validación de
        completitud del schema del caso es responsabilidad del runner (T048).
    """
    rendered_text = render_markdown_free(insight)
    precheck_result = run_prechecks(insight, context, forbidden_names=forbidden_names)

    themes = list(case.get("expected_themes") or [])
    forbidden = list(case.get("forbidden_terms") or [])
    max_words = case.get("max_words")

    score = RULE_WEIGHTS["prechecks"] * precheck_pass_rate(precheck_result)
    if _all_themes_present(rendered_text, themes):
        score += RULE_WEIGHTS["expected_themes"]
    if _no_forbidden_terms(rendered_text, forbidden):
        score += RULE_WEIGHTS["forbidden_terms"]
    if _within_case_word_limit(rendered_text, max_words):
        score += RULE_WEIGHTS["max_words"]

    # Defensa: clamp [0, 1] por seguridad ante errores de pesos futuros.
    return max(0.0, min(1.0, round(score, 4)))


def weighted_judge_score(dimension_scores: Mapping[str, float]) -> float:
    """Combina las 5 notas por-dimensión del juez LLM con los pesos de FR-035.

    Args:
        dimension_scores: dict con EXACTAMENTE las 5 claves de
            :data:`JUDGE_DIMENSION_WEIGHTS` (``grounding``,
            ``uncertainty_calibration``, ``privacy_developmental_safety``,
            ``tone_and_format``, ``actionability``), cada una en ``[0, 1]``
            (o coercible a ``float``; se clampea defensivamente).

    Returns:
        ``judge_score`` en ``[0.0, 1.0]``, listo para pasar a
        :func:`composite_score` junto con :func:`rule_based_score`.

    Raises:
        KeyError: falta alguna de las 5 dimensiones — a propósito, no se
            sustituye por un neutral aquí: ese fallback "no silencioso" vive
            en ``judge.py`` (T045), que decide explícitamente cuándo degradar
            a neutral (fallo del LLM) frente a cuándo fallar duro (bug de
            programación en el caller, p. ej. un dict incompleto pasado a
            mano en un test).
    """
    total = 0.0
    for dimension, weight in JUDGE_DIMENSION_WEIGHTS.items():
        raw_value = float(dimension_scores[dimension])
        total += weight * max(0.0, min(1.0, raw_value))
    return round(total, 4)
