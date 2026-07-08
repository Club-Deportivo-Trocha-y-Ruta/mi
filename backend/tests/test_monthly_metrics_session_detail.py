"""
Tests T013 (specs/022-align-monthly-report-format) — agregación de
``session_detail`` en ``compute_monthly_metrics``.

Cubre:
1. Happy path: 3 sesiones ejecutadas -> 3 filas de session_detail con
   session_date/start_time/technical_focus/location/status="executed"/
   present_count/attendee_total correctos.
2. Edge: una sesión cancelada aparece con status="cancelled".
3. Edge: un atleta sin asistencia (0) o con status=lesionado no rompe los
   totales de present_count/attendee_total.

NOTA: al momento de escribir este test, ``compute_monthly_metrics`` todavía
no puebla ``session_detail`` (tarea T016 pendiente) — se espera que estos
tests FALLEN hasta que T016 se implemente.
"""

from __future__ import annotations

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.services.training import metrics as metrics_svc


def _make_mock_session(
    session_id: int,
    status: SessionStatus,
    technical_focus: str = "Descenso técnico",
    duration_min: int = 90,
    scheduled_date: date | None = None,
    scheduled_start_time: time | None = None,
    location: str = "Bosque Municipal",
) -> MagicMock:
    s = MagicMock(spec=TrainingSession)
    s.id = session_id
    s.status = status
    s.technical_focus = technical_focus
    s.duration_min = duration_min
    s.scheduled_date = scheduled_date or date(2026, 3, session_id)
    s.scheduled_start_time = scheduled_start_time or time(17, 0)
    s.location = location
    return s


def _make_mock_attendance(
    att_id: int,
    session_id: int,
    athlete_id: int,
    status: AttendanceStatus,
) -> MagicMock:
    a = MagicMock(spec=SessionAttendance)
    a.id = att_id
    a.session_id = session_id
    a.athlete_id = athlete_id
    a.status = status
    a.rpe_omni = None
    a.rubric_effort = None
    a.rubric_attitude = None
    a.rubric_technique = None
    return a


def _make_db(sessions_data: list, attendances_data: list) -> AsyncMock:
    call_count = 0

    async def execute_side(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=sessions_data))
            )
        else:
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=attendances_data))
            )
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute_side)
    return db


