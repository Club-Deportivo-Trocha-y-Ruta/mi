"""Modelo SQLAlchemy de ``agent_run_events``.

Eventos emitidos por los nodos del grafo race-analysis (LangGraph) y
persistidos para polling del coach (``GET /runs/{run_id}/status``).

La tabla ya existe en DB (creada por la migración
``7a8b9c0d1e2f_race_agentic_module_tables.py``); este modelo se añade en
BE-A1 para eliminar el SQL crudo del router.

Privacidad
==========
- ``payload_json`` NUNCA debe contener PII real (nombre, DOB). El grafo
  garantiza pseudónimos en todos los payloads de eventos.
- El test ``tests/routers/test_race_analysis_privacy.py`` valida la
  invariante. NO relajarla sin un test sentinela paralelo.

Mapeo enum
==========
``AgentRunEventType`` refleja el ENUM físico declarado en la migración.
Los wrappers ``with_events`` en ``app.services.race.ai.events`` emiten
nombres más ricos (``node_error``, ``run_failed``); el servicio
``app.services.race.ai.runs._normalize_event_type`` los mapea al subset
que la DB acepta antes de persistir.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun


class AgentRunEventType(str, enum.Enum):
    """Tipos de eventos persistidos en ``agent_run_events``.

    Subset de los emitidos in-memory (``app.services.race.ai.events``)
    porque el ENUM físico de la tabla es más restrictivo. Mapeo
    documentado en ``app.services.race.ai.runs._EVENT_TYPE_TO_DB``.
    """

    node_start = "node_start"
    node_end = "node_end"
    hitl_request = "hitl_request"
    hitl_response = "hitl_response"
    explain = "explain"
    token = "token"
    error = "error"
    done = "done"


class AgentRunEvent(Base):
    """Evento de un :class:`AgentRun`. Persistido para polling del coach."""

    __tablename__ = "agent_run_events"
    __table_args__ = (
        Index("ix_agent_run_events_run_seq", "run_id", "seq"),
        Index("ix_agent_run_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[AgentRunEventType] = mapped_column(
        Enum(
            AgentRunEventType,
            name="agentruneventtype",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    node_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )

    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="events")
