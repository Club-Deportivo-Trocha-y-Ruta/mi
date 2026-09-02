"""``InsightV3`` — contrato estructurado del análisis v3 (feature 037, T201).

Implementa ``specs/037-ai-insights-v3-causal/data-model.md`` §InsightV3 y el
renderizado de ``plan.md`` §Rendering.

Por qué un modelo Pydantic y no markdown libre
==============================================
El analista v2 devolvía markdown con 3 secciones y el sistema lo re-parseaba
con regex (``_split_sections_v2`` / ``_REC_BULLET_RE``). Ese contrato es
frágil: un bullet que termina en punto perdía la recomendación entera
(spec.md §problem 6). En v3 el modelo devuelve **JSON validado por Pydantic**
(structured output de Gemini) y el markdown se *genera* determinísticamente
desde el objeto — nunca al revés. Consecuencias:

- ``summary_text`` (lo que ve el coach y consumen newsletter/chat) sigue
  siendo markdown, pero es una proyección fiel del JSON persistido.
- Las acciones ya no se re-parsean: viajan tipadas hasta
  ``recommendations_json``.
- El crítico determinista (T202) valida campos, no prosa.

Privacidad (CLAUDE.md): este modelo NUNCA lleva nombre real, peso, IMC ni
estado nutricional. El sujeto se referencia con ``athlete_ref``
("el deportista" / "la deportista") resuelto por sexo aguas arriba.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EvidenceDomain",
    "ActionCategory",
    "Priority",
    "Horizon",
    "CatalogKind",
    "Trend",
    "Observation",
    "CatalogRef",
    "ActionV3",
    "FieldReading",
    "InsightV3",
    "PRINCIPLE_LABELS",
    "render_insight_v3_markdown",
    "insight_v3_sections",
    "extract_numeric_tokens",
    "normalize_numeric_token",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvidenceDomain(str, Enum):
    """Dominio del dato que sostiene una observación."""

    RACE = "race"
    FIELD = "field"
    TRAINING = "training"
    MATURATION = "maturation"
    CONDITIONS = "conditions"
    HISTORY = "history"


class ActionCategory(str, Enum):
    """Categoría de la acción prescrita.

    Superset de :class:`app.services.race.schemas.RecommendationCategory`:
    v3 agrega ``tactics`` (lectura de carrera / posicionamiento), que el
    enum legacy no tiene. El mapeo hacia el schema legacy vive en
    :data:`_ACTION_TO_LEGACY_CATEGORY`.
    """

    TECHNIQUE = "technique"
    VOLUME = "volume"
    RECOVERY = "recovery"
    NUTRITION = "nutrition"
    PSYCHOLOGY = "psychology"
    TACTICS = "tactics"


class Priority(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class Horizon(str, Enum):
    """Ventana temporal en la que la acción se ejecuta."""

    NEXT_WEEK = "next_week"
    NEXT_RACE = "next_race"
    SEASON = "season"


class CatalogKind(str, Enum):
    """Tipo de recurso del catálogo del club referenciado por una acción."""

    TECHNIQUE_SKILL = "technique_skill"
    STRENGTH_BLOCK = "strength_block"
    INTERVAL_TEMPLATE = "interval_template"


Trend = Literal["improving", "stable", "declining", "mixed", "first_reference"]

# Etiquetas citables de ``docs/01-marco-teorico.md`` (catálogo cerrado).
# El prompt las lista para que ``principles_cited`` sea verificable: el
# precheck (T202) puede exigir pertenencia exacta a esta lista en vez de
# aceptar cualquier título inventado.
PRINCIPLE_LABELS: tuple[str, ...] = (
    "1. Desarrollo físico y fisiológico 10-15",
    "2. Capacidades físicas y dosificación por edad",
    "3. Progresión técnica en MTB/XCO",
    "4. Estrategia y táctica en XCO",
    "5. Periodización de la temporada",
    "6. Motivación, miedo y resiliencia",
    "7. Nutrición para crecer, entrenar y competir",
    "8. Prevención de lesiones y crecimiento",
    "9. Tecnología al servicio del desarrollo",
    "10. Reglamentos y filosofía federativa",
)

# ActionCategory → RecommendationCategory (schema legacy). ``tactics`` no
# existe en el enum legacy: se degrada a ``technique`` SOLO para la copia de
# compatibilidad (``AnalysisOutput.recommendations``). El valor original se
# conserva intacto en ``structured_json`` y en ``recommendations_json``.
_ACTION_TO_LEGACY_CATEGORY: dict[str, str] = {
    "technique": "technique",
    "volume": "volume",
    "recovery": "recovery",
    "nutrition": "nutrition",
    "psychology": "psychology",
    "tactics": "technique",
}

_HORIZON_LABELS: dict[str, str] = {
    "next_week": "próxima semana",
    "next_race": "próxima carrera",
    "season": "temporada",
}


# ---------------------------------------------------------------------------
# Sub-modelos
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    """Una observación interpretativa sostenida por evidencia numérica."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="Una sola frase interpretativa (qué significa el dato).",
    )
    evidence: list[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description=(
            "1-3 evidencias, cada una con al menos un número copiado tal cual "
            "de los datos entregados al modelo."
        ),
    )
    domain: EvidenceDomain
    confidence: Literal["high", "medium", "low"] = "medium"


