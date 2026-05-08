"""
Tests PASO 7 — Notificación a padres al planificar sesión de entrenamiento.

Cubre:
1. Happy path: coach crea sesión con 2 convocados que tienen padre → send() x2
2. Sin padre: atleta sin padre vinculado → no email para ese atleta
3. Throttle: doble creación en <60min para mismo par → segundo send() no llama
4. Failure isolation: send() lanza excepción → create_session igual retorna sesión
5. PII en logs: logs no contienen email del padre ni nombre del atleta
6. Sin notification_service → no emails (back-compat)
"""

from __future__ import annotations

import logging
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.notification import NotificationResult, NotificationTemplate
from app.schemas.training_session import TrainingSessionCreate
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.training import sessions as sessions_svc
from app.models.training_session import SessionStatus


# ---------------------------------------------------------------------------
# Fixtures helpers — usan MagicMock para evitar el estado ORM de SQLAlchemy
# ---------------------------------------------------------------------------


def _make_user(
    user_id: int,
    email: str | None = None,
    first_name: str = "Test",
    last_name: str = "User",
) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = email
    u.first_name = first_name
    u.last_name = last_name
    u.is_active = True
    u.can_login = True
    u.club_memberships = []
    return u


def _make_athlete(
    athlete_id: int, club_id: int, first_name: str = "Atleta", last_name: str = "Test"
) -> MagicMock:
    a = MagicMock()
    a.id = athlete_id
    a.club_id = club_id
    a.first_name = first_name
    a.last_name = last_name
    return a


def _make_parent_athlete(pa_id: int, parent: MagicMock, athlete: MagicMock) -> MagicMock:
    pa = MagicMock()
    pa.id = pa_id
    pa.parent_id = parent.id
    pa.athlete_id = athlete.id
    pa.parent = parent
    pa.athlete = athlete
    return pa


def _make_club(club_id: int = 1, name: str = "Club Trocha y Ruta") -> MagicMock:
    c = MagicMock()
    c.id = club_id
    c.name = name
    return c


def _make_payload(athlete_ids: list[int]) -> TrainingSessionCreate:
    return TrainingSessionCreate(
        scheduled_date=date(2026, 5, 20),
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location="Bosque Municipal",
        technical_focus="Descenso técnico",
        convocados_athlete_ids=athlete_ids,
    )


def _make_notification_service(success: bool = True) -> MagicMock:
    svc = MagicMock()
    svc.send = AsyncMock(return_value=NotificationResult(success=success, message_id="q"))
    return svc


def _make_session_mock(session_id: int) -> MagicMock:
    """Crea un mock de TrainingSession con scheduled_date real para evitar errores de comparación."""
    from app.models.training_session import TrainingSession
    s = MagicMock(spec=TrainingSession)
    s.id = session_id
    s.status = SessionStatus.PLANNED
    s.scheduled_date = date(2026, 5, 20)
    s.scheduled_start_time = time(17, 0)
    s.duration_min = 90
    s.location = "Bosque Municipal"
    s.technical_focus = "Descenso técnico"
    s.attendances = []
    return s


def _make_db(
    club: MagicMock | None,
    parent_athlete_pairs: list[tuple[MagicMock, MagicMock]],
    session_id: int = 1,
) -> AsyncMock:
    """Construye un mock de AsyncSession con las respuestas adecuadas."""
    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj, **kwargs):
        obj.id = session_id
        obj.status = SessionStatus.PLANNED
        obj.scheduled_date = date(2026, 5, 20)
        obj.scheduled_start_time = time(17, 0)
        obj.duration_min = 90
        obj.location = "Bosque Municipal"
        obj.technical_focus = "Descenso técnico"
        obj.attendances = []

    db.refresh = _refresh

    # db.execute se llama en este orden:
    # 1. get_session (por selectinload tras flush+commit)
    # 2. Club select (para notificación)
    # 3. ParentAthlete join (para notificación)
    session_mock = _make_session_mock(session_id)
    get_session_result = MagicMock()
    get_session_result.scalar_one_or_none = MagicMock(return_value=session_mock)
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=[])
    get_session_result.scalars = MagicMock(return_value=scalars_mock)

    club_result = MagicMock()
    club_result.scalar_one_or_none = MagicMock(return_value=club)

    pa_result = MagicMock()
    pa_result.all = MagicMock(return_value=parent_athlete_pairs)

    db.execute = AsyncMock(side_effect=[get_session_result, club_result, pa_result])
    return db


