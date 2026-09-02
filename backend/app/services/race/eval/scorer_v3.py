"""Rule-based scorer del eval v3 (``InsightV3``) — feature 037, T401.

Por qué un scorer nuevo y no una extensión de :mod:`scorer`
==========================================================
El scorer v2 puntúa **markdown**: busca 3 headings canónicos, conectores
relacionales y repetición de cifras dentro de la Sección 1. El analista v3
ya no produce markdown: produce un :class:`~app.services.race.insight_v3.InsightV3`
validado por Pydantic, del que el markdown es una *proyección*
(``render_insight_v3_markdown``). Medir la proyección sería medir nuestro
propio renderer; lo que hay que medir es el objeto.

Rúbrica (pesos suman 1.0 — ``RULE_WEIGHTS_V3``)
===============================================

| Peso | Rúbrica            | Qué verifica                                                      |
|------|--------------------|-------------------------------------------------------------------|
| 0.15 | ``schema``         | Objeto válido, cardinalidades, coherencia de ``field_reading``, no fallback |
| 0.25 | ``grounding``      | Cada número de headline/claim/evidence existe en los datos del caso |
| 0.15 | ``forbidden``      | Ningún término prohibido y ningún issue ``privacy``/``ltad`` de los prechecks |
| 0.10 | ``catalog``        | ``catalog_ref`` existentes (+ al menos uno si el caso lo exige)     |
| 0.10 | ``headline``       | No es plantilla y comparte ≥1 keyword esperada                      |
| 0.10 | ``themes``         | Proporción de ``expected_themes`` presentes en el texto             |
| 0.10 | ``word_limits``    | Presupuestos de palabras del prompt v3                              |
| 0.05 | ``coach_question`` | Exactamente una pregunta, no vacía, termina en "?"                  |

Decisiones de diseño
====================

- **Grounding proporcional, no binario (0.25, el peso más alto).** Es el
  defecto que más duele en producción: una cifra inventada convierte el
  insight en desinformación. Se puntúa como fracción de tokens numéricos
  respaldados para que el scoreboard distinga "una cifra suelta mal citada"
  de "el modelo alucina la mitad de la evidencia" — un booleano colapsaría
  ambos casos en 0.
- **Fuente de verdad del grounding = SOLO los bloques de datos**, no el
  prompt renderizado completo. ``AnalystV3Input`` → ``_build_v3_context``
  produce los bloques (carrera, pelotón, temporada, condiciones,
  maduración, entrenamiento, diálogo, catálogo); el prompt además contiene
  un **ejemplo resuelto** con cifras ficticias (58.3, 0:03:12, 62.5…). Si
  el eval usara ``V3CallResult.grounding_numbers`` (tokens del prompt
  entero, que es lo correcto para el precheck de producción, más
  permisivo a propósito), un modelo que copiara los números del ejemplo
  puntuaría perfecto en la rúbrica que existe justamente para detectar eso.
- **Reutilización, no duplicación.** La extracción/normalización numérica
  es :func:`app.services.race.insight_v3.extract_numeric_tokens` (la misma
  que alimenta ``grounding_numbers`` en producción) y las reglas de
  privacidad/LTAD/catálogo son :func:`app.services.race.ai.prechecks.run_prechecks`
  (las mismas que corre el critic v3). Este módulo no reimplementa ninguna:
  solo las pondera.
- **Sub-rúbricas parciales donde hay gradiente** (grounding, themes,
  word_limits, schema, catalog) y binarias donde el fallo es categórico
  (forbidden, headline, coach_question). ``themes`` deja de ser
  all-or-nothing como en v2: con 3-4 themes por caso, castigar con 0 la
  ausencia de uno solo hace la métrica ciega a las mejoras parciales.
- **Composite**: se reexporta :func:`app.services.race.eval.scorer.composite_score`
  (``0.4 * rule + 0.6 * judge``) — misma fórmula que v2, un solo lugar donde
  cambiarla.

Privacidad: este módulo nunca loggea el contenido del draft ni de los casos.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from app.services.race.eval.scorer import composite_score
from app.services.race.insight_v3 import (
    InsightV3,
    extract_numeric_tokens,
    render_insight_v3_markdown,
)

__all__ = [
    "RULE_WEIGHTS_V3",
    "case_data_blocks",
    "case_grounding_numbers",
    "composite_score",
    "rule_based_score_v3",
    "rule_subscores_v3",
]


RULE_WEIGHTS_V3: dict[str, float] = {
    "schema": 0.15,
    "grounding": 0.25,
    "forbidden": 0.15,
    "catalog": 0.10,
    "headline": 0.10,
    "themes": 0.10,
    "word_limits": 0.10,
    "coach_question": 0.05,
}

# Presupuestos declarados en ``prompts/race_analyst_v3.md`` §Método.
_HEADLINE_MAX_WORDS = 30
_CLAIM_MAX_WORDS = 45
_EVIDENCE_MAX_WORDS = 20
_ACTION_MAX_WORDS = 40
_DEFAULT_MAX_WORDS = 450

# Aperturas de plantilla: el defecto documentado en spec.md §problem 2 es un
# headline que describe el resultado ("La deportista finalizó en la posición
# 4…") en vez de explicar la causa. Se detecta por prefijo, ya normalizado
# (minúsculas, sin tildes).
_TEMPLATE_HEADLINE_PREFIXES: tuple[str, ...] = (
    "la deportista finalizo",
    "el deportista finalizo",
    "la deportista completo",
    "el deportista completo",
    "la deportista termino",
    "el deportista termino",
)

_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")


def _normalize(text: str) -> str:
    """Minúsculas + espacios colapsados (conserva tildes)."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _deaccent(text: str) -> str:
    """Normaliza y quita tildes — solo para el matcheo del headline plantilla."""
    return _normalize(text).translate(_ACCENTS)


