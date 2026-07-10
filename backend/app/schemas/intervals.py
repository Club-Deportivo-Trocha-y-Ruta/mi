"""Pydantic v2 schemas for Structured Interval Training (feature 026).

Schema ↔ contract mapping (contracts/api.md):
  BlockIn             → one block within StructureCreate/Update & Template*
  BlockOut            → one block within StructureOut / TemplateOut
  StructureCreate     → POST /api/intervals/structures body
  StructureUpdate     → PUT  /api/intervals/structures/{id} body (band + blocks)
  StructureOut        → structure read view (create/get/put/attach response)
  TemplateCreate      → POST /api/intervals/templates body
  TemplateUpdate      → PUT  /api/intervals/templates/{id} body (same shape)
  TemplateOut         → template read view (list/create/get response)
  TemplateAttachIn    → POST /api/intervals/templates/{id}/attach body
  MatchBlockOut       → one block row inside the match-detail response
  MatchDetailOut      → GET  /api/intervals/sessions/{id}/match response
  LapOut              → single persisted lap (StravaActivityLap read view)
  RecalculateIn       → POST /api/intervals/structures/{id}/recalculate body
  RecalculateOut      → POST .../recalculate 202 response
  MatchResultPayload  → validates result_json before it is persisted

Enum-like fields use ``Literal`` (same pattern as ``schemas/strava.py``) so the
schema module stays import-independent of the parallel model modules; the ORM
enums (``ageband``, ``intervalblocktype``, ``hrzone``, ``matchtrigger``) carry
the same string values.

Privacidad Ley 1581 / minors:
- ``LapOut`` / ``MatchBlockOut`` / ``MatchResultPayload`` expose ONLY numeric
  duration + HR + speed summaries. No GPS, polyline, map, lap name, cadence, or
  power fields exist here — mirrors ``strava_activity_laps`` which has no such
  columns. ``MatchResultPayload`` sets ``extra="forbid"`` so a stray geo/power
  key in a computed payload fails validation before it can be persisted.
- Cadencia objetivo siempre ``>= 60`` rpm (``target_cadence_rpm``), toda banda,
  sin excepción (FR-004).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enum-like literals (values match the ORM enums / migration b5c6d7e8f9a0)
# ---------------------------------------------------------------------------

AgeBandLiteral = Literal["10-12", "13-15"]
BlockTypeLiteral = Literal["warmup", "work", "recovery", "cooldown"]
HrZoneLiteral = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]
MatchTriggerLiteral = Literal["link", "structure_change", "manual"]
# Match-detail envelope status — UI-designed states, never raw errors (api.md).
MatchStatusLiteral = Literal["computed", "no_activity", "computing", "failed"]
# Per-block compliance badge semantics (Constitution III / data-model.md).
BlockMatchStatusLiteral = Literal["cumplido", "fuera_tolerancia", "sin_dato", "extra"]

MIN_CADENCE_RPM = 60


# ---------------------------------------------------------------------------
# Blocks — shared authoring shape (structures + templates)
# ---------------------------------------------------------------------------


class BlockIn(BaseModel):
    """Un bloque autor-declarado dentro de una estructura o plantilla.

    ``repeat_group``/``repeat_count`` modelan repeticiones: los bloques que
    comparten un ``repeat_group`` forman un grupo, ``repeat_count`` (>= 2)
    idéntico en todo el grupo. ``NULL`` ⇢ el bloque corre una sola vez.
    Validación cruzada (grupos, banda/edad, gate) vive en el service layer.
    """

    position: int = Field(ge=1)
    block_type: BlockTypeLiteral
    duration_s: int = Field(gt=0)
    target_zone: HrZoneLiteral
    target_cadence_rpm: int = Field(
        ge=MIN_CADENCE_RPM,
        description="Cadencia objetivo en rpm; mínimo 60 para toda categoría (FR-004).",
    )
    repeat_group: int | None = Field(default=None, ge=1)
    repeat_count: int | None = Field(default=None, ge=2)


class BlockOut(BlockIn):
    """Bloque en respuestas de lectura (StructureOut / TemplateOut)."""

    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------------------
# Structures (US1)
# ---------------------------------------------------------------------------


class StructureCreate(BaseModel):
    """Body para POST /api/intervals/structures."""

    training_session_id: int
    target_age_band: AgeBandLiteral
    age_gate_confirmed: bool = Field(
        default=False,
        description="Confirmación explícita para estructuras 10-12 (FR-007).",
    )
    blocks: list[BlockIn] = Field(min_length=1)


class StructureUpdate(BaseModel):
    """Body para PUT /api/intervals/structures/{id} — reemplazo total de banda + bloques."""

    target_age_band: AgeBandLiteral
    age_gate_confirmed: bool = False
    blocks: list[BlockIn] = Field(min_length=1)


class StructureOut(BaseModel):
    """Vista de lectura de una estructura (create/get/put/attach).

    ``total_planned_duration_s`` es computado en el service layer (suma de los
    bloques ya aplanados por repetición) y ecoado aquí para el frontend.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    training_session_id: int
    target_age_band: AgeBandLiteral
    age_gate_confirmed: bool
    age_gate_confirmed_by: str | None = None
    age_gate_confirmed_at: datetime | None = None
    blocks: list[BlockOut]
    total_planned_duration_s: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Templates (US4)
