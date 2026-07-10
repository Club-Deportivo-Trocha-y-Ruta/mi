"""Pydantic schemas para la capa agéntica (Fase 3 race-results v2).

Estos schemas son el **contrato de I/O** de los agentes core
(`RaceAnalystAgent`, `RaceCriticAgent`, `RaceChatAgent`) y de los nodos
del grafo LangGraph (Fase 4). Diseño guiado por:

- Privacidad menores (CLAUDE.md §Privacidad): el analyst recibe
  ``athlete_pseudonym`` — NUNCA un nombre real. ``athlete_id`` viaja sólo
  para audit-trail interno (persistencia en ``athlete_ai_insights``), no
  para el prompt.
- Trazabilidad: ``citations_used`` lista referencias ``[N]`` que el
  modelo incluyó en su output, para verificación humana.
- JSON-serializable: todos los modelos exponen ``.model_dump()`` plano
  (sin objetos no-Pydantic) para persistir como JSON en MySQL.
- Defensa en profundidad: enums cerrados para ``category`` /
  ``priority`` / ``risk_flag`` / ``severity`` — el critic puede
  bloquear si llega un valor fuera del enum.

Convención: estos schemas viven en el **service layer**, no en
``app/schemas/``. Razón: ``app/schemas/`` está reservado a contratos
HTTP (Pydantic v2 de routers FastAPI). Estos son contratos internos del
módulo race; el router de race-analysis (Fase 5) hará el mapping a sus
propios DTOs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    # Enums
    "LTADGroup",
    "RecommendationCategory",
    "Priority",
    "RiskFlagType",
    "Severity",
    "CriticIssueSeverity",
    # Pydantic models
    "Recommendation",
    "RiskFlag",
    "AnalysisInput",
    "AnalysisOutput",
    "CriticIssue",
    "CriticFeedback",
    "ChatResponse",
    "RunMetrics",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LTADGroup(str, Enum):
    """Grupos LTAD (Long-Term Athlete Development) del marco teórico.

    Mapeo edad cronológica → grupo (orientativo, ajustar por PHV en
    nodos del grafo):

    - mini-bambino: 6-9 años
    - bambino:      10-12 años
    - juvenil:      13-15 años
    - junior:       16-17 años (fuera del scope MVP pero contemplado)
    """

    MINI_BAMBINO = "mini-bambino"
    BAMBINO = "bambino"
    JUVENIL = "juvenil"
    JUNIOR = "junior"


class RecommendationCategory(str, Enum):
    """Categorías de recomendación — alineadas al marco teórico LTAD."""

    TECHNIQUE = "technique"
    VOLUME = "volume"
    RECOVERY = "recovery"
    NUTRITION = "nutrition"
    PSYCHOLOGY = "psychology"


class Priority(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class RiskFlagType(str, Enum):
    LOAD_EXCESS = "load_excess"
    UNDER_RECOVERY = "under_recovery"
    GROWTH_SPURT = "growth_spurt"
    TECHNICAL_GAP = "technical_gap"
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class CriticIssueSeverity(str, Enum):
    """Severidad del issue reportado por el critic."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Sub-modelos
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    """Una recomendación accionable extraída del análisis."""

    text: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Texto de la recomendación (≤500 chars, una idea por reco).",
    )
    category: RecommendationCategory
    priority: Priority = Priority.MED


class RiskFlag(BaseModel):
    """Riesgo identificado por el agente (cargas, recuperación, etc.)."""

    flag: RiskFlagType
    severity: Severity
    evidence: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Cita/evidencia (datos del progresión o principio LTAD).",
    )


class CriticIssue(BaseModel):
    """Un problema detectado por el critic en el draft del analyst."""

    section: str = Field(..., description="Sección del análisis con el problema.")
    problem: str = Field(..., min_length=3, max_length=500)
    suggested_fix: str = Field(..., min_length=3, max_length=500)


# ---------------------------------------------------------------------------
# Analyst I/O
# ---------------------------------------------------------------------------


