"""
Tests T014 (specs/022-align-monthly-report-format) — Promedios de rúbrica por
atleta en `compute_monthly_metrics`.

Cubre:
1. Promedio por atleta correctamente calculado a partir de sus propias
   asistencias presentes/tarde en el período (independiente del promedio
   agregado del club).
2. `None` para un atleta sin ningún registro de rúbrica en el período.
3. Asistencias ausentes/justificadas/lesionadas no contaminan el promedio
   del atleta (invariante ya vigente para el agregado del club).

Sigue el patrón de mocks de AsyncSession usado en
`test_training_session_service.py::TestComputeMonthlyMetrics`.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.services.training import metrics as metrics_svc
from unittest.mock import AsyncMock, MagicMock


def _make_session(session_id: int, status: SessionStatus = SessionStatus.EXECUTED) -> MagicMock:
    s = MagicMock(spec=TrainingSession)
    s.id = session_id
    s.status = status
    s.technical_focus = "Descenso"
    s.duration_min = 90
    s.scheduled_date = date(2026, 3, session_id)
    s.scheduled_start_time = time(17, 0)
    s.location = "Bosque Municipal"
    return s


def _make_attendance(
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


def _make_db(sessions_data: list, attendances_data: list) -> AsyncMock:
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
    return db


class TestPerAthleteRubricAverages:
    async def test_promedio_por_atleta_calculado_desde_sus_propias_asistencias(self):
        """Cada atleta debe tener su propio promedio de rúbrica, distinto del
        promedio agregado del club, calculado solo con sus asistencias
        presente/tarde."""
        sessions_data = [
            _make_session(1),
            _make_session(2),
        ]
        attendances_data = [
            # Atleta 100: rúbricas 4 y 5 → promedio esfuerzo = 4.5
            _make_attendance(
                1, 1, 100, AttendanceStatus.PRESENTE,
                rpe_omni=7, rubric_effort=4, rubric_attitude=5, rubric_technique=3,
            ),
            _make_attendance(
                2, 2, 100, AttendanceStatus.PRESENTE,
                rpe_omni=8, rubric_effort=5, rubric_attitude=4, rubric_technique=5,
            ),
            # Atleta 101: rúbrica solo esfuerzo=2 → promedio esfuerzo = 2.0
            # (distinto del promedio del atleta 100 y del agregado club)
            _make_attendance(
                3, 1, 101, AttendanceStatus.TARDE,
                rpe_omni=5, rubric_effort=2,
            ),
        ]

        db = _make_db(sessions_data, attendances_data)
        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)

        stats_100 = metrics.attendance_by_athlete[100]
        assert stats_100.avg_rubric_effort == 4.5
        assert stats_100.avg_rubric_attitude == 4.5
        assert stats_100.avg_rubric_technique == 4.0

        stats_101 = metrics.attendance_by_athlete[101]
        assert stats_101.avg_rubric_effort == 2.0
        assert stats_101.avg_rubric_attitude is None
        assert stats_101.avg_rubric_technique is None

        # Los promedios por atleta no deben coincidir entre sí ni ser
        # simplemente el promedio agregado del club (que mezclaría a ambos).
        assert stats_100.avg_rubric_effort != stats_101.avg_rubric_effort
        assert metrics.avg_rubric_effort == pytest.approx(round((4 + 5 + 2) / 3, 2))

    async def test_none_cuando_atleta_no_tiene_registros_de_rubrica(self):
        """Un atleta presente en el período pero sin ningún valor de rúbrica
        cargado (p.ej. sesión sin rúbrica diligenciada) debe recibir None,
        nunca 0 ni una excepción."""
        sessions_data = [_make_session(1)]
        attendances_data = [
            _make_attendance(1, 1, 200, AttendanceStatus.PRESENTE, rpe_omni=6),
        ]

        db = _make_db(sessions_data, attendances_data)
        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)

        stats_200 = metrics.attendance_by_athlete[200]
        assert stats_200.avg_rubric_effort is None
        assert stats_200.avg_rubric_attitude is None
        assert stats_200.avg_rubric_technique is None

    async def test_asistencias_no_presentes_no_contaminan_promedio_atleta(self):
        """Registros de asistencia ausente/justificado/lesionado no deben
        entrar en el promedio de rúbrica del atleta, aun si por error
        tuvieran un valor de rúbrica cargado."""
        sessions_data = [_make_session(1), _make_session(2), _make_session(3)]
        attendances_data = [
            _make_attendance(
                1, 1, 300, AttendanceStatus.PRESENTE,
                rubric_effort=3, rubric_attitude=3, rubric_technique=3,
            ),
            # No debe contar aunque tenga rubric_effort cargado.
            _make_attendance(2, 2, 300, AttendanceStatus.AUSENTE, rubric_effort=9),
            _make_attendance(3, 3, 300, AttendanceStatus.JUSTIFICADO, rubric_effort=9),
        ]

        db = _make_db(sessions_data, attendances_data)
        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=3)

        stats_300 = metrics.attendance_by_athlete[300]
        assert stats_300.avg_rubric_effort == 3.0

    async def test_sin_atletas_diccionario_vacio(self):
        """Sin sesiones en el período, attendance_by_athlete debe quedar
        vacío (comportamiento existente, no debe romperse por el nuevo
        cálculo por atleta)."""
        db = _make_db([], [])
        metrics = await metrics_svc.compute_monthly_metrics(db, club_id=1, year=2026, month=2)

        assert metrics.attendance_by_athlete == {}
