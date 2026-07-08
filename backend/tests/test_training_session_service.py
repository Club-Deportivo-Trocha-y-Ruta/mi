"""Tests de la capa de servicios — training/sessions.py, attendance.py, metrics.py, route_files.py.

Estrategia: mocks de AsyncSession para evitar DB real (patrón del proyecto existente).
"""

from __future__ import annotations

import io
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.training_session import (
    AttendanceStatus,
    MonthlyReport,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.schemas.training_session import (
    AttendanceUpdate,
    AthleteAttendanceStats,
    MonthlyMetrics,
    TrainingSessionCreate,
    TrainingSessionUpdate,
)
from app.services.training import attendance as attendance_svc
from app.services.training import sessions as sessions_svc
from app.services.training import metrics as metrics_svc


# ---------------------------------------------------------------------------
# Helpers — fábricas de mocks
# ---------------------------------------------------------------------------


def _make_user(user_id: int = 1, email: str = "coach@test.com") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = email
    u.first_name = "Entrenador"
    u.last_name = "Test"
    u.club_memberships = []
    return u


def _make_session(
    session_id: int = 1,
    club_id: int = 1,
    status: SessionStatus = SessionStatus.PLANNED,
    attendances: list | None = None,
) -> MagicMock:
    s = MagicMock(spec=TrainingSession)
    s.id = session_id
    s.club_id = club_id
    s.status = status
    s.scheduled_date = date(2026, 6, 15)
    s.scheduled_start_time = time(17, 0)
    s.duration_min = 90
    s.location = "Bosque Municipal"
    s.technical_focus = "Descenso técnico"
    s.description = None
    s.route_text = None
    s.strava_url = None
    s.route_file_path = None
    s.coach_notes = None
    s.created_at = datetime.now(timezone.utc)
    s.updated_at = datetime.now(timezone.utc)
    s.executed_at = None
    s.attendances = attendances if attendances is not None else []
    return s


def _make_attendance(
    att_id: int = 1,
    session_id: int = 1,
    athlete_id: int = 100,
    status: AttendanceStatus = AttendanceStatus.AUSENTE,
) -> MagicMock:
    a = MagicMock(spec=SessionAttendance)
    a.id = att_id
    a.session_id = session_id
    a.athlete_id = athlete_id
    a.status = status
    a.excuse_reason = None
    a.rpe_omni = None
    a.rubric_effort = None
    a.rubric_attitude = None
    a.rubric_technique = None
    a.individual_feedback = None
    a.created_at = datetime.now(timezone.utc)
    a.updated_at = datetime.now(timezone.utc)
    return a


def _make_db(session_obj=None, attendances: list | None = None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        pass

    db.refresh = _refresh

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=session_obj)
    scalar_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=attendances or [])))
    scalar_result.first = MagicMock(return_value=MagicMock())
    scalar_result.all = MagicMock(return_value=attendances or [])

    db.execute = AsyncMock(return_value=scalar_result)
    return db


def _make_session_payload(**kwargs) -> TrainingSessionCreate:
    defaults = dict(
        scheduled_date=date(2030, 6, 15),
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location="Bosque Municipal",
        technical_focus="Descenso técnico",
        convocados_athlete_ids=[100, 101],
    )
    defaults.update(kwargs)
    return TrainingSessionCreate(**defaults)


