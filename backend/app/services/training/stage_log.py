"""``StageLog`` — modelo de contenido de la bitácora de etapa (feature 038).

Implementa ``specs/038-newsletter-bitacora-redesign/data-model.md`` §1. El
mes del boletín se presenta como una "etapa" de la temporada: una ruta con
hitos (waypoints), una cima, "lo que vio el entrenador" (observaciones),
la lectura del analista (037 traducida a lenguaje familiar), el perfil de
esfuerzo semanal, el próximo tramo y la brújula de la familia.

Este módulo solo define el **contrato de datos** (Pydantic) y la proyección
allow-list hacia el DTO que consume el portal de padres
(:func:`to_parent_dto`). La construcción del contenido vive en
``stage_log_builder.py``; la narrativa IA vive en
``app/services/ai/use_cases/athlete_monthly_newsletter_v2.py`` (feature 038,
Wave 2 — no implementada en este módulo).

Privacidad (Ley 1581, CLAUDE.md):
  - ``athlete_first_name`` se usa solo para render; nunca viaja a un
    proveedor de IA (ver ``family_translation.py`` / prompt v2, Wave 2).
  - :func:`to_parent_dto` aplica un **allow-list** explícito, nunca un
    deny-list: cualquier campo nuevo que se añada a ``StageLog`` en el
    futuro queda oculto al padre por defecto hasta que se agregue
    explícitamente a ``_PARENT_DTO_KEYS``.
  - ``block_states``, ``grounding_violations`` y
    ``analyst_reading.source_insight_id`` son de uso exclusivo del
    entrenador (studio) y nunca llegan al padre.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.race.audience import Audience, redact_for_audience

# NOTA (bug de Pydantic v2 + `from __future__ import annotations`): varios
# modelos abajo tienen un campo LLAMADO ``date`` tipado como ``date``. Con
# anotaciones diferidas (PEP 563), Pydantic resuelve la anotación de forma
# perezosa usando el ``__dict__`` de la clase como namespace local; como el
# valor por defecto (``None``) de ese mismo campo queda asignado a
# ``ClaseX.date`` en ese diccionario, la búsqueda del nombre ``date`` dentro
# de la anotación ``"date | None"`` encuentra ese ``None`` en vez de la clase
# importada — y pydantic revienta con
# ``TypeError: unsupported operand type(s) for |: 'NoneType' and 'NoneType'``.
# Por eso esos campos usan el tipo calificado ``dt.date`` (atributo de
# módulo, no un nombre plano) en vez de ``date`` a secas: el nombre que hay
# que resolver es ``dt`` (el módulo), que ningún campo sombrea.

__all__ = [
    "WaypointKind",
    "BlockState",
    "SummitKind",
    "Waypoint",
    "EffortWeek",
    "Summit",
    "Observation",
    "AnalystReading",
    "NextRace",
    "NextSegment",
    "FamilyCompass",
    "BadgeView",
    "PhotoView",
    "StageLog",
    "BADGE_LABELS",
    "badge_label_for",
    "to_parent_dto",
]


# ---------------------------------------------------------------------------
# Helpers de recorte de palabras (regla de negocio, no solo de tipo).
# ---------------------------------------------------------------------------


def _limit_words(value: str, max_words: int) -> str:
    """Recorta ``value`` a ``max_words`` palabras, sin agregar elipsis.

    Nunca lanza excepción: la bitácora debe poder renderizarse siempre, aun
    si un texto (estático o IA) llega más largo de lo esperado. Los límites
    de palabras documentados en data-model.md §1 son reglas de negocio de
    esta etapa (contenido para familias, no un reporte técnico) por eso se
    aplican aquí, en el propio modelo, y no solo en el generador.
    """
    words = value.split()
    if len(words) <= max_words:
        return value
    return " ".join(words[:max_words])


def _ensure_question(value: str) -> str:
    """Garantiza que un texto termine en ``?`` (brújula de la familia)."""
    stripped = value.rstrip()
    if stripped.endswith("?"):
        return stripped
    return stripped.rstrip(".,;: ") + "?"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WaypointKind(str, Enum):
    """Tipo de hito en la ruta del mes ("ruta del mes")."""

    FIRST_SESSION = "first_session"
    RACE = "race"
    STREAK = "streak"
    BADGE = "badge"
    BEST_SESSION = "best_session"
    NEXT_RACE = "next_race"


class BlockState(str, Enum):
    """Estado de un bloque de contenido, tal como lo ve el entrenador en el
    studio (AC-4.2): IA / Editado / Estático / Oculto / Vacío."""

    AI = "ai"
    EDITED = "edited"
    STATIC = "static"
    HIDDEN = "hidden"
    EMPTY = "empty"


class SummitKind(str, Enum):
    """Origen de la "cima del mes": un resultado de carrera o un hito de
    entrenamiento (cuando no hubo carrera en el mes)."""

    RACE = "race"
    TRAINING = "training"


# Iconos lucide permitidos para waypoints (research.md / spec.md vocabulario).
WaypointIcon = Literal["flag", "award", "flame", "star", "map-pin", "compass"]


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------


class Waypoint(BaseModel):
    """Un hito de la ruta del mes."""

    model_config = ConfigDict(extra="forbid")

    kind: WaypointKind
    date: dt.date
    label: str = Field(..., min_length=1, max_length=120)
    sublabel: str | None = Field(default=None, max_length=120)
    icon: WaypointIcon
    is_future: bool = False


class EffortWeek(BaseModel):
    """Una semana ISO del "perfil de esfuerzo" (altimetría)."""

    model_config = ConfigDict(extra="forbid")

    week_label: str = Field(..., min_length=1, max_length=40)
    sessions_planned: int = Field(..., ge=0)
    sessions_attended: int = Field(..., ge=0)
    mean_rpe: float | None = Field(default=None, ge=0, le=10)


class Summit(BaseModel):
    """La "cima del mes": el único highlight (carrera o hito de entrenamiento)."""

    model_config = ConfigDict(extra="forbid")

    kind: SummitKind
    title: str = Field(..., min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=400)
    date: dt.date | None = None

    @field_validator("caption", mode="before")
    @classmethod
    def _v_caption(cls, v: str | None) -> str | None:
        return _limit_words(v, 25) if v else v


class Observation(BaseModel):
    """Una de "lo que vio el entrenador": afirmación + evidencia numérica."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(..., min_length=1, max_length=400)
    evidence: str = Field(..., min_length=1, max_length=200)
    block_ref: Literal["attendance", "technical", "race", "badges", "streak"]

    @field_validator("claim", mode="before")
    @classmethod
    def _v_claim(cls, v: str) -> str:
        return _limit_words(v, 35)

    @field_validator("evidence", mode="before")
    @classmethod
    def _v_evidence(cls, v: str) -> str:
        return _limit_words(v, 20)


