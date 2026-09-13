"""Schemas Pydantic para los endpoints `/api/ai/*`.

Feature 042 (T042) — respuesta discriminada v1|v2
==================================================
Implementa `specs/042-traceable-growth-ai/contracts/measurement-analysis-api.md`
§2: `PHVExplanationResponse` y `AnthropometricRecordExplanationResponse` ganan
los mismos cinco campos nuevos (`schema_version`, `structured`,
`critic_verdict`, `is_fallback`, `prompt_version`, `trace_id`) — seis en
total, ver abajo — para exponer, sin romper compatibilidad, tanto una fila
de prosa libre heredada (`schema_version="v1"`, `structured=None`) como una
fila del análisis estructurado de esta feature (`schema_version="v2"`).

Colisión de nombres (data-model.md §0 — LEER ANTES DE TOCAR ESTE ARCHIVO):
`schema_version` aquí es el discriminador de *formato de fila* — el mismo
eje que `AthleteAIExplanation.schema_version` (columna DB: `NULL` legado →
API `"v1"`; `"v2"` estructurado). **No** es la versión del *payload* del
insight (`AnthropometryInsightV1.schema_version`, siempre `Literal["v1"]`
hoy, en `app/services/ai/anthro/schemas.py`) — un `AnthropometryInsightOut`
de esta API puede convivir con cualquiera de los dos ejes sin que se
confundan entre sí.

`AnthropometryInsightOut` es un espejo deliberadamente independiente de
`AnthropometryInsightV1` (no una re-exportación) para que el contrato de
la API nunca cambie de forma silenciosamente si el schema interno del
analista gana un campo propio de uso analista/crítico.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AIHealthResponse(BaseModel):
    """Respuesta del endpoint de salud de la capa de IA."""

    enabled: bool
    provider: str
    model: str


class AIStatusResponse(BaseModel):
    """Respuesta de `GET /api/ai/status` (feature 033, pre-launch hint).

    Read-model puramente informativo para que el frontend muestre un
    hint ANTES del click de lanzar un análisis (presupuesto/backpressure),
    en vez de solo reaccionar a un 503/429 después del intento. No expone
    identificadores de atletas ni ningún dato personal — solo agregados
    de costo/latencia/capacidad ya usados por `admin_ai_usage()`/`check_budget()`.
    """

    budget_status: Literal["ok", "warning", "exhausted"]
    budget_remaining_pct: int = Field(..., ge=0, le=100)
    concurrency_available: bool
    est_wait_seconds: int = Field(..., ge=0)


class ConfidenceOut(BaseModel):
    """Confianza declarada del análisis estructurado (v2) — nivel + razón breve.

    Espejo de `app.services.ai.anthro.schemas.Confidence` para el cable de la
    API (ver nota de independencia deliberada en el docstring del módulo).
    """

    model_config = ConfigDict(extra="forbid")

    level: Literal["high", "medium", "low"]
    reason: str


class AnthropometryInsightOut(BaseModel):
    """Espejo de `AnthropometryInsightV1` para el cable de la API (§2 del contrato).

    Mantenido como clase Pydantic separada — nunca una re-exportación — para
    que el contrato de la API no cambie de forma silenciosamente si el
    schema interno del analista (`app/services/ai/anthro/schemas.py`) gana
    un campo propio de uso analista/crítico. `None` (campo completo ausente,
    no esta clase) en la respuesta cuando `schema_version="v1"`; siempre
    poblado cuando `schema_version="v2"`, incluidas las filas
    `critic_verdict="fallback"` (la plantilla determinista es, ella misma,
    un `AnthropometryInsightV1` válido — data-model.md §3).
    """

    model_config = ConfigDict(extra="forbid")

    summary_line: str
    changes: list[str]
    meaning: list[str]
    next_weeks: list[str]
    warning_signs: list[str]
    confidence: ConfidenceOut
    data_gaps: list[str]

    @classmethod
    def from_stored(cls, payload: dict) -> "AnthropometryInsightOut":
        """Proyecta una fila `structured_json` sobre los campos del cable.

        `structured_json` guarda el `AnthropometryInsightV1` COMPLETO
        (`data-model.md` §1), que incluye tres campos que este espejo excluye
        a propósito: `schema_version` (versión del payload, distinta del
        discriminador de fila — §0), `audience` (ya implícito en quién pide) y
        `word_count` (telemetría del modelo, nunca confiable). Con
        `extra="forbid"`, validar el dict crudo reventaría en TODA fila v2.

        La proyección es explícita, campo por campo, a propósito: si el schema
        interno del analista gana un campo nuevo, este cable NO lo expone solo
        por existir — hay que agregarlo aquí a mano. Ese era el motivo de
        `extra="forbid"`, y se conserva; lo que cambia es que el desajuste
        esperado deja de ser un error y el inesperado (un campo del cable que
        falta en lo guardado) sigue reventando.
        """
        return cls.model_validate(
            {name: payload[name] for name in cls.model_fields if name in payload}
        )


class PHVExplanationResponse(BaseModel):
    """Texto generado por el análisis PHV (feature 042: `anthro.pipeline.run_analysis`;
    filas heredadas de `PHVExplainerUseCase` siguen renderizando como `schema_version="v1"`).
    """

    text: str = Field(..., description="Explicación lista para enviar al padre.")
    model: str
    provider: str
    generated_at: datetime
    age_group: str
    maturation_status: str

    # --- Feature 042 (T042), contracts/measurement-analysis-api.md §2 -----
    #: Discriminador de *formato de fila* — ver la nota de colisión del
    #: docstring del módulo. Una fila heredada (`AthleteAIExplanation.
    #: schema_version IS NULL`) SIEMPRE se expone aquí como `"v1"`, nunca
    #: como `NULL`/`None` — invariante de compatibilidad (FR-026).
    schema_version: Literal["v1", "v2"] = "v1"
    #: `None` para `schema_version="v1"`; siempre poblado para `"v2"`.
    structured: AnthropometryInsightOut | None = None
    #: Los cinco valores persistidos del estado de revisión (data-model.md
    #: §3). `None` para una fila `"v1"` (nunca pasó por el crítico).
    critic_verdict: (
        Literal["approved", "revised", "flagged", "fallback", "skipped"] | None
    ) = None
    #: Atajo de conveniencia — `True` exactamente cuando `critic_verdict ==
    #: "fallback"`; nunca se deriva de forma independiente.
    is_fallback: bool = False
    #: `AI_ANTHRO_PROMPT_VERSION` vigente en la generación (`None` en `"v1"`).
    prompt_version: str | None = None
    #: Solo coach/admin (§4 del contrato); `None` para un padre, en
    #: producción (Langfuse deshabilitado por diseño) o si la corrida no
    #: llegó a abrir su span de traza (p. ej. un fallback temprano).
    trace_id: str | None = None


class AnthropometricRecordExplanationResponse(BaseModel):
    """Análisis particular por medición (feature 042: `anthro.pipeline.run_analysis`;
    filas heredadas de `AnthropometricRecordExplainerUseCase` siguen
    renderizando como `schema_version="v1"`).

    Adiciona campos derivados del análisis particular para que el frontend
    pueda renderizar un resumen del delta antes del texto completo.
    """

    text: str = Field(..., description="Explicación lista para enviar al padre.")
    model: str
    provider: str
    generated_at: datetime
    age_group: str
    maturation_status: str
    record_id: int
    num_previous_measurements: int
    delta_height_cm: float | None = None
    delta_weight_kg: float | None = None

    # --- Feature 042 (T042), contracts/measurement-analysis-api.md §2 -----
    # Mismos seis campos y mismo significado que `PHVExplanationResponse`
    # arriba — ver esa clase para el docstring completo de cada uno; no se
    # reexplican aquí para no arriesgar que las dos copias diverjan.
    schema_version: Literal["v1", "v2"] = "v1"
    structured: AnthropometryInsightOut | None = None
    critic_verdict: (
        Literal["approved", "revised", "flagged", "fallback", "skipped"] | None
    ) = None
    is_fallback: bool = False
    prompt_version: str | None = None
    trace_id: str | None = None
