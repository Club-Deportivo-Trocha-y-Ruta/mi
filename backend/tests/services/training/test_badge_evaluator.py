"""Tests para badge_evaluator.py — insignias idempotentes por periodo."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.athlete_badge import BadgeSource, BadgeType
from app.services.training.badge_evaluator import (
    _compute_streak,
    evaluate_and_persist_badges,
)


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def make_session() -> Any:
    """Fake DB session mínima."""
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.add = MagicMock()
    return sess


def make_scalars_result(items: list) -> Any:
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_athlete(id_=1, club_id=10) -> Any:
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Atleta",
        last_name="Test",
        birth_date=date(2012, 3, 15),
    )


def make_session_obj(id_, date_=None, club_id=10) -> Any:
    from app.models.training_session import SessionStatus
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        scheduled_date=date_ or date(2026, 4, 10 + id_),
        status=SessionStatus.EXECUTED,
        duration_min=90,
        technical_focus="Curvas",
    )


def make_attendance(session_id: int, status_) -> Any:
    return SimpleNamespace(
        session_id=session_id,
        athlete_id=1,
        status=status_,
        rpe_omni=6,
        rubric_effort=4,
        rubric_attitude=4,
        rubric_technique=3,
    )


def is_delete_stmt(stmt: Any) -> bool:
    """Detecta DELETE inicial del re-evaluador (clean slate del periodo)."""
    from sqlalchemy.sql.dml import Delete

    return isinstance(stmt, Delete)


# ---------------------------------------------------------------------------
# Test: compute_streak
# ---------------------------------------------------------------------------


def test_compute_streak_all_present():
    """Racha = total sesiones si todas presentes."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(i) for i in range(1, 5)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]
    streak = _compute_streak(sessions, attendances)
    assert streak == 4


def test_compute_streak_breaks_on_absent():
    """Racha se rompe cuando hay una ausencia."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(i) for i in range(1, 6)]
    # última sesión (id=5) es la más reciente → streak desde ahí
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
        make_attendance(3, AttendanceStatus.PRESENTE),
        make_attendance(4, AttendanceStatus.PRESENTE),
        make_attendance(5, AttendanceStatus.PRESENTE),
    ]
    # sessions están ordenadas desc por fecha; la primera en la lista es la más reciente
    # make_session_obj genera fechas 2026-04-11 ... 2026-04-15 para ids 1..5
    # sorted desc: id=5 (15), id=4 (14), id=3 (13), id=2 (12), id=1 (11)
    # Desde el más reciente: 5=PRESENTE, 4=PRESENTE, 3=PRESENTE, 2=AUSENTE → streak=3
    streak = _compute_streak(sessions, attendances)
    assert streak == 3


def test_compute_streak_zero_if_last_absent():
    """Racha = 0 si la última sesión fue ausencia."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(1), make_session_obj(2)]
    # id=2 es el más reciente (fecha 12), id=1 es el anterior (fecha 11)
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
    ]
    streak = _compute_streak(sessions, attendances)
    assert streak == 0


# ---------------------------------------------------------------------------
# Test: evaluate_and_persist_badges — asistencia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_badge_attendance_100():
    """attendance_100 se genera con 100% de asistencia."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            # select Athlete
            return make_scalars_result([athlete])
        elif call_count == 2:
            # select TrainingSession
            return make_scalars_result(sessions)
        elif call_count == 3:
            # select SessionAttendance
            return make_scalars_result(attendances)
        elif call_count == 4:
            # select RaceCompetitor
            return make_scalars_result([])
        else:
            # select existing badge (no existe)
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)

    # Debe haber creado al menos el badge de attendance_100
    badge_types = [b.badge_type for b in badges]
    assert BadgeType.attendance_100 in badge_types


@pytest.mark.asyncio
async def test_badge_attendance_90():
    """attendance_90 se genera con >=90% de asistencia."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    # 9 sesiones, 9 presentes = 100% → attendance_100
    # 10 sesiones, 9 presentes = 90% → attendance_90
    sessions = [make_session_obj(i) for i in range(1, 11)]
    # i va 0..9; i < 9 → índices 0..8 PRESENTE, índice 9 AUSENTE → 9/10 = 90%
    attendances = [
        make_attendance(s.id, AttendanceStatus.PRESENTE if i < 9 else AttendanceStatus.AUSENTE)
        for i, s in enumerate(sessions)
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    badge_types = [b.badge_type for b in badges]
    assert BadgeType.attendance_90 in badge_types
    assert BadgeType.attendance_100 not in badge_types


@pytest.mark.asyncio
async def test_badge_no_badge_below_75():
    """No se genera ningún badge si asistencia < 75%."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 5)]  # 4 sesiones
    # 2 presentes / 4 = 50%
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
        make_attendance(3, AttendanceStatus.AUSENTE),
        make_attendance(4, AttendanceStatus.PRESENTE),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    assert badges == []


@pytest.mark.asyncio
async def test_badge_idempotent():
    """Re-evaluar el periodo refleja métricas actuales sin duplicar.

    El evaluador borra los badges del periodo y reinserta. Si las métricas no
    cambiaron, el set final es el mismo; si cambiaron (e.g. asistencia subió
    de 94% a 100%), reemplaza attendance_90 por attendance_100.
    """
    from app.models.athlete_badge import AthleteBadge
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    # Simular que el badge ya existe
    existing_badge = SimpleNamespace(
        id=99,
        athlete_id=athlete.id,
        badge_type=BadgeType.attendance_100,
        badge_source=BadgeSource.attendance,
        period_year=2026,
        period_month=4,
        earned_at=datetime.now(timezone.utc),
        metadata_json={"attendance_pct": 100.0},
    )

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # _upsert_badge check: badge attendance_100 → ya existe
            return make_scalars_result([existing_badge])
        elif call_count == 5:
            # RaceCompetitor — no hay
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    # Badge ya existía → no se crea nuevo
    assert badges == []
    # db.add nunca fue llamado
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test: atleta sin sesiones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sessions_no_badges():
    """Sin sesiones en el mes, no se generan badges."""
    db = make_session()
    athlete = make_athlete()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            # Sesiones: vacío
            return make_scalars_result([])
        elif call_count == 3:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    assert badges == []


@pytest.mark.asyncio
async def test_athlete_not_found_returns_empty():
    """Si el atleta no existe, retorna lista vacía."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, 999, 2026, 4)
    assert badges == []
