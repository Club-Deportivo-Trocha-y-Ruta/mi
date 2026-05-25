"""Modelo SQLAlchemy de ``agent_runs`` (race-results v2 agéntico).

Histórico
=========
Originalmente este modelo era *mínimo* — solo mapeaba un subconjunto de
columnas para soportar la relación ``Athlete.agent_runs``. El router
``app/routers/race_analysis.py`` consumía/escribía la tabla con SQL
crudo (``sqlalchemy.text``).

A partir del refactor BE-A1 el router pasa a usar exclusivamente el
service ORM ``app.services.race.ai.runs``. Por eso ahora **todas** las
columnas físicas de la tabla se mapean en el modelo (``input_json``,
``final_output_json``, ``error_message``, ``explain_mode``, ``cost_usd``,
``langfuse_trace_id``).

La tabla DB ya existe (creada por la migración
``7a8b9c0d1e2f_race_agentic_module_tables.py``). NO se requiere
migración adicional: solo se amplía la superficie ORM.
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_run_event import AgentRunEvent
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

    Mapea **todas** las columnas físicas de la tabla a partir de BE-A1.
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
    # Columnas mapeadas en BE-A1 (antes accedidas via SQL crudo).
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    explain_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    events: Mapped[list["AgentRunEvent"]] = relationship(
        "AgentRunEvent",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