class AnalysisInput(BaseModel):
    """Input al ``RaceAnalystAgent.invoke``.

    Notas privacidad:
    - ``athlete_pseudonym`` es lo que ve el LLM. ``athlete_id`` es para
      audit; el agente NO debe re-emitirlo en el output.
    - ``progression_df_records`` y ``podium_context`` ya vienen
      anonimizados desde el nodo ``anonymize`` del grafo.

    Season context (T014 — feature 010):
    - ``season_comparative``: per-prior-válida comparison table, computed in
      Python by compute_metrics. The LLM must ground every comparative claim
      exclusively in this table and never invent history.
    - ``progression_assessment``: ProgressionAssessment enum value string,
      also computed in Python. When "first_reference", the LLM must state
      "primera referencia de la temporada" and make no cross-race comparison.
    """

    model_config = ConfigDict(extra="forbid")

    athlete_pseudonym: str = Field(..., min_length=1, max_length=64)
    age: int = Field(..., ge=6, le=20)
    ltad_group: LTADGroup
    progression_df_records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Filas de progresión por válida (event_date, position, etc.).",
    )
    podium_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Output de fetch_podium_context() para evento foco.",
    )
    memory_recent_insights: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Resúmenes textuales de últimos N insights (máx 10).",
    )
    explain_mode: bool = Field(
        False,
        description="Si True, el agente narra '¿por qué hago X?' (modo aprendizaje).",
    )
    # Season context fields (T014) — injected into the v2 prompt template.
    season_comparative: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-prior-válida comparison entries. Each dict: "
            "{valida_num, event_label, position, race_time_ms, field_size, "
            "delta_position, delta_time_ms}. Empty when first_reference."
        ),
    )
    progression_assessment: str = Field(
        default="first_reference",
        description=(
            "ProgressionAssessment value computed by compute_metrics. "
            "Values: improving | stable | declining | mixed | first_reference."
        ),
    )
    # Grounding fields (feature 011) — per-válida real data threaded from the
    # graph state. Both are anonymized/derived upstream; never defaulted to a
    # plausible-but-false value.
    race_meta: str | None = Field(
        default=None,
        description=(
            "Pre-formatted, anonymized recorded-conditions block for THE "
            "válida this input analyzes (clima/temperatura/superficie/altitud/"
            "notas). None → the prompt omits the conditions section entirely "
            "and the anti-fabrication veto activates. NEVER an empty string."
        ),
    )
    maturation_status: str | None = Field(
        default=None,
        description=(
            "Real maturation phase from the athlete's latest anthropometric "
            "record (Pre-PHV/Circa-PHV/Post-PHV). None → no maturation-phase "
            "claim is made in the analysis (no Pre-PHV default)."
        ),
    )
    # Audit-only — NO se inyecta al prompt:
    athlete_id: int = Field(..., ge=1)
    season: int = Field(..., ge=2000, le=2100)


class AnalysisOutput(BaseModel):
    """Output estructurado del ``RaceAnalystAgent``.

    El ``raw_markdown`` siempre se preserva (es lo que renderiza el coach
    UI). Las ``sections`` son una vista parseada — si el parseo falla
    parcialmente, los campos quedan vacíos pero ``raw_markdown`` siempre
    está disponible.
    """

    model_config = ConfigDict(extra="forbid")

    pseudonym: str = Field(..., min_length=1, max_length=64)
    sections: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Secciones markdown parseadas. Keys esperadas: "
            "'evolution', 'technical', 'recommendations', 'risks', 'next_steps'."
        ),
    )
    citations_used: list[str] = Field(
        default_factory=list,
        description="chunk_id de citas referenciadas (formato '[1]','[2]'...).",
    )
    recommendations: list[Recommendation] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    raw_markdown: str = Field(..., min_length=1)
    word_count: int = Field(..., ge=0)

    @field_validator("citations_used")
    @classmethod
    def _dedupe_citations(cls, v: list[str]) -> list[str]:
        """Deduplica preservando orden — el LLM a veces repite [1] varias veces."""
        seen: set[str] = set()
        out: list[str] = []
        for cid in v:
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
        return out


# ---------------------------------------------------------------------------
# Critic I/O
# ---------------------------------------------------------------------------


class CriticFeedback(BaseModel):
    """Feedback estructurado del ``RaceCriticAgent``.

    Reglas:
    - ``must_block=True`` fuerza HITL **antes** de mostrar al coach.
      Usar para: PII leak, violación a principios inviolables del
      CLAUDE.md (cadencia <60, suplementos, >5 días/sem, etc.).
    - ``approved=True`` + ``must_block=False`` → camino feliz.
    - ``severity`` aplica al worst-case del set de issues.
    """

    model_config = ConfigDict(extra="forbid")

    approved: bool
    severity: CriticIssueSeverity = CriticIssueSeverity.LOW
    issues: list[CriticIssue] = Field(default_factory=list)
    must_block: bool = False


# ---------------------------------------------------------------------------
# Chat I/O
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Respuesta del ``RaceChatAgent`` para un turn conversacional."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1)
    citations_used: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class RunMetrics(BaseModel):
    """Métricas de una invocación LLM — persistidas en ``athlete_ai_insights``.

    ``cost_usd`` se calcula con las constantes de
    :mod:`app.services.race.agents.pricing` (tarifas Gemini Flash Lite).
    """

    model_config = ConfigDict(extra="forbid")

    tokens_in: int = Field(..., ge=0)
    tokens_out: int = Field(..., ge=0)
    latency_ms: int = Field(..., ge=0)
    cost_usd: float = Field(..., ge=0.0)
    prompt_version: str = Field(..., min_length=1, max_length=32)
