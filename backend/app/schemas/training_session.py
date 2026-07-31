from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models.training_session import (
    AttendanceStatus,
    MonthlyReportStatus,
    SessionKind,
    SessionStatus,
)
from app.schemas.session_media import SessionMediaRead, SessionMediaReadParent


# ---------------------------------------------------------------------------
# Claves de bloque permitidas en el Informe Técnico Mensual
# ---------------------------------------------------------------------------

ALLOWED_BLOCK_KEYS: frozenset[str] = frozenset({
    "objetivo",
    "desarrollo",
    "resultados",
    "conclusiones",
    "apoyos_materiales",
    "analisis_grupo",
    "competencia",
    "plan_entrenamiento",
})


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
    session_kind: SessionKind | None = Field(
        default=None,
        description="Tipo de sesión. Si se omite, el modelo usa 'entrenamiento'.",
    )
    objectives: str | None = Field(default=None, max_length=1000)
    route_text: str | None = Field(default=None, max_length=500)
    strava_url: HttpUrl | None = None
    coach_notes: str | None = Field(default=None, max_length=2000)
    convocados_athlete_ids: list[int] = Field(min_length=1)
    send_notification: bool = Field(
        default=False,
        description="Si True, envía email a los padres de los convocados.",
    )

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
    session_kind: SessionKind | None = None
    objectives: str | None = Field(default=None, max_length=1000)
    route_text: str | None = Field(default=None, max_length=500)
    strava_url: HttpUrl | None = None
    coach_notes: str | None = Field(default=None, max_length=2000)
    send_notification: bool = Field(
        default=False,
        description="Si True, envía email a los padres avisando del cambio.",
    )

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
    """Asistencia de un atleta del padre, para vista padre.

    Incluye rúbrica y comentario individual del entrenador para permitir
    al padre ver la información de la sesión sin entrar al detalle.
    Se asume que el frontend mostrará disclaimers contextuales adecuados
    (ver `frontend/src/components/parents/ParentSessionCard.tsx`).
    """

    athlete_id: int
    status: AttendanceStatus
    excuse_reason: str | None = None
    rpe_omni: int | None = None
    rubric_effort: int | None = None
    rubric_attitude: int | None = None
    rubric_technique: int | None = None
    individual_feedback: str | None = None


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
    session_kind: SessionKind | None = None
    objectives: str | None = None
    route_text: str | None
    strava_url: str | None
    route_file_path: str | None
    coach_notes: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    attendance_summary: AttendanceSummary | None = None
    kid_attendances: list[KidAttendance] | None = None
    media: list[SessionMediaRead] = Field(default_factory=list)

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
    session_kind: SessionKind | None = None
    objectives: str | None = None
    route_text: str | None
    strava_url: str | None
    created_at: datetime
    updated_at: datetime
    executed_at: datetime | None
    # Solo asistencias de los propios hijos; resumen recalculado con esos datos
    attendance_summary: AttendanceSummary | None = None
    kid_attendances: list[KidAttendance] | None = None
    # Media filtradas por intersección con los atletas del padre
    media: list[SessionMediaReadParent] = Field(default_factory=list)

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


class AttendanceBulkSet(BaseModel):
    """Payload para bulk set de la convocatoria de una sesión."""

    athlete_ids: list[int] = Field(default_factory=list)
    send_notification: bool = Field(
        default=False,
        description="Si True, envía email a padres de atletas recién añadidos.",
    )


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
    """Respuesta de asistencia para padres.

    Incluye `individual_feedback` para que el padre lo vea inline en la lista
    de sesiones; el frontend muestra disclaimers contextuales (ver
    `frontend/src/components/parents/ParentSessionCard.tsx`).
    """

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
        # TEMPORAL (revertir tras generar el informe de julio 2026 on-demand):
        # relaja el corte de "mes>=actual" a "mes>actual" para permitir el
        # mes en curso. Bloquea igual cualquier mes realmente futuro.
        today = date.today()
        if self.year > today.year or (
            self.year == today.year and self.month > today.month
        ):
            raise ValueError(
                "Solo se puede generar el reporte de meses ya cerrados "
                "(mes anterior o antes)"
            )
        return self


# ---------------------------------------------------------------------------
# Tipos auxiliares para el Informe Técnico Mensual
# ---------------------------------------------------------------------------


class NarrativeBlock(BaseModel):
    """Bloque de narrativa IA + texto final editado por el coach.

    - ``ai_draft``: borrador generado por la IA (anonimizado, sin nombres reales).
    - ``final_text``: texto aprobado por el coach. Se inicializa igual al
      ai_draft y el coach lo puede editar antes de aprobar.
    - ``ai_model``: identificador del modelo que generó el borrador.
    - ``ai_generated_at``: timestamp de generación del borrador.

    PRIVACIDAD: este objeto NUNCA se devuelve a padres. El router aplica
    ``narrative_blocks=None`` para el rol ``parent``.
    """

    ai_draft: str | None = None
    final_text: str | None = None
    ai_model: str | None = None
    ai_generated_at: datetime | None = None


class CompetitionResultItem(BaseModel):
    """Un resultado de competencia de un atleta del club en el período.

    Los nombres de atletas aquí son intencionales: el Informe Técnico Mensual
    es un documento controlado de distribución restringida (coach/admin del club),
    no se expone a la IA ni a padres. El router asegura RBAC.
    """

    athlete_name: str
    category: str | None = None
    position: int | None = None
    points: int | None = None
    event_name: str | None = None
    event_date: date | None = None
    event_id: int = 0
    series_kind: str | None = None
    awards_points: bool = True


