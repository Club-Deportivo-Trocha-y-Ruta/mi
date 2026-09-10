"""
Tests PASO 7 — Notificación a padres al planificar sesión de entrenamiento.

Cubre:
1. Happy path: coach crea sesión con 2 convocados que tienen padre → send() x2
2. Sin padre: atleta sin padre vinculado → no email para ese atleta
3. Throttle: doble creación en <60min para mismo par → segundo send() no llama
4. Failure isolation: send() lanza excepción → create_session igual retorna sesión
5. PII en logs: logs no contienen email del padre ni nombre del atleta
6. Sin notification_service → no emails (back-compat)
7. send_notification=False → no emails (opt-in explícito)
8. update_session con cambios + flag → despacha training_session_updated
9. cancel_session con flag → despacha training_session_cancelled
"""

from __future__ import annotations

import logging
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.user import User
from app.schemas.notification import NotificationResult, NotificationTemplate
from app.schemas.training_session import (
    TrainingSessionCreate,
    TrainingSessionUpdate,
)
from app.services.audit import CancelReasonCode
from app.services.notification.task_dispatcher import TaskDispatcher
from app.services.training import sessions as sessions_svc
from app.models.training_session import SessionStatus

from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches
from tests.helpers.audit_tables import AUDIT_TABLES

#: Fecha futura calculada en relación con "hoy" — nunca una fecha fija, que
#: con el paso del calendario real deja de ser futura y apaga en silencio
#: las notificaciones que estos tests dicen estar probando (flaky conocido
#: de este archivo: usaba `date(2026, 5, 20)` a fuego).
FUTURE_DATE = date.today() + timedelta(days=30)


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
    # 041 — `_actor_display_name` (sessions.py) primero intenta
    # `actor.display_name`; en un `User` real es una `@property` que siempre
    # devuelve texto, pero en un MagicMock sin `spec` cualquier atributo no
    # fijado se auto-crea como OTRO MagicMock (truthy), así que sin esto el
    # contexto del email terminaría llevando un MagicMock en vez de un
    # nombre. Se fija explícitamente para que el doble se comporte como el
    # modelo real.
    u.display_name = f"{first_name} {last_name}".strip()
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


def _make_payload(
    athlete_ids: list[int], send_notification: bool = True
) -> TrainingSessionCreate:
    return TrainingSessionCreate(
        scheduled_date=FUTURE_DATE,
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location="Bosque Municipal",
        technical_focus="Descenso técnico",
        convocados_athlete_ids=athlete_ids,
        send_notification=send_notification,
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
    s.scheduled_date = FUTURE_DATE
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
        obj.scheduled_date = FUTURE_DATE
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

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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
    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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
    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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
async def test_send_notification_false_no_emails():
    """Cuando el coach elige 'No enviar' (send_notification=False), no se despacha email."""
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1)
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    db = _make_db(club, [(pa, athlete)])

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
        payload = _make_payload([100], send_notification=False)
        await sessions_svc.create_session(
            db=db,
            payload=payload,
            coach=coach,
            club_id=1,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    notification_service.send.assert_not_called()


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

    with (
        patch.object(sessions_svc, "_assert_coach_in_club", new=AsyncMock()),
        # 041 — create_session ahora siempre pasa por _replace_session_coaches
        # (que valida elegibilidad contra `users`/`club_members`, tablas que
        # este `db` de puro AsyncMock no modela) y por _load_session_coaches
        # (consulta aparte para el contexto del email). Ninguna de las dos
        # es lo que este test verifica — B-01…B-07 y B-08/B-09 las cubren
        # con DB real — así que se neutralizan como dobles: el reemplazo del
        # puente se vuelve no-op y la carga de entrenadores cae al fallback
        # de `_coach_names_context` (nombre del actor).
        patch.object(sessions_svc, "_replace_session_coaches", new=AsyncMock()),
        patch.object(sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])),
    ):
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


