"""Schemas Pydantic para los endpoints `/api/ai/*`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIHealthResponse(BaseModel):
    """Respuesta del endpoint de salud de la capa de IA."""

    enabled: bool
    provider: str
    model: str


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
