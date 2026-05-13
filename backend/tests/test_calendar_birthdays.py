"""Tests del servicio de cumpleaños virtuales.

Cubre:
- Codificación/decodificación de IDs negativos.
- birthday_in_year (incluyendo 29-feb en años no bisiestos).
- list_birthday_events_in_range con/sin filtro de atletas.
- get_birthday_event reconstruye desde ID negativo.
- Bloqueos del router: POST/PATCH/DELETE/RSVP a BIRTHDAY → 400.
- Visibilidad: todos los miembros del club ven todos los cumples.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.calendar_event import EventStatus, EventType
from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.calendar.birthdays import (
    birthday_in_year,
    decode_birthday_id,
    encode_birthday_id,
    get_birthday_event,
    is_birthday_id,
    list_birthday_events_in_range,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_athlete(id_: int, club_id: int = 1, birth: date = date(2013, 7, 15)):
    a = MagicMock()
    a.id = id_
    a.club_id = club_id
    a.first_name = "Santiago"
    a.last_name = "García"
    a.birth_date = birth
    return a


# ---------------------------------------------------------------------------
# Codificación
# ---------------------------------------------------------------------------


class TestEncoding:
    def test_encode_decode_round_trip(self):
        for year in (2024, 2026, 2030, 1999):
            for athlete_id in (1, 42, 999_999):
                eid = encode_birthday_id(year, athlete_id)
                assert eid < 0
                assert decode_birthday_id(eid) == (year, athlete_id)

    def test_decode_positive_id_returns_none(self):
        assert decode_birthday_id(1) is None
        assert decode_birthday_id(0) is None

    def test_is_birthday_id_true_for_negative(self):
        assert is_birthday_id(encode_birthday_id(2026, 42)) is True

    def test_is_birthday_id_false_for_positive(self):
        assert is_birthday_id(123) is False

    def test_year_out_of_range_returns_none(self):
        assert decode_birthday_id(-(1800 * 1_000_000 + 1)) is None
        assert decode_birthday_id(-(2200 * 1_000_000 + 1)) is None


# ---------------------------------------------------------------------------
# birthday_in_year
# ---------------------------------------------------------------------------


class TestBirthdayInYear:
    def test_regular_date(self):
        assert birthday_in_year(date(2013, 7, 15), 2026) == date(2026, 7, 15)

    def test_29_feb_leap_year(self):
        assert birthday_in_year(date(2012, 2, 29), 2024) == date(2024, 2, 29)

    def test_29_feb_non_leap_year_shifts_to_28(self):
        assert birthday_in_year(date(2012, 2, 29), 2026) == date(2026, 2, 28)
        assert birthday_in_year(date(2012, 2, 29), 2025) == date(2025, 2, 28)


# ---------------------------------------------------------------------------
# list_birthday_events_in_range
# ---------------------------------------------------------------------------


class TestListBirthdays:
    async def test_evento_dentro_del_rango(self):
        athletes = [_make_athlete(1, birth=date(2013, 6, 15))]
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = athletes
        db.execute = AsyncMock(return_value=result_mock)

        events = await list_birthday_events_in_range(
            db, club_id=1,
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
        )

        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == EventType.BIRTHDAY
        assert ev.all_day is True
        assert ev.start_at.date() == date(2026, 6, 15)
        assert ev.event_data["athlete_id"] == 1
        assert ev.event_data["age_turning"] == 13
        assert "Santiago" in ev.title

    async def test_evento_fuera_del_rango_se_omite(self):
        athletes = [_make_athlete(1, birth=date(2013, 6, 15))]
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = athletes
        db.execute = AsyncMock(return_value=result_mock)

        events = await list_birthday_events_in_range(
            db, club_id=1,
            from_date=date(2026, 7, 1), to_date=date(2026, 7, 31),
        )
        assert events == []

    async def test_rango_cruza_year_boundary_emite_dos_anyos(self):
        athletes = [_make_athlete(1, birth=date(2013, 1, 5))]
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = athletes
        db.execute = AsyncMock(return_value=result_mock)

        # Diciembre 2025 - Febrero 2026 cubre el cumpleaños 2026-01-05
        events = await list_birthday_events_in_range(
            db, club_id=1,
            from_date=date(2025, 12, 1), to_date=date(2026, 2, 28),
        )
        assert len(events) == 1
        assert events[0].start_at.date() == date(2026, 1, 5)

    async def test_athlete_ids_filter_restringe(self):
        # Solo el atleta filtrado debe aparecer
        athletes = [_make_athlete(42, birth=date(2013, 6, 15))]
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = athletes
        db.execute = AsyncMock(return_value=result_mock)

        events = await list_birthday_events_in_range(
            db, club_id=1,
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
            athlete_ids=[42],
        )
        assert len(events) == 1
        assert events[0].event_data["athlete_id"] == 42

    async def test_athlete_ids_vacio_retorna_vacio_sin_query(self):
        db = MagicMock()
        db.execute = AsyncMock()
        events = await list_birthday_events_in_range(
            db, club_id=1,
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30),
            athlete_ids=[],
        )
        assert events == []
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# get_birthday_event
# ---------------------------------------------------------------------------


class TestGetBirthdayEvent:
    async def test_reconstruye_evento_desde_id_negativo(self):
        athlete = _make_athlete(7, birth=date(2014, 3, 22))
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = athlete
        db.execute = AsyncMock(return_value=result_mock)

        eid = encode_birthday_id(2026, 7)
        ev = await get_birthday_event(db, eid)

        assert ev is not None
        assert ev.event_type == EventType.BIRTHDAY
        assert ev.id == eid
        assert ev.start_at.date() == date(2026, 3, 22)
        assert ev.event_data["athlete_id"] == 7
        assert ev.event_data["age_turning"] == 12

    async def test_id_positivo_retorna_none(self):
        db = MagicMock()
        assert await get_birthday_event(db, 123) is None

    async def test_athlete_inexistente_retorna_none(self):
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        eid = encode_birthday_id(2026, 99999)
        assert await get_birthday_event(db, eid) is None


# ---------------------------------------------------------------------------
# Router: bloqueos de mutación sobre BIRTHDAY
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


def _coach_user():
    m = SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)
    return SimpleNamespace(
        id=1, first_name="Coach", last_name="X", email="c@test.com",
        role=UserRole.coach, can_login=True, is_active=True,
        club_memberships=[m],
    )


def _virtual_birthday_event():
    """Simula el SimpleNamespace devuelto por get_birthday_event."""
    return SimpleNamespace(
        id=encode_birthday_id(2026, 42),
        club_id=1,
        event_type=EventType.BIRTHDAY,
        status=EventStatus.SCHEDULED,
        title="🎂 Cumpleaños de Santiago",
        description=None,
        location=None,
        start_at=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 15, 23, 59, 59, tzinfo=timezone.utc),
        all_day=True,
        timezone="America/Bogota",
        event_data={"athlete_id": 42, "athlete_first_name": "Santiago", "age_turning": 13},
        color_hex=None,
        created_by_user_id=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        audiences=[],
        attendances=[],
    )


class TestBirthdayMutationsBlocked:
    async def test_post_birthday_retorna_400(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        body = {
            "event_type": "birthday",
            "title": "X",
            "start_at": "2026-06-15T00:00:00",
            "end_at": "2026-06-15T23:59:59",
            "audiences": [{"audience_type": "all_club", "audience_value": {}}],
        }
        resp = await client.post(
            "/api/calendar/events",
            json=body,
            headers={"Authorization": "Bearer fake"},
        )
        assert resp.status_code == 400
        assert "automáticamente" in resp.json()["detail"]

    async def test_patch_birthday_retorna_400(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        ev = _virtual_birthday_event()
        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=ev),
        ):
            resp = await client.patch(
                f"/api/calendar/events/{ev.id}",
                json={"title": "Nuevo"},
                headers={"Authorization": "Bearer fake"},
            )
        assert resp.status_code == 400
        assert "automáticos" in resp.json()["detail"]

    async def test_delete_birthday_retorna_400(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        ev = _virtual_birthday_event()
        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=ev),
        ):
            resp = await client.delete(
                f"/api/calendar/events/{ev.id}",
                headers={"Authorization": "Bearer fake"},
            )
        assert resp.status_code == 400

    async def test_rsvp_birthday_retorna_400(self, client: AsyncClient):
        app.dependency_overrides[get_current_user] = _coach_user
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        ev = _virtual_birthday_event()
        with patch(
            "app.services.calendar.events.get_event",
            AsyncMock(return_value=ev),
        ):
            resp = await client.post(
                f"/api/calendar/events/{ev.id}/rsvp",
                json={"athlete_id": 42, "rsvp_status": "accepted"},
                headers={"Authorization": "Bearer fake"},
            )
        assert resp.status_code == 400