# ---------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    """Body para POST /api/intervals/templates."""

    name: str = Field(min_length=1, max_length=120)
    target_age_band: AgeBandLiteral
    mesocycle_phase: str = Field(min_length=1, max_length=50)
    competition_proximity: str = Field(min_length=1, max_length=50)
    blocks: list[BlockIn] = Field(min_length=1)


class TemplateUpdate(TemplateCreate):
    """Body para PUT /api/intervals/templates/{id} — mismo shape que create."""


class TemplateOut(BaseModel):
    """Vista de lectura de una plantilla (list/create/get)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_age_band: AgeBandLiteral
    mesocycle_phase: str
    competition_proximity: str
    is_archived: bool
    blocks: list[BlockOut]
    total_planned_duration_s: int
    created_at: datetime
    updated_at: datetime


class TemplateListOut(BaseModel):
    """Envelope para GET /api/intervals/templates."""

    items: list[TemplateOut]
    total: int


class TemplateAttachIn(BaseModel):
    """Body para POST /api/intervals/templates/{id}/attach.

    Clona los bloques de la plantilla en una estructura nueva para la sesión
    (copy-on-attach). ``age_gate_confirmed`` reevalúa el gate de edad al adjuntar.
    """

    training_session_id: int
    age_gate_confirmed: bool = False


# ---------------------------------------------------------------------------
# Matching (US2) — detail view
# ---------------------------------------------------------------------------


class MatchActivityOut(BaseModel):
    """Actividad Strava embebida en la respuesta de match (numérica, sin geo)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    start_date_local: datetime
    elapsed_time_s: int
    sport_type: str


class MatchBlockOut(BaseModel):
    """Fila plan-vs-real por bloque aplanado (MatchDetailOut.blocks).

    Solo métricas numéricas de la vuelta (duración, FC, velocidad). Nunca GPS,
    polyline, cadencia ni potencia (Ley 1581 / D4).
    """

    flat_index: int
    block_type: BlockTypeLiteral
    repeat_iteration: int | None = None
    planned_duration_s: int
    target_zone: HrZoneLiteral
    target_cadence_rpm: int
    lap_index: int | None = None
    lap_elapsed_time_s: int | None = None
    lap_moving_time_s: int | None = None
    lap_average_heartrate: float | None = None
    lap_average_speed_m_s: float | None = None
    status: BlockMatchStatusLiteral


class ExtraLapOut(BaseModel):
    """Vuelta del dispositivo sin bloque planificado — informativa, no error."""

    lap_index: int
    elapsed_time_s: int
    average_heartrate: float | None = None