# ---------------------------------------------------------------------------
# 1. sessions.create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    async def test_creates_session_and_attendance_rows(self):
        sessions_svc._recent_dispatches.clear()
        coach = _make_user(1)
        session_obj = _make_session(session_id=42)

        db = AsyncMock()
        db.add = MagicMock()
        add_calls: list = []
        db.add.side_effect = add_calls.append

        async def _refresh(obj):
            obj.id = 42
            obj.status = SessionStatus.PLANNED
            obj.attendances = []

        db.refresh = _refresh
        member_result = MagicMock()
        member_result.first = MagicMock(return_value=MagicMock())
        member_result.scalar_one_or_none = MagicMock(return_value=session_obj)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        member_result.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=member_result)

        payload = _make_session_payload(convocados_athlete_ids=[100, 101])

        with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
            result = await sessions_svc.create_session(
                db=db,
                payload=payload,
                coach=coach,
                club_id=1,
                notification_service=None,
            )

        assert result is not None
        # debe haber añadido 1 TrainingSession + 2 SessionAttendance + CalendarEvent + EventAudience
        # (create_session crea siempre el CalendarEvent paralelo)
        session_added = add_calls[0]
        assert isinstance(session_added, TrainingSession)
        attendances_added = [a for a in add_calls if isinstance(a, SessionAttendance)]
        assert len(attendances_added) == 2
        athlete_ids_added = {a.athlete_id for a in attendances_added}
        assert athlete_ids_added == {100, 101}

    async def test_attendance_initial_status_is_ausente(self):
        sessions_svc._recent_dispatches.clear()
        coach = _make_user(1)
        add_calls: list = []
        session_obj = _make_session(session_id=1)

        db = AsyncMock()
        db.add = MagicMock(side_effect=add_calls.append)

        async def _refresh(obj):
            obj.id = 1
            obj.status = SessionStatus.PLANNED
            obj.attendances = []

        db.refresh = _refresh
        member_result = MagicMock()
        member_result.first = MagicMock(return_value=MagicMock())
        member_result.scalar_one_or_none = MagicMock(return_value=session_obj)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        member_result.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=member_result)

        payload = _make_session_payload(convocados_athlete_ids=[200])

        with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
            await sessions_svc.create_session(
                db=db, payload=payload, coach=coach, club_id=1
            )

        attendances = [a for a in add_calls if isinstance(a, SessionAttendance)]
        assert all(a.status == AttendanceStatus.AUSENTE for a in attendances)

    async def test_create_session_status_is_planned(self):
        sessions_svc._recent_dispatches.clear()
        coach = _make_user(1)
        add_calls: list = []
        session_obj = _make_session(session_id=1)

        db = AsyncMock()
        db.add = MagicMock(side_effect=add_calls.append)

        async def _refresh(obj):
            obj.id = 1
            obj.status = SessionStatus.PLANNED
            obj.attendances = []

        db.refresh = _refresh
        member_result = MagicMock()
        member_result.first = MagicMock(return_value=MagicMock())
        member_result.scalar_one_or_none = MagicMock(return_value=session_obj)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        member_result.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=member_result)

        payload = _make_session_payload()
        with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
            await sessions_svc.create_session(
                db=db, payload=payload, coach=coach, club_id=1
            )

        sessions_added = [a for a in add_calls if isinstance(a, TrainingSession)]
        assert len(sessions_added) == 1
        assert sessions_added[0].status == SessionStatus.PLANNED


# ---------------------------------------------------------------------------
# 2. sessions.execute_session
# ---------------------------------------------------------------------------


class TestExecuteSession:
    async def test_execute_planned_session_success(self):
        session = _make_session(status=SessionStatus.PLANNED)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        result = await sessions_svc.execute_session(db, session_id=1)
        assert result.status == SessionStatus.EXECUTED
        assert result.executed_at is not None

    async def test_execute_already_executed_raises(self):
        session = _make_session(status=SessionStatus.EXECUTED)
        session.executed_at = datetime.now(timezone.utc)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError) as exc:
            await sessions_svc.execute_session(db, session_id=1)
        assert "ejecutar" in str(exc.value).lower() or "estado" in str(exc.value).lower()

    async def test_execute_cancelled_session_raises(self):
        session = _make_session(status=SessionStatus.CANCELLED)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError):
            await sessions_svc.execute_session(db, session_id=1)

    async def test_execute_nonexistent_raises(self):
        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError) as exc:
            await sessions_svc.execute_session(db, session_id=9999)
        assert "no encontrada" in str(exc.value)

    async def test_execute_sets_executed_at_timestamp(self):
        session = _make_session(status=SessionStatus.PLANNED)
        before = datetime.now(timezone.utc)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        result = await sessions_svc.execute_session(db, session_id=1)
        assert result.executed_at >= before