def _word_count(text: str) -> int:
    return len([w for w in (text or "").split() if w])


def _as_insight(output: Any) -> InsightV3 | None:
    """Acepta ``InsightV3`` o dict; ``None`` si no valida."""
    if isinstance(output, InsightV3):
        return output
    if isinstance(output, Mapping):
        try:
            return InsightV3.model_validate(dict(output))
        except Exception:  # noqa: BLE001 - el score decide, no explota
            return None
    return None


def _draft_text_fields(draft: InsightV3) -> list[str]:
    """Campos de texto libre del draft (para themes/forbidden)."""
    parts: list[str] = [draft.headline, draft.coach_question]
    if draft.field_reading is not None:
        parts.extend([draft.field_reading.series_label, draft.field_reading.summary])
    for obs in draft.observations:
        parts.append(obs.claim)
        parts.extend(obs.evidence)
    for action in draft.actions:
        parts.append(action.text)
    parts.extend(draft.watch_signals)
    parts.extend(draft.data_gaps)
    parts.extend(draft.principles_cited)
    return [p for p in parts if p]


def _grounded_text_fields(draft: InsightV3) -> list[str]:
    """Campos sujetos al grounding numérico: headline, claims y evidencias.

    Mismo alcance que el precheck de producción
    (``prechecks.run_prechecks``): las acciones y las señales a vigilar
    hablan del futuro ("cuatro semanas", "20 minutos") y no pueden exigir
    respaldo en los datos de la carrera.
    """
    parts: list[str] = [draft.headline]
    for obs in draft.observations:
        parts.append(obs.claim)
        parts.extend(obs.evidence)
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Grounding: números disponibles en el caso
# ---------------------------------------------------------------------------

# Claves de ``_build_v3_context`` que contienen datos reales del atleta/carrera.
_DATA_BLOCK_KEYS: tuple[str, ...] = (
    "race_block",
    "field_block",
    "season_block",
    "conditions_block",
    "anthro_block",
    "training_block",
    "dialogue_block",
    "catalog_block",
    "valida_label",
)


def case_data_blocks(case: Mapping[str, Any]) -> str:
    """Bloques de datos del caso golden, tal como los ve el modelo.

    Construye el mismo contexto Jinja que consume el prompt v3
    (``RaceAnalystAgent._build_v3_context``) y concatena solo los bloques de
    datos, dejando fuera el método, las reglas y el ejemplo resuelto del
    prompt (ver docstring del módulo). Lo consumen el grounding de este
    scorer y el prompt del juez v2.

    Returns:
        Markdown con los bloques presentes. ``""`` si el caso no trae un
        ``input`` construible.
    """
    from app.services.race.agents.analyst import (
        AnalystV3Input,
        RaceAnalystAgent,
        v3_prompt_version,
    )

    payload = dict(case.get("input") or {})
    if not payload:
        return ""
    try:
        input_ = AnalystV3Input(**payload)
    except TypeError:
        return ""

    agent = RaceAnalystAgent(prompt_version=v3_prompt_version(input_.analysis_kind))
    # Acceso a un método "privado" a propósito: reconstruir los bloques acá
    # sería duplicar el formateo del prompt (y desincronizarse en el primer
    # cambio de formato). Ver open issue del reporte: conviene promoverlo a
    # helper público en ``analyst.py``.
    context = agent._build_v3_context(input_)  # noqa: SLF001

    parts: list[str] = []
    for scalar_key, label in (
        ("age", "Edad"),
        ("ltad_group", "Grupo LTAD"),
        ("season", "Temporada"),
        ("validas_count", "Carreras con resultado"),
    ):
        value = context.get(scalar_key)
        if value is not None:
            parts.append(f"- {label}: {value}")
    for key in _DATA_BLOCK_KEYS:
        value = context.get(key)
        if value:
            parts.append(f"### {key}\n{value}")
    memory = context.get("memory_recent_insights") or []
    if memory:
        parts.append("### memory\n" + "\n".join(f"- {m}" for m in memory))
    return "\n\n".join(parts)


