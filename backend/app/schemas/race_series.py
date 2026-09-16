"""Pydantic v2 schemas para CRUD de ``race_series``.

Cubre los DTOs de los endpoints:

- ``GET   /api/race-analysis/race-series``       → lista de series con event_count.
- ``POST  /api/race-analysis/race-series``       → crea serie nueva.
- ``PATCH /api/race-analysis/race-series/{id}``  → edita name / short_name.

Convenciones:
- Pydantic v2 (``ConfigDict``).
- ``extra="forbid"`` en schemas de escritura para evitar inyección de campos.
- ``points_scheme_code`` NO se expone en el body de escritura — el servidor
  impone el default ``copa_valle_2026`` (decisión D5 del spec 014).
- Ningún campo expone datos PII de menores.

Hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``): agrega ``short_name`` a
``RaceSeriesRead`` y el endpoint ``PATCH`` para poder editarlo — usado por
los labels de válida/insight para nunca mostrar el literal "Copa" genérico
cuando hay más de una copa activa en la temporada.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel


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
    level: RaceSeriesLevel = Field(
        default=RaceSeriesLevel.departmental,
        description=(
            "Ámbito territorial: 'departmental' (ej. Valle del Cauca) o 'national' "
            "(ej. Campeonato Nacional Fedeciclismo). Opcional, por defecto 'departmental'. "
            "Solo relevante cuando kind='championship'."
        ),
    )


# ---------------------------------------------------------------------------
# PATCH — Editar serie
# ---------------------------------------------------------------------------


class RaceSeriesUpdate(BaseModel):
    """Body del ``PATCH /api/race-analysis/race-series/{series_id}``.

    Actualización parcial: solo ``name`` y ``short_name`` son editables (no
    ``season_year``, ``kind``, ``organizer`` ni ``level`` — cambiar esos
    equivale a otra serie). Solo los campos enviados se aplican
    (``exclude_unset=True``).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        description="Nuevo nombre descriptivo de la serie.",
    )
    short_name: str | None = Field(
        default=None,
        max_length=40,
        description=(
            "Nombre corto para labels (ej. 'Let's Go'). Enviar cadena vacía "
            "o ``null`` limpia el campo (vuelve a usar el nombre completo)."
        ),
    )

    @field_validator("short_name", mode="before")
    @classmethod
    def _empty_short_name_to_none(cls, v: str | None) -> str | None:
        """Cadena vacía (tras strip) se normaliza a ``None`` — 'limpiar campo'."""
        if v is None:
            return None
        if isinstance(v, str):
            trimmed = v.strip()
            return trimmed or None
        return v


# ---------------------------------------------------------------------------
# GET single / response de POST y PATCH
# ---------------------------------------------------------------------------


class RaceSeriesRead(BaseModel):
    """Representación de una ``RaceSeries`` para respuestas de lista y creación."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    season_year: int
    organizer: str | None = None
    kind: RaceSeriesKind
    level: RaceSeriesLevel = Field(
        description="Ámbito territorial de la serie: 'departmental' o 'national'.",
    )
    short_name: str | None = Field(
        default=None,
        description=(
            "Nombre corto para labels ('Let's Go' en vez de 'Copa Let's Go "
            "Interdepartamental XCO'). ``None`` = usa ``name`` completo."
        ),
    )
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
