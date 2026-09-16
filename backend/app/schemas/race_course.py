"""Pydantic v2 schemas para el perfil de circuito de una válida (feature 043).

Cubre los DTOs de los endpoints bajo
``/api/race-analysis/race-events/{race_event_id}/course/*``:

- ``GET    /course``                       → ``CourseRead`` (variantes, setups,
  descripción, sugerencia de prefill, categorías del padre).
- ``POST   /course/variants``              → crea variante (multipart, no aquí).
- ``PUT    /course/variants/{id}/file``    → reemplaza geometría (multipart, no aquí).
- ``PATCH  /course/variants/{id}``         → ``VariantRename``.
- ``PUT    /course/setups``                → ``SetupsReplace``.
- ``PATCH  /course/description``           → ``CourseDescriptionUpdate``.

Convenciones:
- Pydantic v2 (``ConfigDict``).
- ``extra="forbid"`` en schemas de escritura para evitar inyección de campos.
- ``key_sectors`` es una lista JSON en `race_events` — no hay enum en la base
  de datos, ``KeySector`` es solo de validación de schema.
- Ningún campo expone datos PII de menores — el circuito es información
  pública de la carrera; ``my_categories`` solo referencia ``athlete_id`` de
  los propios hijos del padre que consulta (filtrado en el servicio).
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.race_event import TerrainType


class KeySector(str, enum.Enum):
    """Elemento técnico destacado del trazado (schema-only, sin enum en DB)."""

    subida_larga = "subida_larga"
    bajada_tecnica = "bajada_tecnica"
    rock_garden = "rock_garden"
    singletrack = "singletrack"
    plano_rapido = "plano_rapido"
    paso_quebrada = "paso_quebrada"
    raices = "raices"
    escalones = "escalones"


# ---------------------------------------------------------------------------
# Variantes de recorrido
# ---------------------------------------------------------------------------


class LapDetectionRead(BaseModel):
    """Cómo se determinó la vuelta a partir del GPX subido."""

    method: Literal["closed_loop", "manual", "single"]
    laps_detected: int
    total_distance_m: int


class VariantRead(BaseModel):
    """Representación de una ``RaceCourseVariant`` (incluye geometría)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    lap_distance_km: float
    lap_distance_m: int
    elevation_gain_m: Optional[int] = None
    has_elevation: bool
    point_count: int
    geometry: list[tuple[float, float, Optional[float]]]
    detection: LapDetectionRead
    created_at: datetime
    updated_at: Optional[datetime] = None


class VariantRename(BaseModel):
    """Body de ``PATCH /course/variants/{id}``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=60)


# ---------------------------------------------------------------------------
# Setups (vueltas por categoría)
# ---------------------------------------------------------------------------


class SetupIn(BaseModel):
    """Un elemento del body de ``PUT /course/setups``."""

    model_config = ConfigDict(extra="forbid")

    category_id: int = Field(gt=0)
    laps: int = Field(ge=1, le=20)
    variant_id: int = Field(gt=0)


class SetupRead(BaseModel):
    """Un setup ya resuelto, con datos de la categoría para mostrar sin joins extra."""

    category_id: int
    category_code: str
    category_label: str
    laps: int
    variant_id: int


class SuggestedSetupRead(BaseModel):
    """Sugerencia de prefill tomada de la válida anterior de la serie (R-14)."""

    category_id: int
    category_label: str
    laps: int
    variant_label: str
    source_event_id: int


class SetupsReplace(BaseModel):
    """Body de ``PUT /course/setups`` — reemplazo total de la tabla de vueltas."""

    model_config = ConfigDict(extra="forbid")

    setups: list[SetupIn]


# ---------------------------------------------------------------------------
# Descripción estructurada del circuito
# ---------------------------------------------------------------------------


class CourseDescriptionRead(BaseModel):
    """Los cuatro campos de descripción del circuito, tal como están en `race_events`."""

    terrain_type: Optional[TerrainType] = None
    technical_difficulty: Optional[int] = None
    key_sectors: list[KeySector] = []
    course_notes: Optional[str] = None

    @field_validator("key_sectors", mode="before")
    @classmethod
    def _key_sectors_none_to_empty(cls, v: Optional[list[KeySector]]) -> list[KeySector]:
        """``race_events.key_sectors`` es JSON nullable: una válida sin sectores
        capturados llega como ``None`` (p. ej. si el servicio construye este
        schema directo desde ``event.key_sectors``); se normaliza a lista vacía."""
        return v if v is not None else []


class CourseDescriptionUpdate(BaseModel):
    """Body de ``PATCH /course/description`` — actualización parcial (``exclude_unset``).

    Un campo ausente del body no se toca; un ``null`` explícito lo limpia.
    La semántica ``exclude_unset`` la aplica el llamador (servicio), no este schema.
    """

    model_config = ConfigDict(extra="forbid")

    terrain_type: Optional[TerrainType] = None
    technical_difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    key_sectors: Optional[list[KeySector]] = None
    course_notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("key_sectors")
    @classmethod
    def _validate_key_sectors(cls, value: Optional[list[KeySector]]) -> Optional[list[KeySector]]:
        if value is None:
            return value
        if len(value) > 8:
            raise ValueError("Máximo 8 elementos técnicos por circuito.")
        if len(set(value)) != len(value):
            raise ValueError("No se permiten elementos técnicos duplicados.")
        return value


# ---------------------------------------------------------------------------
# Respuesta compuesta — GET /course y toda mutación
# ---------------------------------------------------------------------------


class MyCategoryRead(BaseModel):
    """Una categoría en la que corre un hijo del padre que consulta."""

    athlete_id: int
    category_id: int


class CourseRead(BaseModel):
    """Respuesta de ``GET /course`` y de toda mutación de este dominio."""

    model_config = ConfigDict(from_attributes=True)

    race_event_id: int
    has_course_data: bool
    variants: list[VariantRead] = []
    setups: list[SetupRead] = []
    suggested_setups: list[SuggestedSetupRead] = []
    description: CourseDescriptionRead
    my_categories: list[MyCategoryRead] = []