class TestSessionDetailAggregation:
    async def test_tres_sesiones_ejecutadas_generan_session_detail_correcto(self):
        sessions_data = [
            _make_mock_session(
                1,
                SessionStatus.EXECUTED,
                technical_focus="Descenso técnico",
                scheduled_date=date(2026, 3, 3),
                scheduled_start_time=time(17, 0),
                location="Bosque Municipal",
            ),
            _make_mock_session(
                2,
                SessionStatus.EXECUTED,
                technical_focus="Pedaleo en pelotón",
                scheduled_date=date(2026, 3, 10),
                scheduled_start_time=time(16, 30),
                location="Pista Panamericana",
            ),
            _make_mock_session(
                3,
                SessionStatus.EXECUTED,
                technical_focus="Salto y equilibrio",
                scheduled_date=date(2026, 3, 17),
                scheduled_start_time=time(17, 0),
                location="Bosque Municipal",
            ),
        ]
        attendances_data = [
            # Sesión 1: 2 presentes, 1 ausente -> present_count=2, total=3
            _make_mock_attendance(1, 1, 100, AttendanceStatus.PRESENTE),
            _make_mock_attendance(2, 1, 101, AttendanceStatus.TARDE),
            _make_mock_attendance(3, 1, 102, AttendanceStatus.AUSENTE),
            # Sesión 2: 3 presentes -> present_count=3, total=3
            _make_mock_attendance(4, 2, 100, AttendanceStatus.PRESENTE),
            _make_mock_attendance(5, 2, 101, AttendanceStatus.PRESENTE),
            _make_mock_attendance(6, 2, 102, AttendanceStatus.PRESENTE),
            # Sesión 3: 1 presente, 1 justificado -> present_count=1, total=2
            _make_mock_attendance(7, 3, 100, AttendanceStatus.PRESENTE),
            _make_mock_attendance(8, 3, 101, AttendanceStatus.JUSTIFICADO),
        ]

        db = _make_db(sessions_data, attendances_data)

        metrics = await metrics_svc.compute_monthly_metrics(
            db, club_id=1, year=2026, month=3
        )

        assert hasattr(metrics, "session_detail")
        assert len(metrics.session_detail) == 3

        # Orden ascendente por session_date, start_time
        detail_by_id = {}
        for idx, item in enumerate(metrics.session_detail):
            detail_by_id[idx] = item

        row_1 = metrics.session_detail[0]
        assert row_1.session_date == date(2026, 3, 3)
        assert row_1.start_time == time(17, 0)
        assert row_1.technical_focus == "Descenso técnico"
        assert row_1.location == "Bosque Municipal"
        assert row_1.status == "executed"
        assert row_1.present_count == 2
        assert row_1.attendee_total == 3

        row_2 = metrics.session_detail[1]
        assert row_2.session_date == date(2026, 3, 10)
        assert row_2.start_time == time(16, 30)
        assert row_2.technical_focus == "Pedaleo en pelotón"
        assert row_2.location == "Pista Panamericana"
        assert row_2.status == "executed"
        assert row_2.present_count == 3
        assert row_2.attendee_total == 3

        row_3 = metrics.session_detail[2]
        assert row_3.session_date == date(2026, 3, 17)
        assert row_3.start_time == time(17, 0)
        assert row_3.technical_focus == "Salto y equilibrio"
        assert row_3.location == "Bosque Municipal"
        assert row_3.status == "executed"
        assert row_3.present_count == 1
        assert row_3.attendee_total == 2

    async def test_sesion_cancelada_aparece_con_status_cancelled(self):
        sessions_data = [
            _make_mock_session(
                1,
                SessionStatus.CANCELLED,
                technical_focus="Resistencia aeróbica",
                scheduled_date=date(2026, 3, 5),
                scheduled_start_time=time(16, 0),
                location="Sede Club",
            ),
        ]
        # Sesión cancelada — no hay registros de asistencia esperados,
        # pero el servicio debe seguir sin romperse.
        attendances_data: list = []

        db = _make_db(sessions_data, attendances_data)

        metrics = await metrics_svc.compute_monthly_metrics(
            db, club_id=1, year=2026, month=3
        )

        assert len(metrics.session_detail) == 1
        row = metrics.session_detail[0]
        assert row.status == "cancelled"
        assert row.session_date == date(2026, 3, 5)
        assert row.technical_focus == "Resistencia aeróbica"
        assert row.present_count == 0
        assert row.attendee_total == 0

    async def test_atleta_sin_asistencia_o_lesionado_no_rompe_totales(self):
        sessions_data = [
            _make_mock_session(
                1,
                SessionStatus.EXECUTED,
                technical_focus="Técnica de frenado",
                scheduled_date=date(2026, 3, 12),
                scheduled_start_time=time(17, 0),
                location="Bosque Municipal",
            ),
        ]
        attendances_data = [
            _make_mock_attendance(1, 1, 100, AttendanceStatus.PRESENTE),
            # Atleta lesionado: cuenta en attendee_total pero no en present_count
            _make_mock_attendance(2, 1, 101, AttendanceStatus.LESIONADO),
        ]

        db = _make_db(sessions_data, attendances_data)

        metrics = await metrics_svc.compute_monthly_metrics(
            db, club_id=1, year=2026, month=3
        )

        assert len(metrics.session_detail) == 1
        row = metrics.session_detail[0]
        assert row.status == "executed"
        assert row.present_count == 1
        assert row.attendee_total == 2

        # El agregado por atleta tampoco debe romperse: el lesionado sigue
        # contando en total_sessions sin ser presente/tarde.
        assert metrics.attendance_by_athlete[101].count_injured == 1
        assert metrics.attendance_by_athlete[101].total_sessions == 1

    async def test_sin_sesiones_retorna_session_detail_vacio(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=result_mock)

        metrics = await metrics_svc.compute_monthly_metrics(
            db, club_id=1, year=2026, month=2
        )

        assert metrics.session_detail == []
