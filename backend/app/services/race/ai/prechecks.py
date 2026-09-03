"""Prechecks deterministas del critic v3 (feature 037, T202).

Reglas Python puras (sin LLM) que corren ANTES del critic LLM sobre cada
:class:`InsightV3`. Cubren: validez de esquema, grounding numérico
(tolerante a formatos: ``8.6%``, ``8,6 %``, ``0:35:30``, ``2:49``,
``35:30``, enteros), nombres prohibidos, reglas LTAD inviolables, referencia
de catálogo inexistente (se sanea, no solo se reporta), pregunta al coach
bien formada, y solapamiento con headlines previos.

Cada issue lleva una categoría interna (``PrecheckCategory``) que decide si
fuerza HITL: solo ``privacy`` y ``ltad`` disparan ``must_block`` — el resto
(``grounding``, ``catalog``, ``style``) degrada confianza pero no bloquea.

El resultado incluye ``sanitized_draft``: una copia del draft con los
``catalog_ref`` inexistentes eliminados (``None``), porque ese fix se aplica
sin intervención del coach.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from app.services.race.schemas import CriticIssue

__all__ = [
    "PrecheckCategory",
    "PrecheckIssue",
    "PrecheckResult",
    "run_prechecks",
    "extract_numeric_tokens",
]


class PrecheckCategory(str, Enum):
    """Categoría interna del issue — decide ``must_block`` en el nodo."""

    PRIVACY = "privacy"
    LTAD = "ltad"
    GROUNDING = "grounding"
    CATALOG = "catalog"
    STYLE = "style"


# Categorías que fuerzan HITL antes de mostrar el insight al coach.
MUST_BLOCK_CATEGORIES = frozenset({PrecheckCategory.PRIVACY, PrecheckCategory.LTAD})


@dataclass(frozen=True)
class PrecheckIssue:
    """Un issue detectado por un precheck determinista + su categoría."""

    category: PrecheckCategory
    issue: CriticIssue


@dataclass
class PrecheckResult:
    """Resultado de :func:`run_prechecks`."""

    issues: list[PrecheckIssue] = field(default_factory=list)
    sanitized_draft: Any = None

    @property
    def must_block(self) -> bool:
        return any(i.category in MUST_BLOCK_CATEGORIES for i in self.issues)


# ---------------------------------------------------------------------------
# Extracción tolerante de números (grounding)
# ---------------------------------------------------------------------------

# hh:mm:ss / mm:ss, porcentajes con coma o punto, y enteros/decimales sueltos.
_TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?")
_PCT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%")
_NUM_RE = re.compile(r"(?<![:\d])\d+(?:[.,]\d+)?(?![:\d%])")


def _normalize_token(tok: str) -> str:
    """Normaliza un token numérico para comparación tolerante a formato."""
    cleaned = tok.strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = cleaned.replace(",", ".")
    cleaned = cleaned.rstrip("%")
    return cleaned


def extract_numeric_tokens(text: str) -> set[str]:
    """Extrae y normaliza todos los tokens numéricos de ``text``.

    Reconoce tiempos (``0:35:30``, ``2:49``), porcentajes (``8.6%``,
    ``8,6 %``) y números sueltos (enteros o decimales, coma o punto).
    """
    if not text:
        return set()
    tokens: set[str] = set()
    for m in _TIME_RE.finditer(text):
        tokens.add(_normalize_token(m.group()))
    remaining = _TIME_RE.sub(" ", text)
    for m in _PCT_RE.finditer(remaining):
        tokens.add(_normalize_token(m.group()))
    remaining = _PCT_RE.sub(" ", remaining)
    for m in _NUM_RE.finditer(remaining):
        tokens.add(_normalize_token(m.group()))
    return tokens


# ---------------------------------------------------------------------------
# Reglas LTAD (inviolables — categoría privacy|ltad)
# ---------------------------------------------------------------------------

_SUPPLEMENT_RE = re.compile(
    r"\bsuplement\w*|\bproteína en polvo\b|\bcreatina\b|\bcarga calórica\b",
    re.IGNORECASE,
)
_CADENCE_RE = re.compile(r"cadencia[^.]{0,40}?(\d{1,3})\s*rpm", re.IGNORECASE)
_HOURS_WEEK_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*horas?\s*(?:por\s*semana|semanal(?:es)?|/\s*sem)",
    re.IGNORECASE,
)
_DAYS_WEEK_RE = re.compile(r"(\d{1,2})\s*d[ií]as?\s*(?:por\s*semana|/\s*sem)", re.IGNORECASE)
_FCMAX_TEST_RE = re.compile(
    r"test\s+de\s+fc\s*m[aá]x|prueba\s+de\s+frecuencia\s+card[ií]aca\s+m[aá]xima|"
    r"intervalos?\s+de\s+alta\s+intensidad|potenci[oó]metro",
    re.IGNORECASE,
)
_DIAGNOSIS_RE = re.compile(
    r"\bdiagn[oó]stic\w*|\bpadece\b|\btiene\s+(?:asma|anemia|diabetes)\b|\btrastorno\b",
    re.IGNORECASE,
)
_OUTCOME_GOAL_RE = re.compile(
    r"\b(ganar|gane|ganará|podio|primer(?:o|a)?\s+lugar|campeón|campeona|medalla\s+de\s+oro)\b",
    re.IGNORECASE,
)


def _ltad_issues(text: str, *, athlete_age: int | None) -> list[PrecheckIssue]:
    issues: list[PrecheckIssue] = []

    for m in _CADENCE_RE.finditer(text):
        try:
            rpm = int(m.group(1))
        except ValueError:
            continue
        if rpm < 60:
            issues.append(
                PrecheckIssue(
                    PrecheckCategory.LTAD,
                    CriticIssue(
                        section="ltad",
                        problem=f"Cadencia recomendada <60 rpm ({rpm} rpm).",
                        suggested_fix="Recomendar cadencia ≥60 rpm.",
                    ),
                )
            )

    if _SUPPLEMENT_RE.search(text):
        issues.append(
            PrecheckIssue(
                PrecheckCategory.LTAD,
                CriticIssue(
                    section="ltad",
                    problem="Mención de suplementos dirigida a un menor.",
                    suggested_fix="Eliminar cualquier referencia a suplementación.",
                ),
            )
        )

    for m in _HOURS_WEEK_RE.finditer(text):
        raw = m.group(1).replace(",", ".")
        try:
            hours = float(raw)
        except ValueError:
            continue
        if athlete_age is not None and hours > athlete_age:
            issues.append(
                PrecheckIssue(
                    PrecheckCategory.LTAD,
                    CriticIssue(
                        section="ltad",
                        problem=f"Horas semanales sugeridas ({hours}) superan la edad del atleta ({athlete_age}).",
                        suggested_fix="Reducir la carga semanal sugerida por debajo de la edad del atleta.",
                    ),
                )
            )

    for m in _DAYS_WEEK_RE.finditer(text):
        try:
            days = int(m.group(1))
        except ValueError:
            continue
        if days > 5:
            issues.append(
                PrecheckIssue(
                    PrecheckCategory.LTAD,
                    CriticIssue(
                        section="ltad",
                        problem=f"Recomendación de {days} días/semana (máximo LTAD: 5).",
                        suggested_fix="Limitar la recomendación a máximo 5 días/semana.",
                    ),
                )
            )

    if athlete_age is not None and athlete_age < 13 and _FCMAX_TEST_RE.search(text):
        issues.append(
            PrecheckIssue(
                PrecheckCategory.LTAD,
                CriticIssue(
                    section="ltad",
                    problem="Test de FC máxima / intervalos de alta intensidad para <13 años.",
                    suggested_fix="Reemplazar por trabajo aeróbico de baja intensidad guiado por RPE.",
                ),
            )
        )

    if _DIAGNOSIS_RE.search(text):
        issues.append(
            PrecheckIssue(
                PrecheckCategory.PRIVACY,
                CriticIssue(
                    section="ltad",
                    problem="Lenguaje de diagnóstico médico explícito.",
                    suggested_fix="Eliminar cualquier afirmación diagnóstica; remitir al profesional de salud.",
                ),
            )
        )

    if _OUTCOME_GOAL_RE.search(text):
        issues.append(
            PrecheckIssue(
                PrecheckCategory.LTAD,
                CriticIssue(
                    section="ltad",
                    problem="Meta de resultado (podio/ganar) en vez de meta de proceso.",
                    suggested_fix="Reformular como meta de proceso (técnica, esfuerzo, comportamiento).",
                ),
            )
        )

    return issues


def _forbidden_name_issues(text: str, forbidden_names: Iterable[str]) -> list[PrecheckIssue]:
    issues: list[PrecheckIssue] = []
    lowered = text.lower()
    for name in forbidden_names or []:
        if not name:
            continue
        if name.lower() in lowered:
            issues.append(
                PrecheckIssue(
                    PrecheckCategory.PRIVACY,
                    CriticIssue(
                        section="privacidad",
                        problem="El draft menciona un nombre real prohibido.",
                        suggested_fix="Reemplazar por el pseudónimo o eliminar la mención.",
                    ),
                )
            )
            break
    return issues


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-záéíóúñ0-9]+", text.lower()) if len(t) > 2}


def _collect_text(draft: Any) -> str:
    parts: list[str] = [str(getattr(draft, "headline", "") or "")]
    for obs in getattr(draft, "observations", None) or []:
        parts.append(str(getattr(obs, "claim", "") or ""))
        parts.extend(str(e) for e in (getattr(obs, "evidence", None) or []))
    for action in getattr(draft, "actions", None) or []:
        parts.append(str(getattr(action, "text", "") or ""))
    for signal in getattr(draft, "watch_signals", None) or []:
        parts.append(str(signal))
    coach_question = getattr(draft, "coach_question", None)
    if coach_question:
        parts.append(str(coach_question))
    field_reading = getattr(draft, "field_reading", None)
    if field_reading is not None:
        parts.append(str(getattr(field_reading, "summary", "") or ""))
    return "\n".join(p for p in parts if p)


def _grounding_issue(missing: set[str]) -> PrecheckIssue:
    sample = ", ".join(sorted(missing)[:5])
    return PrecheckIssue(
        PrecheckCategory.GROUNDING,
        CriticIssue(
            section="grounding",
            problem=f"Números sin respaldo en los datos: {sample}.",
            suggested_fix="Usar únicamente cifras presentes en los datos de la carrera/atleta.",
        ),
    )


def _catalog_issue(code: str) -> PrecheckIssue:
    return PrecheckIssue(
        PrecheckCategory.CATALOG,
        CriticIssue(
            section="catalog_ref",
            problem=f"catalog_ref con código '{code}' no existe en el catálogo del club.",
            suggested_fix="Eliminar la referencia o usar un código válido del catálogo.",
        ),
    )


def _catalog_label(catalog_context: dict | None, kind: str, code: str) -> str | None:
    """Nombre legible del recurso del catálogo referido (o ``None``).

    Rellena ``catalog_ref.label`` para que la UI muestre "Cambios y cadencia"
    en vez de "H" (feature 037). Solo se llama cuando el código ya validó.
    """
    if not catalog_context:
        return None
    key = {
        "interval_template": "interval_templates",
    }.get(kind, kind)
    for item in catalog_context.get(key) or []:
        get = item.get if isinstance(item, dict) else (lambda k, _i=item: getattr(_i, k, None))
        item_code = get("code")
        if item_code is None:
            item_code = get("id")
        if item_code is not None and str(item_code) == code:
            name = get("name")
            return str(name) if name else None
    return None


def _catalog_codes(catalog_context: dict | None, kind: str) -> set[str]:
    if not catalog_context:
        return set()
    key = {
        "interval_template": "interval_templates",
    }.get(kind, kind)
    items = catalog_context.get(key) or []
    codes: set[str] = set()
    for item in items:
        code = item.get("code") if isinstance(item, dict) else getattr(item, "code", None)
        if code is None:
            code = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
        if code is not None:
            codes.add(str(code))
    return codes


def run_prechecks(
    draft: Any,
    *,
    grounding_numbers: Iterable[str] | None = None,
    catalog_context: dict | None = None,
    athlete_age: int | None = None,
    ltad_group: str | None = None,
    forbidden_names: Iterable[str] | None = None,
    previous_headlines: Iterable[str] | None = None,
) -> PrecheckResult:
    """Corre todas las reglas deterministas sobre ``draft`` (InsightV3).

    No lanza excepción por draft inválido: si ``draft`` es ``None`` retorna un
    issue ``high``-equivalente (categoría ``privacy`` para forzar HITL) sin
    ``sanitized_draft``.
    """
    if draft is None:
        return PrecheckResult(
            issues=[
                PrecheckIssue(
                    PrecheckCategory.PRIVACY,
                    CriticIssue(
                        section="global",
                        problem="No hay draft estructurado para revisar.",
                        suggested_fix="Forzar HITL manual.",
                    ),
                )
            ],
            sanitized_draft=None,
        )

    issues: list[PrecheckIssue] = []
    full_text = _collect_text(draft)

    # 1) Nombres prohibidos.
    issues.extend(_forbidden_name_issues(full_text, forbidden_names or []))

    # 2) Reglas LTAD inviolables.
    issues.extend(_ltad_issues(full_text, athlete_age=athlete_age))

    # 3) Grounding numérico.
    ground_set = {_normalize_token(t) for t in (grounding_numbers or [])}
    draft_tokens: set[str] = set()
    draft_tokens |= extract_numeric_tokens(str(getattr(draft, "headline", "") or ""))
    for obs in getattr(draft, "observations", None) or []:
        draft_tokens |= extract_numeric_tokens(str(getattr(obs, "claim", "") or ""))
        for ev in getattr(obs, "evidence", None) or []:
            draft_tokens |= extract_numeric_tokens(str(ev))
    missing = {t for t in draft_tokens if t not in ground_set} if ground_set else set()
    if missing:
        issues.append(_grounding_issue(missing))

    # 4) catalog_ref inexistente → saneado.
    sanitized_actions = []
    actions = getattr(draft, "actions", None) or []
    dirty = False
    for action in actions:
        ref = getattr(action, "catalog_ref", None)
        if ref is not None:
            code = str(getattr(ref, "code", ""))
            kind = getattr(ref, "kind", None)
            kind_value = getattr(kind, "value", kind)
            valid_codes = _catalog_codes(catalog_context, str(kind_value))
            if valid_codes and code not in valid_codes:
                issues.append(_catalog_issue(code))
                try:
                    action = action.model_copy(update={"catalog_ref": None})
                except AttributeError:
                    action = None
                dirty = True
            elif getattr(ref, "label", None) in (None, ""):
                label = _catalog_label(catalog_context, str(kind_value), code)
                if label:
                    try:
                        action = action.model_copy(
                            update={"catalog_ref": ref.model_copy(update={"label": label})}
                        )
                        dirty = True
                    except AttributeError:
                        pass
        sanitized_actions.append(action)

    sanitized_draft = draft
    if dirty:
        try:
            sanitized_draft = draft.model_copy(update={"actions": sanitized_actions})
        except AttributeError:
            sanitized_draft = draft

    # 5) coach_question bien formada.
    coach_question = str(getattr(draft, "coach_question", "") or "").strip()
    if not coach_question or not coach_question.endswith("?"):
        issues.append(
            PrecheckIssue(
                PrecheckCategory.STYLE,
                CriticIssue(
                    section="coach_question",
                    problem="coach_question vacía o no termina en '?'.",
                    suggested_fix="Formular una pregunta concreta que termine en '?'.",
                ),
            )
        )

    # 6) Solapamiento con headlines previos (Jaccard ≥0.85).
    headline = str(getattr(draft, "headline", "") or "")
    headline_tokens = _tokenize(headline)
    for prev in previous_headlines or []:
        if _jaccard(headline_tokens, _tokenize(str(prev))) >= 0.85:
            issues.append(
                PrecheckIssue(
                    PrecheckCategory.STYLE,
                    CriticIssue(
                        section="headline",
                        problem="El headline repite casi textualmente un insight previo.",
                        suggested_fix="Reformular el headline con un ángulo distinto para esta válida.",
                    ),
                )
            )
            break

    return PrecheckResult(issues=issues, sanitized_draft=sanitized_draft)
