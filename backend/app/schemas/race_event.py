"""Pydantic v2 schemas para CRUD de ``race_events``.

Cubre los DTOs de los endpoints:

- ``POST   /api/race-analysis/race-events``          → crea evento vacío.
- ``GET    /api/race-analysis/race-events``           → listado con filtros.
- ``PATCH  /api/race-analysis/race-events/{id}``     → edita metadata.
- ``DELETE /api/race-analysis/race-events/{id}``     → borrado si sin dependencias.

El endpoint ``PATCH /{id}/conditions`` (condiciones de carrera) usa los schemas
de ``race_imports`` y no se toca aquí.

Convenciones:
- Pydantic v2 (``ConfigDict``).
- ``extra="forbid"`` en schemas de escritura para evitar inyección de campos.
- Ningún campo expone datos PII de menores — los race_events son públicos
  (carrera de federación).
- ``conditions_completeness`` indica qué tan completos están los campos de
  clima del evento: "complete" (todos 5), "partial" (alguno), "empty" (ninguno).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.race_event import RaceEventStatus, SurfaceCondition


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _ConditionsFields(BaseModel):
    """Mixin con los cinco campos de condiciones de carrera (reutilizado en Create)."""

    climate: Optional[str] = Field(
        default=None,
        max_length=60,
        description="Descripción libre del clima (ej: 'Soleado con viento moderado').",
    )
    temperature_c: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=50,
        decimal_places=1,
        description="Temperatura en grados Celsius (0-50). Un decimal.",
    )
    surface_condition: Optional[SurfaceCondition] = Field(
        default=None,
        description="Condición del trazado: seca | humeda | barro | lluvia | mixta.",
    )
    altitude_msnm: Optional[int] = Field(
        default=None,
        ge=0,
        le=5000,
        description="Altitud en metros sobre el nivel del mar (0-5000).",
    )
    weather_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Notas adicionales de condiciones climatológicas.",
    )


# ---------------------------------------------------------------------------
# POST — Crear race_event
# ---------------------------------------------------------------------------


class RaceEventCreate(_ConditionsFields):
    """Body del ``POST /api/race-analysis/race-events``.

    Crea un evento vacío (sin resultados) asociado a una serie existente.
    Los campos de condiciones son opcionales y pueden completarse después
    vía ``PATCH /{id}/conditions``.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    series_id: int = Field(gt=0, description="ID de la serie a la que pertenece el evento.")
    sequence_number: int = Field(
        ge=1,
        le=99,
        description="Número de válida en la serie (1-7 regulares, 99 = Campeonato Departamental).",
    )
    name: str = Field(min_length=1, max_length=200, description="Nombre descriptivo del evento.")
    event_date: date = Field(description="Fecha de la carrera (YYYY-MM-DD).")
    location: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Municipio o lugar de la carrera.",
    )
    is_championship: bool = Field(
        default=False,
        description="True si es Campeonato Departamental (sequence_number=99 por convención).",
    )
    status: Optional[RaceEventStatus] = Field(
        default=RaceEventStatus.SCHEDULED,
        description="Estado inicial del evento. Por defecto: scheduled.",
    )

    @field_validator("sequence_number")
    @classmethod
    def _validate_championship_sequence(cls, v: int, info) -> int:
        """Advierte coherencia entre is_championship y sequence_number=99.

        No bloquea (puede haber campeonatos con numeración distinta en futuros
        formatos de federación); solo normaliza el valor recibido.
        """
        return v


# ---------------------------------------------------------------------------
# PATCH — Editar metadata del race_event
# ---------------------------------------------------------------------------


class RaceEventUpdate(BaseModel):
    """Body del ``PATCH /api/race-analysis/race-events/{id}``.

    Actualización parcial de metadata. No toca condiciones de carrera
    (eso es ``PATCH /{id}/conditions``). Todos los campos son opcionales;
    solo los enviados se aplican (``exclude_unset=True``).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    event_date: Optional[date] = None
    location: Optional[str] = Field(default=None, max_length=150)
    sequence_number: Optional[int] = Field(default=None, ge=1, le=99)
    status: Optional[RaceEventStatus] = None
    is_championship: Optional[bool] = None


# ---------------------------------------------------------------------------
# GET single / response de POST y PATCH
# ---------------------------------------------------------------------------


class RaceEventRead(BaseModel):
    """Representación completa de un ``RaceEvent`` (respuesta de POST y PATCH)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    sequence_number: int
    name: str
    event_date: date
    location: Optional[str] = None
    is_championship: bool
    status: RaceEventStatus
    # Condiciones de carrera (pueden ser None si aún no se capturaron)
    climate: Optional[str] = None
    temperature_c: Optional[Decimal] = None
    surface_condition: Optional[SurfaceCondition] = None
    altitude_msnm: Optional[int] = None
    weather_notes: Optional[str] = None
    # Trazabilidad
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    # Flag derivado (calculado en el endpoint, no es columna de race_events)
    has_calendar_event: bool = False


# ---------------------------------------------------------------------------
# GET list — item compacto con flags derivados
# ---------------------------------------------------------------------------

ConditionsCompleteness = Literal["complete", "partial", "empty"]


class RaceEventListItem(BaseModel):
    """Item compacto para el listado ``GET /api/race-analysis/race-events``.

    Los flags ``has_results`` y ``has_calendar_event`` se calculan en el
    servicio mediante subqueries/EXISTS para evitar cargar relaciones completas.

    ``conditions_completeness``:
    - ``"complete"``  → los 5 campos de condiciones están presentes.
    - ``"partial"``   → al menos uno presente.
    - ``"empty"``     → ningún campo de condiciones está capturado.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    sequence_number: int
    name: str
    event_date: date
    location: Optional[str] = None
    is_championship: bool
    status: RaceEventStatus
    # Flags derivados (calculados en el servicio)
    has_results: bool = False
    has_calendar_event: bool = False
    conditions_completeness: ConditionsCompleteness = "empty"


class RaceEventListResponse(BaseModel):
    """Respuesta del ``GET /api/race-analysis/race-events``."""

    model_config = ConfigDict(from_attributes=True)

    items: list[RaceEventListItem]
    total: int
