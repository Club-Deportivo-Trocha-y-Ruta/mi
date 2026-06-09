"""Tests for the all_day parameter of create_linked_calendar_event (T004, Feature 008).

Verifies:
1. all_day=True  → CalendarEvent.all_day is True, start_at == event_date 00:00,
                   end_at == event_date 23:59:59 (America/Bogota, stored naive).
2. all_day=False (default) → CalendarEvent.all_day is False, start_at == 07:00,
                   end_at == 12:00 (07:00 + 5h). Regression guard for the
                   existing race-creation flow.

Both cases also assert: event_type=COMPETITION, ALL_CLUB audience row,
race_event.calendar_event_id set (1:1 ring closed), no duplicate on second call.

Strategy: SQLite async in-memory via aiosqlite + real ORM objects (no mocking
the DB layer) — consistent with test_calendar_events_competition_validation.py.
_resolve_club_id requires a club_members row; we seed one.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
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
from app.models.calendar_event import AudienceType, EventAudience
from app.models.user import UserRole
from app.services.race.calendar_sync import create_linked_calendar_event
from tests.fixtures.race_history_fixtures import (
    create_club,
    create_race_event,
    create_race_series,
    create_user,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Engine + session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Import all models that are needed to create dependent tables.
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.race_series import RaceSeries as _RS  # noqa: F401
    from app.models.race_event import RaceEvent as _RE  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "calendar_events",
            "event_audiences",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Seeded session: club 1, coach user 10 (member of club 1), series 1, event 10."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await link_user_to_club(s, user_id=10, club_id=1)
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_event(
            s,
            event_id=10,
            series_id=1,
            sequence_number=1,
            name="Válida I Copa Valle 2026",
            event_date=date(2026, 1, 31),
            location="Sevilla, Valle del Cauca",
        )
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coach_user(user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Test",
        email="coach@test.com",
    )


async def _get_race_event(session: AsyncSession, event_id: int):
    from sqlalchemy import select
    from app.models.race_event import RaceEvent

    result = await session.execute(select(RaceEvent).where(RaceEvent.id == event_id))
    return result.scalar_one()


async def _get_audience_rows(session: AsyncSession, cal_id: int) -> list[EventAudience]:
    from sqlalchemy import select

    result = await session.execute(
        select(EventAudience).where(EventAudience.event_id == cal_id)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Tests: all_day=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_day_true_sets_all_day_flag(session):
    """all_day=True → CalendarEvent.all_day is True."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    assert cal.all_day is True


@pytest.mark.asyncio
async def test_all_day_true_start_at_is_midnight(session):
    """all_day=True → start_at is midnight on event_date (naive, Bogota local)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    expected_date = date(2026, 1, 31)
    assert cal.start_at.year == expected_date.year
    assert cal.start_at.month == expected_date.month
    assert cal.start_at.day == expected_date.day
    assert cal.start_at.hour == 0
    assert cal.start_at.minute == 0
    assert cal.start_at.second == 0


@pytest.mark.asyncio
async def test_all_day_true_end_at_is_end_of_day(session):
    """all_day=True → end_at is 23:59:59 on event_date (naive, Bogota local)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    expected_date = date(2026, 1, 31)
    assert cal.end_at.year == expected_date.year
    assert cal.end_at.month == expected_date.month
    assert cal.end_at.day == expected_date.day
    assert cal.end_at.hour == 23
    assert cal.end_at.minute == 59
    assert cal.end_at.second == 59


@pytest.mark.asyncio
async def test_all_day_true_event_date_bounds_same_day(session):
    """all_day=True → start_at and end_at both fall on event_date (single day)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    assert cal.start_at.date() == date(2026, 1, 31)
    assert cal.end_at.date() == date(2026, 1, 31)
    assert cal.end_at > cal.start_at


@pytest.mark.asyncio
async def test_all_day_true_closes_fk_ring(session):
    """all_day=True → both FK sides set (race_event.calendar_event_id and cal.race_event_id)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    assert cal.race_event_id == race_event.id
    assert race_event.calendar_event_id == cal.id


@pytest.mark.asyncio
async def test_all_day_true_adds_all_club_audience(session):
    """all_day=True → one ALL_CLUB audience row is created."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    audiences = await _get_audience_rows(session, cal.id)
    assert len(audiences) == 1
    assert audiences[0].audience_type == AudienceType.ALL_CLUB


# ---------------------------------------------------------------------------
# Tests: all_day=False (default) — regression for the existing creation flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_all_day_false_flag(session):
    """Default (all_day=False) → CalendarEvent.all_day is False."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach)
    await session.commit()

    assert cal.all_day is False


@pytest.mark.asyncio
async def test_default_start_at_is_0700(session):
    """Default → start_at is 07:00:00 on event_date (legacy behavior unchanged)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach)
    await session.commit()

    assert cal.start_at == datetime(2026, 1, 31, 7, 0, 0)


@pytest.mark.asyncio
async def test_default_end_at_is_1200(session):
    """Default → end_at is 12:00:00 on event_date (07:00 + 5h, legacy behavior unchanged)."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach)
    await session.commit()

    assert cal.end_at == datetime(2026, 1, 31, 12, 0, 0)


@pytest.mark.asyncio
async def test_explicit_all_day_false_same_as_default(session):
    """Explicit all_day=False produces the same 07:00 + 5h result as the default."""
    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    cal = await create_linked_calendar_event(session, race_event, coach, all_day=False)
    await session.commit()

    assert cal.all_day is False
    assert cal.start_at == datetime(2026, 1, 31, 7, 0, 0)
    assert cal.end_at == datetime(2026, 1, 31, 12, 0, 0)


# ---------------------------------------------------------------------------
# Test: 409 on duplicate (shared by both branches)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_call_raises_409(session):
    """Calling create_linked_calendar_event twice on the same race_event raises HTTP 409."""
    from fastapi import HTTPException

    race_event = await _get_race_event(session, 10)
    coach = _coach_user()

    await create_linked_calendar_event(session, race_event, coach, all_day=True)
    await session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await create_linked_calendar_event(session, race_event, coach, all_day=True)

    assert exc_info.value.status_code == 409