# ---------------------------------------------------------------------------
# 8. update_session — flag + cambios reales → despacha TRAINING_SESSION_UPDATED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_session_with_changes_dispatches_updated_template():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com", "Entrenador", "Bueno")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1, first_name="Miguel", last_name="Ramirez")
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    # Sesión existente con asistencia del atleta 100
    session = _make_session_mock(session_id=42)
    session.club_id = 1
    session.created_by_user_id = coach.id
    attendance = MagicMock()
    attendance.athlete_id = 100
    # 041 §6.4 — todo listado de convocados filtra `archived_at IS NULL`;
    # sin fijarlo, un MagicMock sin spec devuelve otro MagicMock (no None),
    # así que el atleta quedaría excluido y el email nunca se despacharía.
    attendance.archived_at = None
    session.attendances = [attendance]
    session.location = "Lugar Antiguo"

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    get_session_result = MagicMock()
    get_session_result.scalar_one_or_none = MagicMock(return_value=session)

    club_result = MagicMock()
    club_result.scalar_one_or_none = MagicMock(return_value=club)

    pa_result = MagicMock()
    pa_result.all = MagicMock(return_value=[(pa, athlete)])

    # 041 — _get_session_or_raise → get_session(refreshed) → Club →
    # ParentAthlete. La vieja 3ª consulta (`User(coach)`, para el borrado
    # `_load_session_coach`) desapareció: `acting_coach_name` ahora sale
    # directo del `actor` que ya se recibe como objeto, sin re-consultarlo;
    # `_load_session_coaches` (nueva, aparte) se neutraliza abajo porque
    # este `db` no modela el puente `training_session_coaches`.
    db.execute = AsyncMock(
        side_effect=[get_session_result, get_session_result, club_result, pa_result]
    )

    payload = TrainingSessionUpdate(location="Pista Nueva", send_notification=True)
    with patch.object(
        sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])
    ):
        await sessions_svc.update_session(
            db=db,
            session_id=42,
            payload=payload,
            actor=coach,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    notification_service.send.assert_called_once()
    request = notification_service.send.call_args.args[0]
    assert request.template == NotificationTemplate.TRAINING_SESSION_UPDATED
    assert request.context["changes"]
    assert request.context["changes"][0]["field_label"] == "Lugar"
    assert request.context["changes"][0]["new"] == "Pista Nueva"
    # 041 §5.1 — el cuerpo nombra a quien EDITÓ (el actor), no a un
    # `coach_name` derivado del creador (ese campo ya no existe).
    assert request.context["acting_coach_name"] == coach.display_name
    assert "coach_name" not in request.context


@pytest.mark.asyncio
async def test_update_session_without_flag_no_emails():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1)
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    session = _make_session_mock(session_id=42)
    session.club_id = 1
    session.created_by_user_id = coach.id
    attendance = MagicMock()
    attendance.athlete_id = 100
    # 041 §6.4 — todo listado de convocados filtra `archived_at IS NULL`;
    # sin fijarlo, un MagicMock sin spec devuelve otro MagicMock (no None),
    # así que el atleta quedaría excluido y el email nunca se despacharía.
    attendance.archived_at = None
    session.attendances = [attendance]
    session.location = "Lugar Antiguo"

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    get_session_result = MagicMock()
    get_session_result.scalar_one_or_none = MagicMock(return_value=session)
    db.execute = AsyncMock(return_value=get_session_result)

    payload = TrainingSessionUpdate(location="Otra", send_notification=False)
    await sessions_svc.update_session(
        db=db,
        session_id=42,
        payload=payload,
        actor=coach,
        notification_service=notification_service,
        dispatcher=dispatcher,
    )

    notification_service.send.assert_not_called()


