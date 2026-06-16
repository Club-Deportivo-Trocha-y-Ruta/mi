"""Schemas Pydantic v2 para el módulo athlete-race-analysis (BE-2).

Esta capa expone insights/runs/analytics filtrados por atleta. Es la
fachada *legible para padre/coach* — distinta de:

- ``app/schemas/race_ai.py`` (contratos del runner LangGraph para coach).
- ``app/services/race/schemas.py`` (contratos internos de los agentes).

Privacidad (CLAUDE.md §Privacidad)
==================================
NUNCA exponer en respuestas:
- ``athlete_id``: el cliente ya consultó la URL ``/athletes/{id}/...``.
- ``competitor_id``: pk interna de race_competitors.
- ``generated_by_user_id`` / ``requested_by_user_id``: identifica al coach.
- ``agent_run_id``: pk interna numérica.
- ``internal AgentRun.id`` (BigInt). Sólo se expone ``external_run_id`` (UUID).

Los pseudónimos en distribución son determinísticos por ``competitor_id``
y NO contienen el ``athlete_id`` real ni nombres. Forma:
``f"C{competitor_id % 10000:04d}"``.

Cualquier campo que se agregue debe pasar por:
1. Revisión de privacidad menores.
2. ``model_config = ConfigDict(extra="forbid")`` activo.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.athlete_ai_insight import InsightConfidence
from app.schemas.race_ai import MetricsSnapshotV1

__all__ = [
    "AthleteInsightOut",
    "AthleteInsightDetailOut",
    "AthleteInsightListResponse",
    "InsightLink",
    "AthleteRunOut",
    "AthleteRunListResponse",
    "AthleteRunStatus",
    "AthleteStartRunBody",
    "EvolutionMetric",
    "EvolutionPoint",
    "EvolutionResponse",
    "DistributionPoint",
    "DistributionCurvePoint",
    "DistributionResponse",
    "AnalysisConfidence",
    "ClubInsightByRaceItem",
    "ClubInsightsByRaceResponse",
    "RaceParticipationOption",
    "RaceParticipationResponse",
]


# ---------------------------------------------------------------------------
# Enums propios de la capa de respuesta
# ---------------------------------------------------------------------------


class AnalysisConfidence(str, Enum):
    """Confianza de una analítica (mismo dominio que ``InsightConfidence``)."""

    low = "low"
    medium = "medium"
    high = "high"


class EvolutionMetric(str, Enum):
    """Métricas válidas para el endpoint ``/evolution``."""

    PODIUM_GAP_MS = "podium_gap_ms"
    RANKING = "ranking"
    TIME_MS = "time_ms"
    PERCENTILE = "percentile"


class AthleteRunStatus(str, Enum):
    """Estados expuestos de un ``agent_runs`` para listado del atleta.

    Subset del enum DB ``agentrunstatus`` — mantenemos los valores DB
    para que el frontend pueda mapear directamente sin traducción.
    """

    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Insights — listado y detalle
# ---------------------------------------------------------------------------


class InsightLink(BaseModel):
    """Referencia ligera a otro insight para la cadena de versionado."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., ge=1)
    generated_at: datetime
    coach_approved: bool


class AthleteInsightOut(BaseModel):
    """Item de listado de insights. Subconjunto público de ``AthleteAiInsight``.

    Nunca incluye ``athlete_id`` / ``competitor_id`` / IDs de usuarios. El
    consumidor ya conoce el atleta por la ruta ``/athletes/{id}/...``.
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., ge=1)
    season: int = Field(..., ge=2020, le=2100)
    valida_num: Optional[int] = Field(
        default=None,
        ge=0,
        le=99,
        description=(
            "0 = use_case agregado de temporada. 1..7 = válida regular. "
            "99 = Cto. Departamental. NULL = no aplica."
        ),
    )
    event_id: Optional[int] = Field(default=None, ge=1)
    use_case: str = Field(..., max_length=32)
    summary_text: str
    confidence: InsightConfidence
    model: str = Field(..., max_length=128)
    prompt_version: str = Field(..., max_length=32)
    coach_approved: bool
    generated_at: datetime
    approved_at: Optional[datetime] = None
    is_active: bool = Field(
        ...,
        description=(
            "True si la fila tiene sentinel ``is_active=1``. "
            "False si fue deprecada / nunca activa."
        ),
    )
    deprecated_at: Optional[datetime] = None


class AthleteInsightDetailOut(AthleteInsightOut):
    """Detalle completo con recommendations, snapshot, principles y cadena."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    metrics_snapshot: MetricsSnapshotV1 | dict[str, Any] = Field(
        ...,
        description=(
            "Si el JSON cumple ``MetricsSnapshotV1`` lo retornamos tipado; "
            "para snapshots viejos sin ``schema_version`` se entrega como dict."
        ),
    )
    principles_cited: list[dict[str, Any]] = Field(default_factory=list)
    supersedes: list[InsightLink] = Field(
        default_factory=list,
        description="Cadena de insights anteriores (más reciente primero).",
    )
    superseded_by: Optional[InsightLink] = None
    is_first_in_season: Optional[bool] = Field(
        default=None,
        description=(
            "True si el atleta tenía 1 sola válida en toda la temporada "
            "cuando se generó este insight. Cuando es True, el frontend "
            "muestra banner N=1. None para insights v1 (sin dato)."
        ),
    )
    season_validas_count: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Número de válidas con participación real en toda la temporada "
            "al momento de generación. Informativo. None para insights v1."
        ),
    )


class AthleteInsightListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AthleteInsightOut]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Runs por atleta
# ---------------------------------------------------------------------------


class AthleteRunOut(BaseModel):
    """Item del historial de runs del agente para un atleta.

    Exponemos sólo ``external_run_id`` (UUID hex) como ``run_id`` —
    la PK BigInt interna NO viaja.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1, max_length=64)
    status: AthleteRunStatus
    season: Optional[int] = Field(default=None, ge=2020, le=2100)
    valida_nums: Optional[list[int]] = Field(default=None)
    started_at: datetime
    finished_at: Optional[datetime] = None
    explain_mode: bool = False
    has_output: bool = Field(
        ...,
        description="True si ``final_output_json`` está poblado (run completo).",
    )


class AthleteRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AthleteRunOut]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)


class AthleteStartRunBody(BaseModel):
    """Body para ``POST /athletes/{id}/race-analysis/runs``.

    A diferencia de :class:`app.schemas.race_ai.StartRunRequest` NO viene
    ``athlete_id`` — se toma del path. ``valida_nums`` opcional.
    """

    model_config = ConfigDict(extra="forbid")

    season: int = Field(..., ge=2020, le=2100)
    valida_nums: Optional[list[int]] = Field(
        default=None,
        max_length=12,
    )
    # Ancla explícita por evento (feature 014, guard cup vs championship): cuando
    # el lanzamiento nace de una competición concreta, el frontend envía
    # ``event_id`` para evitar la ambigüedad de ``valida_num`` (un mismo
    # ``sequence_number`` puede pertenecer a copa y a campeonato en la temporada).
    event_id: Optional[int] = Field(default=None, ge=1)
    explain_mode: bool = False


# ---------------------------------------------------------------------------
# Analytics — evolution y distribution
# ---------------------------------------------------------------------------


class EvolutionPoint(BaseModel):
    """Un punto en la serie cronológica de una métrica."""

    model_config = ConfigDict(extra="forbid")

    valida_num: int = Field(
        ...,
        ge=0,
        le=99,
        description=(
            "Número de válida (back-compat). Preferir ``event_id`` como "
            "identidad estable del evento. Mantenido para compatibilidad con clientes existentes."
        ),
    )
    event_id: int = Field(..., ge=1)
    event_date: date
    value: Optional[float] = Field(
        default=None,
        description=(
            "Valor de la métrica. NULL si el atleta no participó o no "
            "finalizó (DNF/DNS/DSQ)."
        ),
    )
    unit: str = Field(..., max_length=16)
    series_kind: Literal["cup", "championship"] = Field(
        ...,
        description=(
            "Tipo de serie a la que pertenece el evento. "
            "``'cup'`` = Copa (válidas regulares del calendario). "
            "``'championship'`` = Campeonato (Cto. Departamental u otro título). "
            "Serializa como string; nunca expone el enum interno."
        ),
    )
    # ``label`` se construye en el servidor mediante ``build_race_label``.
    # El frontend NO debe re-derivar la identidad del evento a partir de
    # ``valida_num`` — este campo es la fuente de verdad para mostrar al usuario.
    label: str = Field(
        ...,
        min_length=1,
        description=(
            "Etiqueta legible del evento, construida por el servidor "
            "vía ``build_race_label``. Ejemplo: ``'Válida 2 — Ginebra'`` o "
            "``'Cto. Dep. — Ginebra'``. Nunca re-derivar desde el frontend."
        ),
    )


class EvolutionResponse(BaseModel):
    """Respuesta de ``GET /evolution`` — serie temporal por temporada."""

    model_config = ConfigDict(extra="forbid")

    season: int = Field(..., ge=2020, le=2100)
    metric: EvolutionMetric
    series: list[EvolutionPoint] = Field(default_factory=list)
    confidence: AnalysisConfidence


class DistributionPoint(BaseModel):
    """Un punto observado en la distribución de tiempos por categoría.

    ``pseudonym`` siempre presente — identificador determinístico no
    reversible por temporada. ``display_name`` solo viene poblado cuando
    el llamador es coach o admin (``include_display_name=True`` en el
    servicio); para rol parent permanece ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    pseudonym: str = Field(..., min_length=2, max_length=16)
    time_ms: int = Field(..., ge=0)
    is_self: bool = False
    display_name: Optional[str] = Field(
        default=None,
        description=(
            "Nombre real del corredor (fuente: PDF federativo público). "
            "Solo presente para coach/admin. Siempre None para parent."
        ),
    )


