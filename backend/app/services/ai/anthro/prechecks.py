"""Prechecks deterministas R01-R12 (feature 042, T029).

Implementa ``specs/042-traceable-growth-ai/data-model.md`` §2.3 y el
catálogo de reglas de ``specs/042-traceable-growth-ai/contracts/
golden-eval-case.md`` §3 — esa sección es la fuente de verdad para la
categoría y el ``must_block`` de cada regla, no este docstring.

Estas reglas corren DESPUÉS del analista y ANTES del crítico (paso
``prechecked`` de la máquina de estados, ``data-model.md`` §3): si alguna
regla con ``must_block=True`` dispara, el pipeline (T039) va directo al
fallback determinista sin invocar al crítico (FR-014). Las reglas
``must_block=False`` solo degradan la confianza reportada al crítico.

Catálogo (``must_block`` set: R01, R02, R04, R06, R09, R11, R12 — privacidad
y seguridad de desarrollo; degradan solamente: R03, R05, R07, R08, R10):

| Regla | Categoría | Bloquea | Qué revisa |
|-------|-----------|---------|------------|
| R01   | privacy   | sí      | Comparación poblacional / con pares. |
| R02   | ltad      | sí      | Etiqueta diagnóstica o clínica. |
| R03   | grounding | no      | Número inventado (ausente del contexto). |
| R04   | privacy   | sí      | Fecha exacta o edad decimal como predicción de PHV. |
| R05   | grounding | no      | Velocidad presentada como confiable sin serlo. |
| R06   | privacy   | sí      | Nombre/identificador prohibido filtrado en el output. |
| R07   | style     | no      | Presupuesto de palabras excedido (+10% tolerancia). |
| R08   | style     | no      | Elogio desproporcionado sobre un delta no significativo. |
| R09   | ltad      | sí      | Mención de suplemento. |
| R10   | style     | no      | Markdown/viñetas dentro de un campo de texto. |
| R11   | grounding | sí      | Cruce de fase de maduración sin corroborar, presentado como confirmado. |
| R12   | privacy   | sí      | Contenido exclusivo del entrenador filtrado a una audiencia familiar. |

REUSO deliberado (para no duplicar reglas ya auditadas, instrucción
explícita del feature):
  - R01 reusa ``_COMPARATIVE_NORM_PATTERN`` de ``app/services/ai/guardrails.py``.
  - R02 reusa las reglas de ``_RECORD_ANALYSIS_RULES`` del mismo módulo.
  - R09 reusa ``_SUPPLEMENT_KEYWORDS`` del mismo módulo.
  - R03 reusa la misma técnica de extracción numérica tolerante que
    ``app/services/race/ai/prechecks.py::extract_numeric_tokens``
    (tiempos, porcentajes, enteros/decimales con coma o punto).
  - R06 reusa la lista de nombres prohibidos del club cargada vía
    ``app/services/race/ai/athlete_context.py::load_club_forbidden_names``
    (el llamador —``pipeline.py``, T039— la carga de forma async y la pasa
    aquí como ``forbidden_names``; este módulo no toca la DB).

Privacidad (CLAUDE.md / Ley 1581): ``PrecheckViolation.detail`` es SIEMPRE
una frase corta y genérica — nunca incluye el fragmento de texto que
disparó la regla, el nombre detectado, ni ningún otro dato del menor. Los
logs de este módulo (si los hubiera) deben respetar la misma restricción.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Sequence

from app.services.ai.guardrails import (
    _COMPARATIVE_NORM_PATTERN,
    _RECORD_ANALYSIS_RULES,
    _SUPPLEMENT_KEYWORDS,
)
from app.services.ai.anthro.schemas import exceeds_word_budget
from app.services.race.ai.prechecks import extract_numeric_tokens

if TYPE_CHECKING:
    from app.services.ai.anthro.context import AnalysisContext
    from app.services.ai.anthro.schemas import AnthropometryInsightV1

__all__ = [
    "PrecheckViolation",
    "PrecheckResult",
    "run_prechecks",
    "check_r01_population_comparison",
    "check_r02_diagnostic_label",
    "check_r03_invented_number",
    "check_r04_exact_phv_prediction",
    "check_r05_unreliable_velocity_claimed_reliable",
    "check_r06_leaked_identifier",
    "check_r07_word_budget",
    "check_r08_sycophancy_over_non_significant_delta",
    "check_r09_supplement_mention",
    "check_r10_markdown_in_fields",
    "check_r11_uncorroborated_phase_crossing",
    "check_r12_coach_only_leak_to_family",
]


PrecheckCategory = Literal["privacy", "ltad", "grounding", "style"]


@dataclass(frozen=True)
class PrecheckViolation:
    """Una violación puntual de una de las reglas R01-R12 (data-model.md §2.3).

    ``detail`` es breve y nunca reproduce el texto del atleta/familia ni el
    fragmento que disparó la regla — ver la nota de privacidad del docstring
    del módulo.
    """

    rule_id: str  # "R01".."R12"
    category: PrecheckCategory
    must_block: bool
    detail: str


@dataclass(frozen=True)
class PrecheckResult:
    """Resultado agregado de :func:`run_prechecks`."""

    violations: tuple[PrecheckViolation, ...]
    must_block: bool  # True sii alguna violación trae must_block=True


# ---------------------------------------------------------------------------
# Helpers de extracción de texto sobre el borrador
# ---------------------------------------------------------------------------


def _all_text_fields(insight: "AnthropometryInsightV1") -> list[str]:
    """Todos los campos de texto libre del insight, en orden estable."""
    return [
        insight.summary_line,
        *insight.changes,
        *insight.meaning,
        *insight.next_weeks,
        *insight.warning_signs,
        *insight.data_gaps,
        insight.confidence.reason,
    ]


def _joined_text(insight: "AnthropometryInsightV1") -> str:
    return "\n".join(_all_text_fields(insight))


# ---------------------------------------------------------------------------
# R01 — comparación poblacional / con pares (privacy, must_block)
# ---------------------------------------------------------------------------


def check_r01_population_comparison(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    """Reusa ``_COMPARATIVE_NORM_PATTERN`` de ``guardrails.py`` sobre el borrador."""
    if _COMPARATIVE_NORM_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R01",
            category="privacy",
            must_block=True,
            detail="Comparación poblacional o con pares detectada en el texto generado.",
        )
    return None


# ---------------------------------------------------------------------------
# R02 — etiqueta diagnóstica o clínica (ltad, must_block)
# ---------------------------------------------------------------------------


def check_r02_diagnostic_label(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    """Reusa las reglas de ``_RECORD_ANALYSIS_RULES`` de ``guardrails.py``."""
    text = _joined_text(insight)
    for rule in _RECORD_ANALYSIS_RULES:
        if rule.pattern.search(text):
            return PrecheckViolation(
                rule_id="R02",
                category="ltad",
                must_block=True,
                detail="Lenguaje diagnóstico o clínico detectado en el texto generado.",
            )
    return None


# ---------------------------------------------------------------------------
# R03 — número inventado (grounding, degrada)
# ---------------------------------------------------------------------------

# Cardinalidades estructurales que el prompt exige explícitamente (p. ej.
# "próximas 2-4 semanas", listas de longitud fija) y que por lo tanto no
# están respaldadas por un campo específico del contexto, pero tampoco son
# una alucinación — son la propia forma del contrato de salida.
_R03_STRUCTURAL_NUMBERS: frozenset[str] = frozenset({"2", "3", "4"})


def _normalize_number_token(token: str) -> str:
    return token.strip().replace(",", ".").rstrip(".")


def _collect_context_numbers(context: "AnalysisContext") -> set[str]:
    """Aplana todo valor numérico presente en ``context`` a tokens normalizados.

    Recorre los seis campos de ``AnalysisContext`` (todos ya saneados por la
    allowlist del constructor de contexto) sin distinguir de cuál provienen —
    R03 solo necesita saber si el número existe EN ALGÚN LADO del contexto
    entregado al prompt, no de qué campo.
    """
    numbers: set[str] = set()

    def _walk(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            token = _normalize_number_token(str(value))
            numbers.add(token)
            # También el entero truncado, para que "13.4" en el contexto
            # respalde una mención de "13" en el texto generado.
            numbers.add(token.split(".")[0])
        elif isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _walk(v)

    for field_value in (
        context.identity,
        context.measurement_deltas,
        context.growth_summary,
        context.training_load_window,
        context.previous_analysis,
    ):
        if field_value is not None:
            _walk(field_value)
    _walk(context.longitudinal_series)

    return numbers


def check_r03_invented_number(
    insight: "AnthropometryInsightV1", context: "AnalysisContext"
) -> PrecheckViolation | None:
    """Todo token numérico del borrador debe existir en el contexto entregado.

    Reusa la misma técnica tolerante de extracción numérica que
    ``app/services/race/ai/prechecks.py::extract_numeric_tokens`` (normaliza
    coma/punto decimal, reconoce tiempos y porcentajes) para no duplicar esa
    lógica ya auditada.
    """
    allowed = _collect_context_numbers(context) | _R03_STRUCTURAL_NUMBERS
    if not allowed:
        # Sin ningún número de referencia (caso degenerado, primera medición
        # sin contexto numérico) preferimos no bloquear falsos positivos.
        return None

    draft_tokens = extract_numeric_tokens(_joined_text(insight))
    missing = {t for t in draft_tokens if t not in allowed}
    if missing:
        return PrecheckViolation(
            rule_id="R03",
            category="grounding",
            must_block=False,
            detail="Número presente en el texto sin respaldo en el contexto entregado.",
        )
    return None


# ---------------------------------------------------------------------------
# R04 — fecha exacta / edad decimal como predicción de PHV (privacy, must_block)
# ---------------------------------------------------------------------------

_MONTHS_ES = (
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre"
)

_CALENDAR_DATE_PATTERN = re.compile(
    rf"\b\d{{1,2}}\s+de\s+(?:{_MONTHS_ES})(?:\s+de\s+\d{{4}})?\b"
    rf"|\b(?:{_MONTHS_ES})\s+de\s+\d{{4}}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    re.IGNORECASE,
)

_PHV_KEYWORD_PATTERN = re.compile(
    r"\bPHV\b|pico\s+de\s+velocidad(?:\s+de\s+crecimiento)?|pico\s+de\s+crecimiento",
    re.IGNORECASE,
)

_DECIMAL_AGE_PATTERN = re.compile(r"\b\d{1,2}[.,]\d\s*años?\b", re.IGNORECASE)


def check_r04_exact_phv_prediction(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    """Ninguna fecha calendario exacta, ni una edad de un decimal ligada a PHV."""
    text = _joined_text(insight)
    if _CALENDAR_DATE_PATTERN.search(text):
        return PrecheckViolation(
            rule_id="R04",
            category="privacy",
            must_block=True,
            detail="Fecha calendario exacta detectada en el texto generado.",
        )
    if _PHV_KEYWORD_PATTERN.search(text) and _DECIMAL_AGE_PATTERN.search(text):
        return PrecheckViolation(
            rule_id="R04",
            category="privacy",
            must_block=True,
            detail="Edad decimal exacta presentada como predicción de PHV.",
        )
    return None


# ---------------------------------------------------------------------------
# R05 — velocidad presentada como confiable sin serlo (grounding, degrada)
# ---------------------------------------------------------------------------

_VELOCITY_RELIABLE_CLAIM_PATTERN = re.compile(
    r"velocidad[^.]{0,40}(?:confiable|consistente|establecida|s[óo]lida)"
    r"|dato\s+confiable\s+de\s+crecimiento"
    r"|ritmo\s+de\s+crecimiento\s+confiable",
    re.IGNORECASE,
)


def check_r05_unreliable_velocity_claimed_reliable(
    insight: "AnthropometryInsightV1", context: "AnalysisContext"
) -> PrecheckViolation | None:
    """Cruza directamente contra ``context.measurement_deltas['velocity_confidence']``.

    Nunca es un juicio del LLM crítico — si el contexto no dice
    ``"reliable"``, ninguna frase del borrador puede afirmarlo.
    """
    deltas = context.measurement_deltas or {}
    if deltas.get("velocity_confidence") == "reliable":
        return None
    if _VELOCITY_RELIABLE_CLAIM_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R05",
            category="grounding",
            must_block=False,
            detail="Velocidad de crecimiento presentada como confiable sin respaldo del contexto.",
        )
    return None


# ---------------------------------------------------------------------------
# R06 — nombre/identificador prohibido filtrado (privacy, must_block)
# ---------------------------------------------------------------------------


def check_r06_leaked_identifier(
    insight: "AnthropometryInsightV1",
    forbidden_names: Sequence[str] = (),
) -> PrecheckViolation | None:
    """Verifica el output contra la lista de nombres prohibidos del club.

    ``forbidden_names`` la carga el llamador (pipeline.py, T039) vía
    ``app/services/race/ai/athlete_context.py::load_club_forbidden_names`` —
    este módulo es síncrono y no toca la DB. Sin nombres para comparar, la
    regla no puede disparar (no es un falso negativo silencioso: el
    ``AnalysisContext`` de entrada ya nunca lleva el nombre real, así que
    esto es defensa en profundidad contra una alucinación del LLM).
    """
    text = _joined_text(insight)
    for raw_name in forbidden_names:
        name = (raw_name or "").strip()
        if not name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            return PrecheckViolation(
                rule_id="R06",
                category="privacy",
                must_block=True,
                detail="Nombre o identificador prohibido detectado en el texto generado.",
            )
    return None


# ---------------------------------------------------------------------------
# R07 — presupuesto de palabras excedido (style, degrada)
# ---------------------------------------------------------------------------


def _render_plain_prose_for_word_count(insight: "AnthropometryInsightV1") -> str:
    """Aproximación mínima de la prosa final (`insight-schema.md` §4) solo
    para contar palabras aquí — el renderizador definitivo vive en
    ``app/services/ai/anthro/persist.py`` (T038, otro módulo/tarea). R07
    recalcula SIEMPRE sobre texto renderizado, nunca sobre
    ``AnthropometryInsightV1.word_count`` (autoreportado, ver
    ``schemas.py::exceeds_word_budget``).
    """
    sections = [
        insight.summary_line,
        " ".join(insight.changes),
        " ".join(insight.meaning),
        " ".join(insight.next_weeks),
        " ".join(insight.warning_signs) if insight.warning_signs else "",
    ]
    return "\n\n".join(section for section in sections if section)


def check_r07_word_budget(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    rendered = _render_plain_prose_for_word_count(insight)
    if exceeds_word_budget(insight.audience, rendered):
        return PrecheckViolation(
            rule_id="R07",
            category="style",
            must_block=False,
            detail=f"Presupuesto de palabras excedido para audiencia '{insight.audience}'.",
        )
    return None


# ---------------------------------------------------------------------------
# R08 — elogio desproporcionado sobre un delta no significativo (style, degrada)
# ---------------------------------------------------------------------------

_PRAISE_PHRASES_PATTERN = re.compile(
    r"gran\s+crecimiento|crecimiento\s+not(?:able|orio)|excelente\s+progreso|"
    r"progreso\s+excelente|impresionante\s+avance|avance\s+impresionante|"
    r"gran\s+avance|salto\s+de\s+crecimiento|crecimiento\s+incre[íi]ble",
    re.IGNORECASE,
)


def check_r08_sycophancy_over_non_significant_delta(
    insight: "AnthropometryInsightV1", context: "AnalysisContext"
) -> PrecheckViolation | None:
    """Cruza una frase de elogio contra ``delta_*_significant`` del contexto."""
    deltas = context.measurement_deltas
    if deltas is None:
        return None
    if deltas.get("delta_height_significant") or deltas.get("delta_weight_significant"):
        return None
    if _PRAISE_PHRASES_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R08",
            category="style",
            must_block=False,
            detail="Elogio desproporcionado sobre un cambio que el contexto marca como no significativo.",
        )
    return None


# ---------------------------------------------------------------------------
# R09 — mención de suplemento (ltad, must_block)
# ---------------------------------------------------------------------------

_SUPPLEMENT_PATTERN = re.compile(rf"\b({_SUPPLEMENT_KEYWORDS})\b", re.IGNORECASE)


def check_r09_supplement_mention(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    """Reusa ``_SUPPLEMENT_KEYWORDS`` de ``guardrails.py``."""
    if _SUPPLEMENT_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R09",
            category="ltad",
            must_block=True,
            detail="Mención de suplemento detectada en el texto generado.",
        )
    return None


# ---------------------------------------------------------------------------
# R10 — Markdown/viñetas dentro de un campo (style, degrada)
# ---------------------------------------------------------------------------

_MARKDOWN_PATTERN = re.compile(
    r"(?:^|\n)\s*[-*#]\s|\*\*[^*]+\*\*|`[^`]+`|_{2,}",
)


def check_r10_markdown_in_fields(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    if _MARKDOWN_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R10",
            category="style",
            must_block=False,
            detail="Carácter de formato Markdown detectado dentro de un campo de texto.",
        )
    return None


# ---------------------------------------------------------------------------
# R11 — cruce de fase sin corroborar presentado como confirmado
# (grounding, must_block)
# ---------------------------------------------------------------------------

_PHASE_CONFIRMED_CLAIM_PATTERN = re.compile(
    r"(?:cambio|cruce)\s+de\s+fase[^.]{0,60}confirmad\w+"
    r"|confirmad\w+[^.]{0,60}(?:cambio|cruce)\s+de\s+fase"
    r"|ya\s+(?:entr[óo]|cruz[óo])\s+(?:a|en)\s+la\s+fase"
    r"|entr[óo]\s+de\s+forma\s+confirmada\s+en\s+la\s+fase",
    re.IGNORECASE,
)


def check_r11_uncorroborated_phase_crossing(
    insight: "AnthropometryInsightV1", context: "AnalysisContext"
) -> PrecheckViolation | None:
    """Cruza directamente contra ``context.measurement_deltas['phase_crossing_corroborated']``."""
    deltas = context.measurement_deltas
    if deltas is None:
        return None
    if not deltas.get("crossed_phv_phase"):
        return None
    if deltas.get("phase_crossing_corroborated"):
        return None
    if _PHASE_CONFIRMED_CLAIM_PATTERN.search(_joined_text(insight)):
        return PrecheckViolation(
            rule_id="R11",
            category="grounding",
            must_block=True,
            detail="Cruce de fase de maduración presentado como confirmado sin corroboración.",
        )
    return None


# ---------------------------------------------------------------------------
# R12 — contenido exclusivo del entrenador en una audiencia familiar
# (privacy, must_block)
# ---------------------------------------------------------------------------

_COACH_ONLY_VELOCITY_FIGURE_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?\s*cm\s*/\s*a[ñn]o", re.IGNORECASE
)
_COACH_ONLY_MONTHS_TO_PHV_PATTERN = re.compile(
    r"\d+(?:[.,]\d+)?\s*mes(?:es)?\s+(?:para|hasta)\s+(?:el\s+)?(?:PHV|pico)",
    re.IGNORECASE,
)


def check_r12_coach_only_leak_to_family(
    insight: "AnthropometryInsightV1",
) -> PrecheckViolation | None:
    if insight.audience != "family":
        return None
    text = _joined_text(insight)
    if _COACH_ONLY_VELOCITY_FIGURE_PATTERN.search(text) or _COACH_ONLY_MONTHS_TO_PHV_PATTERN.search(
        text
    ):
        return PrecheckViolation(
            rule_id="R12",
            category="privacy",
            must_block=True,
            detail="Contenido exclusivo del entrenador presente en un texto dirigido a familia.",
        )
    return None


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------


def run_prechecks(
    insight: "AnthropometryInsightV1",
    context: "AnalysisContext",
    *,
    forbidden_names: Sequence[str] = (),
) -> PrecheckResult:
    """Corre las doce reglas R01-R12 sobre ``insight`` y devuelve el resultado agregado.

    ``forbidden_names`` es opcional (R06 solamente) para que el llamador
    pueda pasar la lista cargada de DB (``load_club_forbidden_names``) sin
    que este módulo dependa de una sesión async — ver el docstring de
    :func:`check_r06_leaked_identifier`.
    """
    checks: tuple[PrecheckViolation | None, ...] = (
        check_r01_population_comparison(insight),
        check_r02_diagnostic_label(insight),
        check_r03_invented_number(insight, context),
        check_r04_exact_phv_prediction(insight),
        check_r05_unreliable_velocity_claimed_reliable(insight, context),
        check_r06_leaked_identifier(insight, forbidden_names),
        check_r07_word_budget(insight),
        check_r08_sycophancy_over_non_significant_delta(insight, context),
        check_r09_supplement_mention(insight),
        check_r10_markdown_in_fields(insight),
        check_r11_uncorroborated_phase_crossing(insight, context),
        check_r12_coach_only_leak_to_family(insight),
    )
    violations = tuple(v for v in checks if v is not None)
    must_block = any(v.must_block for v in violations)
    return PrecheckResult(violations=violations, must_block=must_block)