# ---------------------------------------------------------------------------
# 9. cancel_session — flag → despacha TRAINING_SESSION_CANCELLED con reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_session_with_flag_dispatches_cancelled_template():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com", "Entrenador", "Bueno")
    parent = _make_user(10, "padre@test.com", "Carlos", "Lopez")
    athlete = _make_athlete(100, club_id=1, first_name="Miguel", last_name="Ramirez")
    pa = _make_parent_athlete(1, parent, athlete)
    club = _make_club(1)
    notification_service = _make_notification_service()
    dispatcher = TaskDispatcher()

    session = _make_session_mock(session_id=42)
    session.club_id = 1
    session.created_by_user_id = coach.id
    attendance = MagicMock()
    attendance.athlete_id = 100
    # 041 §6.4 — todo listado de convocados filtra `archived_at IS NULL`;
    # sin fijarlo, un MagicMock sin spec devuelve otro MagicMock (no None),
    # así que el atleta quedaría excluido y el email nunca se despacharía.
    attendance.archived_at = None
    session.attendances = [attendance]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    get_session_result = MagicMock()
    get_session_result.scalar_one_or_none = MagicMock(return_value=session)

    club_result = MagicMock()
    club_result.scalar_one_or_none = MagicMock(return_value=club)

    pa_result = MagicMock()
    pa_result.all = MagicMock(return_value=[(pa, athlete)])

    # 041 — misma poda que en update_session: sin la vieja consulta
    # `User(coach)` de `_load_session_coach` (eliminada).
    db.execute = AsyncMock(
        side_effect=[get_session_result, get_session_result, club_result, pa_result]
    )

    with patch.object(
        sessions_svc, "_load_session_coaches", new=AsyncMock(return_value=[])
    ):
        await sessions_svc.cancel_session(
            db=db,
            session_id=42,
            actor=coach,
            send_notification=True,
            reason_code=CancelReasonCode.cancel_weather,
            notification_service=notification_service,
            dispatcher=dispatcher,
        )

    notification_service.send.assert_called_once()
    request = notification_service.send.call_args.args[0]
    assert request.template == NotificationTemplate.TRAINING_SESSION_CANCELLED
    # 041 §7.1 — `reason` es la ETIQUETA en español resuelta desde
    # `reason_code`, nunca el texto libre que este test enviaba antes.
    assert request.context["reason"] == "Clima adverso"
    assert request.context["acting_coach_name"] == coach.display_name


@pytest.mark.asyncio
async def test_cancel_session_without_flag_no_emails():
    sessions_svc._recent_dispatches.clear()

    coach = _make_user(1, "coach@test.com")
    notification_service = _make_notification_service()

    session = _make_session_mock(session_id=42)
    session.club_id = 1
    session.created_by_user_id = coach.id
    session.attendances = []

    db = AsyncMock()
    db.commit = AsyncMock()

    get_session_result = MagicMock()
    get_session_result.scalar_one_or_none = MagicMock(return_value=session)
    db.execute = AsyncMock(return_value=get_session_result)

    await sessions_svc.cancel_session(
        db=db,
        session_id=42,
        actor=coach,
        reason_code=CancelReasonCode.cancel_weather,
        send_notification=False,
        notification_service=notification_service,
    )

    notification_service.send.assert_not_called()


# ---------------------------------------------------------------------------
# 10. B-08 / B-09 — contracts/session-coaches.md §12: el email nombra a QUIEN
# ACTUÓ, nunca al `created_by_user_id` de la sesión (bug de US4 en el viejo
# `_load_session_coach`). A diferencia de los tests de arriba (mocks de
# AsyncSession, que aíslan la lógica de despacho de la carga de
# entrenadores), estos dos usan una DB sqlite real con las tablas puente
# `training_session_coaches` sembradas — es la única manera de hacer que
# `test_b08` falle de verdad contra el código viejo: un mock nunca modela
# "quién creó" vs. "quién actuó" como dos filas distintas de la misma tabla.
# ---------------------------------------------------------------------------

_GOV_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "training_sessions",
    "session_attendance",
    "session_media",
    "session_media_athlete",
    "calendar_events",
    "event_audiences",
    *AUDIT_TABLES,  # incluye "training_session_coaches" — no listarla aparte
)


