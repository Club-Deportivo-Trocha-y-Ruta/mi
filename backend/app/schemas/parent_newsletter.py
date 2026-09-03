"""Schemas del portal de padres para la bitácora de etapa (feature 038, T202).

Contrato: ``specs/038-newsletter-bitacora-redesign/data-model.md`` §5 y
``contracts/api.md`` (sección "Parent").

Privacidad (Ley 1581, CLAUDE.md): estos DTOs viajan tal cual al padre —
``ParentNewsletterOut.stage_log`` SIEMPRE se construye con
``app.services.training.stage_log.to_parent_dto`` (allow-list explícito),
nunca con el ``stage_log_json`` crudo del boletín (que incluye
``block_states``, ``grounding_violations`` y ``source_insight_id``,
exclusivos del coach/studio).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ParentNewsletterListItem(BaseModel):
    """Fila de la lista de bitácoras del portal de padres."""

    id: int
    athlete_id: int
    year: int
    month: int
    period_label: str
    stage_title: str | None
    sent_at: datetime | None
    read_at: datetime | None

    model_config = {"from_attributes": False}


class ParentNewsletterOut(BaseModel):
    """Detalle de una bitácora para el portal de padres."""

    id: int
    athlete_id: int
    year: int
    month: int
    period_label: str
    sent_at: datetime | None
    read_at: datetime | None
    has_pdf: bool
    # Resultado de ``to_parent_dto`` — allow-list, nunca el stage_log_json crudo.
    stage_log: dict[str, Any]

    model_config = {"from_attributes": False}
