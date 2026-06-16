"""Pydantic v2 schemas para CRUD de ``race_series``.

Cubre los DTOs de los endpoints:

- ``GET  /api/race-analysis/race-series``  → lista de series con event_count.
- ``POST /api/race-analysis/race-series``  → crea serie nueva.

Convenciones:
- Pydantic v2 (``ConfigDict``).
- ``extra="forbid"`` en schemas de escritura para evitar inyección de campos.
- ``points_scheme_code`` NO se expone en el body de escritura — el servidor
  impone el default ``copa_valle_2026`` (decisión D5 del spec 014).
- Ningún campo expone datos PII de menores.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.race_series import RaceSeriesKind


# ---------------------------------------------------------------------------
# POST — Crear serie
# ---------------------------------------------------------------------------


class RaceSeriesCreate(BaseModel):
    """Body del ``POST /api/race-analysis/race-series``.

    El cliente no envía ``points_scheme_code`` — el servidor lo fija en
    ``copa_valle_2026`` (decisión D5: championships reúsan el scheme por defecto;
    la exclusión del ranking es responsabilidad del filtro ``kind='cup'``).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(
        min_length=1,
        max_length=150,
        description="Nombre descriptivo de la serie (ej. 'Copa Valle de Ciclomontañismo').",
    )
    season_year: int = Field(
        ge=2020,
        le=2100,
        description="Año de la temporada.",
    )
    kind: RaceSeriesKind = Field(
        description="Tipo de serie: 'cup' (copa con rondas) o 'championship' (campeonato único anual).",
    )
    organizer: str | None = Field(
        default=None,
        max_length=150,
        description="Organizador oficial (ej. 'Liga Vallecaucana de Ciclismo'). Opcional.",
    )


# ---------------------------------------------------------------------------
# GET single / response de POST
# ---------------------------------------------------------------------------


class RaceSeriesRead(BaseModel):
    """Representación de una ``RaceSeries`` para respuestas de lista y creación."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    season_year: int
    organizer: str | None = None
    kind: RaceSeriesKind
    event_count: int = Field(
        default=0,
        description="Número de eventos (válidas o campeonatos) en la serie.",
    )


# ---------------------------------------------------------------------------
# GET list — respuesta paginada
# ---------------------------------------------------------------------------


class RaceSeriesListResponse(BaseModel):
    """Respuesta del ``GET /api/race-analysis/race-series``."""

    model_config = ConfigDict(from_attributes=True)

    items: list[RaceSeriesRead]
    total: int