class MatchSummary(BaseModel):
    """Conteos agregados por estado de cumplimiento."""

    cumplido: int = 0
    fuera_tolerancia: int = 0
    sin_dato: int = 0
    extra: int = 0


class MatchDetailOut(BaseModel):
    """Respuesta de GET /api/intervals/sessions/{id}/match (FR-017).

    ``status`` cubre los estados diseñados de UI: ``computed`` trae el detalle
    completo; ``no_activity`` / ``computing`` / ``failed`` traen el envelope con
    los campos de detalle vacíos/ausentes (nunca un error crudo).
    """

    structure_id: int
    status: MatchStatusLiteral
    activity: MatchActivityOut | None = None
    computed_at: datetime | None = None
    engine_version: int | None = None
    tolerance_pct: int | None = None
    blocks: list[MatchBlockOut] = Field(default_factory=list)
    extra_laps: list[ExtraLapOut] = Field(default_factory=list)
    summary: MatchSummary | None = None
    retry_available: bool | None = Field(
        default=None, description="Presente en status='failed' (reintento manual disponible)."
    )


# ---------------------------------------------------------------------------
# Recalculate (US2)
# ---------------------------------------------------------------------------


class RecalculateIn(BaseModel):
    """Body para POST /api/intervals/structures/{id}/recalculate.

    ``activity_id`` es opcional cuando la sesión tiene exactamente una
    actividad vinculada.
    """

    activity_id: int | None = None


class RecalculateOut(BaseModel):
    """Respuesta 202 de recalculate — job diferido despachado."""

    status: Literal["computing"] = "computing"


# ---------------------------------------------------------------------------
# Laps (read view — only ever serialized inside match responses)
# ---------------------------------------------------------------------------


class LapOut(BaseModel):
    """Vuelta persistida de una actividad (StravaActivityLap).

    Campos permitidos exclusivamente numéricos (D4). Sin geo/nombre/cadencia/
    potencia — esos campos no existen en el modelo.
    """

    model_config = ConfigDict(from_attributes=True)

    lap_index: int
    elapsed_time_s: int
    moving_time_s: int | None = None
    average_heartrate: float | None = None
    average_speed_m_s: float | None = None
    fetched_at: datetime


# ---------------------------------------------------------------------------
# result_json validation (persisted on interval_match_results.result_json)
# ---------------------------------------------------------------------------


class MatchResultBlock(BaseModel):
    """Bloque dentro del result_json persistido.

    ``extra="forbid"`` impide que una clave inesperada (geo/potencia/cadencia)
    entre al JSON persistido.
    """

    model_config = ConfigDict(extra="forbid")

    flat_index: int
    block_id: int | None = None
    block_type: BlockTypeLiteral
    repeat_iteration: int | None = None
    planned_duration_s: int
    target_zone: HrZoneLiteral
    target_cadence_rpm: int
    lap_index: int | None = None
    lap_elapsed_time_s: int | None = None
    lap_average_heartrate: float | None = None
    status: BlockMatchStatusLiteral


class MatchResultExtraLap(BaseModel):
    """Vuelta extra dentro del result_json persistido."""

    model_config = ConfigDict(extra="forbid")

    lap_index: int
    elapsed_time_s: int
    average_heartrate: float | None = None


class MatchResultPayload(BaseModel):
    """Valida el result_json completo antes de persistirlo (data-model.md §6).

    ``extra="forbid"`` en todo el árbol garantiza que solo los campos numéricos
    allow-listed por el match runner lleguen a la base (invariante de privacidad
    D4): cualquier fuga de GPS/mapa/cadencia/potencia falla la validación.
    """

    model_config = ConfigDict(extra="forbid")

    blocks: list[MatchResultBlock]
    extra_laps: list[MatchResultExtraLap] = Field(default_factory=list)
    summary: MatchSummary
    tolerance_pct: int = Field(gt=0, le=100)
    laps_discarded_under_10s: int = Field(default=0, ge=0)
