"""Pydantic v2 schemas para el módulo de enlace retroactivo competidor↔atleta.

Cubre los DTOs del router ``/api/race-competitors/*``:

- ``CompetitorLinkRequest``     — body para ``POST /{id}/link``.
- ``CompetitorLinkResponse``    — respuesta tras un link exitoso.
- ``CompetitorUnlinkResponse``  — respuesta tras un unlink exitoso (también idempotente).
- ``AthleteSuggestion``         — top-N candidatos para resolución HITL.
- ``UnlinkedCompetitorItem``    — fila del listado ``GET /``.
- ``UnlinkedCompetitorsResponse`` — wrapper con ``items`` + ``total``.

Convenciones del proyecto:
- Sin datos sensibles de menores en logs ni en payloads — `display_name` viene
  del PDF público de Federación; el ``normalized_name`` se incluye para que
  el frontend pueda hacer de-duplicación cliente sin re-normalizar.
- ``score`` siempre ∈ [0, 1] en la respuesta API; internamente rapidfuzz usa
  0..100 pero exponemos float normalizado para que el frontend renderice
  porcentajes sin re-escalar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class CompetitorLinkRequest(BaseModel):
    """Body del ``POST /api/race-competitors/{competitor_id}/link``."""

    model_config = ConfigDict(extra="forbid")

    athlete_id: int = Field(gt=0, description="PK del Athlete a enlazar")


# ---------------------------------------------------------------------------
# Sugerencias (matcher fuzzy)
# ---------------------------------------------------------------------------


class AthleteSuggestion(BaseModel):
    """Candidato sugerido por el matcher para un competidor sin linkage.

    - ``score`` ∈ [0, 1]. 1.0 = match exacto post-normalización.
    - ``reason`` es texto humano para que el coach decida (no machine-readable).
      Valores observables: ``"exact name match"``, ``"fuzzy 0.92"``,
      ``"fuzzy 0.87 + same club"``.
    """

    athlete_id: int
    full_name: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=120)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class CompetitorLinkResponse(BaseModel):
    """Respuesta tras un link exitoso (200 o 201)."""

    competitor_id: int
    athlete_id: int
    linked_at: datetime
    linked_by_user_id: int
    results_propagated: int = Field(
        ge=0,
        description="Filas de race_results actualizadas con el nuevo athlete_id",
    )
    already_linked: bool = Field(
        default=False,
        description=(
            "True si el competitor ya estaba enlazado al mismo athlete_id "
            "antes de la llamada (operación idempotente, sin cambios)."
        ),
    )


class CompetitorUnlinkResponse(BaseModel):
    """Respuesta tras un unlink (también devuelta cuando ya estaba unlinked)."""

    competitor_id: int
    results_propagated: int = Field(
        ge=0,
        description="Filas de race_results donde se seteó athlete_id=NULL",
    )
    was_linked: bool = Field(
        description=(
            "True si el competitor estaba enlazado antes de la llamada. "
            "False si ya estaba en NULL (operación idempotente, sin cambios)."
        )
    )


class UnlinkedCompetitorItem(BaseModel):
    """Fila del listado ``GET /api/race-competitors/?unlinked=true``."""

    id: int
    display_name: str
    normalized_name: str
    club_text: Optional[str] = None
    sex: Optional[str] = None
    results_count: int = Field(ge=0, description="Cuántos race_results no-eliminados tiene")
    seasons: list[int] = Field(
        default_factory=list,
        description="Temporadas en las que el competidor tiene results (ordenadas asc)",
    )
    suggestions: list[AthleteSuggestion] = Field(default_factory=list)


class UnlinkedCompetitorsResponse(BaseModel):
    """Wrapper del listado paginado de competidores sin linkage."""

    items: list[UnlinkedCompetitorItem]
    total: int = Field(ge=0)


class CompetitorSuggestionsResponse(BaseModel):
    """Respuesta del ``GET /api/race-competitors/{id}/suggestions``."""

    competitor_id: int
    suggestions: list[AthleteSuggestion]


# ---------------------------------------------------------------------------
# Sugerencias INVERSAS — Option B: por nombre de athlete a crear
# ---------------------------------------------------------------------------


class CompetitorSuggestion(BaseModel):
    """Candidato ``RaceCompetitor`` huérfano sugerido para enlazar a un
    athlete que está siendo creado.

    Devuelto por ``GET /api/race-competitors/suggestions-by-name``. Permite
    al frontend, en el flujo de creación de athlete, ofrecer al coach
    competitors sin enlace cuyo nombre matchea por fuzzy.

    - ``score`` ∈ [0, 1]. 1.0 = match exacto post-normalización.
    - ``reason`` es texto humano: ``"exact name match"``, ``"fuzzy 0.92"``,
      ``"fuzzy 0.87 + same club"``.
    - ``results_count`` y ``seasons`` se incluyen para que el frontend pueda
      mostrar "Tiene N resultados pendientes en 2025-2026" y motivar el link.
    """

    competitor_id: int
    display_name: str
    club_text: Optional[str] = None
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=120)
    results_count: int = Field(ge=0)
    seasons: list[int] = Field(default_factory=list)


class CompetitorSuggestionsByNameResponse(BaseModel):
    """Respuesta del ``GET /api/race-competitors/suggestions-by-name``."""

    suggestions: list[CompetitorSuggestion]
