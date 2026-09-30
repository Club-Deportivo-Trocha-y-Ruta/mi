"""Per-day attendance marks for the IMDERTY sheet (feature 047, research R4/R5).

Pure data service: it reads recorded attendance and returns, per athlete, a
``{date: "A" | "E" | "F"}`` mapping for a date range. A blank cell is an
absent key. Nothing is written and nothing is logged about any athlete.

Sources (R4), merged per cell with precedence A > E > F:

1. **Training sessions** — ``TrainingSession.status == executed`` of the club,
   ``SessionAttendance.archived_at IS NULL``; day = ``scheduled_date``.
   presente/tarde → A, justificado/lesionado → E, ausente → F.
2. **Club outings / joint trainings** — ``CalendarEvent`` of type
   ``club_event``/``group_training``, not cancelled, not soft-deleted, and not
   linked to a ``TrainingSession`` (same ``not_in(linked_event_ids)`` guard as
   ``training/reports.py::get_conjoint_sessions``; the linked session already
   counts). ``EventAttendance.actual_status`` attended → A, excused → E,
   no_show → F, unknown → blank. The single status applies to every day of a
   multi-day event that falls in the range.
3. **Competitions** — a ``RaceResult`` (not soft-deleted) of a club athlete on
   ``RaceEvent.event_date`` → A (``_resolve_race_dates`` generalized to
   ``(athlete_id, event_date)``); plus the competition ``CalendarEvent``'s
   ``EventAttendance`` mapped as above, so "result or attended" → A.

``personal_training``, ``rest_day``, ``birthday`` and ``training_session``
events never count (the last are covered by ``session_attendance``).

Dates: ``CalendarEvent.start_at``/``end_at`` are naive Bogotá wall-clock
values, so ``.date()`` is taken directly — never ``astimezone()`` first.
``scheduled_date`` and ``event_date`` are already local dates.
``Athlete.deleted_at`` is written as UTC (``athlete_scope.archive_athlete``),
so it *is* converted to Bogotá before taking its date.

Active window (R5): an athlete is active on day D when
``(club_join_date IS NULL OR club_join_date <= D) AND
(deleted_at IS NULL OR local_date(deleted_at) > D)``. Days outside the window
stay blank; an athlete inactive the whole range is left out.

Privacy (Ley 1581): the sensitive block is loaded by a separate helper
(``load_active_sensitive_data``) and never through an ``Athlete`` relationship,
so it cannot leak into any code path that merely loads athletes.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete, ParentAthlete
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
)
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionStatus,
    TrainingSession,
)
from app.services.category import get_category

Mark = Literal["A", "E", "F"]

BOGOTA = ZoneInfo("America/Bogota")

_PRECEDENCE: dict[Mark, int] = {"A": 3, "E": 2, "F": 1}

_SESSION_MARKS: dict[AttendanceStatus, Mark] = {
    AttendanceStatus.PRESENTE: "A",
    AttendanceStatus.TARDE: "A",
    AttendanceStatus.JUSTIFICADO: "E",
    AttendanceStatus.LESIONADO: "E",
    AttendanceStatus.AUSENTE: "F",
}

_EVENT_MARKS: dict[ActualAttendanceStatus, Mark] = {
    ActualAttendanceStatus.ATTENDED: "A",
    ActualAttendanceStatus.EXCUSED: "E",
    ActualAttendanceStatus.NO_SHOW: "F",
}

# Calendar event types that count as attendance (R4). Everything else
# (personal_training, rest_day, birthday, training_session) is excluded.
_COUNTED_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.CLUB_EVENT,
    EventType.GROUP_TRAINING,
    EventType.COMPETITION,
)


class AttendanceGrid(dict[int, dict[date, Mark]]):
    """``{athlete_id: {date: Mark}}`` for every athlete active in the range.

    A plain ``dict`` (so callers can treat it as the mapping), plus
    ``unrecorded``: ``{athlete_id: {date, …}}`` of days on which the athlete
    was in the audience of a counted calendar event (or has an ``unknown``
    attendance row) but the cell stayed blank — the readiness gap
    ``activity_without_record``. Only past-or-today days are reported.
    """

    unrecorded: dict[int, set[date]]

    def __init__(
        self,
        marks: dict[int, dict[date, Mark]] | None = None,
        unrecorded: dict[int, set[date]] | None = None,
    ) -> None:
        super().__init__(marks or {})
        self.unrecorded = unrecorded or {}


# ---------------------------------------------------------------------------
# Active window (R5)
# ---------------------------------------------------------------------------


def _deletion_local_date(deleted_at: datetime) -> date:
    """Local (Bogotá) date of an archive timestamp stored as UTC."""
    aware = (
        deleted_at.replace(tzinfo=timezone.utc)
        if deleted_at.tzinfo is None
        else deleted_at
    )
    return aware.astimezone(BOGOTA).date()


def active_window(athlete: Athlete, start: date, end: date) -> tuple[date, date] | None:
    """First and last active day of ``athlete`` within ``[start, end]``.

    ``None`` when the athlete is not active on any day of the range.
    """
    first = start
    if athlete.club_join_date is not None and athlete.club_join_date > first:
        first = athlete.club_join_date
    last = end
    if athlete.deleted_at is not None:
        last_active = _deletion_local_date(athlete.deleted_at) - timedelta(days=1)
        if last_active < last:
            last = last_active
    return (first, last) if first <= last else None


def is_active_on(athlete: Athlete, day: date) -> bool:
    """R5: active on ``day`` (join date reached, not yet archived)."""
    return active_window(athlete, day, day) is not None


async def active_athletes_in_range(
    db: AsyncSession,
    club_id: int,
    start: date,
    end: date,
) -> list[Athlete]:
    """Club athletes active on at least one day of ``[start, end]`` (R5).

    Archived athletes are included when they were still active on some day of
    the range. Batch-loads ``imderty_profile`` (with its barrio) and
    ``parents`` (with the guardian ``User``, which carries ``phone``), so the
    sheet builder never triggers a lazy load. The sensitive block is loaded by
    :func:`load_active_sensitive_data` instead (see module docstring).

    Ordered by ``id``; the sheet orders rows by surname itself.
    """
    # Coarse SQL pre-filter; the exact per-day window (UTC → Bogotá date of
    # deleted_at, join after deletion) is refined in Python below.
    first_possible_deletion = datetime.combine(start, time.min)
    result = await db.execute(
        select(Athlete)
        .where(
            Athlete.club_id == club_id,
            or_(Athlete.club_join_date.is_(None), Athlete.club_join_date <= end),
            or_(
                Athlete.deleted_at.is_(None),
                Athlete.deleted_at >= first_possible_deletion,
            ),
        )
        .options(
            selectinload(Athlete.imderty_profile).selectinload(
                AthleteImdertyProfile.barrio
            ),
            selectinload(Athlete.parents).selectinload(ParentAthlete.parent),
        )
        .order_by(Athlete.id)
    )
    return [
        athlete
        for athlete in result.scalars().all()
        if active_window(athlete, start, end) is not None
    ]


async def load_active_sensitive_data(
    db: AsyncSession,
    athlete_ids: Iterable[int],
) -> dict[int, AthleteSensitiveData]:
    """Sensitive rows backed by an *active* authorization, keyed by athlete.

    One batch query. A row whose authorization was withdrawn is never
    returned, even if it somehow survived the erasure transaction (FR-007).
    """
    ids = list(set(athlete_ids))
    if not ids:
        return {}
    result = await db.execute(
        select(AthleteSensitiveData)
        .join(
            AthleteSensitiveAuthorization,
            AthleteSensitiveAuthorization.id == AthleteSensitiveData.authorization_id,
        )
        .where(
            AthleteSensitiveData.athlete_id.in_(ids),
            AthleteSensitiveAuthorization.athlete_id == AthleteSensitiveData.athlete_id,
            AthleteSensitiveAuthorization.withdrawn_at.is_(None),
            AthleteSensitiveAuthorization.active_key.is_not(None),
        )
    )
    return {row.athlete_id: row for row in result.scalars().all()}


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _event_days(event: CalendarEvent, start: date, end: date) -> list[date]:
    """In-range local dates covered by the event.

    Naive Bogotá wall clock: ``.date()`` directly, never ``astimezone()``.
    A competition linked to a race uses the race's ``event_date``.
    """
    if event.event_type == EventType.COMPETITION and event.race_event is not None:
        first = last = event.race_event.event_date
    else:
        first = event.start_at.date()
        last = max(event.end_at.date(), first)
    first = max(first, start)
    last = min(last, end)
    return _days(first, last) if first <= last else []


def _audience_ids(
    audiences: Sequence[EventAudience],
    athletes: Sequence[Athlete],
) -> set[int]:
    """In-memory mirror of ``calendar/audiences.py::_resolve_single_audience``.

    Resolved over the athletes already loaded for the range (one pass, no
    query per audience), which also keeps athletes archived after the event.
    """
    ids: set[int] = set()
    by_id = {a.id: a for a in athletes}
    for audience in audiences:
        value = audience.audience_value or {}
        if audience.audience_type == AudienceType.ALL_CLUB:
            ids.update(by_id)
        elif audience.audience_type == AudienceType.CATEGORY:
            target = value.get("category", "")
            ids.update(
                a.id
                for a in athletes
                if get_category(a.birth_date.year, a.sex.value) == target
            )
        elif audience.audience_type == AudienceType.ATHLETE_LIST:
            ids.update(i for i in value.get("athlete_ids", []) or [] if i in by_id)
        elif audience.audience_type == AudienceType.INDIVIDUAL:
            athlete_id = value.get("athlete_id")
            if athlete_id in by_id:
                ids.add(athlete_id)
    return ids


def _today_bogota() -> date:
    return datetime.now(BOGOTA).date()


async def build_attendance_grid(
    db: AsyncSession,
    club_id: int,
    start: date,
    end: date,
    *,
    athletes: Sequence[Athlete] | None = None,
    today: date | None = None,
) -> AttendanceGrid:
    """Per-day marks for every club athlete active in ``[start, end]``.

    Returns an :class:`AttendanceGrid` — a ``dict[int, dict[date, Mark]]``
    with one (possibly empty) entry per active athlete, where a blank cell is
    an absent key — plus ``.unrecorded`` for readiness.

    ``athletes`` may be passed when the caller already ran
    :func:`active_athletes_in_range` for the same range; ``today`` (Bogotá
    date by default) bounds the ``unrecorded`` report.
    """
    if athletes is None:
        athletes = await active_athletes_in_range(db, club_id, start, end)
    today = today or _today_bogota()

    windows: dict[int, tuple[date, date]] = {}
    for athlete in athletes:
        window = active_window(athlete, start, end)
        if window is not None:
            windows[athlete.id] = window
    athlete_ids = list(windows)
    marks: dict[int, dict[date, Mark]] = {aid: {} for aid in athlete_ids}
    if not athlete_ids:
        return AttendanceGrid(marks)

    def put(athlete_id: int, day: date, mark: Mark) -> None:
        window = windows.get(athlete_id)
        if window is None or not (window[0] <= day <= window[1]):
            return
        cell = marks[athlete_id]
        current = cell.get(day)
        if current is None or _PRECEDENCE[mark] > _PRECEDENCE[current]:
            cell[day] = mark

    # --- 1. Training sessions ----------------------------------------------
    session_rows = await db.execute(
        select(
            SessionAttendance.athlete_id,
            TrainingSession.scheduled_date,
            SessionAttendance.status,
        )
        .join(TrainingSession, TrainingSession.id == SessionAttendance.session_id)
        .where(
            TrainingSession.club_id == club_id,
            TrainingSession.status == SessionStatus.EXECUTED,
            TrainingSession.scheduled_date >= start,
            TrainingSession.scheduled_date <= end,
            SessionAttendance.archived_at.is_(None),
            SessionAttendance.athlete_id.in_(athlete_ids),
        )
    )
    for athlete_id, day, status in session_rows.all():
        put(athlete_id, day, _SESSION_MARKS[status])

    # --- 2 + 3a. Counted calendar events (outings, joint trainings, comps) --
    linked_event_ids = select(TrainingSession.calendar_event_id).where(
        TrainingSession.calendar_event_id.is_not(None)
    )
    range_start = datetime.combine(start, time.min)
    range_end_exclusive = datetime.combine(end + timedelta(days=1), time.min)
    event_result = await db.execute(
        select(CalendarEvent)
        .outerjoin(RaceEvent, RaceEvent.id == CalendarEvent.race_event_id)
        .where(
            CalendarEvent.club_id == club_id,
            CalendarEvent.event_type.in_(_COUNTED_EVENT_TYPES),
            CalendarEvent.status != EventStatus.CANCELLED,
            CalendarEvent.deleted_at.is_(None),
            CalendarEvent.id.not_in(linked_event_ids),
            or_(
                # Overlaps the range on the calendar's own dates…
                and_(
                    CalendarEvent.start_at < range_end_exclusive,
                    CalendarEvent.end_at >= range_start,
                ),
                # …or, for a competition, its race day falls in the range.
                and_(
                    RaceEvent.event_date >= start,
                    RaceEvent.event_date <= end,
                ),
            ),
        )
        .options(
            selectinload(CalendarEvent.audiences),
            selectinload(CalendarEvent.race_event),
        )
    )
    events = list(event_result.scalars().unique().all())

    attendance_by_event: dict[int, dict[int, ActualAttendanceStatus]] = defaultdict(dict)
    if events:
        attendance_rows = await db.execute(
            select(
                EventAttendance.event_id,
                EventAttendance.athlete_id,
                EventAttendance.actual_status,
            ).where(
                EventAttendance.event_id.in_([e.id for e in events]),
                EventAttendance.athlete_id.in_(athlete_ids),
            )
        )
        for event_id, athlete_id, actual in attendance_rows.all():
            attendance_by_event[event_id][athlete_id] = actual

    # Candidate gaps, resolved after every source has been merged.
    pending: list[tuple[int, date]] = []
    for event in events:
        days = _event_days(event, start, end)
        if not days:
            continue
        recorded = attendance_by_event.get(event.id, {})
        for athlete_id, actual in recorded.items():
            mark = _EVENT_MARKS.get(actual)
            if mark is not None:
                for day in days:
                    put(athlete_id, day, mark)
        expected = _audience_ids(event.audiences, athletes) | set(recorded)
        for athlete_id in expected:
            actual = recorded.get(athlete_id)
            if actual is None or actual == ActualAttendanceStatus.UNKNOWN:
                pending.extend((athlete_id, day) for day in days)

    # --- 3b. Race results ----------------------------------------------------
    race_rows = await db.execute(
        select(RaceResult.athlete_id, RaceEvent.event_date)
        .join(RaceEvent, RaceEvent.id == RaceResult.event_id)
        .where(
            RaceResult.athlete_id.in_(athlete_ids),
            RaceResult.deleted_at.is_(None),
            RaceEvent.event_date >= start,
            RaceEvent.event_date <= end,
        )
        .distinct()
    )
    for athlete_id, day in race_rows.all():
        put(athlete_id, day, "A")

    # --- Unrecorded (readiness) ----------------------------------------------
    unrecorded: dict[int, set[date]] = defaultdict(set)
    for athlete_id, day in pending:
        window = windows.get(athlete_id)
        if (
            window is not None
            and window[0] <= day <= window[1]
            and day <= today
            and day not in marks[athlete_id]
        ):
            unrecorded[athlete_id].add(day)

    return AttendanceGrid(marks, dict(unrecorded))


__all__ = [
    "AttendanceGrid",
    "Mark",
    "active_athletes_in_range",
    "active_window",
    "build_attendance_grid",
    "is_active_on",
    "load_active_sensitive_data",
]