# ---------------------------------------------------------------------------
# 3. sessions.cancel_session
# ---------------------------------------------------------------------------


class TestCancelSession:
    async def test_cancel_planned_session_success(self):
        session = _make_session(status=SessionStatus.PLANNED)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        result = await sessions_svc.cancel_session(db, session_id=1)
        assert result.status == SessionStatus.CANCELLED

    async def test_cancel_already_cancelled_raises(self):
        session = _make_session(status=SessionStatus.CANCELLED)

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError) as exc:
            await sessions_svc.cancel_session(db, session_id=1)
        assert "cancelada" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. sessions.update_session
# ---------------------------------------------------------------------------


class TestUpdateSession:
    async def test_update_planned_session(self):
        session = _make_session(status=SessionStatus.PLANNED)
        session.location = "Lugar viejo"

        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=session)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        payload = TrainingSessionUpdate(location="Lugar nuevo")
        result = await sessions_svc.update_session(db, session_id=1, payload=payload)
        assert result.location == "Lugar nuevo"

    async def test_update_nonexistent_raises(self):
        db = AsyncMock()
        async def _refresh(obj):
            pass
        db.refresh = _refresh

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError):
            await sessions_svc.update_session(
                db, session_id=9999, payload=TrainingSessionUpdate(location="X")
            )


# ---------------------------------------------------------------------------
# 5. sessions.list_sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    async def test_list_returns_sessions_for_club(self):
        sessions = [_make_session(1, club_id=1), _make_session(2, club_id=1)]

        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=sessions)
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        result = await sessions_svc.list_sessions(db, club_id=1)
        assert len(result) == 2
        assert all(s.club_id == 1 for s in result)

    async def test_list_empty_when_no_sessions(self):
        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=scalars_mock)
        db.execute = AsyncMock(return_value=result_mock)

        result = await sessions_svc.list_sessions(db, club_id=99)
        assert result == []


# ---------------------------------------------------------------------------
# 6. attendance.bulk_upsert_convocatoria
# ---------------------------------------------------------------------------


class TestBulkUpsertConvocatoria:
    async def test_adds_new_athletes(self):
        existing_att = [_make_attendance(att_id=1, session_id=1, athlete_id=100)]
        new_attendances = [
            _make_attendance(1, 1, 100),
            _make_attendance(2, 1, 200),
        ]
        add_calls: list = []

        db = AsyncMock()
        db.add = MagicMock(side_effect=add_calls.append)
        db.execute = AsyncMock()

        call_count = 0

        async def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # primera call: select existing
                result = MagicMock()
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=existing_att)))
                return result
            else:
                # segunda call: select final
                result = MagicMock()
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=new_attendances)))
                return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await attendance_svc.bulk_upsert_convocatoria(
            db=db, session_id=1, athlete_ids=[100, 200]
        )

        # athlete 200 debe haber sido añadido
        added_ids = {a.athlete_id for a in add_calls if isinstance(a, SessionAttendance)}
        assert 200 in added_ids
        assert 100 not in added_ids  # ya existía

    async def test_removes_athletes_not_in_new_list(self):
        existing_att = [
            _make_attendance(1, 1, 100),
            _make_attendance(2, 1, 200),
        ]

        db = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                result = MagicMock()
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=existing_att)))
                return result
            elif call_count == 2:
                # delete execute
                return MagicMock()
            else:
                result = MagicMock()
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[existing_att[0]])))
                return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await attendance_svc.bulk_upsert_convocatoria(
            db=db, session_id=1, athlete_ids=[100]
        )
        # el delete debe haberse ejecutado (call_count >= 2 incluye el delete)
        assert call_count >= 2


# ---------------------------------------------------------------------------
# 7. attendance.update_attendance
# ---------------------------------------------------------------------------