class CatalogRef(BaseModel):
    """Referencia a un recurso real del catálogo del club."""

    model_config = ConfigDict(extra="forbid")

    kind: CatalogKind
    code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Código de skill técnica ('A'..'H') o id numérico como string.",
    )
    label: Optional[str] = Field(
        default=None,
        max_length=160,
        description="Nombre legible; lo rellenan los prechecks desde catalog_context.",
    )


class ActionV3(BaseModel):
    """Acción prescrita, ligada al catálogo y a una observación."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ...,
        min_length=3,
        max_length=280,
        description="Imperativo y concreto: qué, con qué frecuencia, por cuánto tiempo.",
    )
    category: ActionCategory
    priority: Priority = Priority.MED
    horizon: Horizon = Horizon.NEXT_WEEK
    catalog_ref: Optional[CatalogRef] = None
    derived_from: Optional[int] = Field(
        default=None,
        ge=0,
        le=3,
        description="Índice (0-based) de la observación de la que se deriva.",
    )


class FieldReading(BaseModel):
    """Lectura del resultado contra el pelotón (determinista aguas arriba)."""

    model_config = ConfigDict(extra="forbid")

    percentile: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    expected_position: Optional[int] = Field(default=None, ge=1)
    actual_position: Optional[int] = Field(default=None, ge=1)
    delta_vs_expected: Optional[int] = None
    gap_to_p3_hhmmss: Optional[str] = Field(default=None, max_length=16)
    series_label: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=200)


class InsightV3(BaseModel):
    """Análisis estructurado de una válida (o de la temporada completa).

    ``schema_version`` es literal ``"v3"``: los consumidores (DTO
    ``AthleteInsightDetailOut.structured``, tarjeta del frontend) lo usan
    para distinguir estas filas de las v1/v2, que tienen
    ``structured_json = NULL``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v3"] = "v3"
    headline: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="El hallazgo causal más fuerte, en una frase.",
    )
    field_reading: Optional[FieldReading] = None
    trend: Trend = "first_reference"
    observations: list[Observation] = Field(..., min_length=2, max_length=4)
    actions: list[ActionV3] = Field(..., min_length=2, max_length=3)
    watch_signals: list[str] = Field(default_factory=list, max_length=2)
    coach_question: str = Field(
        ...,
        min_length=3,
        max_length=240,
        description=(
            "Exactamente una pregunta para el coach sobre algo que los datos "
            "no pueden responder. El precheck de T202 valida que termine en '?'."
        ),
    )
    data_gaps: list[str] = Field(default_factory=list, max_length=3)
    principles_cited: list[str] = Field(default_factory=list, max_length=3)


# ---------------------------------------------------------------------------
# Rendering → markdown (plan.md §Rendering)
# ---------------------------------------------------------------------------


def _catalog_suffix(action: ActionV3) -> str:
    ref = action.catalog_ref
    if ref is None:
        return ""
    kind = ref.kind.value if hasattr(ref.kind, "value") else str(ref.kind)
    return f", catálogo={kind}:{ref.code}"


def _action_bullet(action: ActionV3) -> str:
    """Bullet compatible con ``analyst._REC_BULLET_RE`` (relajada en T101)."""
    category = getattr(action.category, "value", action.category)
    priority = getattr(action.priority, "value", action.priority)
    horizon = getattr(action.horizon, "value", action.horizon)
    return (
        f"- {action.text} (categoría={category}, prioridad={priority}, "
        f"horizonte={horizon}{_catalog_suffix(action)})"
    )