@pytest_asyncio.fixture
async def gov_engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _GOV_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def gov_session_factory(
    gov_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(gov_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def gov_scenario(
    gov_session_factory: async_sessionmaker[AsyncSession],
) -> TwoCoachesScenario:
    async with gov_session_factory() as session:
        yield await seed_two_coaches(session)


async def _load_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_b08_cancel_by_coach_b_names_b_not_creator_a(gov_scenario):
    """B-08 — regresión US4 (DEBE fallar contra el `_load_session_coach` de
    hoy, `backend/app/services/training/sessions.py:853` antes de esta
    feature): coach A crea la sesión con A y B como entrenadores; coach B la
    cancela. El correo de cancelación debe nombrar a QUIEN CANCELÓ (B) en el
    cuerpo (`acting_coach_name`) y listar a AMBOS en la firma
    (`coaches_text`) — nunca solo a A, el creador.
    """
    s = gov_scenario
    db = s.session

    coach_a = await _load_user(db, s.coach_a_user_id)
    coach_b = await _load_user(db, s.coach_b_user_id)

    payload = TrainingSessionCreate(
        scheduled_date=FUTURE_DATE,
        scheduled_start_time=time(8, 0),
        duration_min=60,
        location="Pista ficticia",
        technical_focus="Base",
        convocados_athlete_ids=[s.athlete_id],
        coach_user_ids=[s.coach_a_user_id, s.coach_b_user_id],
        send_notification=False,
    )
    session = await sessions_svc.create_session(
        db=db, payload=payload, coach=coach_a, club_id=s.club_id
    )

    notification_service = _make_notification_service()
    await sessions_svc.cancel_session(
        db=db,
        session_id=session.id,
        actor=coach_b,
        reason_code=CancelReasonCode.cancel_weather,
        send_notification=True,
        notification_service=notification_service,
    )

    notification_service.send.assert_called_once()
    request = notification_service.send.call_args.args[0]
    assert request.template == NotificationTemplate.TRAINING_SESSION_CANCELLED
    # El cuerpo nombra a quien canceló — B, nunca al creador A.
    assert request.context["acting_coach_name"] == coach_b.display_name
    assert request.context["acting_coach_name"] != coach_a.display_name
    # La firma lista a ambos entrenadores de la sesión.
    assert coach_a.display_name in request.context["coaches_text"]
    assert coach_b.display_name in request.context["coaches_text"]
    assert coach_a.display_name in request.context["coach_names"]
    assert coach_b.display_name in request.context["coach_names"]


@pytest.mark.asyncio
async def test_b09_update_by_coach_b_names_the_editor(gov_scenario):
    """B-09 — misma exigencia para `update_session`: el email nombra a quien
    EDITÓ, no a quien creó. Coach A crea (como único entrenador); coach B
    edita un campo de la sesión con `send_notification=True`."""
    s = gov_scenario
    db = s.session

    coach_a = await _load_user(db, s.coach_a_user_id)
    coach_b = await _load_user(db, s.coach_b_user_id)

    payload = TrainingSessionCreate(
        scheduled_date=FUTURE_DATE,
        scheduled_start_time=time(8, 0),
        duration_min=60,
        location="Pista ficticia",
        technical_focus="Base",
        convocados_athlete_ids=[s.athlete_id],
        send_notification=False,
    )
    session = await sessions_svc.create_session(
        db=db, payload=payload, coach=coach_a, club_id=s.club_id
    )

    notification_service = _make_notification_service()
    update_payload = TrainingSessionUpdate(
        location="Pista Nueva Ficticia", send_notification=True
    )
    await sessions_svc.update_session(
        db=db,
        session_id=session.id,
        payload=update_payload,
        actor=coach_b,
        notification_service=notification_service,
    )

    notification_service.send.assert_called_once()
    request = notification_service.send.call_args.args[0]
    assert request.template == NotificationTemplate.TRAINING_SESSION_UPDATED
    # El cuerpo nombra a quien EDITÓ (B), no a quien creó (A, único
    # entrenador de la sesión — la firma también dice A, no hay ambigüedad
    # posible salvo que el código vuelva a derivar del creador).
    assert request.context["acting_coach_name"] == coach_b.display_name
    assert request.context["acting_coach_name"] != coach_a.display_name
    assert request.context["changes"][0]["new"] == "Pista Nueva Ficticia"
