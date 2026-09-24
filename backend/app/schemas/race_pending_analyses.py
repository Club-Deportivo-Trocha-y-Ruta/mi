"""Schemas de los análisis IA pendientes del coach (feature 045, US5).

Contrato: ``specs/045-competitions-one-place/contracts/api.md``
(``GET /api/race-analysis/pending-analyses`` y
``POST /api/race-analysis/runs/{run_id}/dismiss-stale``).
"""
from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PendingAnalysisState(str, enum.Enum):
    """Estado de un análisis que espera acción del coach.

    ``awaiting_approval`` → ``analyses_awaiting_approval`` del resumen del Home;
    ``stale`` → ``insights_stale``. Un valor desconocido en el query param
    responde 422 (validación del enum).
    """

    awaiting_approval = "awaiting_approval"
    stale = "stale"


class PendingAnalysisKind(str, enum.Enum):
    """Tipo de análisis que respalda el ítem pendiente.

    ``valida`` → análisis de una válida (se re-ejecuta con ``event_id``);
    ``season_summary`` → resumen agregado de temporada (``valida_num=0``; se
    re-ejecuta con ``POST /athletes/{id}/race-analysis/season-summary``).
    """

    valida = "valida"
    season_summary = "season_summary"


class PendingAnalysisOut(BaseModel):
    """Un análisis pendiente en la lista de «Temporada».

    ``athlete_ref`` es el nombre que la UI del coach ya muestra (endpoint solo
    coach/admin, acotado por club). Nunca se escribe en un log.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="``external_run_id`` del run (no la PK interna).")
    insight_id: int | None = Field(
        description="Insight activo del run; ``null`` mientras espera aprobación."
    )
    athlete_id: int
    athlete_ref: str
    event_id: int | None = Field(description="Válida del análisis; ``null`` si es de temporada.")
    event_label: str
    season: int | None = Field(
        default=None,
        description="Temporada del análisis (la usa «Re-ejecutar»); ``null`` si no se pudo resolver.",
    )
    kind: PendingAnalysisKind | None = Field(
        default=None,
        description=(
            "Tipo de análisis (``valida`` | ``season_summary``); ``null`` si no se "
            "pudo determinar. Decide cómo se re-ejecuta el ítem."
        ),
    )
    state: PendingAnalysisState
    updated_at: datetime


class RunDismissStaleResponse(BaseModel):
    """Respuesta de ``POST /runs/{run_id}/dismiss-stale`` (siempre ``stale=false``)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    stale: bool
