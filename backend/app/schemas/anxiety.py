"""Schemas Pydantic v2 para el módulo de ansiedad competitiva (feature 017).

Cubre creación (individual/lote), respuesta vía token, lectura, puntuación,
interpretación, dashboards e import/export. Todo el copy de error/ayuda en
español neutro; sin PII de menores en logs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InstrumentTypeLiteral = Literal["csai2", "csai2r", "sas2"]
SubscaleLiteral = Literal["cognitive", "somatic", "selfconfidence"]
StatusLiteral = Literal["pending", "partial", "completed"]
SourceLiteral = Literal["llm", "rule"]
GroupPatternLiteral = Literal[
    "somatic_high", "cognitive_high", "confidence_low", "favorable"
]


# ---------------------------------------------------------------------------
# Creation (US1)
# ---------------------------------------------------------------------------


class AssessmentCreate(BaseModel):
    athlete_id: int
    event_id: int | None = None
    scheduled_at: datetime
    instrument_type: InstrumentTypeLiteral | None = Field(
        default=None,
        description="Forzar instrumento; si se omite se elige por edad.",
    )
    override: bool = Field(
        default=False,
        description="Confirma el override del instrumento por edad (FR-003).",
    )


class BatchCreate(BaseModel):
    athlete_ids: list[int] = Field(..., min_length=1)
    event_id: int
    scheduled_at: datetime


class IssuedToken(BaseModel):
    """Token crudo devuelto UNA sola vez al crear la evaluación."""

    token: str
    expires_at: datetime


class AssessmentCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    instrument_type: InstrumentTypeLiteral
    status: StatusLiteral
    instrument_override: bool
    scheduled_at: datetime
    warning: str | None = None
    token: IssuedToken | None = None


class BatchItemResult(BaseModel):
    """Resultado por atleta dentro de un lote (no falla todo el lote)."""

    athlete_id: int
    created: bool
    assessment: AssessmentCreated | None = None
    warning: str | None = None
    error: str | None = None


class BatchCreated(BaseModel):
    items: list[BatchItemResult]


# ---------------------------------------------------------------------------
# Answering via token (US2)
# ---------------------------------------------------------------------------


class AnswerItem(BaseModel):
    item_id: int
    text: str | None = None  # texto licenciado; None si no aprovisionado


class AnswerForm(BaseModel):
    """Lo que ve el atleta al abrir el token (sin interpretaciones)."""

    instrument_type: InstrumentTypeLiteral
    intro: str
    scale_min: int = 1
    scale_max: int = 4
    items: list[AnswerItem]


class AnswerSubmit(BaseModel):
    # Mapa "<item_id>" → 1..4. Ítems faltantes permitidos (parcial).
    answers: dict[int, int]


class AnswerResult(BaseModel):
    status: Literal["completed", "partial"]
    short_message: str


# ---------------------------------------------------------------------------
# Scoring & read (US3)
# ---------------------------------------------------------------------------


class SubscaleRead(BaseModel):
    score: float | None = None
    baseline: float | None = None
    delta: float | None = None


class InterpretationRead(BaseModel):
    resumen: str
    por_dimension: dict[str, str]
    estrategias: list[str]
    mensaje_para_el_atleta: str
    banderas: list[str] = Field(default_factory=list)


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    instrument_type: InstrumentTypeLiteral
    event_id: int | None
    priority: Literal["A", "B", "C"] | None
    scheduled_at: datetime
    status: StatusLiteral
    is_partial: bool
    instrument_override: bool
    cognitive: SubscaleRead
    somatic: SubscaleRead
    selfconfidence: SubscaleRead
    interpretation: InterpretationRead | None = None
    interpretation_source: SourceLiteral | None = None
    flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Interpretation (US4)
# ---------------------------------------------------------------------------


class InterpretationResponse(BaseModel):
    assessment_id: int
    interpretation: InterpretationRead
    source: SourceLiteral
    model: str | None = None


class InterpretGroupRequest(BaseModel):
    assessment_ids: list[int] = Field(..., min_length=1)


class InterpretGroupResponse(BaseModel):
    items: list[InterpretationResponse]


# ---------------------------------------------------------------------------
# Dashboards (US5)
# ---------------------------------------------------------------------------


class SeriesPoint(BaseModel):
    assessment_id: int
    scheduled_at: datetime
    event_id: int | None
    cognitive: float | None
    somatic: float | None
    selfconfidence: float | None
    flags: list[str] = Field(default_factory=list)


class AthleteSeries(BaseModel):
    athlete_id: int
    instrument_type: InstrumentTypeLiteral
    baseline_cognitive: float | None = None
    baseline_somatic: float | None = None
    baseline_selfconfidence: float | None = None
    points: list[SeriesPoint]
    note: str | None = None  # p. ej. familias no comparables


class GroupMember(BaseModel):
    athlete_id: int
    assessment_id: int
    cognitive: float | None
    somatic: float | None
    selfconfidence: float | None
    flags: list[str] = Field(default_factory=list)


class GroupTriage(BaseModel):
    event_id: int
    buckets: dict[GroupPatternLiteral, list[GroupMember]]
    alerts: list[GroupMember] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Import / export (US6)
# ---------------------------------------------------------------------------


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportRowError] = Field(default_factory=list)