class DistributionCurvePoint(BaseModel):
    """Punto de la curva normal teórica fitteada sobre la distribución."""

    model_config = ConfigDict(extra="forbid")

    x_ms: float = Field(..., ge=0.0)
    density: float = Field(..., ge=0.0)


class DistributionResponse(BaseModel):
    """Respuesta de ``GET /distribution`` — histograma + curva + z-score.

    Si ``sample_size < 5`` la API NO ajusta curva normal (``curve=[]``,
    ``confidence="low"``); el cliente debe caer a tabla de tiempos. Los
    ``points`` (pseudonimizados) vienen siempre poblados para n≥1.

    ``display_name`` en cada :class:`DistributionPoint` solo viene
    poblado para coach/admin — el router lo activa según el rol del
    usuario autenticado. Para parent permanece ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    season: int = Field(..., ge=2020, le=2100)
    event_id: int = Field(
        ...,
        ge=1,
        description=(
            "Identificador estable del evento de competencia (PK de race_events). "
            "Reemplaza a valida_num como identidad de carrera en la distribución."
        ),
    )
    category_id: int = Field(..., ge=1)
    category_code: str = Field(..., min_length=1, max_length=32)
    sample_size: int = Field(..., ge=0)
    mean_ms: Optional[float] = Field(default=None, ge=0.0)
    stddev_ms: Optional[float] = Field(default=None, ge=0.0)
    athlete_time_ms: Optional[int] = Field(default=None, ge=0)
    athlete_z_score: Optional[float] = None
    athlete_percentile: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    points: list[DistributionPoint] = Field(default_factory=list)
    curve: list[DistributionCurvePoint] = Field(default_factory=list)
    confidence: AnalysisConfidence


# ---------------------------------------------------------------------------
# Participación en carreras — selector de evento (feature 016)
# ---------------------------------------------------------------------------


class RaceParticipationOption(BaseModel):
    """Evento de competencia en el que el atleta participó.

    Privacidad (CLAUDE.md §Privacidad):
    - NO contiene ``athlete_id``, ``competitor_id`` ni ningún identificador
      de menor. ``event_name`` y ``location`` son datos federativos públicos
      (publicados por la Federación), no PII del deportista.
    - El llamador ya conoce al atleta por la ruta ``/athletes/{id}/...``.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: int = Field(..., ge=1, description="PK estable del evento (race_events).")
    sequence_number: int = Field(
        ...,
        ge=1,
        le=99,
        description=(
            "Número de ronda/válida. Informativo — usar ``event_id`` como "
            "identidad estable. Para campeonatos siempre es ``1``."
        ),
    )
    series_kind: Literal["cup", "championship"] = Field(
        ...,
        description=(
            "Tipo de serie. ``'cup'`` = Copa (válidas regulares). "
            "``'championship'`` = Campeonato departamental u otro título. "
            "Serializa como string; nunca expone el enum interno."
        ),
    )
    event_date: date = Field(..., description="Fecha de la competencia.")
    event_name: str = Field(
        ...,
        min_length=1,
        description="Nombre público del evento (fuente: federación).",
    )
    location: str | None = Field(
        default=None,
        description="Ciudad sede del evento. Nulo si no está disponible.",
    )
    label: str = Field(
        ...,
        min_length=1,
        description=(
            "Etiqueta legible construida por el servidor vía ``build_race_label``. "
            "Ejemplo: ``'Válida 2 — Ginebra'`` o ``'Cto. Dep. — Ginebra'``. "
            "El frontend NO debe re-derivar esta etiqueta."
        ),
    )


class RaceParticipationResponse(BaseModel):
    """Respuesta del endpoint ``GET /athletes/{id}/race-analysis/races``.

    Lista los eventos en los que el atleta compitió durante la temporada,
    ordenados por ``event_date`` ascendente. Solo incluye carreras con
    participación efectiva (excluye eventos sin resultado registrado).

    Privacidad: no contiene ningún identificador personal del atleta —
    ver :class:`RaceParticipationOption` para el detalle por evento.
    """

    model_config = ConfigDict(extra="forbid")

    season: int = Field(..., ge=2020, le=2100, description="Temporada consultada.")
    items: list[RaceParticipationOption] = Field(
        default_factory=list,
        description=(
            "Eventos con participación real del atleta, ordenados por "
            "``event_date`` ascendente."
        ),
    )


