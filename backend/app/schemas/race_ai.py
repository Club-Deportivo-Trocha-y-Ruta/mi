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

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

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
    "MetricsSnapshotV1",
    "MetricsSnapshotStatus",
    # Feature 010 — group launch + season analysis
    "GroupRunOutcome",
    "GroupRunLaunchRequest",
    "GroupRunItem",
    "GroupRunLaunchResponse",
    "RaceEventRunItem",
    "RaceEventRunsResponse",
    "ProgressionAssessment",
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
    # Feature 037 (T101). "valida" = análisis por válida(s) (comportamiento
    # actual, default). "season" = resumen de temporada (T203 lo conecta a
    # un endpoint dedicado; aquí se acepta ya para no requerir otro cambio
    # de contrato cuando ese router se implemente).
    analysis_kind: str = Field(
        default="valida",
        description="Tipo de análisis: 'valida' (default) | 'season'.",
    )

    @field_validator("analysis_kind")
    @classmethod
    def _validate_analysis_kind(cls, v: str) -> str:
        if v not in {"valida", "season"}:
            raise ValueError("analysis_kind debe ser 'valida' o 'season'")
        return v

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
    si usarlo via tools. ``race_event_id`` (feature 010) es contexto
    opcional de evento; cuando se pasa, las tools del chat limitan
    resultados/insights a ese evento y siembran la sesión con la
    etiqueta del evento.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=2_000)
    athlete_id: Optional[int] = Field(default=None, ge=1)
    race_event_id: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Contexto de evento (feature 010). Cuando se incluye, el chat "
            "restringe resultados e insights al evento indicado."
        ),
    )


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


# ---------------------------------------------------------------------------
# Persisted snapshot (athlete_ai_insights.metrics_snapshot_json)
# ---------------------------------------------------------------------------


MetricsSnapshotStatus = Literal["finished", "dnf", "dns", "dsq"]
"""Estados aceptados para un resultado individual dentro de un snapshot.

Subconjunto del enum DB ``raceresultstatus`` — ``minus_laps`` (agregado
en migración ``64c263edd07f``) NO se acepta aquí porque el snapshot
representa la métrica del atleta tal como aparece en el reporte
publicable (un corredor con ``minus_laps`` se considera ``finished`` con
gap explícito en ``podium_gap_ms`` para fines del insight).
"""


