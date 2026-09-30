"""Feature 047 — T014: per-day attendance grid (research R4/R5).

One test per rule of ``app/services/imderty/attendance_grid.py``:

- session mapping and exclusions (archived rows, planned/cancelled sessions);
- club outings / joint trainings (A/E/F, ``unknown`` blank, cancelled ignored);
- no double counting of an event linked to a ``TrainingSession``;
- competitions (result alone, attended, excused, no-show, neither);
- excluded event types;
- per-cell precedence A > E > F and multi-day events;
- active window (``club_join_date``, ``deleted_at``, inactive all month);
- naive ``start_at`` late at night stays on its local date;
- ``unrecorded`` for readiness, batch loading and the sensitive-row helper.

Self-contained aiosqlite in-memory engine with the full schema. Every name
is fictitious (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, ParentAthlete, Sex
from app.models.calendar_event import (
    ActualAttendanceStatus,
    AudienceType,
    CalendarEvent,
    EventAttendance,
    EventAudience,
    EventStatus,
    EventType,
)
from app.models.imderty import (
    AthleteImdertyProfile,
    AthleteSensitiveAuthorization,
    AthleteSensitiveData,
    ImdertyDisability,
    ImdertyEthnicity,
    ImdertyYesNo,
)
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.models.user import User, UserRole
from app.services.imderty.attendance_grid import (
    AttendanceGrid,
    active_athletes_in_range,
    build_attendance_grid,
    load_active_sensitive_data,
)
from tests.fixtures.race_history_fixtures import (
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
)

CLUB_ID = 4801
OTHER_CLUB_ID = 4802
COACH_ID = 4810
PARENT_ID = 4811

AUG_START = date(2026, 8, 1)
AUG_END = date(2026, 8, 31)
# A "today" well after August so no August day is treated as future.
TODAY = date(2026, 9, 28)

_next_athlete_id = 4900


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def grid_engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(grid_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(grid_engine, expire_on_commit=False)
    async with factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio 048", code="cf-048-a")
        await create_club(
            session, club_id=OTHER_CLUB_ID, name="Club Ficticio 048 Dos", code="cf-048-b"
        )
        await create_user(session, user_id=COACH_ID, role=UserRole.coach)
        await create_user(
            session, user_id=PARENT_ID, role=UserRole.parent,
            first_name="Acudiente", last_name="Ficticio",
        )
        await session.commit()
        yield session


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


async def _athlete(
    db: AsyncSession,
    *,
    club_id: int = CLUB_ID,
    join: date | None = None,
    deleted_at: datetime | None = None,
    birth_date: date = date(2014, 5, 2),
    sex: Sex = Sex.M,
) -> Athlete:
    global _next_athlete_id
    _next_athlete_id += 1
    athlete_id = _next_athlete_id
    await create_user(
        db, user_id=athlete_id + 10_000, role=UserRole.athlete, can_login=False
    )
    athlete = Athlete(
        id=athlete_id,
        user_id=athlete_id + 10_000,
        first_name="Deportista Ficticio",
        last_name=f"Prueba {athlete_id}",
        birth_date=birth_date,
        sex=sex,
        club_id=club_id,
        created_by=COACH_ID,
        club_join_date=join,
        deleted_at=deleted_at,
    )
    db.add(athlete)
    await db.flush()
    return athlete


async def _session(
    db: AsyncSession,
    day: date,
    marks: dict[int, AttendanceStatus],
    *,
    status: SessionStatus = SessionStatus.EXECUTED,
    club_id: int = CLUB_ID,
    archived: set[int] | None = None,
    calendar_event_id: int | None = None,
) -> TrainingSession:
    session = TrainingSession(
        club_id=club_id,
        created_by_user_id=COACH_ID,
        status=status,
        scheduled_date=day,
        scheduled_start_time=time(15, 0),
        duration_min=90,
        location="Parque ficticio",
        technical_focus="Técnica",
        calendar_event_id=calendar_event_id,
    )
    db.add(session)
    await db.flush()
    for athlete_id, mark in marks.items():
        db.add(
            SessionAttendance(
                session_id=session.id,
                athlete_id=athlete_id,
                status=mark,
                archived_at=(
                    datetime(2026, 9, 1, 12, 0)
                    if archived and athlete_id in archived
                    else None
                ),
            )
        )
    await db.flush()
    return session


async def _event(
    db: AsyncSession,
    start_at: datetime,
    end_at: datetime | None = None,
    *,
    event_type: EventType = EventType.CLUB_EVENT,
    status: EventStatus = EventStatus.COMPLETED,
    attendance: dict[int, ActualAttendanceStatus] | None = None,
    audience: list[tuple[AudienceType, dict | None]] | None = None,
    race_event_id: int | None = None,
    club_id: int = CLUB_ID,
    deleted: bool = False,
) -> CalendarEvent:
    event = CalendarEvent(
        club_id=club_id,
        event_type=event_type,
        status=status,
        title="Actividad ficticia",
        start_at=start_at,
        end_at=end_at or start_at.replace(hour=min(start_at.hour + 1, 23)),
        all_day=False,
        timezone="America/Bogota",
        created_by_user_id=COACH_ID,
        race_event_id=race_event_id,
        deleted_at=datetime(2026, 9, 1, 12, 0) if deleted else None,
    )
    db.add(event)
    await db.flush()
    for audience_type, value in audience or []:
        db.add(
            EventAudience(
                event_id=event.id, audience_type=audience_type, audience_value=value
            )
        )
    for athlete_id, actual in (attendance or {}).items():
        db.add(
            EventAttendance(
                event_id=event.id, athlete_id=athlete_id, actual_status=actual
            )
        )
    await db.flush()
    return event


async def _race(db: AsyncSession, day: date) -> int:
    """Series + category + race event on ``day``; returns the race event id."""
    await create_race_series(db, series_id=4801)
    await create_race_category(db, category_id=4801)
    await create_race_event(
        db, event_id=4801, series_id=4801, event_date=day,
        created_by_user_id=COACH_ID,
    )
    return 4801


async def _grid(db: AsyncSession, **kwargs) -> AttendanceGrid:
    await db.commit()
    return await build_attendance_grid(
        db, CLUB_ID, AUG_START, AUG_END, today=TODAY, **kwargs
    )


def _d(day: int) -> date:
    return date(2026, 8, day)


# ---------------------------------------------------------------------------
# Training sessions
# ---------------------------------------------------------------------------


async def test_session_status_mapping(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _session(db, _d(3), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(4), {athlete.id: AttendanceStatus.TARDE})
    await _session(db, _d(5), {athlete.id: AttendanceStatus.JUSTIFICADO})
    await _session(db, _d(6), {athlete.id: AttendanceStatus.LESIONADO})
    await _session(db, _d(7), {athlete.id: AttendanceStatus.AUSENTE})

    grid = await _grid(db)

    assert grid[athlete.id] == {
        _d(3): "A", _d(4): "A", _d(5): "E", _d(6): "E", _d(7): "F",
    }


async def test_archived_session_attendance_is_excluded(db: AsyncSession) -> None:
    kept = await _athlete(db)
    archived = await _athlete(db)
    await _session(
        db,
        _d(3),
        {kept.id: AttendanceStatus.PRESENTE, archived.id: AttendanceStatus.PRESENTE},
        archived={archived.id},
    )

    grid = await _grid(db)

    assert grid[kept.id] == {_d(3): "A"}
    assert grid[archived.id] == {}


async def test_planned_and_cancelled_sessions_are_excluded(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _session(
        db, _d(3), {athlete.id: AttendanceStatus.PRESENTE}, status=SessionStatus.PLANNED
    )
    await _session(
        db, _d(4), {athlete.id: AttendanceStatus.AUSENTE}, status=SessionStatus.CANCELLED
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {}


async def test_other_club_sessions_do_not_count(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _session(
        db, _d(3), {athlete.id: AttendanceStatus.PRESENTE}, club_id=OTHER_CLUB_ID
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {}


# ---------------------------------------------------------------------------
# Club outings / joint trainings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", [EventType.CLUB_EVENT, EventType.GROUP_TRAINING])
async def test_event_actual_status_mapping(
    db: AsyncSession, event_type: EventType
) -> None:
    attended = await _athlete(db)
    excused = await _athlete(db)
    no_show = await _athlete(db)
    unknown = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 9, 8, 0),
        event_type=event_type,
        attendance={
            attended.id: ActualAttendanceStatus.ATTENDED,
            excused.id: ActualAttendanceStatus.EXCUSED,
            no_show.id: ActualAttendanceStatus.NO_SHOW,
            unknown.id: ActualAttendanceStatus.UNKNOWN,
        },
    )

    grid = await _grid(db)

    assert grid[attended.id] == {_d(9): "A"}
    assert grid[excused.id] == {_d(9): "E"}
    assert grid[no_show.id] == {_d(9): "F"}
    assert grid[unknown.id] == {}
    assert grid.unrecorded == {unknown.id: {_d(9)}}


async def test_cancelled_and_deleted_events_are_ignored(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 9, 8, 0),
        status=EventStatus.CANCELLED,
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
        audience=[(AudienceType.ALL_CLUB, None)],
    )
    await _event(
        db,
        datetime(2026, 8, 10, 8, 0),
        deleted=True,
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
        audience=[(AudienceType.ALL_CLUB, None)],
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {}
    assert grid.unrecorded == {}


async def test_event_linked_to_session_is_not_counted_twice(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    event = await _event(
        db,
        datetime(2026, 8, 12, 8, 0),
        event_type=EventType.GROUP_TRAINING,
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
        audience=[(AudienceType.ALL_CLUB, None)],
    )
    # The linked session is the source of truth: the athlete was absent there.
    await _session(
        db, _d(12), {athlete.id: AttendanceStatus.AUSENTE}, calendar_event_id=event.id
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(12): "F"}
    assert grid.unrecorded == {}


# ---------------------------------------------------------------------------
# Competitions
# ---------------------------------------------------------------------------


async def test_competition_rules(db: AsyncSession) -> None:
    result_only = await _athlete(db)
    attended_no_result = await _athlete(db)
    excused = await _athlete(db)
    no_show = await _athlete(db)
    neither = await _athlete(db)
    race_event_id = await _race(db, _d(16))
    await create_race_competitor(db, competitor_id=4801, athlete_id=result_only.id)
    await create_race_result(
        db,
        event_id=race_event_id,
        category_id=4801,
        competitor_id=4801,
        athlete_id=result_only.id,
        created_by_user_id=COACH_ID,
    )
    await _event(
        db,
        datetime(2026, 8, 16, 7, 0),
        event_type=EventType.COMPETITION,
        race_event_id=race_event_id,
        attendance={
            attended_no_result.id: ActualAttendanceStatus.ATTENDED,
            excused.id: ActualAttendanceStatus.EXCUSED,
            no_show.id: ActualAttendanceStatus.NO_SHOW,
        },
    )

    grid = await _grid(db)

    assert grid[result_only.id] == {_d(16): "A"}
    assert grid[attended_no_result.id] == {_d(16): "A"}
    assert grid[excused.id] == {_d(16): "E"}
    assert grid[no_show.id] == {_d(16): "F"}
    assert grid[neither.id] == {}


async def test_result_wins_over_no_show_on_competition_day(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    race_event_id = await _race(db, _d(16))
    await create_race_competitor(db, competitor_id=4801, athlete_id=athlete.id)
    await create_race_result(
        db, event_id=race_event_id, category_id=4801, competitor_id=4801,
        athlete_id=athlete.id, created_by_user_id=COACH_ID,
    )
    await _event(
        db,
        datetime(2026, 8, 16, 7, 0),
        event_type=EventType.COMPETITION,
        race_event_id=race_event_id,
        attendance={athlete.id: ActualAttendanceStatus.NO_SHOW},
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(16): "A"}


async def test_soft_deleted_race_result_does_not_count(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    race_event_id = await _race(db, _d(16))
    await create_race_competitor(db, competitor_id=4801, athlete_id=athlete.id)
    await create_race_result(
        db, event_id=race_event_id, category_id=4801, competitor_id=4801,
        athlete_id=athlete.id, created_by_user_id=COACH_ID,
        deleted_at=datetime(2026, 8, 20, 12, 0),
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {}


# ---------------------------------------------------------------------------
# Excluded event types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.PERSONAL_TRAINING,
        EventType.REST_DAY,
        EventType.BIRTHDAY,
        EventType.TRAINING_SESSION,
    ],
)
async def test_excluded_event_types(db: AsyncSession, event_type: EventType) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 9, 8, 0),
        event_type=event_type,
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
        audience=[(AudienceType.ALL_CLUB, None)],
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {}
    assert grid.unrecorded == {}


# ---------------------------------------------------------------------------
# Per-cell rules
# ---------------------------------------------------------------------------


async def test_precedence_a_over_e_over_f(db: AsyncSession) -> None:
    e_over_f = await _athlete(db)
    a_over_e = await _athlete(db)
    await _session(
        db,
        _d(20),
        {e_over_f.id: AttendanceStatus.AUSENTE, a_over_e.id: AttendanceStatus.JUSTIFICADO},
    )
    await _event(
        db,
        datetime(2026, 8, 20, 16, 0),
        attendance={
            e_over_f.id: ActualAttendanceStatus.EXCUSED,
            a_over_e.id: ActualAttendanceStatus.ATTENDED,
        },
    )
    # A later F must never overwrite an earlier A.
    await _session(db, _d(20), {a_over_e.id: AttendanceStatus.AUSENTE})

    grid = await _grid(db)

    assert grid[e_over_f.id] == {_d(20): "E"}
    assert grid[a_over_e.id] == {_d(20): "A"}


async def test_precedence_holds_when_the_weaker_mark_comes_later(
    db: AsyncSession,
) -> None:
    # Sessions are merged before events: a later event F/E must not overwrite.
    a_then_f = await _athlete(db)
    e_then_f = await _athlete(db)
    await _session(
        db,
        _d(21),
        {a_then_f.id: AttendanceStatus.PRESENTE, e_then_f.id: AttendanceStatus.LESIONADO},
    )
    await _event(
        db,
        datetime(2026, 8, 21, 16, 0),
        attendance={
            a_then_f.id: ActualAttendanceStatus.NO_SHOW,
            e_then_f.id: ActualAttendanceStatus.NO_SHOW,
        },
    )

    grid = await _grid(db)

    assert grid[a_then_f.id] == {_d(21): "A"}
    assert grid[e_then_f.id] == {_d(21): "E"}


async def test_multi_day_event_marks_each_in_month_day(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 30, 6, 0),
        datetime(2026, 9, 1, 18, 0),
        event_type=EventType.GROUP_TRAINING,
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(30): "A", _d(31): "A"}


async def test_multi_day_event_started_last_month_marks_in_month_days(
    db: AsyncSession,
) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 7, 31, 6, 0),
        datetime(2026, 8, 1, 18, 0),
        attendance={athlete.id: ActualAttendanceStatus.EXCUSED},
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(1): "E"}


# ---------------------------------------------------------------------------
# Active window (R5)
# ---------------------------------------------------------------------------


async def test_join_date_after_day_ten_blanks_earlier_days(db: AsyncSession) -> None:
    athlete = await _athlete(db, join=_d(11))
    await _session(db, _d(5), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(11), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(15), {athlete.id: AttendanceStatus.AUSENTE})

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(11): "A", _d(15): "F"}


async def test_deleted_on_day_twenty_blanks_later_days(db: AsyncSession) -> None:
    athlete = await _athlete(db, deleted_at=datetime(2026, 8, 20, 15, 0))
    await _session(db, _d(19), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(20), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(21), {athlete.id: AttendanceStatus.PRESENTE})

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(19): "A"}


async def test_deleted_at_is_utc_and_resolved_to_bogota_date(db: AsyncSession) -> None:
    # 02:00 UTC on the 21st is 21:00 on the 20th in Bogotá.
    athlete = await _athlete(db, deleted_at=datetime(2026, 8, 21, 2, 0))
    await _session(db, _d(19), {athlete.id: AttendanceStatus.PRESENTE})
    await _session(db, _d(20), {athlete.id: AttendanceStatus.PRESENTE})

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(19): "A"}


async def test_athlete_inactive_all_month_is_excluded(db: AsyncSession) -> None:
    active = await _athlete(db)
    joined_later = await _athlete(db, join=date(2026, 9, 1))
    archived_before = await _athlete(db, deleted_at=datetime(2026, 7, 20, 12, 0))
    archived_on_first = await _athlete(db, deleted_at=datetime(2026, 8, 1, 12, 0))
    other_club = await _athlete(db, club_id=OTHER_CLUB_ID)
    await db.commit()

    athletes = await active_athletes_in_range(db, CLUB_ID, AUG_START, AUG_END)
    grid = await _grid(db)

    assert [a.id for a in athletes] == [active.id]
    assert set(grid) == {active.id}
    for excluded in (joined_later, archived_before, archived_on_first, other_club):
        assert excluded.id not in grid


async def test_athlete_archived_mid_month_is_still_listed(db: AsyncSession) -> None:
    athlete = await _athlete(db, deleted_at=datetime(2026, 8, 20, 15, 0))
    await db.commit()

    athletes = await active_athletes_in_range(db, CLUB_ID, AUG_START, AUG_END)

    assert [a.id for a in athletes] == [athlete.id]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


async def test_naive_start_at_late_evening_stays_on_local_date(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 14, 23, 30),
        datetime(2026, 8, 14, 23, 59),
        attendance={athlete.id: ActualAttendanceStatus.ATTENDED},
    )

    grid = await _grid(db)

    assert grid[athlete.id] == {_d(14): "A"}


# ---------------------------------------------------------------------------
# Unrecorded (readiness)
# ---------------------------------------------------------------------------


async def test_unrecorded_lists_audience_members_without_record(
    db: AsyncSession,
) -> None:
    in_list = await _athlete(db)
    recorded = await _athlete(db)
    outside = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 22, 8, 0),
        audience=[(AudienceType.ATHLETE_LIST, {"athlete_ids": [in_list.id, recorded.id]})],
        attendance={recorded.id: ActualAttendanceStatus.ATTENDED},
    )

    grid = await _grid(db)

    assert grid.unrecorded == {in_list.id: {_d(22)}}
    assert grid[in_list.id] == {}
    assert grid[outside.id] == {}


async def test_unrecorded_skips_days_with_a_mark_and_inactive_days(
    db: AsyncSession,
) -> None:
    trained = await _athlete(db)
    joined_late = await _athlete(db, join=_d(25))
    await _session(db, _d(22), {trained.id: AttendanceStatus.PRESENTE})
    await _event(
        db,
        datetime(2026, 8, 22, 16, 0),
        audience=[(AudienceType.ALL_CLUB, None)],
    )

    grid = await _grid(db)

    assert grid[trained.id] == {_d(22): "A"}
    assert grid.unrecorded == {}
    assert joined_late.id not in grid.unrecorded


async def test_unrecorded_ignores_future_days(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _event(
        db,
        datetime(2026, 8, 22, 8, 0),
        audience=[(AudienceType.INDIVIDUAL, {"athlete_id": athlete.id})],
    )
    await db.commit()

    grid = await build_attendance_grid(
        db, CLUB_ID, AUG_START, AUG_END, today=_d(21)
    )

    assert grid.unrecorded == {}


async def test_unrecorded_category_audience(db: AsyncSession) -> None:
    # Same birth year and sex → same FCC category; a different sex does not match.
    target = await _athlete(db, birth_date=date(2014, 1, 3), sex=Sex.F)
    other = await _athlete(db, birth_date=date(2014, 1, 3), sex=Sex.M)
    from app.services.category import get_category

    category = get_category(2014, Sex.F.value)
    assert get_category(2014, Sex.M.value) != category
    await _event(
        db,
        datetime(2026, 8, 23, 8, 0),
        audience=[(AudienceType.CATEGORY, {"category": category})],
    )

    grid = await _grid(db)

    assert grid.unrecorded == {target.id: {_d(23)}}
    assert other.id not in grid.unrecorded


async def test_grid_is_a_plain_mapping_by_athlete(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _session(db, _d(3), {athlete.id: AttendanceStatus.PRESENTE})

    grid = await _grid(db)

    assert isinstance(grid, dict)
    assert dict(grid) == {athlete.id: {_d(3): "A"}}


async def test_grid_accepts_preloaded_athletes(db: AsyncSession) -> None:
    athlete = await _athlete(db)
    await _session(db, _d(3), {athlete.id: AttendanceStatus.PRESENTE})
    await db.commit()
    athletes = await active_athletes_in_range(db, CLUB_ID, AUG_START, AUG_END)

    grid = await build_attendance_grid(
        db, CLUB_ID, AUG_START, AUG_END, athletes=athletes, today=TODAY
    )

    assert grid == {athlete.id: {_d(3): "A"}}


# ---------------------------------------------------------------------------
# Batch loading
# ---------------------------------------------------------------------------


async def test_active_athletes_batch_loads_profile_and_guardians(
    db: AsyncSession,
) -> None:
    athlete = await _athlete(db)
    db.add(AthleteImdertyProfile(athlete_id=athlete.id, phone="3000000000"))
    await link_parent_to_athlete(db, parent_user_id=PARENT_ID, athlete_id=athlete.id)
    parent = await db.get(User, PARENT_ID)
    assert parent is not None
    parent.phone = "3110000000"
    await db.commit()
    db.expunge_all()

    athletes = await active_athletes_in_range(db, CLUB_ID, AUG_START, AUG_END)
    db.expunge_all()  # any lazy load past this point would raise

    [loaded] = athletes
    assert loaded.imderty_profile is not None
    assert loaded.imderty_profile.phone == "3000000000"
    assert loaded.imderty_profile.barrio is None
    [link] = loaded.parents
    assert isinstance(link, ParentAthlete)
    assert link.parent.phone == "3110000000"


async def test_load_active_sensitive_data_only_returns_authorized_rows(
    db: AsyncSession,
) -> None:
    authorized = await _athlete(db)
    withdrawn = await _athlete(db)
    no_row = await _athlete(db)

    active_auth = AthleteSensitiveAuthorization(
        athlete_id=authorized.id,
        guardian_user_id=PARENT_ID,
        authorized_on=date(2026, 8, 1),
        recorded_by_user_id=COACH_ID,
        active_key=authorized.id,
    )
    withdrawn_auth = AthleteSensitiveAuthorization(
        athlete_id=withdrawn.id,
        guardian_user_id=PARENT_ID,
        authorized_on=date(2026, 8, 1),
        recorded_by_user_id=COACH_ID,
        withdrawn_at=datetime(2026, 8, 10, 12, 0),
        withdrawn_by_user_id=COACH_ID,
        active_key=None,
    )
    db.add_all([active_auth, withdrawn_auth])
    await db.flush()
    db.add(
        AthleteSensitiveData(
            athlete_id=authorized.id,
            authorization_id=active_auth.id,
            ethnicity=ImdertyEthnicity.NO_SABE_NO_RESPONDE,
            disability=ImdertyDisability.NA,
            conflict_victim=ImdertyYesNo.no,
        )
    )
    # A stale row whose authorization was withdrawn must never be returned.
    db.add(
        AthleteSensitiveData(
            athlete_id=withdrawn.id,
            authorization_id=withdrawn_auth.id,
        )
    )
    await db.commit()

    rows = await load_active_sensitive_data(
        db, [authorized.id, withdrawn.id, no_row.id]
    )

    assert set(rows) == {authorized.id}
    assert rows[authorized.id].conflict_victim == ImdertyYesNo.no
    assert await load_active_sensitive_data(db, []) == {}
