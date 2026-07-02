from __future__ import annotations

import enum
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.calendar_event import CalendarEvent
    from app.models.club import Club
    from app.models.session_media import SessionMedia
    from app.models.strength import StrengthSessionBlock
    from app.models.technique_exercise import TechniqueSessionExercise
    from app.models.user import User


class SessionStatus(str, enum.Enum):
    PLANNED = "planned"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class AttendanceStatus(str, enum.Enum):
    PRESENTE = "presente"
    AUSENTE = "ausente"
    JUSTIFICADO = "justificado"
    TARDE = "tarde"
    LESIONADO = "lesionado"


class SessionKind(str, enum.Enum):
    ENTRENAMIENTO = "entrenamiento"
    ACTIVIDAD_CONJUNTA = "actividad_conjunta"
    SALIDA = "salida"
    OTRO = "otro"


class MonthlyReportStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"


class TrainingSession(Base):
    """Sesión de entrenamiento planificada o ejecutada por el club."""

    __tablename__ = "training_sessions"
    __table_args__ = (
        CheckConstraint(
            "duration_min BETWEEN 15 AND 240",
            name="ck_session_duration_range",
        ),
        Index("idx_training_session_club_date", "club_id", "scheduled_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=SessionStatus.PLANNED,
    )
    scheduled_date: Mapped[date] = mapped_column(nullable=False)
    scheduled_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    technical_focus: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    strava_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    route_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coach_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_kind: Mapped[SessionKind] = mapped_column(
        Enum(SessionKind, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=SessionKind.ENTRENAMIENTO,
        server_default=SessionKind.ENTRENAMIENTO.value,
    )
    objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    calendar_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("calendar_events.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # Relaciones
    club: Mapped[Club] = relationship(
        "Club",
        foreign_keys="[TrainingSession.club_id]",
    )
    creator: Mapped[User] = relationship(
        "User",
        foreign_keys="[TrainingSession.created_by_user_id]",
    )
    attendances: Mapped[list[SessionAttendance]] = relationship(
        "SessionAttendance",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    media: Mapped[list[SessionMedia]] = relationship(
        "SessionMedia",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionMedia.uploaded_at.desc()",
    )
    calendar_event: Mapped[CalendarEvent | None] = relationship(
        "CalendarEvent",
        back_populates="training_session",
        foreign_keys="[TrainingSession.calendar_event_id]",
    )
    # Feature 018 — technique session builder (selectinload in detail reads).
    technique_exercises: Mapped[list[TechniqueSessionExercise]] = relationship(
        "TechniqueSessionExercise",
        back_populates="training_session",
        cascade="all, delete-orphan",
        foreign_keys="[TechniqueSessionExercise.training_session_id]",
    )
    # Feature 021 — strength blocks attached to this session (selectinload in detail reads).
    strength_blocks: Mapped[list[StrengthSessionBlock]] = relationship(
        "StrengthSessionBlock",
        back_populates="training_session",
        cascade="all, delete-orphan",
        foreign_keys="[StrengthSessionBlock.training_session_id]",
    )


class SessionAttendance(Base):
    """Asistencia y rúbrica de un atleta en una sesión de entrenamiento."""

    __tablename__ = "session_attendance"
    __table_args__ = (
        CheckConstraint(
            "rpe_omni BETWEEN 0 AND 10 OR rpe_omni IS NULL",
            name="ck_attendance_rpe_range",
        ),
        CheckConstraint(
            "rubric_effort BETWEEN 1 AND 5 OR rubric_effort IS NULL",
            name="ck_attendance_rubric_effort_range",
        ),
        CheckConstraint(
            "rubric_attitude BETWEEN 1 AND 5 OR rubric_attitude IS NULL",
            name="ck_attendance_rubric_attitude_range",
        ),
        CheckConstraint(
            "rubric_technique BETWEEN 1 AND 5 OR rubric_technique IS NULL",
            name="ck_attendance_rubric_technique_range",
        ),
        UniqueConstraint("session_id", "athlete_id", name="uq_session_attendance"),
        Index("idx_session_attendance_athlete_created", "athlete_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False
    )
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=AttendanceStatus.AUSENTE,
    )
    excuse_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rpe_omni: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rubric_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rubric_attitude: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rubric_technique: Mapped[int | None] = mapped_column(Integer, nullable=True)
    individual_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    session: Mapped[TrainingSession] = relationship(
        "TrainingSession",
        back_populates="attendances",
        foreign_keys="[SessionAttendance.session_id]",
    )
    athlete: Mapped[Athlete] = relationship(
        "Athlete",
        foreign_keys="[SessionAttendance.athlete_id]",
    )


class MonthlyReport(Base):
    """Reporte mensual generado por IA con métricas agregadas del club."""

    __tablename__ = "monthly_reports"
    __table_args__ = (
        UniqueConstraint("club_id", "year", "month", name="uq_monthly_report_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="RESTRICT"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narrative_blocks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    competition_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[MonthlyReportStatus] = mapped_column(
        Enum(MonthlyReportStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=MonthlyReportStatus.DRAFT,
        server_default=MonthlyReportStatus.DRAFT.value,
    )
    generated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    coach_observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    club: Mapped[Club] = relationship(
        "Club",
        foreign_keys="[MonthlyReport.club_id]",
    )
    generator: Mapped[User] = relationship(
        "User",
        foreign_keys="[MonthlyReport.generated_by_user_id]",
    )
