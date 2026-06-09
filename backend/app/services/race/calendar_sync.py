"""Bidirectional 1:1 calendar sync for race_events (Feature 007, Wave E, US5).

The race_event is the **source of truth** in all cases:
- ``create_linked_calendar_event`` → create a new COMPETITION CalendarEvent and
  set both FK sides (race_events.calendar_event_id and
  calendar_events.race_event_id).
- ``propagate_to_calendar`` → when name/event_date/location/status change on the
  race_event, mirror the change to the linked CalendarEvent.
- ``link_existing_calendar_event`` → associate an existing COMPETITION
  CalendarEvent with a race_event (strict 1:1).

All three functions operate inside the caller's transaction (they call
``db.flush()`` but never ``db.commit()``).  The router / service layer is
responsible for the final commit.

Privacy (Ley 1581):
- Logs emit IDs only.  No names, locations, or notes in log messages.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import (
    AudienceType,
    CalendarEvent,
    EventAudience,
    EventStatus,
    EventType,
)
from app.models.race_event import RaceEvent, RaceEventStatus

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)

# Default race start time (07:00 local) and duration (5 hours) when no
# existing calendar event provides a reference time.
_DEFAULT_START_TIME = time(7, 0, 0)
_DEFAULT_DURATION_HOURS = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_club_id(db: AsyncSession, user: "User") -> int:
    """Return the first club_id the user belongs to.

    Race events are not club-scoped in the DB, but CalendarEvents are.
    For the sync path we pick the user's primary club membership.

    Raises HTTP 422 if the user has no club membership.
    """
    from app.models.club import ClubMember

    result = await db.execute(
        select(ClubMember.club_id).where(ClubMember.user_id == user.id).limit(1)
    )
    club_id = result.scalar_one_or_none()
    if club_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "El usuario no pertenece a ningún club. "
                "No se puede crear el evento de calendario."
            ),
        )
    return club_id


def _race_status_to_event_status(race_status: RaceEventStatus) -> EventStatus:
    """Map RaceEventStatus → EventStatus.

    - CANCELLED → CANCELLED
    - COMPLETED → COMPLETED
    - SCHEDULED → SCHEDULED (default)
    """
    if race_status == RaceEventStatus.CANCELLED:
        return EventStatus.CANCELLED
    if race_status == RaceEventStatus.COMPLETED:
        return EventStatus.COMPLETED
    return EventStatus.SCHEDULED


def _build_start_end(event_date, existing_cal: CalendarEvent | None):
    """Derive start_at / end_at for the CalendarEvent.

    If *existing_cal* is provided, preserve the existing time-of-day and
    duration (only the date changes).  Otherwise use the default start time
    and duration.
    """
    if existing_cal is not None:
        start = existing_cal.start_at.replace(
            year=event_date.year,
            month=event_date.month,
            day=event_date.day,
        )
        duration = existing_cal.end_at - existing_cal.start_at
        end = start + duration
    else:
        start = datetime.combine(event_date, _DEFAULT_START_TIME)
        from datetime import timedelta
        end = start + timedelta(hours=_DEFAULT_DURATION_HOURS)
    return start, end


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def create_linked_calendar_event(
    db: AsyncSession,
    race_event: RaceEvent,
    user: "User",
) -> CalendarEvent:
    """Create a COMPETITION CalendarEvent and establish a strict 1:1 link.

    - Creates ``calendar_events`` row (event_type=competition, audiences=ALL_CLUB).
    - Sets ``calendar_events.race_event_id = race_event.id``.
    - Sets ``race_events.calendar_event_id = <new_cal.id>``.

    Raises:
      HTTP 409 — if the race_event already has a calendar_event_id set.

    The new CalendarEvent is added to the session but NOT committed; the
    caller owns the transaction boundary.

    Audience default: ALL_CLUB (single row in event_audiences).
    """
    if race_event.calendar_event_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La válida id={race_event.id} ya está vinculada al "
                f"evento de calendario id={race_event.calendar_event_id}."
            ),
        )

    club_id = await _resolve_club_id(db, user)
    start_at, end_at = _build_start_end(race_event.event_date, None)
    event_status = _race_status_to_event_status(race_event.status)

    # IDs are assigned by the database (autoincrement) on both MySQL and
    # SQLite — same pattern as services/calendar/events.py::create_event.
    cal = CalendarEvent(
        club_id=club_id,
        event_type=EventType.COMPETITION,
        status=event_status,
        title=race_event.name,
        location=race_event.location,
        start_at=start_at,
        end_at=end_at,
        race_event_id=race_event.id,
        created_by_user_id=user.id,
    )
    db.add(cal)
    await db.flush()  # obtain cal.id (confirms the insert succeeded)

    # Add ALL_CLUB audience row
    db.add(
        EventAudience(
            event_id=cal.id,
            audience_type=AudienceType.ALL_CLUB,
            audience_value={},
        )
    )

    # Close the 1:1 ring: race_event → calendar_event
    race_event.calendar_event_id = cal.id
    await db.flush()

    logger.info(
        "race_event_calendar_created race_event_id=%s cal_id=%s club_id=%s user_id=%s",
        race_event.id,
        cal.id,
        club_id,
        user.id,
    )
    return cal


async def propagate_to_calendar(
    db: AsyncSession,
    race_event: RaceEvent,
    changed_fields: set[str],
) -> None:
    """Propagate race_event changes to the linked CalendarEvent (race_event is source of truth).

    Fields propagated:
      - ``name``       → ``CalendarEvent.title``
      - ``location``   → ``CalendarEvent.location``
      - ``event_date`` → ``CalendarEvent.start_at`` / ``end_at`` (preserving time-of-day)
      - ``status``     → ``CalendarEvent.status`` via ``_race_status_to_event_status``

    Does nothing if no CalendarEvent is linked (not an error).

    Calls ``db.flush()`` before returning; does NOT commit.

    Args:
      db: async SQLAlchemy session (within caller's transaction).
      race_event: already-updated RaceEvent ORM object.
      changed_fields: set of field names that were modified in this update.
    """
    _PROPAGATABLE = {"name", "location", "event_date", "status"}
    if not (_PROPAGATABLE & changed_fields):
        return

    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.race_event_id == race_event.id)
    )
    cal = result.scalar_one_or_none()
    if cal is None:
        return

    if "name" in changed_fields:
        cal.title = race_event.name
    if "location" in changed_fields:
        cal.location = race_event.location
    if "event_date" in changed_fields and race_event.event_date is not None:
        _, end_at = _build_start_end(race_event.event_date, cal)
        start_at, _ = _build_start_end(race_event.event_date, cal)
        cal.start_at = start_at
        cal.end_at = end_at
    if "status" in changed_fields:
        cal.status = _race_status_to_event_status(race_event.status)

    await db.flush()
    logger.info(
        "race_event_calendar_propagated race_event_id=%s cal_id=%s fields=%s",
        race_event.id,
        cal.id,
        sorted(changed_fields & _PROPAGATABLE),
    )


async def link_existing_calendar_event(
    db: AsyncSession,
    race_event: RaceEvent,
    calendar_event_id: int,
    user: "User",
) -> CalendarEvent:
    """Associate an existing CalendarEvent with a RaceEvent (strict 1:1).

    Preconditions enforced (raises HTTP 409 on violation):
    1. The race_event MUST NOT already have a calendar_event_id set.
    2. The CalendarEvent MUST exist — raises 404 if not.
    3. The CalendarEvent MUST be of type COMPETITION.
    4. The CalendarEvent MUST NOT already be linked to a different race_event.

    On success:
    - Sets ``calendar_events.race_event_id = race_event.id``.
    - Sets ``race_events.calendar_event_id = calendar_event_id``.
    - Calls ``db.flush()`` but does NOT commit.
    """
    # 1. race_event must not already be linked
    if race_event.calendar_event_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La válida id={race_event.id} ya está vinculada al "
                f"evento de calendario id={race_event.calendar_event_id}. "
                "Desasóciale primero."
            ),
        )

    # 2. target CalendarEvent must exist
    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.id == calendar_event_id)
    )
    cal = result.scalar_one_or_none()
    if cal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento de calendario id={calendar_event_id} no existe.",
        )

    # 3. must be a competition-type event
    if cal.event_type != EventType.COMPETITION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El evento de calendario id={calendar_event_id} no es de tipo "
                "'competition'. Solo se puede vincular un evento de tipo competition."
            ),
        )

    # 4. CalendarEvent must not already reference a DIFFERENT race_event.
    #    If it already points to this same race_event (idempotent), we proceed
    #    (only the race_events.calendar_event_id side needs to be set).
    if cal.race_event_id is not None and cal.race_event_id != race_event.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El evento de calendario id={calendar_event_id} ya está vinculado "
                f"a la válida id={cal.race_event_id}. Estricto 1:1."
            ),
        )

    # Establish the link on both sides (idempotent if cal already points here)
    cal.race_event_id = race_event.id
    race_event.calendar_event_id = cal.id
    await db.flush()

    logger.info(
        "race_event_calendar_linked race_event_id=%s cal_id=%s user_id=%s",
        race_event.id,
        cal.id,
        user.id,
    )
    return cal
