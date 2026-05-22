from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.club import Club
    from app.models.race_event import RaceEvent
    from app.models.training_session import TrainingSession
    from app.models.user import User


class EventType(str, enum.Enum):
    TRAINING_SESSION = "training_session"
    COMPETITION = "competition"
    CLUB_EVENT = "club_event"
    PERSONAL_TRAINING = "personal_training"
    GROUP_TRAINING = "group_training"
    REST_DAY = "rest_day"
    BIRTHDAY = "birthday"


class EventStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class AudienceType(str, enum.Enum):
    ALL_CLUB = "all_club"
    CATEGORY = "category"
    ATHLETE_LIST = "athlete_list"
    INDIVIDUAL = "individual"


class RSVPStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


class ActualAttendanceStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    EXCUSED = "excused"


class CalendarEvent(Base):
    """Evento del calendario del club. Tabla polimórfica que unifica entrenamientos,
    competencias, eventos del club y días de descanso. El payload específico
    por tipo se almacena en el campo JSON event_data."""

    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint(
            "end_at >= start_at",
            name="ck_calendar_event_range",
        ),
        # Añadido en migración BE-1 ``8c1d2e3f4a5b``: si el evento es una
        # competencia, debe estar enlazado a un race_event concreto.
        # Eventos legacy quedan NULL (no se backfillea masivo).
        CheckConstraint(
            "event_type != 'competition' OR race_event_id IS NOT NULL",
            name="ck_calendar_competition_race_event",
        ),
        Index("idx_calendar_club_start", "club_id", "start_at"),
        Index("ix_calendar_events_race_event_id", "race_event_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("clubs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=EventStatus.SCHEDULED,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="America/Bogota"
    )
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # BE-1: link explícito al race_event correspondiente cuando el evento
    # es una competencia. NULL para no-competencias o legacy sin matchear.
    # Coexiste con race_events.calendar_event_id (FK inversa, SET NULL).
    # ondelete=RESTRICT obligado por MySQL: CHECK
    # ck_calendar_competition_race_event no admite columna en FK con SET NULL
    # (MySQL 8 error 3823). El coach debe desasociar antes de borrar race_event.
    race_event_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("race_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones
    club: Mapped[Club] = relationship(
        "Club",
        foreign_keys="[CalendarEvent.club_id]",
    )
    creator: Mapped[User] = relationship(
        "User",
        foreign_keys="[CalendarEvent.created_by_user_id]",
    )
    audiences: Mapped[list[EventAudience]] = relationship(
        "EventAudience",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    attendances: Mapped[list[EventAttendance]] = relationship(
        "EventAttendance",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    training_session: Mapped[TrainingSession | None] = relationship(
        "TrainingSession",
        back_populates="calendar_event",
        uselist=False,
    )
    # BE-1: link directo a la válida de carrera correspondiente.
    # No usa back_populates: race_events.calendar_event_id es la FK
    # inversa preexistente (migración 04536432643f) y se modela como
    # `RaceEvent.calendar_event` sin back_populates para evitar ciclo.
    race_event: Mapped["RaceEvent | None"] = relationship(
        "RaceEvent",
        foreign_keys="[CalendarEvent.race_event_id]",
    )


class EventAudience(Base):
    """Audiencia de un evento. Un evento puede tener múltiples filas de audiencia
    (unión): todo el club, por categoría FCC, lista de atletas, o individual."""

    __tablename__ = "event_audiences"
    __table_args__ = (
        Index("idx_audience_event", "event_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("calendar_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    audience_type: Mapped[AudienceType] = mapped_column(
        Enum(AudienceType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    audience_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relaciones
    event: Mapped[CalendarEvent] = relationship(
        "CalendarEvent",
        back_populates="audiences",
    )


class EventAttendance(Base):
    """RSVP y asistencia real de un atleta a un evento (no-training).
    Para eventos de tipo training_session se usa session_attendance."""

    __tablename__ = "event_attendances"
    __table_args__ = (
        UniqueConstraint("event_id", "athlete_id", name="uq_event_attendance"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("calendar_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    athlete_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("athletes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rsvp_status: Mapped[RSVPStatus] = mapped_column(
        Enum(RSVPStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=RSVPStatus.PENDING,
    )
    rsvp_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rsvp_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actual_status: Mapped[ActualAttendanceStatus] = mapped_column(
        Enum(ActualAttendanceStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ActualAttendanceStatus.UNKNOWN,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones
    event: Mapped[CalendarEvent] = relationship(
        "CalendarEvent",
        back_populates="attendances",
    )
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[EventAttendance.athlete_id]",
    )
    rsvp_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys="[EventAttendance.rsvp_by_user_id]",
    )
