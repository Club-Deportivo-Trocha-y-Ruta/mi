"""Pydantic schemas para el router ``race_analysis`` (F5).

Contratos HTTP del módulo agéntico race-results v2. Esta capa es
distinta de :mod:`app.services.race.schemas` — aquellos son contratos
internos de los agentes (analyst/critic/chat). Este módulo es la
fachada hacia el frontend.

Diseño:
- Privacidad menores (CLAUDE.md §Privacidad): NUNCA viaja un nombre
  real en estos schemas. El cliente sólo ve ``pseudonym`` + ``run_id``.
  El test sentinela ``test_race_analysis_privacy.py`` valida la
  invariante.
- Polling: ``RunStatusResponse.new_events`` slicing por ``seq``
  monotónico (no por timestamp — agentes pueden generar 2 eventos en
  el mismo ms).
- Estados expuestos al cliente: derivados del enum DB
  ``agentrunstatus`` (running, awaiting_hitl, completed, rejected,
  failed, cancelled). El cliente sólo necesita saber si está activo,
  esperando HITL, o terminó.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "RunState",
    "HITLDecision",
    "StartRunRequest",
    "StartRunResponse",
    "RunEvent",
    "RunStatusResponse",
    "HITLDecisionRequest",
    "HITLDecisionResponse",
    "ChatRequest",
    "AIUsageResponse",
    "AIUsageByPromptVersion",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunState(str, Enum):
    """Estados expuestos al cliente.

    Mapeo desde el enum DB ``agentrunstatus``:
    - ``running``        → running
    - ``awaiting_hitl``  → hitl_waiting
    - ``completed``      → done
    - ``rejected``       → done (rejected, ver result)
    - ``failed``         → failed
    - ``cancelled``      → cancelled
    """

    RUNNING = "running"
    HITL_WAITING = "hitl_waiting"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HITLDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


# ---------------------------------------------------------------------------
# Start run
# ---------------------------------------------------------------------------


class StartRunRequest(BaseModel):
    """Body para ``POST /api/race-analysis/runs``.

    ``valida_nums`` opcional: si None → todas las válidas de la temporada
    (decidido por ``load_race_data``). ``explain_mode`` activa el modo
    aprendizaje + HITL siempre (workflow §"Decisiones cerradas").
    """

    model_config = ConfigDict(extra="forbid")

    athlete_id: int = Field(..., ge=1, description="PK del atleta en `athletes`.")
    season: int = Field(..., ge=2020, le=2100, description="Año de la temporada.")
    valida_nums: Optional[list[int]] = Field(
        default=None,
        max_length=12,
        description="Subset de válidas a analizar; None = todas.",
    )
    explain_mode: bool = Field(
        default=False,
        description="Si True, agente narra '¿por qué hago X?' y HITL siempre activo.",
    )

    @field_validator("valida_nums")
    @classmethod
    def _validate_valida_nums(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return None
        if not v:
            raise ValueError("valida_nums no puede ser lista vacía (usa None para todas)")
        for n in v:
            if n < 1 or n > 12:
                raise ValueError(f"valida_num fuera de rango (1-12): {n}")
        # Dedupe preservando orden.
        seen: set[int] = set()
        out: list[int] = []
        for n in v:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out


class StartRunResponse(BaseModel):
    """Response 201 de ``POST /runs``."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1, max_length=64)
    status: RunState = RunState.RUNNING
    started_at: datetime
    status_url: str
    estimated_seconds: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class RunEvent(BaseModel):
    """Un evento emitido por un nodo del grafo.

    ``seq`` monotónico por run (1, 2, 3, ...). El cliente envía
    ``?since=<last_seq>`` para slicing.
    """

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(..., ge=1)
    ts: datetime
    type: str = Field(..., min_length=1, max_length=32)
    node: Optional[str] = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStatusResponse(BaseModel):
    """Response de ``GET /runs/{run_id}/status``.

    ``new_events`` retorna sólo eventos con ``seq > since`` (param query).
    ``progress_pct`` heurístico: nodos completados / 13.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    state: RunState
    progress_pct: int = Field(..., ge=0, le=100)
    current_node: Optional[str] = Field(default=None, max_length=64)
    started_at: datetime
    estimated_seconds_remaining: int = Field(..., ge=0)
    new_events: list[RunEvent] = Field(default_factory=list)
    last_seq: int = Field(..., ge=0, description="Mayor seq emitido hasta ahora.")


# ---------------------------------------------------------------------------
# HITL
# ---------------------------------------------------------------------------


class HITLDecisionRequest(BaseModel):
    """Body para ``POST /runs/{run_id}/hitl/{step_id}``."""

    model_config = ConfigDict(extra="forbid")

    decision: HITLDecision
    edits: Optional[str] = Field(
        default=None,
        max_length=20_000,
        description="Markdown editado por el coach (sólo si decision=edit).",
    )
    notes: Optional[str] = Field(default=None, max_length=2_000)


class HITLDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    run_id: str
    step_id: str
    next_state: RunState


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Body para ``POST /api/race-analysis/chat``.

    ``session_id`` lo genera el frontend (uuid v4 estable por
    conversación). ``athlete_id`` es contexto opcional; el LLM decide
    si usarlo via tools.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=2_000)
    athlete_id: Optional[int] = Field(default=None, ge=1)


# ---------------------------------------------------------------------------
# Admin metrics
# ---------------------------------------------------------------------------


class AIUsageByPromptVersion(BaseModel):
    """Métricas agregadas por versión de prompt."""

    model_config = ConfigDict(extra="forbid")

    prompt_version: str
    run_count: int = Field(..., ge=0)
    cost_usd_total: float = Field(..., ge=0.0)


class AIUsageResponse(BaseModel):
    """Response de ``GET /admin/ai-usage?days=30``.

    Lee desde ``athlete_ai_insights`` (latency_ms y cost_usd
    persistidos por cada run). Solo admin.
    """

    model_config = ConfigDict(extra="forbid")

    window_days: int = Field(..., ge=1, le=365)
    run_count: int = Field(..., ge=0)
    cost_usd_total: float = Field(..., ge=0.0)
    latency_ms_p50: int = Field(..., ge=0)
    latency_ms_p95: int = Field(..., ge=0)
    fail_rate: float = Field(..., ge=0.0, le=1.0)
    by_prompt_version: list[AIUsageByPromptVersion] = Field(default_factory=list)
