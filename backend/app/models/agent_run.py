"""Modelo SQLAlchemy *mínimo* para ``agent_runs`` (race-results v2 agéntico).

Coexistencia con SQL crudo
==========================
La tabla ``agent_runs`` fue creada por la migración
``7a8b9c0d1e2f_race_agentic_module_tables.py`` para soportar el grafo
LangGraph del módulo race-analysis (workflow §3.1). Hoy el router
``app/routers/race_analysis.py`` interactúa con ella **vía SQL crudo
``text()``** — esa convención NO debe romperse en BE-1 (las queries
existentes siguen funcionando porque la tabla física no cambia).

Este modelo se crea sólo para:

1. Exponer la columna ``athlete_id`` (añadida en BE-1) como relación ORM
   navegable desde ``Athlete.agent_runs``, habilitando el endpoint
   "histórico de runs por atleta" sin necesidad de queries crudas.
2. Permitir relaciones ORM desde otros modelos del mismo módulo
   (``AthleteAiInsight.agent_run`` apunta aquí).

Las columnas mapeadas son **un subconjunto** de las físicas: solo las
que necesitamos para queries y eager loading. Las demás (cost_usd,
input_json, final_output_json, langfuse_trace_id, etc.) siguen
disponibles via SQL crudo en el router; agregarlas al modelo no es
necesario para BE-1 y mantiene la superficie pequeña.
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
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.athlete_ai_insight import AthleteAiInsight
    from app.models.user import User


class AgentRunStatus(str, enum.Enum):
    """Estados del run del grafo agéntico.

    Debe permanecer en lock-step con el enum DB ``agentrunstatus``
    declarado en la migración ``7a8b9c0d1e2f``.
    """

    running = "running"
    awaiting_hitl = "awaiting_hitl"
    completed = "completed"
    rejected = "rejected"
    failed = "failed"
    cancelled = "cancelled"


class AgentRun(Base):
    """Ejecución del grafo race-analysis (LangGraph).

    Solo se mapean las columnas necesarias para queries ORM en BE-1+:
    listado por atleta, joins con insights, eager-load del usuario que
    inició el run.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        # Índice compuesto añadido en BE-1 para listado por atleta.
        Index("ix_agent_runs_athlete_started", "athlete_id", "started_at"),
        # Índices preexistentes (re-declarados sin unique para que el
        # autogenerate de Alembic no los proponga como faltantes).
        Index("ix_agent_runs_user_started", "requested_by_user_id", "started_at"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    graph_name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(
            AgentRunStatus,
            name="agentrunstatus",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=AgentRunStatus.running,
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # NUEVA en BE-1: FK SET NULL contra athletes.
    athlete_id: Mapped[int | None] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True
    )
    checkpoint_thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relaciones
    requested_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[AgentRun.requested_by_user_id]",
    )
    athlete: Mapped["Athlete | None"] = relationship(
        "Athlete",
        back_populates="agent_runs",
        foreign_keys="[AgentRun.athlete_id]",
    )
    insights: Mapped[list["AthleteAiInsight"]] = relationship(
        "AthleteAiInsight",
        back_populates="agent_run",
        foreign_keys="[AthleteAiInsight.agent_run_id]",
    )
