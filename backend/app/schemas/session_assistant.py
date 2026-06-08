"""Schemas transitorios para el Asistente IA de sesiones.

Ningún campo de estos schemas toca la DB; todo es stateless
request/response. Los athlete_ids que llegan en el request se
descartan en el servidor después de calcular los conteos agregados
(nunca se reenvían al LLM ni se retornan al cliente).
"""

from __future__ import annotations

import enum
from datetime import date, time

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AthleteCallUpCriterion(str, enum.Enum):
    """Propuesta no-identificante del grupo convocado.

    El frontend resuelve este criterio contra el roster local para
    llenar ``convocados_athlete_ids``. Nunca se transmiten ids o nombres.
    """

    todos_convocados = "todos_convocados"
    grupo_10_12 = "grupo_10_12"
    grupo_13_15 = "grupo_13_15"
    ninguno = "ninguno"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SessionClarifyRequest(BaseModel):
    """Cuerpo del POST /clarify.

    ``selected_athlete_ids`` se usa únicamente en el servidor para
    calcular el age_mix agregado. Nunca se envía al LLM ni se registra
    en logs.
    """

    intent_text: str | None = Field(
        default=None,
        max_length=500,
        description="Descripción libre de la sesión (cualquier idioma).",
    )
    selected_athlete_ids: list[int] = Field(
        default_factory=list,
        description="IDs de atletas seleccionados (solo para calcular age_mix).",
    )


class SessionAnswer(BaseModel):
    """Una respuesta a una pregunta de clarificación retornada."""

    question_id: str = Field(
        ...,
        description="Coincide con el ``id`` de la pregunta retornada.",
    )
    selected_labels: list[str] = Field(
        default_factory=list,
        description="Etiquetas de opciones elegidas.",
    )
    other_text: str | None = Field(
        default=None,
        max_length=300,
        description="Texto libre cuando se eligió 'Otro'.",
    )


class SessionDraftRequest(BaseModel):
    """Cuerpo del POST /draft."""

    intent_text: str | None = Field(
        default=None,
        max_length=500,
    )
    selected_athlete_ids: list[int] = Field(
        default_factory=list,
    )
    answers: list[SessionAnswer] = Field(
        default_factory=list,
        description="Respuestas del coach a las preguntas de clarificación.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ClarifyOption(BaseModel):
    """Una opción de respuesta dentro de una pregunta de clarificación."""

    label: str = Field(..., min_length=1, max_length=40)
    description: str = Field(..., min_length=1, max_length=120)


class ClarifyQuestion(BaseModel):
    """Una pregunta de clarificación generada por la IA."""

    id: str = Field(..., description="Identificador estable, ej. 'q1'.")
    header: str = Field(..., min_length=1, max_length=12)
    question: str = Field(..., min_length=1, max_length=160)
    multi_select: bool = False
    allow_other: bool = False
    options: list[ClarifyOption] = Field(
        ...,
        description="2–4 opciones.",
    )

    @field_validator("options")
    @classmethod
    def _validate_options_count(cls, v: list[ClarifyOption]) -> list[ClarifyOption]:
        if len(v) < 2 or len(v) > 4:
            raise ValueError(
                f"Cada pregunta debe tener entre 2 y 4 opciones; se recibieron {len(v)}."
            )
        return v


class SessionClarifyResponse(BaseModel):
    """Respuesta del endpoint /clarify."""

    questions: list[ClarifyQuestion] = Field(
        default_factory=list,
        description="0–4 preguntas; 0 significa que el coach puede pasar directo a /draft.",
    )
    model: str = Field(..., description="ID del modelo utilizado.")

    @field_validator("questions")
    @classmethod
    def _validate_questions_count(
        cls, v: list[ClarifyQuestion]
    ) -> list[ClarifyQuestion]:
        if len(v) > 4:
            raise ValueError(
                f"La respuesta no puede contener más de 4 preguntas; se recibieron {len(v)}."
            )
        return v


class SessionDraftResponse(BaseModel):
    """Respuesta del endpoint /draft — mapea campo a campo con el wizard."""

    technical_focus: str = Field(..., min_length=1, max_length=200)
    objectives: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    duration_min: int = Field(..., ge=15, le=240)
    session_kind: str = Field(
        default="entrenamiento",
        description="Valor de SessionKind.",
    )
    location: str | None = Field(default=None, max_length=200)
    scheduled_date: date | None = None
    scheduled_start_time: time | None = None
    athlete_call_up: AthleteCallUpCriterion = AthleteCallUpCriterion.ninguno
    notes: str | None = Field(default=None, max_length=500)
    model: str = Field(..., description="ID del modelo utilizado.")

    @field_validator("session_kind")
    @classmethod
    def _validate_session_kind(cls, v: str) -> str:
        from app.models.training_session import SessionKind

        valid = {e.value for e in SessionKind}
        if v not in valid:
            raise ValueError(
                f"session_kind '{v}' inválido. Valores aceptados: {sorted(valid)}."
            )
        return v
