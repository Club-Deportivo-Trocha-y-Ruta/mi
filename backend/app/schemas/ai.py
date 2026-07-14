"""Schemas Pydantic para los endpoints `/api/ai/*`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class PHVExplanationResponse(BaseModel):
    """Texto generado por `PHVExplainerUseCase`."""

    text: str = Field(..., description="Explicación lista para enviar al padre.")
    model: str
    provider: str
    generated_at: datetime
    age_group: str
    maturation_status: str


class AnthropometricRecordExplanationResponse(BaseModel):
    """Texto generado por `AnthropometricRecordExplainerUseCase`.

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
