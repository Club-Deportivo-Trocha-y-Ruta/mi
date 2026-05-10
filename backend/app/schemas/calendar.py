"""Schemas Pydantic para el módulo de calendario.

Cubre: EventCreate, EventUpdate, EventRead (coach/admin), EventReadParent,
AudienceCreate/Read, EventAttendanceRead, RSVPUpdate, EventListQuery,
EventListItem (para FullCalendar).

Los event_data usan discriminated unions por event_type.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.calendar_event import (
    ActualAttendanceStatus,
    AudienceType,
    EventStatus,
    EventType,
    RSVPStatus,
)


# ---------------------------------------------------------------------------
# Discriminated union — event_data por tipo de evento
# ---------------------------------------------------------------------------


class EventDataTrainingSession(BaseModel):
    """Payload para event_type=training_session."""

    event_type: Literal["training_session"]
    training_session_id: int | None = None


class EventDataCompetition(BaseModel):
    """Payload placeholder para event_type=competition (sin tabla satélite aún)."""

    event_type: Literal["competition"]
    city: str = Field(max_length=100)
    race_category: Literal["A", "B", "C"]
    is_departmental: bool = False


class EventDataClubEvent(BaseModel):
    """Payload para event_type=club_event."""

    event_type: Literal["club_event"]
    kind: Literal["social", "meeting", "workshop"]
    registration_url: str | None = Field(default=None, max_length=500)


class EventDataPersonalTraining(BaseModel):
    """Payload para event_type=personal_training."""

    event_type: Literal["personal_training"]
    athlete_id: int
    intensity: Literal["low", "medium", "high"]


class EventDataGroupTraining(BaseModel):
    """Payload para event_type=group_training."""

    event_type: Literal["group_training"]
    intensity: Literal["low", "medium", "high"]
    group_size_max: int | None = Field(default=None, ge=1, le=100)


class EventDataRestDay(BaseModel):
    """Payload para event_type=rest_day."""

    event_type: Literal["rest_day"]
    scope: Literal["club", "category", "athlete"]
    reason: str | None = Field(default=None, max_length=500)


# Union discriminada por el campo literal event_type dentro del payload
EventData = Annotated[
    Union[
        EventDataTrainingSession,
        EventDataCompetition,
        EventDataClubEvent,
        EventDataPersonalTraining,
        EventDataGroupTraining,
        EventDataRestDay,
    ],
    Field(discriminator="event_type"),
]


# ---------------------------------------------------------------------------
# Audiencia
# ---------------------------------------------------------------------------


class AudienceCreate(BaseModel):
    """Payload para definir una audiencia al crear/actualizar un evento."""

    audience_type: AudienceType
    audience_value: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_audience_value_shape(self) -> "AudienceCreate":
        t = self.audience_type
        v = self.audience_value
        if t == AudienceType.ALL_CLUB:
            # Debe ser vacío o no importa su contenido
            pass
        elif t == AudienceType.CATEGORY:
            if "category" not in v or not isinstance(v.get("category"), str):
                raise ValueError(
                    "audience_value debe contener {'category': str} para tipo CATEGORY"
                )
        elif t == AudienceType.ATHLETE_LIST:
            ids = v.get("athlete_ids")
            if not isinstance(ids, list) or len(ids) == 0:
                raise ValueError(
                    "audience_value debe contener {'athlete_ids': [int, ...]} "
                    "con al menos un atleta para tipo ATHLETE_LIST"
                )
            if not all(isinstance(i, int) for i in ids):
                raise ValueError("Todos los athlete_ids deben ser enteros")
        elif t == AudienceType.INDIVIDUAL:
            if "athlete_id" not in v or not isinstance(v.get("athlete_id"), int):
                raise ValueError(
                    "audience_value debe contener {'athlete_id': int} para tipo INDIVIDUAL"
                )
        return self


class AudienceRead(BaseModel):
    """Representación de audiencia en respuestas."""

    id: int
    event_id: int
    audience_type: AudienceType
    audience_value: dict[str, Any] | None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Evento — schemas base, create, update, read
# ---------------------------------------------------------------------------


class EventBase(BaseModel):
    """Campos compartidos entre create y update."""

    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=200)
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    timezone: str = Field(default="America/Bogota", max_length=50)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def _validate_range(self) -> "EventBase":
        if self.end_at < self.start_at:
            raise ValueError(
                "end_at debe ser mayor o igual que start_at"
            )
        return self


class EventCreate(EventBase):
    """Payload completo para crear un evento de calendario."""

    event_type: EventType
    status: EventStatus = EventStatus.SCHEDULED
    event_data: dict[str, Any] | None = None
    audiences: list[AudienceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_event_data_shape(self) -> "EventCreate":
        """Valida que event_data tenga la forma correcta para el event_type indicado."""
        if self.event_data is None:
            return self
        et = self.event_type
        ed = self.event_data
        if et == EventType.TRAINING_SESSION:
            EventDataTrainingSession(event_type="training_session", **{k: v for k, v in ed.items() if k != "event_type"})
        elif et == EventType.COMPETITION:
            EventDataCompetition(event_type="competition", **{k: v for k, v in ed.items() if k != "event_type"})
        elif et == EventType.CLUB_EVENT:
            EventDataClubEvent(event_type="club_event", **{k: v for k, v in ed.items() if k != "event_type"})
        elif et == EventType.PERSONAL_TRAINING:
            EventDataPersonalTraining(event_type="personal_training", **{k: v for k, v in ed.items() if k != "event_type"})
        elif et == EventType.GROUP_TRAINING:
            EventDataGroupTraining(event_type="group_training", **{k: v for k, v in ed.items() if k != "event_type"})
        elif et == EventType.REST_DAY:
            EventDataRestDay(event_type="rest_day", **{k: v for k, v in ed.items() if k != "event_type"})
        return self


class EventUpdate(BaseModel):
    """Payload parcial para actualizar un evento. Todos los campos son opcionales."""

    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    timezone: str | None = Field(default=None, max_length=50)
    status: EventStatus | None = None
    event_data: dict[str, Any] | None = None
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def _validate_range_if_both_present(self) -> "EventUpdate":
        if self.start_at is not None and self.end_at is not None:
            if self.end_at < self.start_at:
                raise ValueError(
                    "end_at debe ser mayor o igual que start_at"
                )
        return self


class EventRead(BaseModel):
    """Respuesta completa de un evento para coach/admin."""

    id: int
    club_id: int
    event_type: EventType
    status: EventStatus
    title: str
    description: str | None
    location: str | None
    start_at: datetime
    end_at: datetime
    all_day: bool
    timezone: str
    event_data: dict[str, Any] | None
    color_hex: str | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    audiences: list[AudienceRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EventReadParent(BaseModel):
    """Respuesta de evento para padres — omite created_by_user_id y audiencia interna."""

    id: int
    club_id: int
    event_type: EventType
    status: EventStatus
    title: str
    description: str | None
    location: str | None
    start_at: datetime
    end_at: datetime
    all_day: bool
    timezone: str
    color_hex: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Asistencia y RSVP
# ---------------------------------------------------------------------------


class EventAttendanceRead(BaseModel):
    """Respuesta de un registro de asistencia/RSVP a un evento."""

    id: int
    event_id: int
    athlete_id: int
    rsvp_status: RSVPStatus
    rsvp_at: datetime | None
    rsvp_by_user_id: int | None
    actual_status: ActualAttendanceStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RSVPUpdate(BaseModel):
    """Payload para registrar o actualizar el RSVP de un atleta a un evento."""

    athlete_id: int
    rsvp_status: RSVPStatus


# ---------------------------------------------------------------------------
# Queries y lista (FullCalendar)
# ---------------------------------------------------------------------------


class EventListQuery(BaseModel):
    """Parámetros de consulta para listar eventos en un rango de fechas."""

    from_date: date
    to_date: date
    event_types: list[EventType] | None = None
    athlete_id: int | None = None
    category: str | None = None
    mine_only: bool = False

    @model_validator(mode="after")
    def _validate_date_range(self) -> "EventListQuery":
        if self.to_date < self.from_date:
            raise ValueError(
                "to_date debe ser mayor o igual que from_date"
            )
        return self


class EventListItem(BaseModel):
    """Evento en formato ligero para consumo de FullCalendar.

    Campos mapeados directamente a la API de FullCalendar:
    - start / end: ISO datetime strings
    - allDay: booleano
    - extendedProps: props adicionales accesibles desde los event handlers
    """

    id: int
    title: str
    start: datetime
    end: datetime
    all_day: bool = Field(alias="allDay", default=False)
    event_type: EventType
    color_hex: str | None
    status: EventStatus
    extended_props: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
