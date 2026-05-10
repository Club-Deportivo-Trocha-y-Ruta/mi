"""Tests de permisos del módulo de calendario.

Cubre: can_view_calendar_event, can_edit_calendar_event, can_rsvp_event
para todos los roles y tipos de audiencia.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.calendar_event import AudienceType, EventType
from app.models.user import UserRole
from app.services.permissions import (
    can_edit_calendar_event,
    can_rsvp_event,
    can_view_calendar_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 1):
    u = MagicMock()
    u.id = user_id
    u.role = role
    return u


def _make_event(club_id: int = 1, event_type: EventType = EventType.CLUB_EVENT):
    ev = MagicMock()
    ev.id = 10
    ev.club_id = club_id
    ev.event_type = event_type
    ev.audiences = []
    return ev


def _async_mock_returning(value):
    return AsyncMock(return_value=value)


# ---------------------------------------------------------------------------
# can_view_calendar_event
# ---------------------------------------------------------------------------


class TestCanViewCalendarEvent:
    async def test_admin_siempre_puede(self):
        user = _make_user(UserRole.admin)
        event = _make_event()
        db = AsyncMock()

        result = await can_view_calendar_event(db, user, event)
        assert result is True

    async def test_coach_del_club_puede(self):
        user = _make_user(UserRole.coach)
        event = _make_event(club_id=1)
        db = AsyncMock()

        from app.models.club import ClubRole

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(ClubRole.coach),
        ):
            result = await can_view_calendar_event(db, user, event)

        assert result is True

    async def test_coach_de_otro_club_no_puede(self):
        user = _make_user(UserRole.coach)
        event = _make_event(club_id=99)
        db = AsyncMock()

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(None),
        ):
            result = await can_view_calendar_event(db, user, event)

        assert result is False

    async def test_padre_con_hijo_en_audiencia_puede(self):
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event()
        db = AsyncMock()

        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([3, 4]),
        ):
            with patch(
                "app.services.calendar.audiences.any_athlete_in_audience",
                _async_mock_returning(True),
            ):
                result = await can_view_calendar_event(db, user, event)

        assert result is True

    async def test_padre_sin_hijos_no_puede(self):
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event()
        db = AsyncMock()

        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([]),
        ):
            result = await can_view_calendar_event(db, user, event)

        assert result is False

    async def test_padre_hijo_fuera_de_audiencia_no_puede(self):
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event()
        db = AsyncMock()

        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([7]),
        ):
            with patch(
                "app.services.calendar.audiences.any_athlete_in_audience",
                _async_mock_returning(False),
            ):
                result = await can_view_calendar_event(db, user, event)

        assert result is False


# ---------------------------------------------------------------------------
# can_edit_calendar_event
# ---------------------------------------------------------------------------


class TestCanEditCalendarEvent:
    async def test_admin_siempre_puede_editar(self):
        user = _make_user(UserRole.admin)
        event = _make_event()
        db = AsyncMock()

        result = await can_edit_calendar_event(db, user, event)
        assert result is True

    async def test_coach_del_club_puede_editar(self):
        user = _make_user(UserRole.coach)
        event = _make_event(club_id=1)
        db = AsyncMock()

        from app.models.club import ClubRole

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(ClubRole.coach),
        ):
            result = await can_edit_calendar_event(db, user, event)

        assert result is True

    async def test_coach_de_otro_club_no_puede_editar(self):
        user = _make_user(UserRole.coach)
        event = _make_event(club_id=99)
        db = AsyncMock()

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(None),
        ):
            result = await can_edit_calendar_event(db, user, event)

        assert result is False

    async def test_padre_no_puede_editar(self):
        user = _make_user(UserRole.parent)
        event = _make_event()
        db = AsyncMock()

        result = await can_edit_calendar_event(db, user, event)
        assert result is False


# ---------------------------------------------------------------------------
# can_rsvp_event
# ---------------------------------------------------------------------------


class TestCanRSVPEvent:
    async def test_admin_puede_rsvp(self):
        user = _make_user(UserRole.admin)
        event = _make_event(event_type=EventType.CLUB_EVENT)
        db = AsyncMock()

        result = await can_rsvp_event(db, user, event, athlete_id=1)
        assert result is True

    async def test_coach_del_club_puede_rsvp(self):
        user = _make_user(UserRole.coach)
        event = _make_event(club_id=1, event_type=EventType.CLUB_EVENT)
        db = AsyncMock()

        from app.models.club import ClubRole

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(ClubRole.coach),
        ):
            result = await can_rsvp_event(db, user, event, athlete_id=1)

        assert result is True

    async def test_padre_puede_rsvp_si_hijo_en_audiencia(self):
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event(event_type=EventType.CLUB_EVENT)
        db = AsyncMock()

        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([3]),
        ):
            with patch(
                "app.services.calendar.audiences.event_visible_to_athlete",
                _async_mock_returning(True),
            ):
                result = await can_rsvp_event(db, user, event, athlete_id=3)

        assert result is True

    async def test_padre_no_puede_rsvp_training_session(self):
        """Regla: padres NO pueden RSVP en training_session events."""
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event(event_type=EventType.TRAINING_SESSION)
        db = AsyncMock()

        result = await can_rsvp_event(db, user, event, athlete_id=3)
        assert result is False

    async def test_padre_no_puede_rsvp_hijo_ajeno(self):
        """Padre no puede RSVP para atleta que no es su hijo."""
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event(event_type=EventType.CLUB_EVENT)
        db = AsyncMock()

        # Padre tiene hijo_id=3, intenta RSVP para athlete_id=99
        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([3]),
        ):
            result = await can_rsvp_event(db, user, event, athlete_id=99)

        assert result is False

    async def test_padre_no_puede_rsvp_hijo_no_en_audiencia(self):
        """Padre no puede RSVP aunque sea su hijo, si el evento no lo incluye."""
        user = _make_user(UserRole.parent, user_id=5)
        event = _make_event(event_type=EventType.COMPETITION)
        db = AsyncMock()

        with patch(
            "app.services.permissions.parent_athlete_ids",
            _async_mock_returning([3]),
        ):
            with patch(
                "app.services.calendar.audiences.event_visible_to_athlete",
                _async_mock_returning(False),
            ):
                result = await can_rsvp_event(db, user, event, athlete_id=3)

        assert result is False

    async def test_coach_de_otro_club_no_puede_rsvp(self):
        user = _make_user(UserRole.coach, user_id=9)
        event = _make_event(club_id=99, event_type=EventType.CLUB_EVENT)
        db = AsyncMock()

        with patch(
            "app.services.permissions.user_club_role",
            _async_mock_returning(None),
        ):
            result = await can_rsvp_event(db, user, event, athlete_id=1)

        assert result is False