class AnalystReading(BaseModel):
    """Lectura del analista (037) traducida a lenguaje familiar.

    ``source_insight_id`` es de uso exclusivo del coach DTO — se elimina en
    :func:`to_parent_dto`.
    """

    model_config = ConfigDict(extra="forbid")

    headline_family: str = Field(..., min_length=1, max_length=250)
    action_family: str = Field(..., min_length=1, max_length=250)
    valida_label: str = Field(..., min_length=1, max_length=80)
    source_insight_id: int

    @field_validator("headline_family", "action_family", mode="before")
    @classmethod
    def _v_family_text(cls, v: str) -> str:
        return _limit_words(v, 30)


class NextRace(BaseModel):
    """Próxima válida del calendario Copa Valle."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=80)
    date: dt.date
    venue: str | None = Field(default=None, max_length=120)
    priority_label: str | None = Field(default=None, max_length=40)


class NextSegment(BaseModel):
    """El "próximo tramo": focos técnicos planificados + próxima carrera."""

    model_config = ConfigDict(extra="forbid")

    focus_groups: list[str] = Field(default_factory=list, max_length=4)
    next_race: NextRace | None = None
    text: str | None = Field(default=None, max_length=400)

    @field_validator("text", mode="before")
    @classmethod
    def _v_text(cls, v: str | None) -> str | None:
        return _limit_words(v, 40) if v else v


class FamilyCompass(BaseModel):
    """La "brújula de la familia" (Rincón de la familia)."""

    model_config = ConfigDict(extra="forbid")

    conversation_question: str = Field(..., min_length=1, max_length=250)
    monthly_challenge: str = Field(..., min_length=1, max_length=250)
    what_to_watch: str = Field(..., min_length=1, max_length=250)

    @field_validator("conversation_question", mode="before")
    @classmethod
    def _v_question(cls, v: str) -> str:
        return _ensure_question(_limit_words(v, 30))

    @field_validator("monthly_challenge", "what_to_watch", mode="before")
    @classmethod
    def _v_compass_text(cls, v: str) -> str:
        return _limit_words(v, 30)


class BadgeView(BaseModel):
    """Insignia lista para render (nunca el código crudo)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=80)
    icon: str = Field(default="award", max_length=40)
    earned_at: date | None = None


