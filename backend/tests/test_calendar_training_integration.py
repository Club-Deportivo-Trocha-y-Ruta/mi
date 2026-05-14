"""Tests de integración TrainingSession <-> CalendarEvent.

Verifica que al crear una TrainingSession también se crea un CalendarEvent
paralelo con calendar_event_id enlazado.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.calendar_event import AudienceType, EventType
from app.models.training_session import SessionStatus, TrainingSession
from app.schemas.training_session import TrainingSessionCreate
from app.services.training import sessions as sessions_svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id: int = 1):
    from app.models.user import UserRole
    u = MagicMock()
    u.id = user_id
    u.email = "coach@test.com"
    u.first_name = "Coach"
    u.last_name = "Test"
    u.role = UserRole.coach
    u.club_memberships = []
    return u


def _make_session(
    session_id: int = 1,
    club_id: int = 1,
    calendar_event_id: int | None = None,
) -> MagicMock:
    s = MagicMock(spec=TrainingSession)
    s.id = session_id
    s.club_id = club_id
    s.status = SessionStatus.PLANNED
    s.scheduled_date = date(2030, 8, 15)
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
    s.attendances = []
    s.calendar_event_id = calendar_event_id
    return s


def _make_payload(athlete_ids: list[int] | None = None) -> TrainingSessionCreate:
    return TrainingSessionCreate(
        scheduled_date=date(2030, 8, 15),
        scheduled_start_time=time(17, 0),
        duration_min=90,
        location="Bosque Municipal",
        technical_focus="Descenso técnico",
        convocados_athlete_ids=athlete_ids or [1, 2],
    )


# ---------------------------------------------------------------------------
# _create_parallel_calendar_event — unit tests
# ---------------------------------------------------------------------------


class TestCreateParallelCalendarEvent:
    async def test_crea_calendar_event_y_enlaza(self):
        """La función silenciosa debe crear CalendarEvent y setear calendar_event_id."""
        session = _make_session(session_id=5)
        payload = _make_payload(athlete_ids=[1, 2])
        coach = _make_user()

        created_event = MagicMock()
        created_event.id = 99

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        from app.models.calendar_event import CalendarEvent, EventAudience

        add_calls = []
        original_add = db.add

        def track_add(obj):
            add_calls.append(type(obj).__name__)

        db.add = track_add

        await sessions_svc._create_parallel_calendar_event(
            db, session, payload, coach, club_id=1
        )

        # Verificar que se intentó crear un CalendarEvent y una EventAudience
        assert "CalendarEvent" in add_calls, f"Tipos creados: {add_calls}"
        assert "EventAudience" in add_calls, f"Tipos creados: {add_calls}"

    async def test_enlaza_session_al_evento(self):
        """Después de crear el evento, session.calendar_event_id debe ser seteado."""
        session = _make_session(session_id=5)
        payload = _make_payload(athlete_ids=[1])
        coach = _make_user()

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Simular que flush asigna id al CalendarEvent
        call_count = 0

        async def mock_flush():
            nonlocal call_count
            call_count += 1

        db.flush = mock_flush

        # Capturar el CalendarEvent creado para simular que obtiene id
        created_objects = []
        original_add = db.add.side_effect

        def track_and_set_id(obj):
            created_objects.append(obj)
            from app.models.calendar_event import CalendarEvent
            if isinstance(obj, CalendarEvent):
                obj.id = 99  # Simular que flush asigna el id

        db.add = MagicMock(side_effect=track_and_set_id)

        await sessions_svc._create_parallel_calendar_event(
            db, session, payload, coach, club_id=1
        )

        # Verificar que session.calendar_event_id fue asignado
        assert session.calendar_event_id is not None

    async def test_audience_athlete_list_con_convocados(self):
        """La audiencia creada debe ser ATHLETE_LIST con los atletas convocados."""
        session = _make_session(session_id=5)
        payload = _make_payload(athlete_ids=[10, 20, 30])
        coach = _make_user()

        db = AsyncMock()
        db.flush = AsyncMock()

        audiences_created = []

        def track_add(obj):
            from app.models.calendar_event import EventAudience
            if isinstance(obj, EventAudience):
                audiences_created.append(obj)

        db.add = MagicMock(side_effect=track_add)

        await sessions_svc._create_parallel_calendar_event(
            db, session, payload, coach, club_id=1
        )

        assert len(audiences_created) == 1
        aud = audiences_created[0]
        assert aud.audience_type == AudienceType.ATHLETE_LIST
        assert set(aud.audience_value["athlete_ids"]) == {10, 20, 30}

    async def test_no_falla_si_error_interno(self):
        """Si hay error interno, la función es silenciosa (loguea, no propaga)."""
        session = _make_session(session_id=5)
        payload = _make_payload()
        coach = _make_user()

        db = AsyncMock()
        db.add = MagicMock(side_effect=Exception("Error de BD simulado"))
        db.flush = AsyncMock()

        # No debe propagarse el error
        await sessions_svc._create_parallel_calendar_event(
            db, session, payload, coach, club_id=1
        )


# ---------------------------------------------------------------------------
# create_session — integración
# ---------------------------------------------------------------------------


class TestCreateSessionIntegration:
    async def test_create_session_llama_parallel_calendar_event(self):
        """create_session debe llamar a _create_parallel_calendar_event."""
        payload = _make_payload(athlete_ids=[1])
        coach = _make_user()

        # La sesión que retorna get_session ya tiene calendar_event_id asignado
        session_with_event = _make_session(session_id=1, calendar_event_id=99)

        parallel_calls = []

        async def mock_parallel(db, session, payload, coach, club_id):
            parallel_calls.append(True)
            # mock_parallel set the attribute on the raw session (before get_session refresh)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch.object(
            sessions_svc,
            "_assert_coach_in_club",
            AsyncMock(),
        ):
            with patch.object(
                sessions_svc,
                "get_session",
                AsyncMock(return_value=session_with_event),
            ):
                with patch.object(
                    sessions_svc,
                    "_create_parallel_calendar_event",
                    mock_parallel,
                ):
                    result = await sessions_svc.create_session(
                        db=db,
                        payload=payload,
                        coach=coach,
                        club_id=1,
                    )

        assert parallel_calls, "Debió llamarse _create_parallel_calendar_event"
        assert result.calendar_event_id == 99

    async def test_calendar_event_id_no_es_none_despues_de_crear(self):
        """Después de create_session, el resultado debe tener calendar_event_id."""
        payload = _make_payload(athlete_ids=[1])
        coach = _make_user()

        session_with_event = _make_session(session_id=1, calendar_event_id=42)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        async def mock_parallel(db, session, payload, coach, club_id):
            session.calendar_event_id = 42

        with patch.object(sessions_svc, "_assert_coach_in_club", AsyncMock()):
            with patch.object(
                sessions_svc, "get_session", AsyncMock(return_value=session_with_event)
            ):
                with patch.object(
                    sessions_svc,
                    "_create_parallel_calendar_event",
                    mock_parallel,
                ):
                    result = await sessions_svc.create_session(
                        db=db,
                        payload=payload,
                        coach=coach,
                        club_id=1,
                    )

        assert result.calendar_event_id is not None
        assert result.calendar_event_id == 42
