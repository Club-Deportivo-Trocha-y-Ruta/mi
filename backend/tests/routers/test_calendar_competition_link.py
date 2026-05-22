"""Tests del endpoint POST /api/calendar/events + GET /api/race-events/
available-for-calendar (BE-3).

Cobertura:

- POST competition sin ``race_event_id`` → 422 (validator schema).
- POST competition con ``race_event_id`` válido → 201.
- POST no-competition con ``race_event_id`` → 422.
- GET available-for-calendar excluye race_events ya enlazados.

Estrategia: SQLite async in-memory + override de auth.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import (
    get_current_user,
    get_db,
    get_notification_service,
)
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_calendar_event,
    create_club,
    create_race_event,
    create_race_series,
    create_user,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Engine + factory + client
# ---------------------------------------------------------------------------


_CALENDAR_EVENTS_DDL = """
CREATE TABLE calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id INTEGER NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    location VARCHAR(200) NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0,
    timezone VARCHAR(50) NOT NULL DEFAULT 'America/Bogota',
    event_data TEXT NULL,
    color_hex VARCHAR(7) NULL,
    race_event_id INTEGER NULL,
    created_by_user_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    CHECK (end_at >= start_at),
    CHECK (event_type != 'competition' OR race_event_id IS NOT NULL)
)
"""

_EVENT_AUDIENCES_DDL = """
CREATE TABLE event_audiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    audience_type VARCHAR(32) NOT NULL,
    audience_value TEXT NULL
)
"""

_EVENT_ATTENDANCES_DDL = """
CREATE TABLE event_attendances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    athlete_id INTEGER NOT NULL,
    rsvp_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    rsvp_at DATETIME NULL,
    rsvp_by_user_id INTEGER NULL,
    actual_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, athlete_id)
)
"""


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # calendar_events / event_audiences / event_attendances tienen PK
    # BigInteger en el modelo — SQLite no soporta AUTOINCREMENT en BigInteger,
    # así que las creamos con DDL custom (INTEGER).
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.exec_driver_sql(_CALENDAR_EVENTS_DDL)
        await conn.exec_driver_sql(_EVENT_AUDIENCES_DDL)
        await conn.exec_driver_sql(_EVENT_ATTENDANCES_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(session_factory):
    """Seed: 1 club + 1 coach con membership + 1 RaceSeries + 2 RaceEvents."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach)
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_event(
            s,
            event_id=10,
            series_id=1,
            sequence_number=1,
            name="V1",
            event_date=date(2026, 1, 31),
        )
        await create_race_event(
            s,
            event_id=11,
            series_id=1,
            sequence_number=2,
            name="V2",
            event_date=date(2026, 2, 28),
        )
        await s.commit()
    return session_factory


def _coach() -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        first_name="Coach",
        last_name="Test",
        email="coach@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)
        ],
    )


@pytest_asyncio.fixture
async def client(seeded_factory):
    """Cliente con auth=coach y notification stub."""

    async def _override_db():
        async with seeded_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _coach
    app.dependency_overrides[get_notification_service] = lambda: MagicMock()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/calendar/events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_calendar_competition_without_race_event_id_returns_422(client):
    body = {
        "event_type": "competition",
        "title": "Valida sin FK",
        "start_at": "2026-01-31T08:00:00",
        "end_at": "2026-01-31T12:00:00",
        "event_data": {"city": "Sevilla", "race_category": "A"},
        # race_event_id ausente
    }
    resp = await client.post(
        "/api/calendar/events",
        json=body,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 422
    assert "race_event_id" in resp.text


@pytest.mark.asyncio
async def test_post_calendar_competition_with_race_event_id_returns_201(client):
    body = {
        "event_type": "competition",
        "title": "Valida I",
        "start_at": "2026-01-31T08:00:00",
        "end_at": "2026-01-31T12:00:00",
        "event_data": {"city": "Sevilla", "race_category": "A"},
        "race_event_id": 10,
        "audiences": [{"audience_type": "all_club", "audience_value": {}}],
    }
    resp = await client.post(
        "/api/calendar/events",
        json=body,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 201, resp.text
    body_out = resp.json()
    assert body_out["race_event_id"] == 10
    assert body_out["event_type"] == "competition"


@pytest.mark.asyncio
async def test_post_calendar_non_competition_with_race_event_id_returns_422(client):
    """Pasar race_event_id en un evento que NO es competition → 422."""
    body = {
        "event_type": "club_event",
        "title": "Asamblea con FK errónea",
        "start_at": "2026-06-01T18:00:00",
        "end_at": "2026-06-01T20:00:00",
        "event_data": {"kind": "meeting"},
        "race_event_id": 10,
    }
    resp = await client.post(
        "/api/calendar/events",
        json=body,
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 422
    assert "race_event_id" in resp.text


# ---------------------------------------------------------------------------
# GET /api/race-events/available-for-calendar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_available_race_events_excludes_already_linked(
    seeded_factory, client
):
    """Si race_event 10 ya está enlazado a un calendar_event, solo race_event 11
    aparece en la lista de disponibles."""
    # Enlazar race_event 10 a un calendar_event ya creado.
    async with seeded_factory() as s:
        await create_calendar_event(
            s,
            event_id=2001,
            club_id=1,
            event_type="competition",  # type: ignore[arg-type]
            title="Valida I",
            race_event_id=10,
            event_data={"city": "Sevilla", "race_category": "A"},
        )
        await s.commit()

    resp = await client.get(
        "/api/race-events/available-for-calendar",
        params={"season": 2026},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200, resp.text
    available = resp.json()
    available_ids = [r["id"] for r in available]
    # 10 está enlazado → excluido. 11 sigue disponible.
    assert 10 not in available_ids
    assert 11 in available_ids
