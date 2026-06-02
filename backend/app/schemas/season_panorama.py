"""Schemas del panorama de temporada (PR3 unificación /competitions).

Contrato del endpoint ``GET /api/race-analysis/insights/season/{year}``.

RBAC: coach/admin only (parents → 403, garantizado por la dependencia
``require_role`` del router).

Privacidad
==========
El response expone ``athlete_id`` + nombre real porque el caller es
coach/admin (autorizado). NO se expone PII de terceros ni datos médicos.
Cualquier narrativa IA derivada del panorama global debe usar
``forbidden_names=[]`` (redacción anónima) — pero este contrato es agregación
numérica, sin texto IA.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SeasonPanoramaAthleteItem(BaseModel):
    """Métricas agregadas de un deportista en una temporada."""

    model_config = ConfigDict(extra="forbid")

    athlete_id: int = Field(..., ge=1, description="PK del deportista.")
    athlete_display_name: str = Field(
        ..., description="Nombre completo del deportista (coach/admin)."
    )
    races_count: int = Field(
        ..., ge=0, description="Número de válidas con resultado vigente en la temporada."
    )
    wins: int = Field(..., ge=0, description="Veces en 1er lugar (position == 1).")
    podiums: int = Field(
        ..., ge=0, description="Veces en podio (position <= 3, incluye victorias)."
    )
    best_position: int | None = Field(
        default=None,
        ge=1,
        description="Mejor posición de la temporada. None si ningún resultado tuvo posición.",
    )
    total_points: int = Field(
        ..., ge=0, description="Puntos acumulados en la temporada."
    )


class SeasonPanoramaResponse(BaseModel):
    """Respuesta del panorama de temporada."""

    model_config = ConfigDict(extra="forbid")

    season: int = Field(..., description="Año de la temporada consultada.")
    total_athletes: int = Field(
        ..., ge=0, description="Número de deportistas con resultados en la temporada."
    )
    items: list[SeasonPanoramaAthleteItem] = Field(
        default_factory=list,
        description="Deportistas ordenados por puntos desc, luego podios desc.",
    )


__all__ = ["SeasonPanoramaAthleteItem", "SeasonPanoramaResponse"]
