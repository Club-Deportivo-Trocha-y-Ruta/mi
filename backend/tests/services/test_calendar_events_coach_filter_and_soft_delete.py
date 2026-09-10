"""T063/T064 — filtro `coach_user_id` y soft-delete a nivel SQL.

Los tests de `tests/test_calendar_events_service.py` y
`tests/test_calendar_router.py` mockean `db.execute`, así que nunca ejercitan
el `WHERE` real armado en `list_events_in_range`/`get_event`. Este módulo usa
un engine aiosqlite in-memory propio (patrón de
`tests/routers/test_audit_log_api.py`/`tests/fixtures/two_coaches.py`, sin
tocar esos archivos compartidos — T063 solo es dueño de
`backend/app/services/calendar/*` y `backend/app/routers/calendar.py`) para
verificar:

- `coach_user_id` empareja por `created_by_user_id` directo, o por el
  bridge `training_session_coaches` cuando el evento es una sesión de
  entrenamiento enlazada (contracts/session-coaches.md §8.2, FR-026).
- los cumpleaños virtuales se excluyen siempre que ese filtro esté activo.
- un evento con `deleted_at` (borrado permanente = soft-delete, §7.3) no
  reaparece ni en `list_events_in_range` ni en `get_event`.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.calendar_event import CalendarEvent, EventStatus, EventType
from app.models.club import ClubRole
from app.models.training_session import (
    SessionKind,
    SessionStatus,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.training_session import AttendanceStatus, SessionAttendance
from app.models.user import UserRole
from app.routers.calendar import list_event_attendances
from app.schemas.calendar import EventListQuery
from app.services.calendar import events as events_svc

from tests.fixtures.race_history_fixtures import create_club, create_user, link_user_to_club

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "calendar_events",
    "event_audiences",
    "event_attendances",
    "training_sessions",
    "training_session_coaches",
    "session_attendance",
)

CLUB_ID = 1
COACH_A_ID = 801
COACH_B_ID = 802


@pytest_asyncio.fixture
async def seeded_session():
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[Base.metadata.tables[t] for t in _TABLES],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio T063", code="cft-t063")
        coach_a = await create_user(
            session, user_id=COACH_A_ID, role=UserRole.coach,
            first_name="Coach", last_name="Ficticio A",
        )
        coach_b = await create_user(
            session, user_id=COACH_B_ID, role=UserRole.coach,
            first_name="Coach", last_name="Ficticio B",
        )
        await link_user_to_club(session, user_id=COACH_A_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach)
        await link_user_to_club(session, user_id=COACH_B_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach)
        await session.commit()
        yield session, coach_a, coach_b

    await engine.dispose()


def _make_club_event(
    *, event_id: int, created_by: int, start: datetime, title: str = "Evento"
) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        club_id=CLUB_ID,
        event_type=EventType.CLUB_EVENT,
        status=EventStatus.SCHEDULED,
        title=title,
        start_at=start,
        end_at=start,
        all_day=False,
        created_by_user_id=created_by,
    )


async def test_coach_filter_matches_direct_creator(seeded_session):
    session, coach_a, coach_b = seeded_session
    start = datetime(2031, 3, 1, 10, 0, tzinfo=timezone.utc)

    ev_a = _make_club_event(event_id=1, created_by=coach_a.id, start=start, title="De A")
    ev_b = _make_club_event(event_id=2, created_by=coach_b.id, start=start, title="De B")
    session.add_all([ev_a, ev_b])
    await session.commit()

    results = await events_svc.list_events_in_range(
        db=session,
        club_id=CLUB_ID,
        from_date=date(2031, 3, 1),
        to_date=date(2031, 3, 31),
        filters=EventListQuery(
            from_date=date(2031, 3, 1),
            to_date=date(2031, 3, 31),
            coach_user_id=coach_a.id,
        ),
        viewer=coach_a,
    )

    titles = {ev.title for ev in results}
    assert titles == {"De A"}


async def test_coach_filter_matches_via_training_session_bridge(seeded_session):
    """Sesión creada por coach_b pero con coach_a asignado como
    session_coach: coach_a debe verla igual (FR-026 — "session coaches for
    sessions; creator for other events")."""
    session, coach_a, coach_b = seeded_session
    start = datetime(2031, 4, 5, 15, 0, tzinfo=timezone.utc)

    ts = TrainingSession(
        id=50,
        club_id=CLUB_ID,
        created_by_user_id=coach_b.id,
        status=SessionStatus.PLANNED,
        scheduled_date=date(2031, 4, 5),
        scheduled_start_time=time(15, 0),
        duration_min=60,
        location="Pista",
        technical_focus="Resistencia",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add(ts)
    await session.flush()

    ev = CalendarEvent(
        id=3,
        club_id=CLUB_ID,
        event_type=EventType.TRAINING_SESSION,
        status=EventStatus.SCHEDULED,
        title="Sesión de B con coach A asignado",
        start_at=start,
        end_at=start,
        all_day=False,
        created_by_user_id=coach_b.id,
        event_data={"training_session_id": ts.id},
    )
    session.add(ev)
    await session.flush()

    ts.calendar_event_id = ev.id
    session.add(TrainingSessionCoach(session_id=ts.id, coach_user_id=coach_a.id))
    await session.commit()

    results = await events_svc.list_events_in_range(
        db=session,
        club_id=CLUB_ID,
        from_date=date(2031, 4, 1),
        to_date=date(2031, 4, 30),
        filters=EventListQuery(
            from_date=date(2031, 4, 1),
            to_date=date(2031, 4, 30),
            coach_user_id=coach_a.id,
        ),
        viewer=coach_a,
    )

    assert {ev.id for ev in results} == {3}


async def test_coach_filter_excludes_virtual_birthdays(seeded_session, monkeypatch):
    session, coach_a, coach_b = seeded_session
    start = datetime(2031, 5, 1, 9, 0, tzinfo=timezone.utc)

    ev = _make_club_event(event_id=4, created_by=coach_a.id, start=start)
    session.add(ev)
    await session.commit()

    fake_birthday = _make_club_event(
        event_id=-999, created_by=coach_a.id, start=start, title="Cumpleaños falso"
    )
    fake_birthday.event_type = EventType.BIRTHDAY

    async def _fake_birthdays(*args, **kwargs):
        return [fake_birthday]

    monkeypatch.setattr(
        "app.services.calendar.birthdays.list_birthday_events_in_range", _fake_birthdays
    )

    results = await events_svc.list_events_in_range(
        db=session,
        club_id=CLUB_ID,
        from_date=date(2031, 5, 1),
        to_date=date(2031, 5, 31),
        filters=EventListQuery(
            from_date=date(2031, 5, 1),
            to_date=date(2031, 5, 31),
            coach_user_id=coach_a.id,
        ),
        viewer=coach_a,
    )

    assert all(r.event_type != EventType.BIRTHDAY for r in results)


async def test_soft_deleted_event_excluded_from_list_and_get(seeded_session):
    session, coach_a, _coach_b = seeded_session
    start = datetime(2031, 6, 1, 8, 0, tzinfo=timezone.utc)

    ev = _make_club_event(event_id=5, created_by=coach_a.id, start=start)
    ev.deleted_at = datetime.now(timezone.utc)
    ev.deleted_by_user_id = coach_a.id
    session.add(ev)
    await session.commit()

    results = await events_svc.list_events_in_range(
        db=session,
        club_id=CLUB_ID,
        from_date=date(2031, 6, 1),
        to_date=date(2031, 6, 30),
        filters=EventListQuery(from_date=date(2031, 6, 1), to_date=date(2031, 6, 30)),
        viewer=coach_a,
    )
    assert results == []

    fetched = await events_svc.get_event(session, ev.id)
    assert fetched is None


async def test_list_event_attendances_filters_archived_session_attendance(seeded_session):
    """§6.4 de session-coaches.md, único sitio de esta tabla que vive en un
    archivo propio de este agente (`backend/app/routers/calendar.py`
    ~547-556): las asistencias de sesión archivadas no deben aparecer como
    asistencias de evento."""
    session, coach_a, _coach_b = seeded_session
    start = datetime(2031, 7, 1, 8, 0, tzinfo=timezone.utc)

    ts = TrainingSession(
        id=60,
        club_id=CLUB_ID,
        created_by_user_id=coach_a.id,
        status=SessionStatus.PLANNED,
        scheduled_date=date(2031, 7, 1),
        scheduled_start_time=time(8, 0),
        duration_min=60,
        location="Pista",
        technical_focus="Fondo",
        session_kind=SessionKind.ENTRENAMIENTO,
    )
    session.add(ts)
    await session.flush()

    ev = CalendarEvent(
        id=6,
        club_id=CLUB_ID,
        event_type=EventType.TRAINING_SESSION,
        status=EventStatus.SCHEDULED,
        title="Sesión con roster archivado",
        start_at=start,
        end_at=start,
        all_day=False,
        created_by_user_id=coach_a.id,
        event_data={"training_session_id": ts.id},
    )
    session.add(ev)
    await session.flush()
    ts.calendar_event_id = ev.id

    active_attendance = SessionAttendance(
        session_id=ts.id, athlete_id=101, status=AttendanceStatus.PRESENTE
    )
    archived_attendance = SessionAttendance(
        session_id=ts.id,
        athlete_id=102,
        status=AttendanceStatus.AUSENTE,
        archived_at=datetime.now(timezone.utc),
    )
    session.add_all([active_attendance, archived_attendance])
    await session.commit()

    result = await list_event_attendances(
        event_id=ev.id, db=session, current_user=coach_a
    )

    athlete_ids = {row.athlete_id for row in result}
    assert athlete_ids == {101}
