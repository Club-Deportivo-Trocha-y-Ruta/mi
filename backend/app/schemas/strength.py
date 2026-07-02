"""Pydantic v2 schemas for the Strength Training Exercise Library (feature 021).

Schema ↔ contract mapping (contracts/strength-api.md):
  ExerciseOut        → GET /api/strength/exercises list row (card view)
  ExerciseDetailOut   → GET /api/strength/exercises/{id} full record
  BlockEntryIn        → one entry within BlockCreate/BlockUpdate.entries
  EntryOut            → one entry within BlockOut.entries (embeds ExerciseOut)
  BlockCreate         → POST /api/strength/blocks body
  BlockUpdate         → PUT  /api/strength/blocks/{id} body (same shape as create)
  BlockOut            → POST/GET /api/strength/blocks(/{id}) response
  AttachIn            → POST /api/strength/blocks/{id}/attach body
  AttachOut           → POST /api/strength/blocks/{id}/attach 201 response
  ProgressIn          → POST /api/strength/athletes/{id}/progress body
  ProgressOut         → GET  /api/strength/athletes/{id}/progress item

Enums are imported from app.models.strength (single source of truth), plus
AgeBand reused from app.models.technique_exercise (data-model.md).
All response schemas that read ORM objects set model_config from_attributes=True.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.strength import (
    EquipmentKind,
    MovementCategory,
    StrengthProgressStatus,
)
from app.models.technique_exercise import AgeBand


# ---------------------------------------------------------------------------
# Catalog — list and detail
# ---------------------------------------------------------------------------


class ExerciseOut(BaseModel):
    """Fila del catálogo de ejercicios de fuerza (card view — GET /exercises)."""

    id: int
    slug: str
    name: str
    summary: str
    equipment: EquipmentKind
    equipment_detail: str | None
    movement_category: MovementCategory
    age_bands: list[AgeBand]
    suggested_duration_min: int
    suggested_reps: str
    is_seeded: bool
    is_hidden: bool

    model_config = {"from_attributes": True}


class ExerciseDetailOut(ExerciseOut):
    """Detalle completo de un ejercicio de fuerza (GET /exercises/{id}).

    Extiende ExerciseOut con la guía de ejecución, errores comunes e
    ilustración ASCII con su texto alternativo (WCAG AA — Constitution III).
    """

    how_to: str
    common_errors: str
    illustration_ascii: str
    illustration_alt: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Blocks — create / update / read
# ---------------------------------------------------------------------------


class BlockEntryIn(BaseModel):
    """Una entrada dentro del payload de creación/actualización de un bloque."""

    exercise_id: int
    position: int = Field(ge=0)
    duration_min: int = Field(gt=0)
    reps: str | None = Field(default=None, max_length=60)
    is_age_override: bool = False
    override_note: str | None = Field(default=None, max_length=300)


class EntryOut(BaseModel):
    """Entrada de un bloque en la respuesta de lectura (BlockOut.entries)."""

    id: int
    position: int
    duration_min: int
    reps: str | None
    is_age_override: bool
    override_note: str | None
    exercise: ExerciseOut

    model_config = {"from_attributes": True}


class BlockCreate(BaseModel):
    """Body para POST /api/strength/blocks."""

    name: str = Field(max_length=120)
    target_age_band: AgeBand
    duration_target_min: int = Field(default=30, gt=0)
    entries: list[BlockEntryIn] = Field(min_length=1)


class BlockUpdate(BlockCreate):
    """Body para PUT /api/strength/blocks/{id}.

    Mismo shape que BlockCreate — reemplazo completo de entries (contrato).
    """


class BlockOut(BaseModel):
    """Respuesta de creación/lectura de un bloque de fuerza.

    total_duration_min es computado en el service layer (Σ duration_min de
    entries) y ecoado aquí para que el frontend no tenga que recalcularlo.
    """

    id: int
    name: str
    target_age_band: AgeBand
    duration_target_min: int
    total_duration_min: int
    is_archived: bool
    entries: list[EntryOut]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Session attachment
# ---------------------------------------------------------------------------


class AttachIn(BaseModel):
    """Body para POST /api/strength/blocks/{id}/attach."""

    training_session_id: int


class AttachOut(BaseModel):
    """Respuesta 201 de POST /api/strength/blocks/{id}/attach."""

    id: int
    training_session_id: int
    block_id: int
    position: int
    attached_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Progress notes (append-only, coach/admin only — minors data)
# ---------------------------------------------------------------------------


class ProgressIn(BaseModel):
    """Body para POST /api/strength/athletes/{athlete_id}/progress."""

    exercise_id: int
    status: StrengthProgressStatus
    coach_note: str | None = Field(default=None, max_length=500)
    season: int = Field(ge=2020, le=2100)


class ProgressOut(BaseModel):
    """Fila de progreso (último por ejercicio) — GET /athletes/{id}/progress."""

    exercise_id: int
    exercise_name: str
    status: StrengthProgressStatus
    coach_note: str | None
    season: int
    recorded_at: datetime

    model_config = {"from_attributes": True}