# ---------------------------------------------------------------------------
# Club insights por válida — vista agregada (Sprint 3)
# ---------------------------------------------------------------------------


class ClubInsightByRaceItem(BaseModel):
    """Item de un atleta del club en la vista agregada por válida.

    Privacidad (CLAUDE.md §Privacidad):
    - ``athlete_display_name``: enmascarado para caller rol=parent si el
      atleta no es hijo suyo. Formato: ``"[Atleta del club]"``.
    - ``summary_excerpt``: solo presente para coach/admin o para el hijo
      propio del parent. Para otros atletas del club: ``None``.
    - ``confidence``: NUNCA exponer a parent. Solo coach/admin.
    - No se expone ``athlete_id`` directamente — el frontend que necesite
      navegar al detalle del atleta lo obtiene del campo ``athlete_id``
      únicamente si es coach/admin; para parent se omite.
    """

    model_config = ConfigDict(extra="forbid")

    athlete_id: int = Field(
        ...,
        ge=0,
        description=(
            "PK del atleta. 0 indica item enmascarado (atleta ajeno a parent) — "
            "el frontend no debe intentar navegar al detalle de ese atleta."
        ),
    )
    athlete_display_name: str = Field(
        ...,
        description=(
            "Nombre completo del atleta (coach/admin). "
            "Nombre propio si es hijo del caller (parent). "
            "``'[Atleta del club]'`` para otros atletas (parent)."
        ),
    )
    valida_num: Optional[int] = Field(default=None, ge=0, le=99)
    insight_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="PK del insight activo aprobado. None si no tiene análisis.",
    )
    summary_excerpt: Optional[str] = Field(
        default=None,
        max_length=200,
        description=(
            "Primeras 200 chars del summary_text del insight activo. "
            "None si no hay insight o si caller es parent y el atleta no es su hijo."
        ),
    )
    generated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp de generación del insight. None si no hay insight.",
    )
    confidence: Optional[InsightConfidence] = Field(
        default=None,
        description=(
            "Confianza del insight. Solo presente para coach/admin. "
            "Siempre None para parent (Ley 1581)."
        ),
    )


class ClubInsightsByRaceResponse(BaseModel):
    """Respuesta del endpoint ``GET /api/races/{race_event_id}/club-insights``.

    Lista todos los atletas del club que corrieron la válida, cada uno con
    su insight activo aprobado más reciente (si existe). El endpoint soporta
    vista filtrada por RBAC según el rol del caller.
    """

    model_config = ConfigDict(extra="forbid")

    race_event_id: int = Field(..., ge=1)
    race_event_label: str = Field(
        ...,
        description=(
            "Etiqueta legible del evento. "
            "Formato: ``'Válida {N} — {location} {date}'`` o ``'{name} {date}'``."
        ),
    )
    total_athletes: int = Field(..., ge=0)
    items: list[ClubInsightByRaceItem]


# ---------------------------------------------------------------------------
# Race analysis v2 — resumen de temporada on-demand
# ---------------------------------------------------------------------------


class SeasonSummaryRequest(BaseModel):
    """Body para ``POST /athletes/{id}/race-analysis/season-summary``.

    ``season`` opcional: si se omite usa el año actual UTC. El endpoint
    verifica que existan ≥3 válidas analizadas (insights activos aprobados)
    antes de proceder. ``explain_mode`` activa el modo aprendizaje activo
    en el prompt v2.
    """

    model_config = ConfigDict(extra="forbid")

    season: int | None = Field(default=None, ge=2020, le=2100)
    explain_mode: bool = False


class SeasonSummaryResponse(BaseModel):
    """Respuesta del endpoint ``POST /race-analysis/season-summary``.

    ``insight_id`` es la PK del insight persistido (``valida_num=0``).
    ``summary_text`` es el texto completo del resumen (≤5000 chars).
    ``prompt_version`` siempre ``"race_analyst_v2"`` cuando se usa este
    endpoint.
    ``validas_analyzed`` es el número de válidas que alimentaron el resumen
    (≥3 requeridas).
    """

    model_config = ConfigDict(extra="forbid")

    insight_id: int = Field(..., ge=1)
    season: int = Field(..., ge=2020, le=2100)
    summary_text: str
    prompt_version: str = Field(..., max_length=32)
    generated_at: datetime
    validas_analyzed: int = Field(
        ...,
        ge=3,
        description="Número de válidas que alimentaron el resumen (≥3 requeridas).",
    )
