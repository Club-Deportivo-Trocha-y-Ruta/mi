from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models.training_session import AttendanceStatus, SessionStatus


# ---------------------------------------------------------------------------
# Sesión de entrenamiento
# ---------------------------------------------------------------------------


class TrainingSessionCreate(BaseModel):
    """Payload para crear una sesión planificada."""

    scheduled_date: date
    scheduled_start_time: time
    duration_min: int = Field(ge=15, le=240)
    location: str = Field(max_length=200)
    technical_focus: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    route_text: str | None = Field(default=None, max_length=500)
    strava_url: HttpUrl | None = None
    coach_notes: str | None = Field(default=None, max_length=2000)
    convocados_athlete_ids: list[int] = Field(min_length=1)

    @field_validator("strava_url", mode="before")
    @classmethod
    def validate_strava_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        if not re.match(r"^https://www\.strava\.com/activities/\d+$", str(v)):
            raise ValueError(
                "La URL de Strava debe tener el formato "
                "https://www.strava.com/activities/<id>"
            )
        return v


class TrainingSessionUpdate(BaseModel):
    """Payload parcial para actualizar campos de una sesión."""

    scheduled_date: date | None = None
    scheduled_start_time: time | None = None
    duration_min: int | None = Field(default=None, ge=15, le=240)
    location: str | None = Field(default=None, max_length=200)
    technical_focus: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    route_text: str | None = Field(default=None, max_length=500)
    strava_url: HttpUrl | None = None
    coach_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("strava_url", mode="before")
    @classmethod
    def validate_strava_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        if not re.match(r"^https://www\.strava\.com/activities/\d+$", str(v)):
            raise ValueError(
                "La URL de Strava debe tener el formato "
                "https://www.strava.com/activities/<id>"
            )
        return v


class AttendanceSummary(BaseModel):
    """Resumen de conteo de asistencia para incluir en la respuesta de sesión."""

    total: int
    presentes: int
    ausentes: int
    justificados: int
    tardes: int
    lesionados: int


class KidAttendance(BaseModel):
    """Asistencia mínima de un atleta del padre, para vista padre."""

    athlete_id: int
    status: AttendanceStatus


class TrainingSessionRead(BaseModel):
    """Respuesta completa de una sesión de entrenamiento."""

    id: int
    club_id: int
    created_by_user_id: int
    status: SessionStatus
    scheduled_date: date
    scheduled_start_time: time
    duration_min: int
    location: str
    technical_focus: str
    description: str | None
    route_text: str | None
    strava_url: str | None
    route_file_path: str | None
    coach_notes: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    attendance_summary: AttendanceSummary | None = None
    kid_attendances: list[KidAttendance] | None = None

    model_config = {"from_attributes": True}


class TrainingSessionReadParent(BaseModel):
    """Respuesta de sesión para padres — omite coach_notes y route_file_path."""

    id: int
    club_id: int
    created_by_user_id: int
    status: SessionStatus
    scheduled_date: date
    scheduled_start_time: time
    duration_min: int
    location: str
    technical_focus: str
    description: str | None
    route_text: str | None
    strava_url: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    # Solo asistencias de los propios hijos; resumen recalculado con esos datos
    attendance_summary: AttendanceSummary | None = None
    kid_attendances: list[KidAttendance] | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Asistencia
# ---------------------------------------------------------------------------

_PRESENT_STATUSES = {AttendanceStatus.PRESENTE, AttendanceStatus.TARDE}
_ABSENT_STATUSES = {
    AttendanceStatus.AUSENTE,
    AttendanceStatus.JUSTIFICADO,
    AttendanceStatus.LESIONADO,
}


class AttendanceUpdate(BaseModel):
    """Payload para actualizar la asistencia y rúbrica de un atleta."""

    status: AttendanceStatus
    excuse_reason: str | None = Field(default=None, max_length=300)
    rpe_omni: int | None = Field(default=None, ge=0, le=10)
    rubric_effort: int | None = Field(default=None, ge=1, le=5)
    rubric_attitude: int | None = Field(default=None, ge=1, le=5)
    rubric_technique: int | None = Field(default=None, ge=1, le=5)
    individual_feedback: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "AttendanceUpdate":
        is_present = self.status in _PRESENT_STATUSES
        has_rubric = any(
            v is not None
            for v in [
                self.rpe_omni,
                self.rubric_effort,
                self.rubric_attitude,
                self.rubric_technique,
                self.individual_feedback,
            ]
        )

        if not is_present and has_rubric:
            raise ValueError(
                "La rúbrica, RPE y retroalimentación solo son válidos "
                "cuando el estado es 'presente' o 'tarde'"
            )

        if self.status in _ABSENT_STATUSES and not self.excuse_reason:
            raise ValueError(
                "Se requiere razón ('excuse_reason') cuando el estado es "
                "'ausente', 'justificado' o 'lesionado'"
            )

        return self


class AttendanceRead(BaseModel):
    """Respuesta de un registro de asistencia individual."""

    id: int
    session_id: int
    athlete_id: int
    athlete_name: str | None = None
    status: AttendanceStatus
    excuse_reason: str | None
    rpe_omni: int | None
    rubric_effort: int | None
    rubric_attitude: int | None
    rubric_technique: int | None
    individual_feedback: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AttendanceReadParent(BaseModel):
    """Respuesta de asistencia para padres — omite individual_feedback."""

    id: int
    session_id: int
    athlete_id: int
    athlete_name: str | None = None
    status: AttendanceStatus
    excuse_reason: str | None
    rpe_omni: int | None
    rubric_effort: int | None
    rubric_attitude: int | None
    rubric_technique: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Reporte mensual
# ---------------------------------------------------------------------------


class MonthlyReportCreate(BaseModel):
    """Payload para generar un reporte mensual."""

    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    coach_observations: str | None = Field(default=None, max_length=2000)
    force_regenerate: bool = False

    @model_validator(mode="after")
    def _validate_period_not_future(self) -> "MonthlyReportCreate":
        today = date.today()
        if self.year > today.year or (
            self.year == today.year and self.month >= today.month
        ):
            raise ValueError(
                "Solo se puede generar el reporte de meses ya cerrados "
                "(mes anterior o antes)"
            )
        return self


class MonthlyReportRead(BaseModel):
    """Respuesta de un reporte mensual."""

    id: int
    club_id: int
    year: int
    month: int
    ai_summary: str | None
    metrics_snapshot: dict[str, Any] | None
    coach_observations: str | None
    generated_by_user_id: int
    generated_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class ParentMonthlySummary(BaseModel):
    """Resumen mensual personalizado para el padre — solo datos de SU atleta."""

    athlete_id: int
    athlete_name: str
    count_present: int
    count_total: int
    percentage: float
    focos_técnicos: list[str]


# ---------------------------------------------------------------------------
# Métricas mensuales (también usadas por el service layer)
# ---------------------------------------------------------------------------


class AthleteAttendanceStats(BaseModel):
    """Estadísticas de asistencia para un atleta en el mes."""

    athlete_id: int
    count_present: int
    count_absent: int
    count_justified: int
    count_late: int
    count_injured: int
    total_sessions: int
    attendance_pct: float


class MonthlyMetrics(BaseModel):
    """Métricas agregadas del club para un mes dado."""

    club_id: int
    year: int
    month: int
    total_sessions_planned: int
    total_sessions_executed: int
    total_sessions_cancelled: int
    attendance_by_athlete: dict[int, AthleteAttendanceStats]
    technical_focus_list: list[str]
    avg_rpe: float | None
    avg_rubric_effort: float | None
    avg_rubric_attitude: float | None
    avg_rubric_technique: float | None