class PhotoView(BaseModel):
    """Foto del mes lista para render (thumbnail + caption, sin metadatos)."""

    model_config = ConfigDict(extra="forbid")

    thumbnail_url: str = Field(..., min_length=1)
    caption: str | None = Field(default=None, max_length=200)


class StageLog(BaseModel):
    """Contenido completo de una bitácora de etapa (schema v2)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    stage_number: int = Field(..., ge=1)
    period_label: str = Field(..., min_length=1, max_length=40)
    is_current_month: bool = False

    athlete_first_name: str = Field(..., min_length=1, max_length=80)
    athlete_reference: str = Field(..., min_length=1, max_length=20)

    stage_title: str = Field(..., min_length=1, max_length=200)

    # "3..6" en data-model.md describe el caso típico; el edge case de mes
    # sin ninguna sesión (AC edge cases, spec.md) produce deliberadamente un
    # trail de un solo waypoint (solo la próxima carrera) — por eso NO se
    # impone un mínimo aquí, solo el tope de 6.
    trail: list[Waypoint] = Field(default_factory=list, max_length=6)

    summit: Summit | None = None
    observations: list[Observation] = Field(default_factory=list, max_length=3)
    analyst_reading: AnalystReading | None = None
    effort_profile: list[EffortWeek] = Field(default_factory=list)
    next_segment: NextSegment | None = None
    family_compass: FamilyCompass | None = None
    badges: list[BadgeView] = Field(default_factory=list)
    photos: list[PhotoView] = Field(default_factory=list)

    coach_note: str | None = Field(default=None, max_length=600)

    # Solo coach DTO — nunca llegan al padre (ver to_parent_dto).
    block_states: dict[str, BlockState] = Field(default_factory=dict)
    grounding_violations: list[str] = Field(default_factory=list)

    @field_validator("stage_title", mode="before")
    @classmethod
    def _v_stage_title(cls, v: str) -> str:
        return _limit_words(v, 20)

    @field_validator("coach_note", mode="before")
    @classmethod
    def _v_coach_note(cls, v: str | None) -> str | None:
        return _limit_words(v, 60) if v else v


# ---------------------------------------------------------------------------
# Badges — etiquetas legibles (nunca el código crudo, ver athlete_badge.py).
# ---------------------------------------------------------------------------

BADGE_LABELS: dict[str, str] = {
    "attendance_100": "Asistencia 100 %",
    "attendance_90": "Asistencia 90 %",
    "attendance_75": "Asistencia 75 %",
    # "Primer podio": la insignia se otorga UNA sola vez por atleta (el
    # primer podio histórico), así que la etiqueta conserva el "Primer" —
    # llamarla solo "Podio" la haría parecer recurrente y le quitaría el
    # carácter de hito, que es justo lo que la familia celebra. Lo que sí
    # cambió el 2026-09-08 es el criterio: badge_evaluator.first_podium
    # ahora exige posición ≤3 (podio clásico) en vez de ≤5, para que la
    # palabra "podio" diga la verdad — la Copa Valle premia hasta el puesto
    # 5, pero con parrillas reales de 5 a 7 corredores un "top 5" no
    # distinguía nada.
    "first_podium": "Primer podio",
    "mtp": "Mejor tiempo personal",
    "top10": "Top 10",
}


def badge_label_for(code: str) -> str:
    """Etiqueta legible para un ``badge_type``. Nunca retorna el código crudo.

    Códigos desconocidos (futuros ``BadgeType`` aún no mapeados aquí) se
    humanizan (guiones bajos → espacios, capitalizado) en vez de mostrarse
    tal cual, para no filtrar identificadores internos a las familias.
    """
    label = BADGE_LABELS.get(code)
    if label:
        return label
    humanized = code.replace("_", " ").strip()
    return humanized.capitalize() if humanized else "Insignia"


# ---------------------------------------------------------------------------
# Proyección al padre — allow-list explícito (nunca deny-list).
# ---------------------------------------------------------------------------

# Todos los campos de StageLog EXCEPTO los de uso exclusivo del coach
# (block_states, grounding_violations). Enumerado explícitamente: un campo
# nuevo agregado a StageLog en el futuro NO se expone al padre hasta que se
# agregue aquí a propósito.
_PARENT_DTO_KEYS: tuple[str, ...] = (
    "schema_version",
    "stage_number",
    "period_label",
    "is_current_month",
    "athlete_first_name",
    "athlete_reference",
    "stage_title",
    "trail",
    "summit",
    "observations",
    "analyst_reading",
    "effort_profile",
    "next_segment",
    "family_compass",
    "badges",
    "photos",
    "coach_note",
)

# Dentro de analyst_reading, allow-list propio: nunca source_insight_id.
_PARENT_ANALYST_READING_KEYS: tuple[str, ...] = (
    "headline_family",
    "action_family",
    "valida_label",
)

# hidden_blocks (data-model.md §3) es un subconjunto de estos cuatro.
_HIDEABLE_BLOCKS: tuple[str, ...] = ("analyst_reading", "photos", "badges", "coach_note")


# ---------------------------------------------------------------------------
# Brecha a la ganadora/podio en snapshots heredados (feature 045, FR-022).
# ---------------------------------------------------------------------------
#
# Decisión del dueño (2026-09-23): la familia nunca ve la brecha contra la
# ganadora ni contra el podio, en ninguna parte. Los ``stage_log_json``
# persistidos ANTES de la 045 traen esa brecha en texto que el builder de
# entonces redactó: «+4,1 % al P1» (sublabel del waypoint de carrera y detalle
# de la cima) y «llegó a 4,1 % del primer lugar» (leyenda estática de la
# cima). Esas filas siguen en la base de datos y se sirven a la familia por
# ``to_parent_dto``, así que la limpieza es **al leer** — sin escribir nada:
# lo persistido no se toca, solo la copia que sale hacia la familia.
#
# El patrón es deliberadamente estrecho: un porcentaje pegado a una
# referencia al líder/podio. «Brecha vs. mediana: +4,1 %» y «86 % de
# asistencia» no coinciden. El texto libre de la IA que mencione al líder sin
# cifra lo cubre el aviso al coach al aprobar (``family_gap_mentions``).

_LEADER_REF = (
    r"(?:P-?[13]|podio|ganador(?:a|es|as)?|l[ií]der(?:es)?"
    r"|primer[oa]?\s+(?:lugar|puesto|posici[oó]n))"
)
_LEADER_GAP_RE = re.compile(
    rf"[+\-−–]?\s*\d+(?:[.,]\d+)?[\s  ]*%[\s  ]*"
    rf"(?:al|del|a\s+la|de\s+la|a)\s+{_LEADER_REF}\b",
    flags=re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_PART_SEPARATOR = " · "

#: Misma frase que ``newsletter_static_copy.static_summit_caption`` usa cuando
#: no hay una lectura cuantitativa que citar (no se importa de allí: ese
#: módulo importa este).
_NEUTRAL_RACE_CAPTION = "{reference} vivió una experiencia de competencia que suma a su proceso."


def _drop_leader_gap_parts(text: str | None) -> str | None:
    """Quita de un texto «parte · parte» las partes que citan la brecha al
    líder/podio (sublabels y detalle de la cima). ``None`` si no queda nada."""
    if not text:
        return text
    kept = [p for p in text.split(_PART_SEPARATOR) if not _LEADER_GAP_RE.search(p)]
    return _PART_SEPARATOR.join(kept) or None


def _drop_leader_gap_sentences(text: str | None) -> str | None:
    """Quita las oraciones que citan la brecha al líder/podio. ``None`` si no
    queda ninguna (el llamador decide qué hacer con el bloque vacío)."""
    if not text or not _LEADER_GAP_RE.search(text):
        return text
    kept = [s for s in _SENTENCE_SPLIT_RE.split(text) if not _LEADER_GAP_RE.search(s)]
    return " ".join(kept) or None


def _scrub_leader_gap_text(dto: dict[str, Any], athlete_reference: str) -> None:
    """Limpia in situ, sobre la copia que se sirve a la familia, la brecha a
    la ganadora/podio de los textos que el builder de la bitácora escribía."""
    for waypoint in dto.get("trail") or []:
        waypoint["sublabel"] = _drop_leader_gap_parts(waypoint.get("sublabel"))

    summit = dto.get("summit")
    if summit is not None:
        summit["detail"] = _drop_leader_gap_parts(summit.get("detail"))
        caption = summit.get("caption")
        if caption and _LEADER_GAP_RE.search(caption):
            summit["caption"] = _NEUTRAL_RACE_CAPTION.format(
                reference=athlete_reference.capitalize()
            )

    kept_observations: list[dict[str, Any]] = []
    for observation in dto.get("observations") or []:
        claim = _drop_leader_gap_sentences(observation.get("claim"))
        evidence = _drop_leader_gap_sentences(observation.get("evidence"))
        if claim and evidence:
            kept_observations.append({**observation, "claim": claim, "evidence": evidence})
    if "observations" in dto:
        dto["observations"] = kept_observations

    next_segment = dto.get("next_segment")
    if next_segment is not None:
        next_segment["text"] = _drop_leader_gap_sentences(next_segment.get("text"))


def to_parent_dto(stage_log: StageLog, hidden_blocks: list[str] | None = None) -> dict[str, Any]:
    """Proyecta ``StageLog`` al DTO que consume el portal de padres.

    Allow-list explícito (nunca deny-list, AC-3.4): solo las claves en
    ``_PARENT_DTO_KEYS`` llegan al padre, y dentro de ``analyst_reading``
    solo las de ``_PARENT_ANALYST_READING_KEYS`` (nunca
    ``source_insight_id``). Los bloques listados en ``hidden_blocks``
    (subconjunto de ``analyst_reading`` / ``photos`` / ``badges`` /
    ``coach_note``) se devuelven vacíos (``None`` o ``[]``).

    Feature 045 (FR-022): a la copia resultante se le quita, al leer, la
    brecha a la ganadora/podio que traen los snapshots heredados (ver
    «Brecha a la ganadora/podio en snapshots heredados») y se pasa por la
    política de audiencia de familia (claves ``gap_to_winner_*``,
    ``gap_to_p3_*``, ``gap_pct``… fuera). No escribe nada ni muta
    ``stage_log``.
    """
    hidden = set(hidden_blocks or [])
    full = stage_log.model_dump(mode="json")

    dto: dict[str, Any] = {key: full[key] for key in _PARENT_DTO_KEYS}

    analyst_reading = dto.get("analyst_reading")
    if analyst_reading is not None:
        dto["analyst_reading"] = {
            key: analyst_reading[key] for key in _PARENT_ANALYST_READING_KEYS
        }

    for block in hidden & set(_HIDEABLE_BLOCKS):
        dto[block] = [] if block in ("photos", "badges") else None

    _scrub_leader_gap_text(dto, stage_log.athlete_reference)
    return redact_for_audience(dto, Audience.FAMILY)