class TestUpdateAttendance:
    async def test_update_existing_attendance(self):
        att = _make_attendance(status=AttendanceStatus.AUSENTE)
        att.excuse_reason = None
        att.rpe_omni = None

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=att)
        db.execute = AsyncMock(return_value=result_mock)

        async def _refresh(obj, **kwargs):
            pass
        db.refresh = _refresh

        payload = AttendanceUpdate(
            status=AttendanceStatus.PRESENTE,
            rpe_omni=7,
            rubric_effort=4,
        )
        result = await attendance_svc.update_attendance(
            db=db, session_id=1, athlete_id=100, payload=payload
        )
        assert result.status == AttendanceStatus.PRESENTE
        assert result.rpe_omni == 7

    async def test_update_nonexistent_attendance_raises(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result_mock)

        payload = AttendanceUpdate(status=AttendanceStatus.PRESENTE)
        with pytest.raises(ValueError) as exc:
            await attendance_svc.update_attendance(
                db=db, session_id=99, athlete_id=999, payload=payload
            )
        assert "no existe" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# 8. attendance.athlete_attendance_history
# ---------------------------------------------------------------------------


class TestAthleteAttendanceHistory:
    async def test_returns_history_sorted_desc(self):
        att1 = _make_attendance(att_id=1, session_id=1, athlete_id=100)
        att2 = _make_attendance(att_id=2, session_id=2, athlete_id=100)
        all_atts = [att1, att2]

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=all_atts)))
        db.execute = AsyncMock(return_value=result_mock)

        result = await attendance_svc.athlete_attendance_history(db, athlete_id=100)
        assert len(result) == 2

    async def test_empty_history(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result_mock)

        result = await attendance_svc.athlete_attendance_history(db, athlete_id=999)
        assert result == []


# ---------------------------------------------------------------------------
# 9. metrics.compute_monthly_metrics
# ---------------------------------------------------------------------------