class MonthlyReportRead(BaseModel):
    """Respuesta de un reporte mensual.

    PRIVACIDAD:
    - ``narrative_blocks``: NUNCA enviado a padres (contiene narrativa interna
      del coach). El router establece ``narrative_blocks=None`` para ``parent``.
    - ``competition_results``: tampoco se envía a padres (contiene nombres de
      otros atletas menores). El router establece ``competition_results=None``
      para ``parent``.
    - ``athlete_names``: solo se rellena para coach/admin en el endpoint de
      detalle; siempre ``{}`` para padres (privacidad de menores ajenos).
    """

    id: int
    club_id: int
    year: int
    month: int
    ai_summary: str | None
    metrics_snapshot: dict[str, Any] | None
    coach_observations: str | None
    generated_by_user_id: int
    generated_at: datetime
    # Campos del Informe Técnico Mensual
    narrative_blocks: dict[str, NarrativeBlock] | None = None
    competition_results: list[CompetitionResultItem] | None = None
    status: MonthlyReportStatus = MonthlyReportStatus.DRAFT
    # Mapa id_atleta (str) -> "Nombre Apellido". Solo para coach/admin.
    athlete_names: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}

    @field_validator("narrative_blocks", mode="before")
    @classmethod
    def _coerce_narrative_blocks(cls, v: Any) -> Any:
        """Acepta dict o None; cualquier otro tipo (ORM JSON, MagicMock) → None."""
        if v is None or isinstance(v, dict):
            return v
        return None

    @field_validator("competition_results", mode="before")
    @classmethod
    def _coerce_competition_results(cls, v: Any) -> Any:
        """Acepta list o None; cualquier otro tipo → None."""
        if v is None or isinstance(v, list):
            return v
        return None

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        """Acepta valor de enum válido; cualquier otro (MagicMock) → draft."""
        if isinstance(v, MonthlyReportStatus):
            return v
        if isinstance(v, str) and v in (m.value for m in MonthlyReportStatus):
            return v
        return MonthlyReportStatus.DRAFT


class MonthlyReportBlocksUpdate(BaseModel):
    """Payload PATCH para que el coach edite los bloques de narrativa y/o apruebe.

    ``blocks``: dict con clave = nombre del bloque y valor = ``final_text``
    editado. Solo se aceptan claves dentro de ``ALLOWED_BLOCK_KEYS``.

    ``status``: si se pasa ``"approved"``, el reporte transiciona de draft
    a approved. Solo se permite ``draft -> approved`` (no reversión en este
    endpoint; para revertir se regenera con force_regenerate).
    """

    blocks: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Claves permitidas: objetivo, desarrollo, resultados, conclusiones, "
            "apoyos_materiales, analisis_grupo, competencia. "
            "Valor: texto final editado por el coach (max 2000 chars por bloque)."
        ),
    )
    status: MonthlyReportStatus | None = None

    @field_validator("blocks")
    @classmethod
    def _validate_block_keys(cls, v: dict[str, str]) -> dict[str, str]:
        invalid = set(v.keys()) - ALLOWED_BLOCK_KEYS
        if invalid:
            raise ValueError(
                f"Claves de bloque no permitidas: {sorted(invalid)}. "
                f"Permitidas: {sorted(ALLOWED_BLOCK_KEYS)}"
            )
        for key, text in v.items():
            if len(text) > 2000:
                raise ValueError(
                    f"El bloque '{key}' excede el máximo de 2000 caracteres."
                )
        return v


class ParentMonthlySummary(BaseModel):
    """Resumen mensual personalizado para el padre — solo datos de SU atleta.

    Incluye promedios de rúbrica y RPE para mostrar en el banner de la
    página de sesiones. Los valores son `None` si no hubo registros de rúbrica
    en el mes (sesiones canceladas, sin ejecutar, o sin rúbrica registrada).
    """

    athlete_id: int
    athlete_name: str
    count_present: int
    count_total: int
    percentage: float
    focos_técnicos: list[str]
    avg_rpe: float | None = None
    avg_rubric_effort: float | None = None
    avg_rubric_attitude: float | None = None
    avg_rubric_technique: float | None = None


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
    # SPEC 2 — promedios de rúbrica por atleta (None si no hubo registros).
    avg_rubric_effort: float | None = None
    avg_rubric_attitude: float | None = None
    avg_rubric_technique: float | None = None


class SessionDetailItem(BaseModel):
    """Detalle de una sesión individual del mes, para el Informe Técnico Mensual."""

    session_date: date
    start_time: time
    technical_focus: str
    location: str
    status: Literal["executed", "cancelled", "planned"]
    present_count: int
    attendee_total: int


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
    # SPEC 1 — datos ya recolectados que enriquecen el reporte (defaults seguros
    # para reportes antiguos cuyo snapshot no los incluye):
    # Volumen de entrenamiento (minutos). Planificado = sesiones no canceladas.
    total_minutes_planned: int = 0
    total_minutes_executed: int = 0
    avg_hours_per_week: float | None = None
    # Frecuencia de cada foco técnico (cuántas sesiones lo trabajaron).
    technical_focus_counts: dict[str, int] = Field(default_factory=dict)
    # Conteos de asistencia a nivel club por estado (presente/tarde/justificado/
    # ausente/lesionado).
    attendance_status_totals: dict[str, int] = Field(default_factory=dict)
    # SPEC 2 — detalle de sesiones del mes para la sección de plan de
    # entrenamiento del Informe Técnico Mensual (default vacío para
    # reportes antiguos cuyo snapshot no lo incluye).
    session_detail: list[SessionDetailItem] = Field(default_factory=list)