def case_grounding_numbers(case: Mapping[str, Any]) -> list[str]:
    """Tokens numéricos de los bloques de datos del caso golden.

    Returns:
        Lista ordenada de tokens normalizados por
        :func:`app.services.race.insight_v3.extract_numeric_tokens`. Vacía si
        el caso no trae ``input`` construible (el sub-score de grounding lo
        trata como "sin verdad de referencia" y no penaliza).
    """
    return sorted(extract_numeric_tokens(case_data_blocks(case)))


# ---------------------------------------------------------------------------
# Sub-rúbricas
# ---------------------------------------------------------------------------


def _score_schema(draft: InsightV3 | None, case: Mapping[str, Any]) -> float:
    """Validez estructural: modelo, cardinalidades, coherencia y no-fallback."""
    if draft is None:
        return 0.0

    from app.services.race.ai.fallback import is_fallback_output

    case_input = dict(case.get("input") or {})
    has_field_metrics = bool(case_input.get("field_metrics"))

    checks = [
        draft.schema_version == "v3",
        2 <= len(draft.observations) <= 4
        and 2 <= len(draft.actions) <= 3
        and all(1 <= len(o.evidence) <= 3 for o in draft.observations),
        # Coherencia con el input: hay lectura de pelotón ⇔ hay field_metrics.
        (draft.field_reading is not None) == has_field_metrics,
        not is_fallback_output(draft),
    ]
    return sum(1.0 for c in checks if c) / len(checks)


def _score_grounding(draft: InsightV3 | None, grounding: set[str]) -> float:
    """Fracción de tokens numéricos del draft respaldados por los datos.

    Casos borde:
    - Sin verdad de referencia (``grounding`` vacío) → 1.0: el caso no
      declara datos numéricos, no hay nada que contrastar.
    - Draft sin un solo número → 0.0: el prompt v3 exige que **cada**
      evidencia lleve una cifra; un draft sin cifras es prosa genérica,
      exactamente el defecto que v3 vino a corregir.
    """
    if draft is None:
        return 0.0
    if not grounding:
        return 1.0
    tokens = extract_numeric_tokens("\n".join(_grounded_text_fields(draft)))
    if not tokens:
        return 0.0
    grounded = sum(1 for t in tokens if t in grounding)
    return grounded / len(tokens)


def _score_forbidden(
    draft: InsightV3 | None,
    case: Mapping[str, Any],
    precheck_categories: set[str],
) -> float:
    """Binaria: ningún término prohibido ni issue de privacidad/LTAD."""
    if draft is None:
        return 0.0
    forbidden = [str(t) for t in (case.get("forbidden_terms") or []) if str(t).strip()]
    haystack = _normalize("\n".join(_draft_text_fields(draft)))
    if any(_normalize(term) in haystack for term in forbidden):
        return 0.0
    if {"privacy", "ltad"} & precheck_categories:
        return 0.0
    return 1.0


def _score_catalog(
    draft: InsightV3 | None,
    case: Mapping[str, Any],
    precheck_categories: set[str],
    sanitized: Any,
) -> float:
    """Refs de catálogo existentes (+ al menos una válida si el caso lo exige).

    La segunda mitad se evalúa sobre el ``sanitized_draft`` que devuelven los
    prechecks —donde las refs inexistentes ya fueron puestas en ``None``—
    para que inventar un código no cuente como "ancló la acción al catálogo".
    """
    if draft is None:
        return 0.0
    checks: list[bool] = ["catalog" not in precheck_categories]
    if bool(case.get("must_reference_catalog", False)):
        actions = getattr(sanitized, "actions", None) or draft.actions
        checks.append(any(getattr(a, "catalog_ref", None) is not None for a in actions))
    return sum(1.0 for c in checks if c) / len(checks)


def _score_headline(draft: InsightV3 | None, case: Mapping[str, Any]) -> float:
    """Binaria: headline no-plantilla Y con ≥1 keyword esperada.

    Las dos mitades van juntas a propósito: un headline causal sobre el tema
    equivocado y una plantilla con la keyword correcta son, ambos, el mismo
    fracaso — el coach no recibe el hallazgo que el caso exige.
    """
    if draft is None:
        return 0.0
    headline = draft.headline or ""
    if not headline.strip():
        return 0.0
    deaccented = _deaccent(headline)
    if any(deaccented.startswith(p) for p in _TEMPLATE_HEADLINE_PREFIXES):
        return 0.0
    keywords = [str(k) for k in (case.get("expected_headline_keywords") or []) if str(k).strip()]
    if not keywords:
        return 1.0
    norm = _normalize(headline)
    return 1.0 if any(_normalize(k) in norm for k in keywords) else 0.0