def _field_reading_line(reading: FieldReading, athlete_ref: str) -> str:
    """Línea única con percentil, esperado-vs-real y gap a P3.

    Sólo incluye las partes con dato: un ``None`` se omite en vez de
    imprimirse como "—" (evita que el coach lea un hueco como un valor).
    """
    parts: list[str] = []
    if reading.series_label:
        parts.append(reading.series_label)
    if reading.percentile is not None:
        parts.append(f"percentil {reading.percentile:g}")
    if reading.actual_position is not None and reading.expected_position is not None:
        delta = reading.delta_vs_expected
        delta_txt = f" ({delta:+d} lugares)" if delta is not None else ""
        parts.append(
            f"{athlete_ref} terminó en P{reading.actual_position} "
            f"frente a P{reading.expected_position} esperada{delta_txt}"
        )
    elif reading.actual_position is not None:
        parts.append(f"{athlete_ref} terminó en P{reading.actual_position}")
    if reading.gap_to_p3_hhmmss:
        parts.append(f"gap a P3 {reading.gap_to_p3_hhmmss}")
    return " · ".join(parts)


def render_insight_v3_markdown(
    draft: InsightV3, athlete_ref: str = "la deportista"
) -> str:
    """Proyecta un :class:`InsightV3` al markdown que consume el coach.

    Formato exacto de ``plan.md`` §Rendering. Las secciones cuyo contenido
    está vacío (``field_reading=None``, ``watch_signals=[]``,
    ``data_gaps=[]``) se **omiten** en vez de emitir un heading huérfano.

    Args:
        draft: análisis estructurado ya validado.
        athlete_ref: "el deportista" | "la deportista" — sólo se usa en la
            línea de "Lectura del pelotón"; el resto del texto ya viene
            redactado por el modelo con la referencia correcta.

    Returns:
        Markdown listo para ``AthleteAiInsight.summary_text``.
    """
    blocks: list[str] = ["## Hallazgo principal", draft.headline]

    if draft.field_reading is not None:
        line = _field_reading_line(draft.field_reading, athlete_ref)
        body = [ln for ln in (line, draft.field_reading.summary) if ln]
        if body:
            blocks.append("")
            blocks.append("## Lectura del pelotón")
            blocks.extend(body)

    if draft.observations:
        blocks.append("")
        blocks.append("## Observaciones")
        for obs in draft.observations:
            evidence = "; ".join(e for e in obs.evidence if e)
            blocks.append(
                f"- {obs.claim} — evidencia: {evidence}" if evidence else f"- {obs.claim}"
            )

    if draft.actions:
        blocks.append("")
        blocks.append("## Acciones")
        blocks.extend(_action_bullet(a) for a in draft.actions)

    if draft.watch_signals:
        blocks.append("")
        blocks.append("## Señales a vigilar")
        blocks.extend(f"- {s}" for s in draft.watch_signals)

    if draft.coach_question:
        blocks.append("")
        blocks.append("## Pregunta para el coach")
        blocks.append(draft.coach_question)

    if draft.data_gaps:
        blocks.append("")
        blocks.append("## Vacíos de datos")
        blocks.extend(f"- {g}" for g in draft.data_gaps)

    return "\n".join(blocks).strip() + "\n"


def insight_v3_sections(draft: InsightV3) -> dict[str, str]:
    """Vista por secciones para ``AnalysisOutput.sections`` (compat).

    Claves v3 (``headline``, ``field_reading``, ``observations``,
    ``actions``, ``watch_signals``, ``coach_question``, ``data_gaps``). El
    único consumidor genérico de ``sections`` es ``rehydrate_names``, que
    itera las claves sin asumir nombres, así que no hay contrato que romper.
    """
    sections: dict[str, str] = {"headline": draft.headline}
    if draft.field_reading is not None and draft.field_reading.summary:
        sections["field_reading"] = draft.field_reading.summary
    if draft.observations:
        sections["observations"] = "\n".join(
            f"- {o.claim} — evidencia: {'; '.join(o.evidence)}" for o in draft.observations
        )
    if draft.actions:
        sections["actions"] = "\n".join(_action_bullet(a) for a in draft.actions)
    if draft.watch_signals:
        sections["watch_signals"] = "\n".join(f"- {s}" for s in draft.watch_signals)
    if draft.coach_question:
        sections["coach_question"] = draft.coach_question
    if draft.data_gaps:
        sections["data_gaps"] = "\n".join(f"- {g}" for g in draft.data_gaps)
    return sections


