"""Pydantic v2 schemas para ``/api/race-identity/*`` (feature 044, US4).

Contrato: ``specs/044-race-history-backfill/contracts/identity-review-api.md``.
Servicio: ``app/services/race/identity_review.py`` (``record_view`` /
``candidate_view`` construyen exactamente estas formas desde los snapshots
persistidos — nunca se arma una respuesta desde JSON crudo).

Privacidad: fuera de la familia del asistente de importación (que devuelve al
coach las filas del mismo PDF que subió), ``IdentityRecordRead`` es el único
schema que serializa ``city`` (ver ``tests/privacy/test_city_not_serialised.py``).
``extra="forbid"`` en cada schema: un campo interno del snapshot (terna
normalizada, ids de resultados adjuntados) que se cuele por error revienta
la respuesta en vez de filtrarse en silencio.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.race_identity_candidate import IdentityCandidateState


# ---------------------------------------------------------------------------
# Respuesta closed enum del body de /decide — subconjunto de
# IdentityCandidateState que excluye `pending` (no es una respuesta válida).
# ---------------------------------------------------------------------------


class IdentityDecisionAnswer(str, enum.Enum):
    same_person = IdentityCandidateState.same_person.value
    different_people = IdentityCandidateState.different_people.value


# ---------------------------------------------------------------------------
# GET /api/race-identity/candidates — registro y candidato
# ---------------------------------------------------------------------------


class IdentityRecordRead(BaseModel):
    """Un lado de un candidato (``record_view``). El único schema con ``city``."""

    model_config = ConfigDict(extra="forbid")

    name_printed: str
    club: str
    city: str
    seasons: list[int]
    category_labels: list[str]
    competitor_id: Optional[int] = None
    athlete_linked: bool


class IdentityCandidateRead(BaseModel):
    """Un candidato de la cola (``candidate_view``)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    kind: str
    score: int
    signals: list[str]
    left: IdentityRecordRead
    right: IdentityRecordRead
    state: str
    linked_athlete_involved: bool
    decided_at: Optional[datetime] = None
    reversed_at: Optional[datetime] = None


class IdentityCandidatePageRead(BaseModel):
    """``CandidatePage`` — cola paginada, ``score DESC``."""

    model_config = ConfigDict(extra="forbid")

    items: list[IdentityCandidateRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# GET /api/race-identity/summary
# ---------------------------------------------------------------------------


class IdentitySummaryRead(BaseModel):
    """Alimenta el banner del candado de commit."""

    model_config = ConfigDict(extra="forbid")

    pending: int
    same_person: int
    different_people: int


# ---------------------------------------------------------------------------
# POST /api/race-identity/candidates/{id}/decide
# ---------------------------------------------------------------------------


class IdentityDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: IdentityDecisionAnswer


class IdentityDecisionOut(BaseModel):
    """``DecisionOutcome``. ``merged`` es True si la decisión unió en el acto
    dos competidores ya confirmados."""

    model_config = ConfigDict(extra="forbid")

    id: int
    state: str
    merged: bool
    results_moved: int


# ---------------------------------------------------------------------------
# POST /api/race-identity/candidates/{id}/reverse
# ---------------------------------------------------------------------------


class IdentityReversalOut(BaseModel):
    """``ReversalOutcome``. ``split`` es True si se separó un competidor
    confirmado; ``links_cleared`` cuenta resultados que perdieron su
    ``athlete_id`` al moverse al competidor separado."""

    model_config = ConfigDict(extra="forbid")

    id: int
    state: str
    split: bool
    results_moved: int
    links_cleared: int


# ---------------------------------------------------------------------------
# POST /api/race-identity/rebuild
# ---------------------------------------------------------------------------


class RebuildResultRead(BaseModel):
    """``RebuildResult``. ``imports_unreadable`` son ids de imports en
    staging cuyo archivo no se pudo re-leer — sus filas NO entraron al
    universo de este rebuild."""

    model_config = ConfigDict(extra="forbid")

    created: int
    unchanged: int
    pending: int
    imports_unreadable: list[int]
