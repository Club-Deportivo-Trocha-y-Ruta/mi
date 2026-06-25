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

from datetime import date, datetime, time
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    SessionSegment,
    SkillProgressStatus,
)


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
    """Body para crear una sesión de técnica via el builder (US3).

    Reutiliza training_svc.create_session internamente para que la sesión
    aparezca en el calendario/lista estándar y soporte asistencia + rúbrica
    (FR-011/012).
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


class TechniqueSessionItem(BaseModel):
    """Ejercicio dentro de una sesión ensamblada por el builder (US3 response)."""

    exercise_id: int
    name: str
    segment: SessionSegment
    position: int
    age_bands: list[AgeBand]
    skills: list[SkillRead]

    model_config = {"from_attributes": True}


class AssembleSessionResponse(BaseModel):
    """Respuesta 201 al ensamblar una sesión de técnica (US3).

    mixes_age_bands=True activa la notificación de mezcla de edades (FR-014).
    La sesión se guarda independientemente de ese valor.
    """

    training_session_id: int
    mixes_age_bands: bool
    items: list[TechniqueSessionItem]


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