def action_to_legacy_recommendation(action: ActionV3) -> dict[str, Any]:
    """Serializa una acción v3 como dict superset del schema legacy.

    Mantiene ``text``/``category``/``priority`` (las claves que consumen el
    DTO y el frontend v2) y agrega ``horizon``/``catalog_ref``/``derived_from``.
    ``category`` conserva el valor v3 real (incluido ``tactics``); la
    degradación a la categoría legacy sólo ocurre en
    :func:`insight_v3_to_legacy_recommendations`.
    """
    ref = action.catalog_ref
    return {
        "text": action.text,
        "category": getattr(action.category, "value", action.category),
        "priority": getattr(action.priority, "value", action.priority),
        "horizon": getattr(action.horizon, "value", action.horizon),
        "catalog_ref": (
            {
                "kind": getattr(ref.kind, "value", ref.kind),
                "code": ref.code,
                "label": ref.label,
            }
            if ref is not None
            else None
        ),
        "derived_from": action.derived_from,
    }


def insight_v3_to_legacy_recommendations(draft: InsightV3) -> list[Any]:
    """Convierte ``actions`` a :class:`Recommendation` (schema legacy).

    Necesario para que ``AnalysisOutput.recommendations`` siga tipado y los
    nodos/DTO existentes no cambien. ``tactics`` se degrada a ``technique``
    (ver :data:`_ACTION_TO_LEGACY_CATEGORY`); el valor original permanece en
    ``structured_json``.
    """
    from app.services.race.schemas import (
        Priority as LegacyPriority,
        Recommendation,
        RecommendationCategory,
    )

    out: list[Any] = []
    for action in draft.actions:
        category = getattr(action.category, "value", action.category)
        priority = getattr(action.priority, "value", action.priority)
        try:
            out.append(
                Recommendation(
                    text=action.text[:500],
                    category=RecommendationCategory(
                        _ACTION_TO_LEGACY_CATEGORY.get(category, "technique")
                    ),
                    priority=LegacyPriority(priority),
                )
            )
        except ValueError:  # pragma: no cover - enums cerrados aguas arriba
            continue
    return out


def horizon_label(horizon: Any) -> str:
    """Etiqueta en español de un ``Horizon`` (para prompts y UI server-side)."""
    value = getattr(horizon, "value", horizon)
    return _HORIZON_LABELS.get(str(value), str(value))


# ---------------------------------------------------------------------------
# Grounding numérico
# ---------------------------------------------------------------------------

# Tiempos hh:mm:ss / mm:ss primero: si se extrajeran números sueltos antes,
# "0:35:30" se partiría en "0", "35" y "30" y el grounding perdería el token.
_TIME_RE = re.compile(r"\d{1,3}:\d{2}(?::\d{2})?")
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def normalize_numeric_token(raw: str) -> str:
    """Normaliza un token numérico para comparaciones tolerantes al formato.

    Reglas (spec.md §Critic v3 — "tolerante a ``8.6%``, ``8,6 %``,
    ``0:35:30``, ``2:49``"):

    - Coma decimal → punto (``"8,6"`` → ``"8.6"``).
    - Ceros decimales finales se recortan (``"8.60"`` → ``"8.6"``,
      ``"12.0"`` → ``"12"``).
    - Los tiempos se dejan tal cual salvo el recorte de ceros a la izquierda
      del primer campo (``"0:35:30"`` → ``"0:35:30"``, ``"02:49"`` → ``"2:49"``).
    - El signo ``-`` se conserva (los deltas negativos son datos reales).
    """
    token = raw.strip()
    if ":" in token:
        head, _, tail = token.partition(":")
        head = head.lstrip("0") or "0"
        return f"{head}:{tail}"
    token = token.replace(",", ".")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token or "0"


def extract_numeric_tokens(text: str) -> set[str]:
    """Extrae los tokens numéricos normalizados presentes en ``text``.

    Se aplica al **prompt renderizado** (para construir ``grounding_numbers``)
    y al texto del draft (para el precheck de grounding de T202): si el
    modelo cita un número que no está en el prompt, lo inventó.

    Args:
        text: markdown/prompt ya renderizado. ``None``/vacío → set vacío.

    Returns:
        Set de tokens normalizados por :func:`normalize_numeric_token`.
    """
    if not text:
        return set()

    tokens: set[str] = set()
    remainder_parts: list[str] = []
    cursor = 0
    for match in _TIME_RE.finditer(text):
        tokens.add(normalize_numeric_token(match.group(0)))
        remainder_parts.append(text[cursor : match.start()])
        cursor = match.end()
    remainder_parts.append(text[cursor:])

    for chunk in remainder_parts:
        for match in _NUMBER_RE.finditer(chunk):
            tokens.add(normalize_numeric_token(match.group(0)))

    return tokens
