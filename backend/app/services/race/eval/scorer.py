"""Rule-based scorer + composite score para eval del ``RaceAnalystAgent``.

Score ∈ [0.0, 1.0] con 5 sub-rúbricas independientes (workflow §7.4):

| Peso  | Rúbrica                                  | Pass condition                                |
|-------|------------------------------------------|-----------------------------------------------|
| 0.25  | Themes presentes                         | TODOS los ``expected_themes`` aparecen        |
| 0.25  | Sin términos prohibidos                  | NINGÚN ``forbidden_term`` aparece             |
| 0.20  | Word count dentro de rango               | ``50 <= word_count <= max_words``             |
| 0.15  | Estructura markdown completa             | 5 secciones canónicas presentes               |
| 0.15  | Citas (must_cite)                        | ``len(citations_used) >= 1`` si must_cite     |

Decisiones de diseño:

- **Substring case-insensitive** para themes/forbidden. Razón: el LLM
  varía conjugaciones ("evolución" / "evoluciona") — Una validación más
  estricta produciría falsos negativos. Si en el futuro queremos
  precisión, usar embeddings (deferido a fase 2).
- **All-or-nothing en themes/forbidden.** Un solo theme ausente = 0.0
  en ese sub-score. Razón: la rúbrica es "verifica que el output cubre
  lo esencial", y un theme faltante revela un sesgo del prompt.
- **Estructura markdown:** las 5 secciones canónicas son
  ``Evolución``, ``Técnico``, ``Recomendaciones``, ``Riesgos``,
  ``Próximos Pasos`` (mismas keys del :class:`AnalysisOutput.sections`,
  pero matcheamos sobre ``raw_markdown`` por substring case-insensitive
  para tolerar variaciones del LLM como "Análisis Técnico").
- **Citas:** si ``must_cite=False`` en el caso, este sub-score es 1.0
  por default (no penalizar al output por algo que no se exigía).

Composite (workflow §7.6):

    composite = 0.4 * rule + 0.6 * judge

Razón del peso: el juez LLM es más holístico, captura tono/rigor; el
rule scorer es determinístico y bloquea regresiones obvias. Si quitamos
el juez (sin AI_API_KEY), composite cae a ``rule`` directamente vía el
runner — el scorer no decide eso, sólo expone la fórmula.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.race.schemas import AnalysisOutput

__all__ = [
    "RULE_WEIGHTS",
    "composite_score",
    "rule_based_score",
]


# Pesos (deben sumar 1.0). Exportados para tests y para documentar la rúbrica.
RULE_WEIGHTS: dict[str, float] = {
    "themes": 0.25,
    "forbidden": 0.25,
    "word_count": 0.20,
    "sections": 0.15,
    "citations": 0.15,
}

# Secciones canónicas — substrings que deben aparecer en el markdown.
# Tolerantes a variantes "Análisis Técnico" / "Técnico" / "Riesgos detectados".
_CANONICAL_SECTIONS: tuple[str, ...] = (
    "evoluci",       # Evolución / evolucion
    "técnic",        # Técnico / Análisis Técnico / tecnica
    "recomendac",    # Recomendaciones / Recomendaciones LTAD
    "riesgo",        # Riesgos / Riesgo detectado
    "próximos pas",  # Próximos pasos / Próximos Pasos
)

_MIN_WORDS = 50


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace para matching case-insensitive."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _all_themes_present(markdown: str, themes: list[str]) -> bool:
    """``True`` si todos los themes aparecen como substring case-insensitive.

    Edge cases:
    - ``themes`` vacío → ``True`` (no había nada que validar).
    - ``markdown`` vacío → ``False`` salvo themes vacío.
    """
    if not themes:
        return True
    norm = _normalize(markdown)
    return all(_normalize(t) in norm for t in themes)


def _no_forbidden_terms(markdown: str, forbidden: list[str]) -> bool:
    """``True`` si NINGÚN término prohibido aparece.

    Edge: ``forbidden`` vacío → ``True``.
    """
    if not forbidden:
        return True
    norm = _normalize(markdown)
    return all(_normalize(t) not in norm for t in forbidden)


def _word_count_in_range(word_count: int, max_words: int) -> bool:
    """``True`` si ``_MIN_WORDS <= word_count <= max_words``."""
    if max_words <= 0:
        return False
    return _MIN_WORDS <= word_count <= max_words


def _has_all_canonical_sections(markdown: str) -> bool:
    """``True`` si las 5 secciones canónicas aparecen (case-insensitive)."""
    if not markdown:
        return False
    norm = _normalize(markdown)
    return all(s in norm for s in _CANONICAL_SECTIONS)


def _citations_satisfied(citations_used: list[str], must_cite: bool) -> bool:
    """``True`` si cumple regla de citas.

    - ``must_cite=False`` → siempre True (no se exigía citar).
    - ``must_cite=True`` → necesita ≥1 cita.
    """
    if not must_cite:
        return True
    return len(citations_used) >= 1


def rule_based_score(output: AnalysisOutput, case: dict[str, Any]) -> float:
    """Calcula score rule-based para un output del analyst contra un caso golden.

    Args:
        output: salida del :class:`RaceAnalystAgent`.
        case: dict cargado desde ``case_NNN.json`` con claves:
            ``expected_themes``, ``forbidden_terms``, ``max_words``,
            ``must_cite``.

    Returns:
        Score ∈ [0.0, 1.0]. ``0.0`` indica fallo total en todas las
        sub-rúbricas; ``1.0`` cumple las 5.

    Notas defensivas:
        - Si el caso no trae alguna clave esperada, se asume default
          permisivo (lista vacía, must_cite=False, max_words=600).
          Razón: evitar crashes si un caso golden está incompleto;
          el test ``test_eval_loader_validates_case_schema`` valida
          completitud por separado.
    """
    md = output.raw_markdown or ""
    themes = list(case.get("expected_themes") or [])
    forbidden = list(case.get("forbidden_terms") or [])
    max_words = int(case.get("max_words") or 600)
    must_cite = bool(case.get("must_cite", False))

    score = 0.0
    if _all_themes_present(md, themes):
        score += RULE_WEIGHTS["themes"]
    if _no_forbidden_terms(md, forbidden):
        score += RULE_WEIGHTS["forbidden"]
    if _word_count_in_range(output.word_count, max_words):
        score += RULE_WEIGHTS["word_count"]
    if _has_all_canonical_sections(md):
        score += RULE_WEIGHTS["sections"]
    if _citations_satisfied(list(output.citations_used), must_cite):
        score += RULE_WEIGHTS["citations"]

    # Defensa: clamp [0, 1] por seguridad ante errores de pesos.
    return max(0.0, min(1.0, round(score, 4)))


def composite_score(rule: float, judge: float) -> float:
    """Combina rule + judge con la fórmula del workflow §7.6.

    ``composite = 0.4 * rule + 0.6 * judge``.

    Inputs fuera de [0, 1] se clampean defensivamente (logged warning
    en el runner, no aquí).
    """
    rule = max(0.0, min(1.0, float(rule)))
    judge = max(0.0, min(1.0, float(judge)))
    return round(0.4 * rule + 0.6 * judge, 4)
