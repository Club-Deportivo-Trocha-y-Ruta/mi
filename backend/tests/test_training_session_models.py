"""Tests del modelo de datos — training_sessions, session_attendance, monthly_reports.

Cubre: CRUD básico, constraints check, unique constraints, cascade/restrict FK.
Estrategia: unit tests contra modelos Pydantic + tests de validación de esquemas.
No requiere DB real: se valida comportamiento de modelos y schemas.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from app.models.training_session import (
    AgeGroup,
    AttendanceStatus,
    MonthlyReport,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.schemas.training_session import (
    AttendanceRead,
    AttendanceUpdate,
    MonthlyReportCreate,
    TrainingSessionCreate,
    TrainingSessionRead,
    TrainingSessionUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_create(**kwargs) -> TrainingSessionCreate:
    defaults = dict(
        age_group=AgeGroup.U15,
        scheduled_date=date(2030, 6, 15),
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location="Bosque Municipal",
        technical_focus="Descenso técnico",
        convocados_athlete_ids=[1, 2],
    )
    defaults.update(kwargs)
    return TrainingSessionCreate(**defaults)


# ---------------------------------------------------------------------------
# 1. Enums — valores correctos
# ---------------------------------------------------------------------------


class TestEnums:
    def test_age_group_values(self):
        assert AgeGroup.U12.value == "u12"
        assert AgeGroup.U15.value == "u15"

    def test_session_status_values(self):
        assert SessionStatus.PLANNED.value == "planned"
        assert SessionStatus.EXECUTED.value == "executed"
        assert SessionStatus.CANCELLED.value == "cancelled"

    def test_attendance_status_values(self):
        assert AttendanceStatus.PRESENTE.value == "presente"
        assert AttendanceStatus.AUSENTE.value == "ausente"
        assert AttendanceStatus.JUSTIFICADO.value == "justificado"
        assert AttendanceStatus.TARDE.value == "tarde"
        assert AttendanceStatus.LESIONADO.value == "lesionado"


# ---------------------------------------------------------------------------
# 2. TrainingSessionCreate — validación Pydantic
# ---------------------------------------------------------------------------


class TestTrainingSessionCreate:
    def test_valid_create(self):
        s = _make_session_create()
        assert s.age_group == AgeGroup.U15
        assert s.duration_min == 90

    def test_duration_min_lower_bound(self):
        s = _make_session_create(duration_min=15)
        assert s.duration_min == 15

    def test_duration_min_upper_bound(self):
        s = _make_session_create(duration_min=240)
        assert s.duration_min == 240

    def test_duration_below_15_raises(self):
        with pytest.raises(ValidationError) as exc:
            _make_session_create(duration_min=14)
        assert "duration_min" in str(exc.value)

    def test_duration_above_240_raises(self):
        with pytest.raises(ValidationError) as exc:
            _make_session_create(duration_min=241)
        assert "duration_min" in str(exc.value)

    def test_past_date_raises(self):
        with pytest.raises(ValidationError) as exc:
            _make_session_create(scheduled_date=date(2000, 1, 1))
        assert "pasada" in str(exc.value)

    def test_today_date_accepted(self):
        s = _make_session_create(scheduled_date=date.today())
        assert s.scheduled_date == date.today()

    def test_empty_convocados_raises(self):
        with pytest.raises(ValidationError):
            _make_session_create(convocados_athlete_ids=[])

    def test_invalid_strava_url_raises(self):
        with pytest.raises(ValidationError) as exc:
            _make_session_create(strava_url="https://strava.com/invalid/path")
        assert "Strava" in str(exc.value)

    def test_valid_strava_url(self):
        s = _make_session_create(strava_url="https://www.strava.com/activities/12345678")
        assert s.strava_url is not None

    def test_none_strava_url_accepted(self):
        s = _make_session_create(strava_url=None)
        assert s.strava_url is None

    def test_location_max_length(self):
        s = _make_session_create(location="A" * 200)
        assert len(s.location) == 200

    def test_location_too_long_raises(self):
        with pytest.raises(ValidationError):
            _make_session_create(location="A" * 201)

    def test_technical_focus_max_length(self):
        s = _make_session_create(technical_focus="A" * 200)
        assert len(s.technical_focus) == 200

    def test_technical_focus_too_long_raises(self):
        with pytest.raises(ValidationError):
            _make_session_create(technical_focus="A" * 201)

    def test_description_max_length(self):
        s = _make_session_create(description="A" * 2000)
        assert len(s.description) == 2000

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError):
            _make_session_create(description="A" * 2001)


# ---------------------------------------------------------------------------
# 3. TrainingSessionUpdate — validación Pydantic
# ---------------------------------------------------------------------------


class TestTrainingSessionUpdate:
    def test_all_optional(self):
        u = TrainingSessionUpdate()
        assert u.duration_min is None
        assert u.location is None

    def test_duration_must_be_in_range_if_provided(self):
        with pytest.raises(ValidationError):
            TrainingSessionUpdate(duration_min=14)
        with pytest.raises(ValidationError):
            TrainingSessionUpdate(duration_min=241)

    def test_valid_partial_update(self):
        u = TrainingSessionUpdate(location="Nuevo lugar", duration_min=60)
        assert u.location == "Nuevo lugar"
        assert u.duration_min == 60


# ---------------------------------------------------------------------------
# 4. AttendanceUpdate — validaciones de consistencia
# ---------------------------------------------------------------------------


class TestAttendanceUpdateValidation:
    def test_presente_no_rubric_valid(self):
        a = AttendanceUpdate(status=AttendanceStatus.PRESENTE)
        assert a.rpe_omni is None

    def test_presente_with_full_rubric_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rpe_omni=7,
            rubric_effort=4,
            rubric_attitude=5,
            rubric_technique=3,
            individual_feedback="Buen trabajo",
        )
        assert a.rpe_omni == 7

    def test_tarde_with_rubric_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.TARDE,
            rpe_omni=5,
            rubric_effort=3,
        )
        assert a.rubric_effort == 3

    def test_ausente_with_excuse_reason_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.AUSENTE,
            excuse_reason="Enfermedad",
        )
        assert a.excuse_reason == "Enfermedad"

    def test_ausente_without_excuse_reason_raises(self):
        with pytest.raises(ValidationError) as exc:
            AttendanceUpdate(status=AttendanceStatus.AUSENTE)
        assert "razón" in str(exc.value) or "excuse_reason" in str(exc.value)

    def test_justificado_without_excuse_reason_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.JUSTIFICADO)

    def test_justificado_with_excuse_reason_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.JUSTIFICADO,
            excuse_reason="Competencia escolar",
        )
        assert a.status == AttendanceStatus.JUSTIFICADO

    def test_lesionado_without_excuse_reason_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(status=AttendanceStatus.LESIONADO)

    def test_lesionado_with_excuse_reason_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.LESIONADO,
            excuse_reason="Lesión tobillo",
        )
        assert a.excuse_reason == "Lesión tobillo"

    def test_ausente_with_rubric_raises(self):
        with pytest.raises(ValidationError) as exc:
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Gripa",
                rpe_omni=5,
            )
        assert "rúbrica" in str(exc.value) or "rubric" in str(exc.value).lower() or "presente" in str(exc.value)

    def test_ausente_with_individual_feedback_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.AUSENTE,
                excuse_reason="Gripa",
                individual_feedback="Buen intento",
            )

    def test_rpe_omni_boundary_zero(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rpe_omni=0,
        )
        assert a.rpe_omni == 0

    def test_rpe_omni_boundary_ten(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rpe_omni=10,
        )
        assert a.rpe_omni == 10

    def test_rpe_omni_above_ten_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                rpe_omni=11,
            )

    def test_rpe_omni_below_zero_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                rpe_omni=-1,
            )

    def test_rubric_below_one_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                rubric_effort=0,
            )

    def test_rubric_above_five_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                rubric_attitude=6,
            )

    def test_rubric_one_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rubric_effort=1,
        )
        assert a.rubric_effort == 1

    def test_rubric_five_valid(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rubric_technique=5,
        )
        assert a.rubric_technique == 5

    def test_individual_feedback_max_length(self):
        a = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            individual_feedback="A" * 500,
        )
        assert len(a.individual_feedback) == 500

    def test_individual_feedback_too_long_raises(self):
        with pytest.raises(ValidationError):
            AttendanceUpdate(
                status=AttendanceStatus.PRESENTE,
                individual_feedback="A" * 501,
            )


# ---------------------------------------------------------------------------
# 5. MonthlyReportCreate — validación de período no futuro
# ---------------------------------------------------------------------------


class TestMonthlyReportCreate:
    def test_past_month_valid(self):
        mr = MonthlyReportCreate(year=2025, month=12)
        assert mr.year == 2025

    def test_future_month_raises(self):
        today = date.today()
        future_year = today.year + 1
        with pytest.raises(ValidationError) as exc:
            MonthlyReportCreate(year=future_year, month=1)
        assert "cerrados" in str(exc.value) or "futuro" in str(exc.value) or "anterior" in str(exc.value)

    def test_current_month_raises(self):
        today = date.today()
        with pytest.raises(ValidationError):
            MonthlyReportCreate(year=today.year, month=today.month)

    def test_month_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            MonthlyReportCreate(year=2025, month=13)
        with pytest.raises(ValidationError):
            MonthlyReportCreate(year=2025, month=0)

    def test_force_regenerate_default_false(self):
        mr = MonthlyReportCreate(year=2025, month=1)
        assert mr.force_regenerate is False

    def test_force_regenerate_true(self):
        mr = MonthlyReportCreate(year=2025, month=1, force_regenerate=True)
        assert mr.force_regenerate is True


# ---------------------------------------------------------------------------
# 6. Model column attributes — verificación estática de columnas y relaciones
# ---------------------------------------------------------------------------


class TestModelAttributes:
    def test_training_session_has_required_columns(self):
        cols = {c.name for c in TrainingSession.__table__.columns}
        required = {
            "id", "club_id", "created_by_user_id", "age_group", "status",
            "scheduled_date", "scheduled_start_time", "duration_min",
            "location", "technical_focus", "description", "route_text",
            "strava_url", "route_file_path", "coach_notes",
            "created_at", "updated_at", "executed_at",
        }
        assert required.issubset(cols)

    def test_session_attendance_has_required_columns(self):
        cols = {c.name for c in SessionAttendance.__table__.columns}
        required = {
            "id", "session_id", "athlete_id", "status", "excuse_reason",
            "rpe_omni", "rubric_effort", "rubric_attitude", "rubric_technique",
            "individual_feedback", "created_at", "updated_at",
        }
        assert required.issubset(cols)

    def test_monthly_report_has_required_columns(self):
        cols = {c.name for c in MonthlyReport.__table__.columns}
        required = {
            "id", "club_id", "year", "month", "ai_summary",
            "metrics_snapshot", "generated_by_user_id", "generated_at", "sent_at",
        }
        assert required.issubset(cols)

    def test_training_session_has_indexes(self):
        index_names = {idx.name for idx in TrainingSession.__table__.indexes}
        assert "idx_training_session_club_date" in index_names
        assert "idx_training_session_club_age_date" in index_names

    def test_session_attendance_has_unique_constraint(self):
        constraint_names = {
            c.name
            for c in SessionAttendance.__table__.constraints
        }
        assert "uq_session_attendance" in constraint_names

    def test_monthly_report_has_unique_constraint(self):
        constraint_names = {
            c.name for c in MonthlyReport.__table__.constraints
        }
        assert "uq_monthly_report_period" in constraint_names

    def test_session_attendance_cascade_from_session(self):
        fk = next(
            fk for fk in SessionAttendance.__table__.foreign_keys
            if "training_sessions" in fk.target_fullname
        )
        assert fk.ondelete == "CASCADE"

    def test_session_attendance_restrict_athlete(self):
        fk = next(
            fk for fk in SessionAttendance.__table__.foreign_keys
            if "athletes" in fk.target_fullname
        )
        assert fk.ondelete == "RESTRICT"

    def test_training_session_restrict_club(self):
        fk = next(
            fk for fk in TrainingSession.__table__.foreign_keys
            if "clubs" in fk.target_fullname
        )
        assert fk.ondelete == "RESTRICT"

    def test_duration_min_check_constraint_present(self):
        check_names = {
            c.name
            for c in TrainingSession.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "ck_session_duration_range" in check_names

    def test_rpe_check_constraint_present(self):
        check_names = {
            c.name
            for c in SessionAttendance.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "ck_attendance_rpe_range" in check_names

    def test_rubric_check_constraints_present(self):
        check_names = {
            c.name
            for c in SessionAttendance.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "ck_attendance_rubric_effort_range" in check_names
        assert "ck_attendance_rubric_attitude_range" in check_names
        assert "ck_attendance_rubric_technique_range" in check_names


# ---------------------------------------------------------------------------
# 7. TrainingSessionRead — from_attributes serialización
# ---------------------------------------------------------------------------


class TestTrainingSessionRead:
    def test_read_model_config(self):
        assert TrainingSessionRead.model_config.get("from_attributes") is True

    def test_attendance_summary_optional(self):
        r = TrainingSessionRead(
            id=1,
            club_id=1,
            created_by_user_id=1,
            age_group=AgeGroup.U15,
            status=SessionStatus.PLANNED,
            scheduled_date=date(2026, 6, 1),
            scheduled_start_time=time(8, 0),
            duration_min=60,
            location="Lugar",
            technical_focus="Foco",
            description=None,
            route_text=None,
            strava_url=None,
            route_file_path=None,
            coach_notes=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            executed_at=None,
        )
        assert r.attendance_summary is None
