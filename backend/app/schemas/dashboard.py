"""Schemas para el resumen del panel de mando del entrenador (coach home)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WeeklyLoadBandOut(BaseModel):
    age_band: Literal["10-12", "13-15"]
    planned_minutes: int
    cap_minutes: int
    athlete_count: int


class CoachSummaryOut(BaseModel):
    """``null`` en un conteo significa "no disponible" (falló ese agregado),
    nunca "cero pendientes" — la UI omite la fila en lugar de mostrar 0.

    Feature 045 (US5) agrega los tres conteos de «Pendientes»; cada uno alimenta
    una fila y la lista que esa fila abre cuenta exactamente los mismos ítems
    (SC-005). ``unlinked_competitors_pending`` (FR-033) solo alimenta la
    insignia de «Cargas e identidades»: cuenta lo mismo que la lista de
    «Sin enlazar» al abrirla.
    """

    generated_at: datetime
    consents_pending: int | None
    insights_stale: int | None
    weekly_load: list[WeeklyLoadBandOut] | None
    identity_decisions_pending: int | None
    imports_in_progress: int | None
    analyses_awaiting_approval: int | None
    unlinked_competitors_pending: int | None