def _score_themes(draft: InsightV3 | None, case: Mapping[str, Any]) -> float:
    """Proporción de ``expected_themes`` presentes (substring case-insensitive)."""
    if draft is None:
        return 0.0
    themes = [str(t) for t in (case.get("expected_themes") or []) if str(t).strip()]
    if not themes:
        return 1.0
    haystack = _normalize("\n".join(_draft_text_fields(draft)))
    hits = sum(1 for t in themes if _normalize(t) in haystack)
    return hits / len(themes)


def _score_word_limits(draft: InsightV3 | None, case: Mapping[str, Any]) -> float:
    """Proporción de presupuestos de palabras respetados (5 checks)."""
    if draft is None:
        return 0.0
    max_words = int(case.get("max_words") or _DEFAULT_MAX_WORDS)
    total_words = _word_count(render_insight_v3_markdown(draft))
    checks = [
        total_words <= max_words,
        _word_count(draft.headline) <= _HEADLINE_MAX_WORDS,
        all(_word_count(o.claim) <= _CLAIM_MAX_WORDS for o in draft.observations),
        all(
            _word_count(e) <= _EVIDENCE_MAX_WORDS
            for o in draft.observations
            for e in o.evidence
        ),
        all(_word_count(a.text) <= _ACTION_MAX_WORDS for a in draft.actions),
    ]
    return sum(1.0 for c in checks if c) / len(checks)


def _score_coach_question(draft: InsightV3 | None) -> float:
    """Binaria: pregunta no vacía, ≤240 caracteres, terminada en '?'."""
    if draft is None:
        return 0.0
    question = (draft.coach_question or "").strip()
    return 1.0 if question.endswith("?") and 3 <= len(question) <= 240 else 0.0


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def rule_subscores_v3(
    output: Any,
    case: Mapping[str, Any],
    *,
    grounding_numbers: Iterable[str] | None = None,
) -> dict[str, float]:
    """Sub-scores ∈ [0, 1] por rúbrica (mismas claves que ``RULE_WEIGHTS_V3``).

    Args:
        output: :class:`InsightV3` (o dict equivalente) producido por el agente.
        case: caso golden v3 cargado de ``golden_v3/case_NNN.json``.
        grounding_numbers: tokens numéricos de referencia. ``None`` →
            :func:`case_grounding_numbers` (los bloques de datos del caso).

    Returns:
        Dict de sub-scores. Un ``output`` no parseable devuelve todos en 0.0
        salvo que la rúbrica no aplique.
    """
    draft = _as_insight(output)

    ground_raw = (
        list(grounding_numbers)
        if grounding_numbers is not None
        else case_grounding_numbers(case)
    )
    # Se re-normalizan con el MISMO extractor del draft para que la
    # comparación no dependa del formato con el que llegó la lista.
    ground: set[str] = set()
    for token in ground_raw:
        ground |= extract_numeric_tokens(str(token))

    precheck_categories: set[str] = set()
    sanitized: Any = draft
    if draft is not None:
        from app.services.race.ai.prechecks import run_prechecks

        result = run_prechecks(
            draft,
            grounding_numbers=None,  # el grounding lo puntúa este scorer, no el precheck
            catalog_context=dict((case.get("input") or {}).get("catalog_context") or {}),
            athlete_age=(case.get("input") or {}).get("age"),
            ltad_group=(case.get("input") or {}).get("ltad_group"),
            forbidden_names=[],
        )
        precheck_categories = {i.category.value for i in result.issues}
        sanitized = result.sanitized_draft or draft

    return {
        "schema": _score_schema(draft, case),
        "grounding": _score_grounding(draft, ground),
        "forbidden": _score_forbidden(draft, case, precheck_categories),
        "catalog": _score_catalog(draft, case, precheck_categories, sanitized),
        "headline": _score_headline(draft, case),
        "themes": _score_themes(draft, case),
        "word_limits": _score_word_limits(draft, case),
        "coach_question": _score_coach_question(draft),
    }


def rule_based_score_v3(
    output: Any,
    case: Mapping[str, Any],
    *,
    grounding_numbers: Iterable[str] | None = None,
) -> float:
    """Score rule-based ∈ [0, 1] de un ``InsightV3`` contra su caso golden.

    Suma ponderada de :func:`rule_subscores_v3` con :data:`RULE_WEIGHTS_V3`.
    """
    subs = rule_subscores_v3(output, case, grounding_numbers=grounding_numbers)
    total = sum(RULE_WEIGHTS_V3[k] * subs.get(k, 0.0) for k in RULE_WEIGHTS_V3)
    return max(0.0, min(1.0, round(total, 4)))