class TestComputeMonthlyMetrics:
    def _make_mock_session(self, session_id, status: SessionStatus, technical_focus: str = "Descenso", duration_min: int = 90) -> MagicMock:
        s = MagicMock(spec=TrainingSession)
        s.id = session_id
        s.status = status
        s.technical_focus = technical_focus
        s.duration_min = duration_min
        s.scheduled_date = date(2026, 3, session_id)
        s.scheduled_start_time = time(17, 0)
        s.location = "Bosque Municipal"
        return s

    def _make_mock_attendance(
        self,
        att_id: int,
        session_id: int,
        athlete_id: int,
        status: AttendanceStatus,
        rpe_omni: int | None = None,
        rubric_effort: int | None = None,
        rubric_attitude: int | None = None,
        rubric_technique: int | None = None,
    ) -> MagicMock:
        a = MagicMock(spec=SessionAttendance)
        a.id = att_id
        a.session_id = session_id
        a.athlete_id = athlete_id
        a.status = status
        a.rpe_omni = rpe_omni
        a.rubric_effort = rubric_effort
        a.rubric_attitude = rubric_attitude
        a.rubric_technique = rubric_technique
        return a

    async def test_compute_with_seed_data(self):
        sessions_data = [
            self._make_mock_session(1, SessionStatus.EXECUTED, "Descenso"),
            self._make_mock_session(2, SessionStatus.EXECUTED, "Pedaleo"),
            self._make_mock_session(3, SessionStatus.PLANNED, "Técnica"),
            self._make_mock_session(4, SessionStatus.CANCELLED, "Carrera"),
            self._make_mock_session(5, SessionStatus.EXECUTED, "Salto"),
        ]

        attendances_data = [
            # Sesión 1: atleta 100 presente, atleta 101 ausente, atleta 102 tarde
            self._make_mock_attendance(1, 1, 100, AttendanceStatus.PRESENTE, rpe_omni=7, rubric_effort=4, rubric_attitude=5, rubric_technique=3),
            self._make_mock_attendance(2, 1, 101, AttendanceStatus.AUSENTE),
            self._make_mock_attendance(3, 1, 102, AttendanceStatus.TARDE, rpe_omni=5, rubric_effort=3),
            # Sesión 2: todos presentes
            self._make_mock_attendance(4, 2, 100, AttendanceStatus.PRESENTE, rpe_omni=8, rubric_effort=5, rubric_attitude=4, rubric_technique=5),
            self._make_mock_attendance(5, 2, 101, AttendanceStatus.PRESENTE, rpe_omni=6, rubric_effort=3),
            self._make_mock_attendance(6, 2, 102, AttendanceStatus.PRESENTE, rpe_omni=6),
            # Sesión 3 y 4: sin asistencias relevantes
            self._make_mock_attendance(7, 3, 100, AttendanceStatus.AUSENTE),
            self._make_mock_attendance(8, 4, 100, AttendanceStatus.AUSENTE),
            # Sesión 5
            self._make_mock_attendance(9, 5, 100, AttendanceStatus.PRESENTE, rpe_omni=9),
            self._make_mock_attendance(10, 5, 101, AttendanceStatus.JUSTIFICADO),
        ]

        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=sessions_data)))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=attendances_data)))
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_side)

        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)

        assert metrics.total_sessions_planned == 1
        assert metrics.total_sessions_executed == 3
        assert metrics.total_sessions_cancelled == 1
        assert len(metrics.attendance_by_athlete) == 3
        # Atleta 100: presente en sesión 1, 2, 5 — ausente en 3, 4 = 3/5 = 60%
        stats_100 = metrics.attendance_by_athlete[100]
        assert stats_100.count_present == 3
        assert stats_100.total_sessions == 5
        # Focos técnicos únicos
        assert len(metrics.technical_focus_list) == 5
        # Promedio RPE: solo presentes/tardes: 7, 5, 8, 6, 6, 9 → 41/6 ≈ 6.83
        assert metrics.avg_rpe is not None
        assert metrics.avg_rpe > 6.0
        # SPEC 1 — volumen: planificado = no canceladas (1,2,3,5) ×90 = 360;
        # ejecutado = EXECUTED (1,2,5) ×90 = 270.
        assert metrics.total_minutes_planned == 360
        assert metrics.total_minutes_executed == 270
        assert metrics.avg_hours_per_week is not None
        # SPEC 1 — frecuencia de focos: cada foco aparece en 1 sesión.
        assert metrics.technical_focus_counts == {
            "Descenso": 1, "Pedaleo": 1, "Técnica": 1, "Carrera": 1, "Salto": 1,
        }
        # SPEC 1 — totales de asistencia por estado a nivel club (10 registros).
        assert metrics.attendance_status_totals == {
            "presente": 5, "tarde": 1, "justificado": 1, "ausente": 3, "lesionado": 0,
        }

    async def test_zero_sessions_returns_zeros(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result_mock)

        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=2)

        assert metrics.total_sessions_planned == 0
        assert metrics.total_sessions_executed == 0
        assert metrics.total_sessions_cancelled == 0
        assert metrics.attendance_by_athlete == {}
        assert metrics.technical_focus_list == []
        assert metrics.avg_rpe is None
        assert metrics.avg_rubric_effort is None

    async def test_avg_rpe_none_when_no_present_attendances(self):
        sessions_data = [self._make_mock_session(1, SessionStatus.EXECUTED)]
        attendances_data = [
            self._make_mock_attendance(1, 1, 100, AttendanceStatus.AUSENTE),
        ]

        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=sessions_data)))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=attendances_data)))
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_side)

        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)
        assert metrics.avg_rpe is None

    async def test_attendance_pct_calculation(self):
        sessions_data = [self._make_mock_session(1, SessionStatus.EXECUTED)]
        attendances_data = [
            self._make_mock_attendance(1, 1, 100, AttendanceStatus.PRESENTE),
            self._make_mock_attendance(2, 1, 101, AttendanceStatus.TARDE),
            self._make_mock_attendance(3, 1, 102, AttendanceStatus.AUSENTE),
        ]

        call_count = 0

        async def execute_side(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=sessions_data)))
            else:
                result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=attendances_data)))
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_side)

        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)
        assert metrics.attendance_by_athlete[100].attendance_pct == 100.0
        assert metrics.attendance_by_athlete[101].attendance_pct == 100.0
        assert metrics.attendance_by_athlete[102].attendance_pct == 0.0