# ---------------------------------------------------------------------------
# 1. Happy path — 2 convocados con padre → send() llamado 2 veces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_two_convocados_two_parents():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com", "Entrenador", "Bueno")
    parent1 = _make_user(10, "padre1@test.com", "Carlos", "Lopez")
    parent2 = _make_user(11, "madre2@test.com", "Ana", "Gomez")
    athlete1 = _make_athlete(100, club_id=1, first_name="Miguel", last_name="Ramirez")
    athlete2 = _make_athlete(101, club_id=1, first_name="Sofia", last_name="Torres")
    pa1 = _make_parent_athlete(1, parent1, athlete1)
    pa2 = _make_parent_athlete(2, parent2, athlete2)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    db = _make_db(club, [(pa1, athlete1), (pa2, athlete2)])

    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        payload = _make_payload([100, 101])
        await sessions_svc.create_session(
            db=db,
            payload=payload,
            coach=coach,
            club_id=1,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    assert notification_service.send.call_count == 2
    calls = notification_service.send.call_args_list
    templates_used = {c.args[0].template for c in calls}
    assert NotificationTemplate.TRAINING_SESSION_INVITE in templates_used

    contexts = [c.args[0].context for c in calls]
    athlete_names = {ctx["athlete_name"] for ctx in contexts}
    assert "Miguel Ramirez" in athlete_names
    assert "Sofia Torres" in athlete_names


# ---------------------------------------------------------------------------
# 2. Sin padre vinculado → no email para ese atleta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_parent_linked_no_email():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    db = _make_db(club, [])  # sin pares padre-atleta

    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        payload = _make_payload([100])
        await sessions_svc.create_session(
            db=db,
            payload=payload,
            coach=coach,
            club_id=1,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    notification_service.send.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Throttle — segunda llamada en <60min NO llama send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_second_call_skipped():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1)
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    # Primera llamada
    db1 = _make_db(club, [(pa, athlete)])
    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        await sessions_svc.create_session(
            db=db1,
            payload=_make_payload([100]),
            coach=coach,
            club_id=1,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    first_count = notification_service.send.call_count
    assert first_count == 1

    # Segunda llamada — debe ser throttleada (mismo parent, athlete, kind en <60min)
    db2 = _make_db(club, [(pa, athlete)])
    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        await sessions_svc.create_session(
            db=db2,
            payload=_make_payload([100]),
            coach=coach,
            club_id=1,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    assert notification_service.send.call_count == first_count


# ---------------------------------------------------------------------------
# 4. Failure isolation — send() lanza → create_session igual retorna sesión
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_isolation_send_raises():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1)
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)

    broken_service = MagicMock()
    broken_service.send = AsyncMock(side_effect=RuntimeError("Provider caído"))
    dispatcher = TaskDispatcher()

    db = _make_db(club, [(pa, athlete)], session_id=99)

    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        with patch("app.services.training.sessions._should_throttle", return_value=False):
            payload = _make_payload([100])
            result = await sessions_svc.create_session(
                db=db,
                payload=payload,
                coach=coach,
                club_id=1,
                notification_service=broken_service,
                dispatcher=dispatcher,
            )

    # La sesión fue creada a pesar del error en notificación
    assert result is not None
    assert result.id == 99


# ---------------------------------------------------------------------------
# 5. PII no en logs — logs no contienen email ni nombre del atleta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pii_not_in_logs(caplog):
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    parent = _make_user(10, "padre.secreto@test.com", "Juan", "Pérez")
    athlete = _make_athlete(100, club_id=1, first_name="Carlos", last_name="García")
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    db = _make_db(club, [(pa, athlete)])

    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        with patch("app.services.training.sessions._should_throttle", return_value=False):
            with caplog.at_level(logging.DEBUG, logger="app.services.training.sessions"):
                payload = _make_payload([100])
                await sessions_svc.create_session(
                    db=db,
                    payload=payload,
                    coach=coach,
                    club_id=1,
                    notification_service=notification_service,
                    dispatcher=dispatcher,
                )

    all_log_text = " ".join(r.message for r in caplog.records)
    assert "padre.secreto@test.com" not in all_log_text
    assert "Carlos García" not in all_log_text
    assert "García" not in all_log_text


# ---------------------------------------------------------------------------
# 6. Sin notification_service → no emails (back-compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_notification_service_no_emails():
    coach = _make_user(1, "coach@test.com")
    session_mock = _make_session_mock(session_id=1)

    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj, **kwargs):
        obj.id = 1
        obj.status = SessionStatus.PLANNED
        obj.attendances = []

    db.refresh = _refresh

    member_result = MagicMock()
    member_result.first = MagicMock(return_value=MagicMock())
    member_result.scalar_one_or_none = MagicMock(return_value=session_mock)
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=[])
    member_result.scalars = MagicMock(return_value=scalars_mock)
    db.execute = AsyncMock(return_value=member_result)

    with patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()):
        payload = _make_payload([100])
        result = await sessions_svc.create_session(
            db=db,
            payload=payload,
            coach=coach,
            club_id=1,
            notification_service=None,
            dispatcher=None,
        )

    assert result is not None
    # Sin notificación → execute solo se llama una vez (get_session para reload)
    # No se consultan Club ni ParentAthlete
    assert db.execute.call_count == 1
