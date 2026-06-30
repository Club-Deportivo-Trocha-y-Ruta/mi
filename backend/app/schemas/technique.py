"""Pydantic v2 schemas for the Technique & Gymkhana Library (feature 018).

Schema ↔ contract mapping (contracts/rest-api.md):
  SkillRead               → skill taxonomy item in filters and nested responses
  MaterialRead            → material item in catalog entries
  ExerciseListItem        → GET /api/technique/exercises list row
  ExerciseDetail          → GET /api/technique/exercises/{id} full record
  CatalogFilterParams     → query-string params for the catalog list endpoint
  AssembleSessionRequest  → POST /api/technique/sessions body
  AssembleSessionResponse → POST /api/technique/sessions 201 body
  TechniqueSessionItem    → one exercise within a technique-assembled session
  SkillProgressEvent      → one append-only progress record
  AthleteProgressRead     → GET /api/technique/athletes/{id}/progress response
  ProgressCreate          → POST /api/technique/athletes/{id}/progress body
  ExerciseCreate          → POST /api/technique/exercises body (curation US5)
  ExerciseUpdate          → PUT  /api/technique/exercises/{id} body (curation US5)
  ExerciseVisibilityPatch → PATCH /api/technique/exercises/{id}/visibility body
  ExerciseVisibilityRead  → PATCH /api/technique/exercises/{id}/visibility response

Enums are imported from app.models.technique_exercise (single source of truth).
All response schemas that read ORM objects set model_config from_attributes=True.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    SessionSegment,
    SkillProgressStatus,
)


# ---------------------------------------------------------------------------
# GymkhanaLayout document schema (feature 019 — Phase A)
# ---------------------------------------------------------------------------

# FR-023 Phase A guard: only the controlled set is accepted as a label —
# kind name (bare) plus an optional ' #<digits>' sequence (e.g. 'cone #2').
_PHASE_A_LABEL_RE = re.compile(
    r"^(cone|line|gate|mine|arrow|beam|ring)( #\d+)?$"
)

# ---------------------------------------------------------------------------
# Phase B label anti-PII constants (feature 019, O-6, FR-019)
# ---------------------------------------------------------------------------

# Reject date-of-birth patterns: dd/mm/yyyy or yyyy-mm-dd.
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
# Maximum allowed length for a Phase B element label.
_MAX_PHASE_B_LABEL = 40


def _phase_b_label_is_pii(label: str) -> bool:
    """Return True when a Phase B label triggers the anti-PII heuristic (FR-019).

    Rejects:
    - Labels longer than _MAX_PHASE_B_LABEL characters.
    - Date patterns (dd/mm/yyyy or yyyy-mm-dd) — date-of-birth heuristic.
    - Two or more "Capitalized Words" (first char uppercase, word ≥ 2 chars) —
      person-name heuristic (e.g. "Juan Carlos", "María Fernanda").

    Allows short circuit annotations: "Salida", "#1", "zona A", "Cono #3".
    Note: "zona principal" (lowercase) and "Zona A" ("A" is 1 char) both pass.
    """
    if len(label) > _MAX_PHASE_B_LABEL:
        return True
    if _DATE_RE.search(label):
        return True
    # Person-name heuristic: ≥ 2 words each starting with uppercase and ≥ 2 chars.
    cap_words = [w for w in label.split() if len(w) >= 2 and w[0].isupper()]
    return len(cap_words) >= 2


class CircuitElement(BaseModel):
    """Un elemento gráfico dentro de un circuito de gymkhana.

    Coordenadas en unidades de canvas; el renderer normaliza al viewBox SVG.
    Phase A no admite etiquetas de texto libre (FR-023/O-5).
    """

    kind: Literal["cone", "line", "gate", "mine", "arrow", "beam", "ring"]
    x: float
    y: float
    rotation: float | None = None
    # style is only meaningful on kind='line': dashed=trayecto guía/libre,
    # solid=trayecto técnico (data-model.md §Element vocabulary, O-2).
    style: Literal["dashed", "solid"] | None = None
    # Phase A: controlled set only — kind name + optional ' #n'. See FR-023.
    label: str | None = None

    @model_validator(mode="after")
    def _validate_element(self) -> "CircuitElement":
        # Reject non-finite coordinate / rotation values.
        if not math.isfinite(self.x):
            raise ValueError("x debe ser un número finito.")
        if not math.isfinite(self.y):
            raise ValueError("y debe ser un número finito.")
        if self.rotation is not None and not math.isfinite(self.rotation):
            raise ValueError("rotation debe ser un número finito.")
        # FR-023 Phase A guard: reject any free-text label.
        if self.label is not None and not _PHASE_A_LABEL_RE.fullmatch(self.label):
            raise ValueError(
                "En Phase A, label solo puede ser el nombre del kind con un número "
                "opcional (e.g. 'cone', 'line #2'). Texto libre no está permitido "
                "(FR-023)."
            )
        return self


class GymkhanaLayout(BaseModel):
    """Documento JSON de un circuito de gymkhana; persiste en layout_json (feature 019).

    width/height son unidades de canvas positivas y finitas.
    elements puede estar vacío (layout válido sin elementos colocados).
    Las coordenadas x/y de cada elemento deben caer dentro de [0, width] × [0, height].
    """

    width: float = Field(gt=0, description="Ancho del canvas en unidades de circuito.")
    height: float = Field(gt=0, description="Alto del canvas en unidades de circuito.")
    elements: list[CircuitElement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_layout(self) -> "GymkhanaLayout":
        # Field(gt=0) does not reject +inf; enforce finiteness explicitly.
        if not math.isfinite(self.width):
            raise ValueError("width debe ser un número finito y positivo.")
        if not math.isfinite(self.height):
            raise ValueError("height debe ser un número finito y positivo.")
        # Bounds check: every element must lie within the canvas.
        for i, el in enumerate(self.elements):
            if not (0 <= el.x <= self.width):
                raise ValueError(
                    f"elements[{i}].x={el.x} está fuera del rango [0, {self.width}]."
                )
            if not (0 <= el.y <= self.height):
                raise ValueError(
                    f"elements[{i}].y={el.y} está fuera del rango [0, {self.height}]."
                )
        return self


# ---------------------------------------------------------------------------
# GymkhanaLayout Phase B — composer combined circuit (feature 019, O-6)
# ---------------------------------------------------------------------------
# IMPORTANT: CircuitElement / GymkhanaLayout (Phase A, above) are UNCHANGED.
# The Phase A strict no-free-text-label guard (FR-023) and its tests must keep
# passing. Phase B is a SEPARATE schema used ONLY for the composer's combined
# circuit in AssembleSessionRequest. Never mix the two schemas.
# ---------------------------------------------------------------------------


class CircuitElementPhaseB(BaseModel):
    """Phase B circuit element: free-text labels allowed with anti-PII guard (O-6).

    Identical geometry rules as CircuitElement (finite coords, bounds validated
    by GymkhanaLayoutPhaseB). Labels pass the _phase_b_label_is_pii heuristic
    to block athlete names and dates of birth (FR-019).

    This schema MUST NOT be used anywhere the Phase A strict guard applies
    (exercise create/update via ExerciseCreate/ExerciseUpdate). It is used
    exclusively as the element type within GymkhanaLayoutPhaseB.
    """

    kind: Literal["cone", "line", "gate", "mine", "arrow", "beam", "ring"]
    x: float
    y: float
    rotation: float | None = None
    style: Literal["dashed", "solid"] | None = None
    # Phase B: free-text allowed; anti-PII heuristic applied (FR-019, O-6).
    label: str | None = None

    @model_validator(mode="after")
    def _validate_element(self) -> "CircuitElementPhaseB":
        if not math.isfinite(self.x):
            raise ValueError("x debe ser un número finito.")
        if not math.isfinite(self.y):
            raise ValueError("y debe ser un número finito.")
        if self.rotation is not None and not math.isfinite(self.rotation):
            raise ValueError("rotation debe ser un número finito.")
        if self.label is not None and _phase_b_label_is_pii(self.label):
            raise ValueError(
                "La etiqueta parece contener información personal (nombre o fecha). "
                "Usa una anotación corta de circuito, por ejemplo 'Salida', '#1', "
                "'zona A' (FR-019)."
            )
        return self


class GymkhanaLayoutPhaseB(BaseModel):
    """Phase B GymkhanaLayout: uses CircuitElementPhaseB for the drag-and-drop composer.

    The Phase A GymkhanaLayout and its strict label guard (FR-023) are
    UNCHANGED — this is a parallel schema for the composer's free-form combined
    circuit only. Same canvas geometry rules; different element label policy.
    Persisted in technique_exercises.layout_json on a hidden synthetic row (O-6).
    """

    width: float = Field(gt=0, description="Ancho del canvas en unidades de circuito.")
    height: float = Field(gt=0, description="Alto del canvas en unidades de circuito.")
    elements: list[CircuitElementPhaseB] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_layout(self) -> "GymkhanaLayoutPhaseB":
        if not math.isfinite(self.width):
            raise ValueError("width debe ser un número finito y positivo.")
        if not math.isfinite(self.height):
            raise ValueError("height debe ser un número finito y positivo.")
        for i, el in enumerate(self.elements):
            if not (0 <= el.x <= self.width):
                raise ValueError(
                    f"elements[{i}].x={el.x} está fuera del rango [0, {self.width}]."
                )
            if not (0 <= el.y <= self.height):
                raise ValueError(
                    f"elements[{i}].y={el.y} está fuera del rango [0, {self.height}]."
                )
        return self


# ---------------------------------------------------------------------------
# Taxonomy / reference read schemas
# ---------------------------------------------------------------------------


class SkillRead(BaseModel):
    """Habilidad técnica anidada en respuestas de ejercicio y progreso."""

    code: str
    slug: str
    name: str

    model_config = {"from_attributes": True}


class MaterialRead(BaseModel):
    """Material físico anidado en respuestas de ejercicio."""

    slug: str
    name: str
    is_none: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Catalog — list and detail
# ---------------------------------------------------------------------------


class ExerciseListItem(BaseModel):
    """Fila del catálogo de ejercicios devuelta por la lista / filtros (US1)."""

    id: int
    slug: str
    name: str
    summary: str
    difficulty: ExerciseDifficulty
    is_game: bool
    is_gymkhana: bool
    # age_bands: derived from the TechniqueExerciseAgeBand one-to-many relation.
    # The service layer maps each row's .age_band value into this list.
    age_bands: list[AgeBand]
    skills: list[SkillRead]
    materials: list[MaterialRead]
    is_seeded: bool
    is_hidden: bool

    model_config = {"from_attributes": True}


class ExerciseDetail(ExerciseListItem):
    """Detalle completo de un ejercicio (US2 — GET /api/technique/exercises/{id}).

    Extiende ExerciseListItem con campos de método pedagógico y layout.
    gymkhana exercises must have non-null layout_ascii (invariant FR-008).
    """

    how_to: str
    layout_ascii: str | None
    layout_alt: str | None
    # Feature 019 Phase A: structured circuit diagram (null when not yet backfilled).
    # ExerciseListItem intentionally omits this field to keep list reads lean.
    #
    # Union with GymkhanaLayoutPhaseB (O-6): this same endpoint
    # (GET /api/technique/exercises/{id}) is the documented round-trip path for
    # re-opening the composer's hidden synthetic combined-circuit exercise
    # (AssembleSessionResponse.combined_exercise_id, SC-006). That row's
    # layout_json may contain Phase B free-text labels, which the strict Phase A
    # CircuitElement rejects. left_to_right union_mode tries the strict
    # GymkhanaLayout first (normal catalog exercises keep validating against it
    # unchanged) and only falls back to the lenient GymkhanaLayoutPhaseB when a
    # label fails the Phase A controlled-set guard.
    layout_json: Annotated[
        GymkhanaLayout | GymkhanaLayoutPhaseB | None,
        Field(union_mode="left_to_right"),
    ] = None
    confidence: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Catalog filter query params (US1 — GET /api/technique/exercises)
# ---------------------------------------------------------------------------


class CatalogFilterParams(BaseModel):
    """Parámetros opcionales de filtrado del catálogo.

    Todos son opcionales y combinables (FR-002). El router los parsea desde
    Query() params y construye el objeto para el service layer.
    """

    skill: str | None = Field(
        default=None,
        description="Slug de habilidad para filtrar (e.g. 'frenado').",
    )
    age_band: AgeBand | None = Field(
        default=None,
        description="Banda de edad: '7-9', '10-12' o '13-15'.",
    )
    difficulty: ExerciseDifficulty | None = Field(
        default=None,
        description="Dificultad del ejercicio.",
    )
    # Received as a comma-separated string from the query string;
    # the router splits it before constructing this object.
    materials: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de slugs de materiales disponibles hoy. "
            "El catálogo devuelve ejercicios cuyos materiales sean subconjunto "
            "de esta lista, más ejercicios sin_material (FR-009)."
        ),
    )
    include_hidden: bool = Field(
        default=False,
        description="Si True, incluye filas ocultas (vistas de curación).",
    )
    is_game: bool | None = Field(
        default=None,
        description="Si True, filtra solo ejercicios marcados como juego puro.",
    )


# ---------------------------------------------------------------------------
# Session assembly (US3 — POST /api/technique/sessions)
# ---------------------------------------------------------------------------


class AssembleItem(BaseModel):
    """Un ejercicio con su segmento y posición dentro de la sesión ensamblada."""

    exercise_id: int
    segment: SessionSegment
    position: int = Field(ge=0)


class AssembleSessionRequest(BaseModel):
    """Body para crear (o re-editar) una sesión de técnica via el builder (US3/019-B).

    Reutiliza training_svc.create_session internamente para que la sesión
    aparezca en el calendario/lista estándar y soporte asistencia + rúbrica
    (FR-011/012).

    Feature 019 Phase B (O-6):
    - combined_layout: el circuito libre combinado dibujado en el compositor.
      Cuando está presente, el backend crea (o actualiza) un TechniqueExercise
      sintético oculto (is_hidden=True, is_gymkhana=True) que persiste ese
      layout en layout_json.
    - combined_exercise_id: en re-edición, identifica el ejercicio sintético
      existente a ACTUALIZAR. Cuando está ausente, se crea uno nuevo.
      El id del sintético se devuelve en AssembleSessionResponse para que el
      frontend lo almacene y habilite el round-trip lossless (SC-006).
    """

    scheduled_date: date
    scheduled_start_time: time
    duration_min: int = Field(ge=15, le=240)
    location: str = Field(max_length=200)
    technical_focus: str = Field(max_length=200)
    objectives: str | None = Field(default=None, max_length=1000)
    convocados_athlete_ids: list[int] = Field(min_length=1)
    items: list[AssembleItem] = Field(
        min_length=1,
        description="Al menos un ejercicio es requerido para ensamblar la sesión.",
    )
    # Feature 019 Phase B (O-6): optional free-form combined gymkhana circuit.
    # Uses GymkhanaLayoutPhaseB (separate from Phase A GymkhanaLayout — FR-023 unchanged).
    combined_layout: GymkhanaLayoutPhaseB | None = None
    # Re-edit path: id of the existing synthetic TechniqueExercise to UPDATE.
    # When absent, a new synthetic exercise is created (create path).
    # Must NOT appear in items — the synthetic exercise is server-managed.
    combined_exercise_id: int | None = None

    @model_validator(mode="after")
    def _validate_combined_fields(self) -> "AssembleSessionRequest":
        if self.combined_exercise_id is not None:
            item_ids = {item.exercise_id for item in self.items}
            if self.combined_exercise_id in item_ids:
                raise ValueError(
                    "combined_exercise_id no puede estar en items; "
                    "el ejercicio sintético del circuito combinado es gestionado "
                    "por el servidor (O-6)."
                )
        return self


class TechniqueSessionItem(BaseModel):
    """Ejercicio dentro de una sesión ensamblada por el builder (US3 / 019 Phase B).

    is_hidden=True identifica el ejercicio sintético del circuito combinado libre
    (feature 019, O-6). El frontend filtra o trata estos items de forma especial
    al mostrar la lista de ejercicios: el sintético no es un ejercicio del catálogo.
    is_gymkhana=True en el sintético permite al frontend distinguirlo de ejercicios
    ocultos de catálogo que pudieran estar referenciados.
    """

    exercise_id: int
    name: str
    segment: SessionSegment
    position: int
    age_bands: list[AgeBand]
    skills: list[SkillRead]
    # Feature 019 Phase B (O-6): True for the synthetic combined-layout exercise.
    # Frontend uses this flag to identify and skip the synthetic item in the
    # exercise list, and to know which exercise_id holds the combined layout_json.
    is_hidden: bool = False
    is_gymkhana: bool = False

    model_config = {"from_attributes": True}


class AssembleSessionResponse(BaseModel):
    """Respuesta 201 al ensamblar una sesión de técnica (US3 / 019 Phase B).

    mixes_age_bands=True activa la notificación de mezcla de edades (FR-014).
    La sesión se guarda independientemente de ese valor.

    Feature 019 Phase B (O-6):
    combined_exercise_id — id del TechniqueExercise sintético oculto que persiste
    el circuito combinado libre. No nulo cuando combined_layout fue enviado en la
    petición. El frontend DEBE almacenar este id para habilitar el round-trip
    lossless (SC-006): al re-abrir, el frontend llama a
    GET /api/technique/exercises/{combined_exercise_id} para recuperar layout_json.
    """

    training_session_id: int
    mixes_age_bands: bool
    items: list[TechniqueSessionItem]
    # Non-null when combined_layout was provided. Null for sessions without a
    # combined circuit. Frontend stores this to enable lossless re-editing.
    combined_exercise_id: int | None = None


# ---------------------------------------------------------------------------
# Per-athlete skill progress (US4)
# ---------------------------------------------------------------------------


class SkillProgressEvent(BaseModel):
    """Evento de progreso de habilidad técnica (append-only, US4).

    Privacidad: coach/admin únicamente. Sin PII de menores más allá de lo
    autorizado al coach (FR-021, SC-005).
    """

    id: int
    skill: SkillRead
    status: SkillProgressStatus
    coach_note: str | None
    season: int
    recorded_at: datetime

    model_config = {"from_attributes": True}


class AthleteProgressRead(BaseModel):
    """Respuesta de GET /api/technique/athletes/{athlete_id}/progress (US4).

    current: último evento por habilidad (estado actual).
    history: todos los eventos de la temporada ordenados cronológicamente.
    No aparece ningún otro atleta — invariante SC-005.
    """

    athlete_id: int
    current: list[SkillProgressEvent]
    history: list[SkillProgressEvent]


class ProgressCreate(BaseModel):
    """Body para POST /api/technique/athletes/{athlete_id}/progress (US4).

    Cada POST añade un nuevo evento; el estado actual refleja el más reciente.
    coach_note usa framing de clima de maestría (mastery-climate), sin PII.
    """

    skill_id: int
    status: SkillProgressStatus
    coach_note: Annotated[str | None, Field(default=None, max_length=300)] = None
    season: int = Field(ge=2020, le=2100)


# ---------------------------------------------------------------------------
# Curation: create / update / visibility (US5)
# ---------------------------------------------------------------------------


class ExerciseCreate(BaseModel):
    """Body para POST /api/technique/exercises (US5 — coach/admin curation).

    Validaciones (data-model invariants):
    - gymkhana ⇒ layout_ascii requerido (FR-008).
    - Al menos 1 banda de edad (FR-003).
    - Al menos 1 habilidad (FR-006).
    """

    name: str = Field(max_length=120)
    summary: str = Field(max_length=300)
    how_to: str
    difficulty: ExerciseDifficulty
    is_game: bool = False
    is_gymkhana: bool = False
    layout_ascii: str | None = None
    layout_alt: str | None = None
    # Feature 019 Phase A: optional structured diagram; validated by GymkhanaLayout.
    layout_json: GymkhanaLayout | None = None
    age_bands: list[AgeBand] = Field(min_length=1)
    skill_slugs: list[str] = Field(min_length=1)
    material_slugs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_gymkhana_layout(self) -> "ExerciseCreate":
        if self.is_gymkhana and not self.layout_ascii:
            raise ValueError(
                "layout_ascii es requerido cuando is_gymkhana es True (FR-008)."
            )
        return self


class ExerciseUpdate(BaseModel):
    """Body para PUT /api/technique/exercises/{id} (US5 — curation, partial).

    Aplica los mismos invariantes que ExerciseCreate cuando los campos
    relevantes están presentes en el payload.
    """

    name: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=300)
    how_to: str | None = None
    difficulty: ExerciseDifficulty | None = None
    is_game: bool | None = None
    is_gymkhana: bool | None = None
    layout_ascii: str | None = None
    layout_alt: str | None = None
    # Feature 019 Phase A: optional structured diagram; validated by GymkhanaLayout.
    layout_json: GymkhanaLayout | None = None
    age_bands: list[AgeBand] | None = Field(default=None, min_length=1)
    skill_slugs: list[str] | None = Field(default=None, min_length=1)
    material_slugs: list[str] | None = None

    @model_validator(mode="after")
    def _validate_gymkhana_layout(self) -> "ExerciseUpdate":
        # Only enforce when both keys are present in the payload.
        # The service layer must additionally check the persisted value when
        # only one of the two fields is included in the update.
        if self.is_gymkhana is True and self.layout_ascii is None:
            raise ValueError(
                "layout_ascii es requerido cuando is_gymkhana es True (FR-008). "
                "Incluye layout_ascii en el mismo payload o actualízalo primero."
            )
        return self


class ExerciseVisibilityPatch(BaseModel):
    """Body para PATCH /api/technique/exercises/{id}/visibility (US5)."""

    is_hidden: bool


class ExerciseVisibilityRead(BaseModel):
    """Respuesta de PATCH /api/technique/exercises/{id}/visibility."""

    id: int
    is_hidden: bool

    model_config = {"from_attributes": True}