class MetricsSnapshotV1(BaseModel):
    """Snapshot estructurado de las métricas que sustentan un insight.

    Persiste en ``athlete_ai_insights.metrics_snapshot_json`` (JSON). El
    versionado vive en el campo ``schema_version`` para que migraciones
    futuras puedan evolucionar el contrato sin romper insights viejos.

    Diseño:
    - ``extra="forbid"``: el snapshot es contrato cerrado. Cualquier
      campo nuevo agregar primero al schema (y subir ``schema_version``).
      Campos custom de use_cases agregados van en ``extras``.
    - Todos los campos numéricos son no-negativos (``ge=0``). Tiempos en
      milisegundos (convención ``parse_time`` en ``services/race/normalizer.py``).
    - ``category_*`` agregados se nullan cuando ``status != finished``
      o cuando la categoría tiene n<2 (no hay distribución).

    Season context fields (T015 — feature 010):
    - ``season_comparative``: per-prior-válida comparison entries as stored
      by compute_metrics. Optional so old snapshots (without this key)
      remain valid — defaults to empty list.
    - ``progression_assessment``: ProgressionAssessment string value.
      Optional so old snapshots remain valid — defaults to None.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(
        default=1,
        description="Versión del contrato del snapshot. Subir si se cambia.",
    )

    # --- Contexto del evento ----------------------------------------------
    event_id: int = Field(..., ge=1)
    season: int = Field(..., ge=2020, le=2100)
    valida_num: int = Field(
        ...,
        ge=0,
        le=99,
        description=(
            "0 = use_case agregado de temporada (season_summary). "
            "1..7 = válida regular. 99 = Cto. Departamental."
        ),
    )
    event_date: date

    # --- Resultado individual ---------------------------------------------
    status: MetricsSnapshotStatus
    race_time_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Tiempo total del atleta en ms. NULL si status != finished.",
    )
    position: Optional[int] = Field(default=None, ge=1)
    podium_gap_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Diferencia en ms vs. P1 de su categoría. NULL si DNF/DNS/DSQ o si es P1.",
    )
    ranking_in_category: Optional[int] = Field(default=None, ge=1)

    # --- Categoría ---------------------------------------------------------
    category_id: int = Field(..., ge=1)
    category_code: str = Field(..., min_length=1, max_length=32)
    category_size: int = Field(..., ge=0, description="N de corredores en la categoría.")
    category_time_mean_ms: Optional[int] = Field(default=None, ge=0)
    category_time_stddev_ms: Optional[int] = Field(default=None, ge=0)
    category_time_min_ms: Optional[int] = Field(default=None, ge=0)
    category_time_max_ms: Optional[int] = Field(default=None, ge=0)

    # --- Season context (T015 — feature 010) — additive, old snapshots stay valid ---
    season_comparative: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-prior-válida comparison entries as produced by compute_metrics. "
            "Empty list for old insights or first_reference athletes."
        ),
    )
    progression_assessment: Optional[str] = Field(
        default=None,
        description=(
            "ProgressionAssessment value: improving | stable | declining | "
            "mixed | first_reference. None for old insights without this data."
        ),
    )

    # --- Extensibilidad por use_case --------------------------------------
    extras: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Campos específicos por use_case (progression, podium_gap, "
            "projection, season_summary) que no son parte del contrato base."
        ),
    )

    @field_validator("category_code")
    @classmethod
    def _normalize_category_code(cls, v: str) -> str:
        # Normalizamos a uppercase sin espacios (consistente con services/race).
        return v.strip().upper()


# ---------------------------------------------------------------------------
# Feature 010 — Group launch + event runs
# ---------------------------------------------------------------------------


class GroupRunOutcome(str, Enum):
    """Resultado individual de un intento de lanzamiento de análisis.

    - ``started``: run lanzado exitosamente.
    - ``backpressure``: semáforo de concurrencia lleno (MAX_CONCURRENT_RUNS).
    - ``budget_exceeded``: presupuesto 30d excedido antes de lanzar.
    - ``already_running``: ya existe un run activo para (atleta, season, valida).
    - ``no_results``: el atleta no tiene resultados en este evento.
    - ``error``: error inesperado por atleta (los demás continúan).
    """

    started = "started"
    backpressure = "backpressure"
    budget_exceeded = "budget_exceeded"
    already_running = "already_running"
    no_results = "no_results"
    error = "error"


class GroupRunLaunchRequest(BaseModel):
    """Body para ``POST /api/race-analysis/race-events/{id}/runs``."""

    model_config = ConfigDict(extra="forbid")

    athlete_ids: Optional[list[int]] = Field(
        default=None,
        description=(
            "Subset de atletas a analizar. None = todos los atletas del club "
            "con resultados en el evento (lanzamiento completo)."
        ),
    )
    explain_mode: bool = Field(
        default=False,
        description="Si True, activa modo aprendizaje + HITL siempre en cada run.",
    )


class GroupRunItem(BaseModel):
    """Resultado individual de lanzamiento de un análisis dentro del grupo."""

    model_config = ConfigDict(extra="forbid")

    athlete_id: int
    athlete_display_name: str
    run_id: Optional[str] = Field(
        default=None,
        description="external_run_id asignado al run. Solo presente si outcome=started.",
    )
    outcome: GroupRunOutcome
    detail: Optional[str] = Field(
        default=None,
        description="Mensaje en español (Colombia) para outcomes no-started.",
    )


class GroupRunLaunchResponse(BaseModel):
    """Response 200 de ``POST /api/race-analysis/race-events/{id}/runs``."""

    model_config = ConfigDict(extra="forbid")

    race_event_id: int
    season: int
    valida_num: int
    started_count: int = Field(..., ge=0)
    skipped_count: int = Field(..., ge=0)
    items: list[GroupRunItem]


class RaceEventRunItem(BaseModel):
    """Un run de análisis asociado a un evento de carrera."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    athlete_id: int
    athlete_display_name: str
    state: RunState
    started_at: datetime
    stale: bool = Field(
        description="True si el run fue marcado como desactualizado (stale_since IS NOT NULL)."
    )


class RaceEventRunsResponse(BaseModel):
    """Response 200 de ``GET /api/race-analysis/race-events/{id}/runs``."""

    model_config = ConfigDict(extra="forbid")

    race_event_id: int
    runs: list[RaceEventRunItem]


# ---------------------------------------------------------------------------
# Feature 010 — Season progression assessment
# ---------------------------------------------------------------------------


class ProgressionAssessment(str, Enum):
    """Evaluación de progresión de un atleta a lo largo de la temporada.

    Derivación (datos: posiciones en válidas previas vs. válida actual):
    - ``improving``: posición estrictamente mejor en válida actual vs. todas las previas.
    - ``stable``: posición igual (delta ±0) en todas las válidas comparables.
    - ``declining``: posición estrictamente peor en válida actual vs. todas las previas.
    - ``mixed``: combinación de mejoras y retrocesos sin tendencia clara.
    - ``first_reference``: no hay válidas previas para comparar — primera carrera del atleta.

    El nodo analyst_agent NUNCA debe inventar comparaciones cuando el valor
    es ``first_reference`` (FR-007, SC-002).
    """

    improving = "improving"
    stable = "stable"
    declining = "declining"
    mixed = "mixed"
    first_reference = "first_reference"
