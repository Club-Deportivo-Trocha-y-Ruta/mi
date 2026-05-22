"""Tests de la validación BE-2 en ``app/services/calendar/events.py``.

Verifica que:

- Crear ``competition`` sin ``race_event_id`` → ValueError (validator schema).
- Crear ``competition`` con ``race_event_id`` inexistente → ValueError
  (chequeo a nivel servicio).
- Crear no-competition con ``race_event_id`` → ValueError (validator schema).
- Update: reasignar ``race_event_id`` en un competition válido.

Estrategia: SQLite async in-memory + helper fixtures. Mockeamos
NotificationService/Dispatcher para evitar IO real.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.calendar_event import EventStatus, EventType
from app.models.user import UserRole
from app.schemas.calendar import EventCreate, EventUpdate
from app.services.calendar import events as events_svc

from tests.fixtures.race_history_fixtures import (
    create_calendar_event,
    create_club,
    create_race_event,
    create_race_series,
    create_user,
)


# ---------------------------------------------------------------------------
# Engine + factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "calendar_events",
            "event_audiences",
            "event_attendances",
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
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_event(
            s,
            event_id=10,
            series_id=1,
            sequence_number=1,
            name="V1",
        )
        await s.commit()
        yield s


def _coach_user(user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Test",
        email="coach@test.com",
        club_memberships=[],
    )


def _competition_payload(
    *,
    race_event_id: int | None = 10,
    title: str = "Valida I",
) -> EventCreate:
    start = datetime(2026, 1, 31, 8, 0, 0)
    end = datetime(2026, 1, 31, 12, 0, 0)
    return EventCreate(
        event_type=EventType.COMPETITION,
        title=title,
        start_at=start,
        end_at=end,
        event_data={"city": "Sevilla", "race_category": "A"},
        race_event_id=race_event_id,
    )


# ---------------------------------------------------------------------------
# Schema-level validations
# ---------------------------------------------------------------------------


def test_create_competition_without_race_event_id_raises():
    """A nivel SCHEMA: instanciar EventCreate competition sin race_event_id
    levanta ValidationError. El router lo traduce a HTTP 422."""
    with pytest.raises(ValidationError) as exc_info:
        EventCreate(
            event_type=EventType.COMPETITION,
            title="Valida sin race_event_id",
            start_at=datetime(2026, 1, 31, 8, 0, 0),
            end_at=datetime(2026, 1, 31, 12, 0, 0),
            event_data={"city": "Sevilla", "race_category": "A"},
            race_event_id=None,
        )
    # El mensaje debe mencionar race_event_id para que el frontend lo entienda.
    assert "race_event_id" in str(exc_info.value)


def test_create_non_competition_with_race_event_id_raises():
    """Crear un evento NO-competition con race_event_id seteado → error."""
    with pytest.raises(ValidationError) as exc_info:
        EventCreate(
            event_type=EventType.CLUB_EVENT,
            title="Asamblea con FK errónea",
            start_at=datetime(2026, 6, 1, 18, 0, 0),
            end_at=datetime(2026, 6, 1, 20, 0, 0),
            event_data={"kind": "meeting"},
            race_event_id=10,
        )
    assert "race_event_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Service-level validations (DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_competition_with_invalid_race_event_id_raises(session):
    """Si el race_event_id apunta a una fila que NO existe, el servicio
    levanta ValueError (router → HTTP 400)."""
    payload = _competition_payload(race_event_id=99999)
    coach = _coach_user()
    notif = AsyncMock()
    dispatcher = AsyncMock()

    with pytest.raises(ValueError) as exc_info:
        await events_svc.create_event(
            db=session,
            payload=payload,
            user=coach,
            club_id=1,
            notification_service=notif,
            dispatcher=dispatcher,
        )
    assert "race_event_id" in str(exc_info.value)
    assert "99999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_competition_can_reassign_race_event(session):
    """Update con race_event_id válido nuevo → reasigna sin error."""
    # Crear segundo race_event para reasignar.
    new_re = await create_race_event(
        session,
        event_id=11,
        series_id=1,
        sequence_number=2,
        name="V2",
    )
    # CalendarEvent competition ya enlazado a race_event 10.
    # NOTA: PK BigInteger; SQLite requiere id explícito.
    ev = await create_calendar_event(
        session,
        event_id=1001,
        club_id=1,
        event_type=EventType.COMPETITION,
        title="Valida I",
        race_event_id=10,
        event_data={"city": "Sevilla", "race_category": "A"},
    )
    await session.commit()

    payload = EventUpdate(race_event_id=11)
    coach = _coach_user()
    notif = AsyncMock()
    dispatcher = AsyncMock()

    updated = await events_svc.update_event(
        db=session,
        event=ev,
        payload=payload,
        user=coach,
        notification_service=notif,
        dispatcher=dispatcher,
    )
    assert updated.race_event_id == 11
