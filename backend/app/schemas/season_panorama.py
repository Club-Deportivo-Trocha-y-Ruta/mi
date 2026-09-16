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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SeasonPanoramaSeriesItem(BaseModel):
    """Métricas de un deportista acotadas a UNA copa de la temporada.

    Ver hotfix "identidad de válida" (``~/.claude/plans/multicopa-identidad-valida.md``
    bug #8, 2026-09-16). Solo copas (``series_kind == "cup"``) — los
    campeonatos no aparecen aquí, igual que en los totales de nivel superior
    (spec 023 SC-004, sin cambios).
    """

    model_config = ConfigDict(extra="forbid")

    series_id: int = Field(..., ge=1, description="PK de la copa (race_series).")
    series_name: str = Field(..., description="Nombre completo de la copa.")
    series_short_name: str | None = Field(
        default=None,
        description="Nombre corto de la copa (p.ej. \"Let's Go\"); None si no está definido.",
    )
    series_kind: Literal["cup", "championship"] = Field(
        ..., description="Siempre 'cup' en este listado (ver docstring)."
    )
    races: int = Field(..., ge=0, description="Válidas de ESTA copa con resultado vigente.")
    points: int = Field(..., ge=0, description="Puntos acumulados en ESTA copa.")
    podiums: int = Field(..., ge=0, description="Podios (position <= 3) en ESTA copa.")
    wins: int = Field(..., ge=0, description="Victorias (position == 1) en ESTA copa.")
    best_position: int | None = Field(
        default=None,
        ge=1,
        description="Mejor posición en ESTA copa. None si ningún resultado tuvo posición.",
    )


class SeasonPanoramaAthleteItem(BaseModel):
    """Métricas agregadas de un deportista en una temporada.

    ``races_count``/``wins``/``podiums``/``best_position``/``total_points``
    son sumas A TRAVÉS DE TODAS LAS COPAS de la temporada. Se mantienen por
    compatibilidad con consumidores existentes pero están DEPRECADOS desde
    el hotfix "identidad de válida" (2026-09-16): en cuanto exista más de
    una copa activa dejan de representar un total con sentido para
    cualquiera de ellas (p.ej. ya NO son "puntos Copa Valle" si el club
    también corre la Copa Let's Go). El desglose correcto, por copa, está en
    ``by_series`` — úsalo para cualquier lectura nueva.
    """

    model_config = ConfigDict(extra="forbid")

    athlete_id: int = Field(..., ge=1, description="PK del deportista.")
    athlete_display_name: str = Field(
        ..., description="Nombre completo del deportista (coach/admin)."
    )
    races_count: int = Field(
        ...,
        ge=0,
        description=(
            "DEPRECADO (suma cross-cup, ver docstring de la clase). "
            "Número de válidas con resultado vigente en la temporada, TODAS las copas."
        ),
    )
    wins: int = Field(
        ...,
        ge=0,
        description="DEPRECADO (suma cross-cup). Veces en 1er lugar (position == 1).",
    )
    podiums: int = Field(
        ...,
        ge=0,
        description=(
            "DEPRECADO (suma cross-cup). Veces en podio (position <= 3, incluye victorias)."
        ),
    )
    best_position: int | None = Field(
        default=None,
        ge=1,
        description=(
            "DEPRECADO (mínimo cross-cup, ya no identifica una copa concreta). "
            "Mejor posición de la temporada. None si ningún resultado tuvo posición."
        ),
    )
    total_points: int = Field(
        ...,
        ge=0,
        description="DEPRECADO (suma cross-cup). Puntos acumulados en la temporada.",
    )
    by_series: list[SeasonPanoramaSeriesItem] = Field(
        default_factory=list,
        description=(
            "Desglose por copa, ordenado por la fecha de la primera válida "
            "corrida de cada copa. Fuente de verdad para puntos/podios/wins "
            "por copa — usar esto, no los campos deprecados de arriba."
        ),
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


__all__ = [
    "SeasonPanoramaAthleteItem",
    "SeasonPanoramaResponse",
    "SeasonPanoramaSeriesItem",
]