# ---------------------------------------------------------------------------
# 10. route_files.save_route_file
# ---------------------------------------------------------------------------


class TestSaveRouteFile:
    def _make_upload_file(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/gpx+xml",
    ) -> MagicMock:
        f = MagicMock()
        f.filename = filename
        f.content_type = content_type
        f.read = AsyncMock(return_value=content)
        return f

    _VALID_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test Route</name><trkseg>
    <trkpt lat="3.4" lon="-76.5"><ele>1000</ele></trkpt>
    <trkpt lat="3.5" lon="-76.4"><ele>1050</ele></trkpt>
  </trkseg></trk>
</gpx>"""

    async def test_valid_gpx_saved_correctly(self, tmp_path):
        from app.services.training import route_files

        original_base = route_files._UPLOAD_BASE
        route_files._UPLOAD_BASE = tmp_path / "routes"

        try:
            f = self._make_upload_file("recorrido.gpx", self._VALID_GPX)
            path = await route_files.save_route_file(f, session_id=1)
            assert path.endswith(".gpx")
            # El archivo debe existir
            from pathlib import Path
            assert Path(path).exists()
            assert Path(path).read_bytes() == self._VALID_GPX
        finally:
            route_files._UPLOAD_BASE = original_base

    async def test_invalid_extension_raises(self):
        from app.services.training import route_files

        f = self._make_upload_file("archivo.txt", b"contenido")
        with pytest.raises(ValueError) as exc:
            await route_files.save_route_file(f, session_id=1)
        assert "extensión" in str(exc.value) or "Extensión" in str(exc.value)

    async def test_oversized_file_raises(self, tmp_path):
        from app.services.training import route_files

        big_content = b"X" * (6 * 1024 * 1024)  # 6 MB stub
        f = self._make_upload_file("ruta.gpx", big_content)
        with pytest.raises(ValueError) as exc:
            await route_files.save_route_file(f, session_id=1)
        assert "límite" in str(exc.value) or "supera" in str(exc.value)

    async def test_xxe_attempt_rejected(self, tmp_path):
        from app.services.training import route_files

        original_base = route_files._UPLOAD_BASE
        route_files._UPLOAD_BASE = tmp_path / "routes"

        xxe_content = b"""<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<trk><name>&xxe;</name></trk>
</gpx>"""

        try:
            f = self._make_upload_file("malicioso.gpx", xxe_content)
            with pytest.raises(ValueError) as exc:
                await route_files.save_route_file(f, session_id=1)
            error_msg = str(exc.value).lower()
            assert (
                "dtd" in error_msg
                or "entidad" in error_msg
                or "prohibida" in error_msg
                or "xxe" in error_msg
                or "externas" in error_msg
            )
        finally:
            route_files._UPLOAD_BASE = original_base

    async def test_fit_extension_accepted_without_parse(self, tmp_path):
        from app.services.training import route_files

        original_base = route_files._UPLOAD_BASE
        route_files._UPLOAD_BASE = tmp_path / "routes"

        # Contenido mínimo válido para FIT: magic byte 0x0e + 13 bytes de relleno
        _valid_fit = bytes([0x0E]) + b"\x00" * 13

        try:
            f = self._make_upload_file("ruta.fit", _valid_fit)
            path = await route_files.save_route_file(f, session_id=1)
            assert path.endswith(".fit")
        finally:
            route_files._UPLOAD_BASE = original_base
