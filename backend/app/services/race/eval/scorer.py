"""Rule-based scorer + composite score para eval del ``RaceAnalystAgent``.

Score ∈ [0.0, 1.0] con 8 sub-rúbricas independientes (workflow §7.4 +
correcciones US2/specs/036 — T050/T052):

| Peso  | Rúbrica                                  | Pass condition                                |
|-------|------------------------------------------|-----------------------------------------------|
| 0.20  | Themes presentes                         | TODOS los ``expected_themes`` aparecen        |
| 0.20  | Sin términos prohibidos                  | NINGÚN ``forbidden_term`` aparece             |
| 0.10  | Word count dentro de rango               | ``50 <= word_count <= max_words``             |
| 0.10  | Estructura markdown completa             | 3 secciones canónicas v2 presentes            |
| 0.10  | Citas (must_cite)                        | ``len(citations_used) >= 1`` si must_cite     |
| 0.10  | Sin cifras repetidas (Sección 1)         | ningún tiempo/gap se repite en 2+ oraciones   |
| 0.10  | Conectores analíticos por sección        | ≥1 conector relacional en cada una de las 3   |
| 0.10  | Sin muletilla de vueltas                 | no aparece si el caso no declara dato de vueltas |

Decisiones de diseño:

- **Substring case-insensitive** para themes/forbidden. Razón: el LLM
  varía conjugaciones ("evolución" / "evoluciona") — Una validación más
  estricta produciría falsos negativos. Si en el futuro queremos
  precisión, usar embeddings (deferido a fase 2).
- **All-or-nothing en themes/forbidden.** Un solo theme ausente = 0.0
  en ese sub-score. Razón: la rúbrica es "verifica que el output cubre
  lo esencial", y un theme faltante revela un sesgo del prompt.
- **Estructura markdown (v2 — specs/036 T050):** el pipeline real
  (``RaceAnalystAgent.invoke_per_valida``, prompt ``race_analyst_v2.md``)
  produce **3** secciones — "Qué pasó en esta válida", "Recorrido hasta
  acá", "Hacia dónde va" — no las 5 de v1 (``invoke`` / ``race_analyst_v1.md``).
  Antes de T050 este scorer verificaba las 5 secciones v1 mientras el
  runner invocaba v1 — ambos lados coherentes entre sí, pero ninguno
  medía el pipeline que corre en producción. Matcheamos sobre
  ``raw_markdown`` por substring case-insensitive, con alternativas
  con/sin tilde por sección (mismo criterio que
  ``agents/analyst.py::_SECTION_KEYS_V2``) para tolerar variantes del LLM.
- **Citas:** si ``must_cite=False`` en el caso, este sub-score es 1.0
  por default (no penalizar al output por algo que no se exigía).
- **Cifras repetidas (T052-a):** el defecto documentado en
  ``spec.md`` US2 es literal — el mismo tiempo o gap aparece en dos
  oraciones distintas de la Sección 1 ("registrando un tiempo de
  0:36:19 ... El tiempo de carrera fue 0:36:19"). Se limita a la
  Sección 1 (no todo el documento) porque es ahí donde el prompt exige
  los datos duros (posición/tiempo/gap) y donde se observó la recitación.
- **Conectores analíticos (T052-b):** proxy barato de "esto no es un
  checklist" — exige al menos una construcción relacional (comparativa,
  causal o consecutiva) en CADA una de las 3 secciones v2. Una sección
  ausente cuenta como fallo (no hay dónde buscar el conector).
- **Muletilla de vueltas (T052-c):** hoy ``AnalysisInput`` no declara
  ningún campo de vueltas (verificado: no existe en
  ``app/services/race/schemas.py``), así que la mención "número de
  vueltas completadas"/"vueltas previstas" que el prompt v2 pedía es
  una alucinación forzada (ver ``spec.md`` US2, causa raíz). La
  detección de "dato de vueltas declarado" se hace sobre las claves
  crudas de ``case["input"]`` (cualquier clave con "lap"/"vuelta") en
  vez de importar ``AnalysisInput`` — así el scorer no asume el nombre
  final del campo si T055 decide agregarlo.

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
# Rebalanceados en T052 (specs/036) para hacer espacio a las 3 sub-rúbricas de
# calidad narrativa sin perder peso relativo de contenido (themes/forbidden
# siguen siendo el bloque más pesado) — ver docstring del módulo.
RULE_WEIGHTS: dict[str, float] = {
    "themes": 0.20,
    "forbidden": 0.20,
    "word_count": 0.10,
    "sections": 0.10,
    "citations": 0.10,
    "no_repeated_figures": 0.10,
    "connectors": 0.10,
    "no_lap_filler": 0.10,
}

# Secciones canónicas v2 (specs/036 T050) — cada entrada es una tupla de
# alternativas (con/sin tilde) para la MISMA sección; basta con que una de
# las alternativas aparezca. Nombres literales tomados de
# ``prompts/race_analyst_v2.md`` (bloque "Tarea"): "Qué pasó en esta
# válida" / "Recorrido hasta acá" / "Hacia dónde va". Mismo criterio de
# tolerancia a acentos que ``agents/analyst.py::_SECTION_KEYS_V2``.
_CANONICAL_SECTIONS: tuple[tuple[str, ...], ...] = (
    ("qué pasó en esta válida", "que paso en esta valida"),
    ("recorrido hasta acá", "recorrido hasta aca"),
    ("hacia dónde va", "hacia donde va"),
)

_MIN_WORDS = 50

# Patrones de "cifra" a vigilar por repetición dentro de la Sección 1
# (T052-a): tiempos ``hh:mm:ss`` (formato obligatorio del prompt v2) y
# gaps/porcentajes. Un mismo token repetido en 2+ oraciones distintas es
# la recitación documentada en spec.md US2.
_TIME_FIGURE_RE = re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b")
_PCT_FIGURE_RE = re.compile(r"\b\d{1,3}(?:[.,]\d+)?\s?%")

# Conectores analíticos (T052-b) — construcciones relacionales (comparativas,
# causales, consecutivas) que sirven de proxy barato de "esto sintetiza, no
# enumera". Substrings case-insensitive; se listan variantes con/sin tilde
# cuando la tilde cae dentro del token (mismo criterio que _CANONICAL_SECTIONS).
_CONNECTOR_PATTERNS: tuple[str, ...] = (
    "comparad", "a diferencia de", "mientras que", "en comparaci", "respecto a",
    "con relaci", "lo que indica", "lo cual indica", "en contraste",
    "por lo tanto", "por lo que", "debido a", "gracias a", "a pesar de",
    "en cambio", "sin embargo", "dado que", "ya que", "puesto que",
    "así como", "asi como", "en línea con", "en linea con", "producto de",
    "como resultado de", "esto significa", "esto llev", "esto se explica",
    "en consecuencia", "frente a", "en función de", "en funcion de",
    "a raíz de", "a raiz de",
)

# Muletilla de vueltas (T052-c) — frases que sólo tienen sentido si existe un
# dato real de vueltas completadas. Ver docstring del módulo.
_LAP_FILLER_PATTERNS: tuple[str, ...] = (
    "vueltas completadas",
    "numero de vueltas",
    "número de vueltas",
    "vueltas previst",
    "maximo de vueltas",
    "máximo de vueltas",
)


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
    """``True`` si las 3 secciones canónicas v2 aparecen (case-insensitive)."""
    if not markdown:
        return False
    norm = _normalize(markdown)
    return all(any(alt in norm for alt in group) for group in _CANONICAL_SECTIONS)


def _citations_satisfied(citations_used: list[str], must_cite: bool) -> bool:
    """``True`` si cumple regla de citas.

    - ``must_cite=False`` → siempre True (no se exigía citar).
    - ``must_cite=True`` → necesita ≥1 cita.
    """
    if not must_cite:
        return True
    return len(citations_used) >= 1


def _find_section_body(markdown: str, heading_alternatives: tuple[str, ...]) -> str:
    """Extrae el cuerpo de una sección ``## Heading`` v2 del markdown.

    Busca una línea de heading (cualquier nivel ``#``) cuyo título
    normalizado contenga alguna de ``heading_alternatives``, y devuelve
    todo el texto hasta el siguiente heading (o el final del documento).

    Returns:
        ``""`` si el heading no aparece — defensivo, no crashea; el
        caller decide si tratar la ausencia como fallo.
    """
    lines = markdown.splitlines()
    body: list[str] = []
    capturing = False
    for line in lines:
        heading_match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading_match:
            if capturing:
                break  # Siguiente heading → cierra la sección que veníamos capturando.
            title_norm = _normalize(heading_match.group(1))
            if any(alt in title_norm for alt in heading_alternatives):
                capturing = True
            continue
        if capturing:
            body.append(line)
    return "\n".join(body).strip()


def _split_into_sentences(text: str) -> list[str]:
    """Divide texto en oraciones — separador simple por puntuación fuerte o salto de línea.

    No pretende ser un tokenizador lingüístico completo; alcanza para
    detectar "misma cifra en 2 oraciones distintas" (T052-a), que es lo
    único que consume esta función.
    """
    raw = re.split(r"[.!?\n]+", text)
    return [s.strip() for s in raw if s.strip()]


def _no_repeated_figures_in_section_1(markdown: str) -> bool:
    """``True`` si ningún tiempo/gap se repite en 2+ oraciones de la Sección 1.

    Defecto documentado en spec.md US2: "El tiempo de carrera fue 0:36:19"
    reafirma un dato ya dado en la oración anterior. Se limita a la
    Sección 1 v2 ("Qué pasó en esta válida") — ahí es donde el prompt
    exige los datos duros y donde se observó la recitación.

    Edge case: si la Sección 1 no aparece o no contiene cifras, no hay
    nada que repetir → ``True`` (esta rúbrica no duplica el trabajo de
    ``_has_all_canonical_sections``, que ya penaliza la sección ausente).
    """
    section_1 = _find_section_body(markdown, _CANONICAL_SECTIONS[0])
    if not section_1:
        return True
    sentences = _split_into_sentences(section_1)
    seen_in_sentence_count: dict[str, int] = {}
    for sentence in sentences:
        tokens = set(_TIME_FIGURE_RE.findall(sentence)) | set(
            m.strip() for m in _PCT_FIGURE_RE.findall(sentence)
        )
        for token in tokens:
            seen_in_sentence_count[token] = seen_in_sentence_count.get(token, 0) + 1
    return all(count <= 1 for count in seen_in_sentence_count.values())


def _has_connector(text: str) -> bool:
    """``True`` si ``text`` contiene al menos un conector analítico."""
    norm = _normalize(text)
    return any(p in norm for p in _CONNECTOR_PATTERNS)


def _all_sections_have_connectors(markdown: str) -> bool:
    """``True`` si CADA una de las 3 secciones v2 trae ≥1 conector analítico.

    Una sección ausente cuenta como fallo — no hay contenido donde
    buscar el conector, y ya la penaliza por separado ``sections``.
    """
    for group in _CANONICAL_SECTIONS:
        body = _find_section_body(markdown, group)
        if not body or not _has_connector(body):
            return False
    return True


def _case_declares_lap_data(case_input: dict[str, Any]) -> bool:
    """``True`` si el caso golden trae algún campo de vueltas con valor no vacío.

    Hoy ``AnalysisInput`` no define ningún campo de vueltas — se busca
    cualquier clave que contenga "lap" o "vuelta" en vez de acoplarse a
    un nombre de campo concreto (ver docstring del módulo).
    """
    for key, value in case_input.items():
        key_l = key.lower()
        if ("lap" in key_l or "vuelta" in key_l) and value not in (None, "", [], {}):
            return True
    return False


def _no_lap_filler_when_absent(markdown: str, *, has_lap_data: bool) -> bool:
    """``True`` si la muletilla de vueltas NO aparece cuando no hay dato real.

    - ``has_lap_data=True`` → siempre ``True`` (mencionar vueltas es
      legítimo si el caso declara el dato).
    - ``has_lap_data=False`` → falla si aparece cualquiera de
      :data:`_LAP_FILLER_PATTERNS` en todo el documento (no sólo en la
      Sección 1 — "nunca aparece" es una aserción sobre el output completo).
    """
    if has_lap_data:
        return True
    norm = _normalize(markdown)
    return not any(p in norm for p in _LAP_FILLER_PATTERNS)


def rule_based_score(output: AnalysisOutput, case: dict[str, Any]) -> float:
    """Calcula score rule-based para un output del analyst contra un caso golden.

    Args:
        output: salida del :class:`RaceAnalystAgent`.
        case: dict cargado desde ``case_NNN.json`` con claves:
            ``expected_themes``, ``forbidden_terms``, ``max_words``,
            ``must_cite``, ``input`` (usado sólo por la rúbrica de vueltas,
            T052-c).

    Returns:
        Score ∈ [0.0, 1.0]. ``0.0`` indica fallo total en todas las
        sub-rúbricas; ``1.0`` cumple las 8.

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
    has_lap_data = _case_declares_lap_data(dict(case.get("input") or {}))

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
    if _no_repeated_figures_in_section_1(md):
        score += RULE_WEIGHTS["no_repeated_figures"]
    if _all_sections_have_connectors(md):
        score += RULE_WEIGHTS["connectors"]
    if _no_lap_filler_when_absent(md, has_lap_data=has_lap_data):
        score += RULE_WEIGHTS["no_lap_filler"]

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
