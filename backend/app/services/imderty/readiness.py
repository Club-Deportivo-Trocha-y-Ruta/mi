"""IMDERTY sheet readiness report (feature 047, US3, T042).

``build_readiness`` lists, per active athlete of a month range, which of the
gaps of ``data-model.md``'s "Readiness gap" block apply — so the coach can
fix them *before* downloading, not after opening the workbook. Nothing here
blocks the download itself (``POST /imderty-sheet`` still works with gaps);
this is a read-only report.

Gap codes (per athlete):
- ``missing_document``: no ``document_type`` or no ``document_number``.
- ``missing_barrio``: neither a barrio nor "otro municipio" is set.
- ``missing_eps``: no EPS on file.
- ``missing_phone``: the FR-022 fallback chain (own → primary guardian →
  first guardian) resolves to nothing.
- ``no_guardian``: no guardian linked at all.
- ``multiple_guardians_no_primary``: more than one guardian, none marked
  "contacto principal".
- ``surname_split_unconfirmed``: the profile's split was never confirmed, or
  a later ``last_name`` edit invalidated it (research R7).
- ``activity_without_record``: the athlete was in the audience of a counted
  calendar event (or has an ``unknown`` attendance row) on a day that stayed
  blank in the grid — ``attendance_grid.py``'s ``.unrecorded``, which already
  resolves audiences in memory (no per-event query here).

Reuses ``active_athletes_in_range`` and ``build_attendance_grid`` from
``attendance_grid.py`` so the athlete set and the day marks are computed by
the exact same code the sheet export uses — a gap reported here is a gap the
export would actually have.

Privacy (Ley 1581): ``display_name`` is built from ``first_name``/
``last_name`` only for this report's response (contracts/api.md: "shown only
to admin and coach, on screen, and is never logged") — nothing here logs it,
and the module never touches the sensitive block.
"""
from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.schemas.imderty import ReadinessGap, ReadinessRead
from app.services.imderty.profile import GuardianPhone, resolve_effective_phone
from app.services.imderty.surnames import rebuilds
from app.services.imderty.attendance_grid import (
    AttendanceGrid,
    active_athletes_in_range,
    build_attendance_grid,
)
from app.services.imderty.workbook import MAX_ROWS

BOGOTA = ZoneInfo("America/Bogota")


class ReadinessTooLarge(Exception):
    """A month of the requested range has more than ``MAX_ROWS`` athletes."""

    def __init__(self, month: str, count: int) -> None:
        super().__init__(f"{month}: {count} athletes")
        self.month = month
        self.count = count


def _month_bounds(month: date) -> tuple[date, date]:
    last_day = calendar.monthrange(month.year, month.month)[1]
    return month, month.replace(day=last_day)


def _today_bogota() -> date:
    return datetime.now(BOGOTA).date()


def _guardian_phones(athlete: Athlete) -> list[GuardianPhone]:
    return [
        GuardianPhone(
            link_id=link.id,
            phone=link.parent.phone if link.parent is not None else None,
            is_primary=link.primary_contact_key == athlete.id,
        )
        for link in athlete.parents
    ]


def _split_confirmed(athlete: Athlete) -> bool:
    profile = athlete.imderty_profile
    if profile is None or profile.surname_split_confirmed_at is None:
        return False
    if not profile.first_surname:
        return False
    return rebuilds(athlete.last_name or "", profile.first_surname, profile.second_surname)


def _gaps_for_athlete(
    athlete: Athlete, unrecorded_dates: set[date]
) -> tuple[list[str], list[date]]:
    codes: list[str] = []
    profile = athlete.imderty_profile

    if profile is None or not profile.document_type or not (
        profile.document_number and profile.document_number.strip()
    ):
        codes.append("missing_document")

    if profile is None or (
        profile.barrio_id is None and not profile.other_municipality
    ):
        codes.append("missing_barrio")

    if profile is None or not (profile.eps and profile.eps.strip()):
        codes.append("missing_eps")

    guardians = _guardian_phones(athlete)
    own_phone = profile.phone if profile is not None else None
    phone, _source = resolve_effective_phone(own_phone, guardians)
    if not phone:
        codes.append("missing_phone")

    if not athlete.parents:
        codes.append("no_guardian")
    elif len(athlete.parents) > 1 and not any(g.is_primary for g in guardians):
        codes.append("multiple_guardians_no_primary")

    if not _split_confirmed(athlete):
        codes.append("surname_split_unconfirmed")

    activity_dates = sorted(unrecorded_dates)
    if activity_dates:
        codes.append("activity_without_record")

    return codes, activity_dates


def _month_has_activity(
    grid: AttendanceGrid, athletes: Sequence[Athlete], start: date, end: date
) -> bool:
    for athlete in athletes:
        if any(start <= day <= end for day in grid.get(athlete.id, {})):
            return True
    return False


async def build_readiness(
    db: AsyncSession,
    club_id: int,
    months: Sequence[date],
    *,
    today: date | None = None,
) -> ReadinessRead:
    """Readiness report for ``months`` (first-of-month dates, chronological).

    Raises ``ReadinessTooLarge`` when a single month has more than
    ``workbook.MAX_ROWS`` (480) active athletes — the router maps that to a
    422, the same limit ``POST /imderty-sheet`` enforces.

    ``today`` (Bogotá date by default, same as ``build_attendance_grid``)
    bounds both ``month_in_progress`` and, through the shared grid, the
    ``activity_without_record`` gap — pass it explicitly only from a test.
    """
    today = today or _today_bogota()
    per_month_athletes: dict[date, list[Athlete]] = {}
    all_athletes: dict[int, Athlete] = {}
    for month in months:
        start, end = _month_bounds(month)
        athletes = await active_athletes_in_range(db, club_id, start, end)
        if len(athletes) > MAX_ROWS:
            raise ReadinessTooLarge(month.strftime("%Y-%m"), len(athletes))
        per_month_athletes[month] = athletes
        for athlete in athletes:
            all_athletes[athlete.id] = athlete

    athletes = list(all_athletes.values())

    range_start = _month_bounds(months[0])[0]
    range_end = _month_bounds(months[-1])[1]
    grid = await build_attendance_grid(
        db, club_id, range_start, range_end, athletes=athletes, today=today
    )

    current_month = date(today.year, today.month, 1)
    month_in_progress = current_month in months

    months_without_activity = [
        month.strftime("%Y-%m")
        for month in months
        if per_month_athletes[month]
        and not _month_has_activity(grid, per_month_athletes[month], *_month_bounds(month))
    ]

    gaps: list[ReadinessGap] = []
    for athlete in sorted(athletes, key=lambda a: a.id):
        codes, activity_dates = _gaps_for_athlete(
            athlete, grid.unrecorded.get(athlete.id, set())
        )
        if codes:
            display_name = f"{athlete.first_name} {athlete.last_name}".strip()
            gaps.append(
                ReadinessGap(
                    athlete_id=athlete.id,
                    display_name=display_name,
                    codes=codes,
                    activity_dates=activity_dates,
                )
            )

    return ReadinessRead(
        months=[month.strftime("%Y-%m") for month in months],
        month_in_progress=month_in_progress,
        months_without_activity=months_without_activity,
        athlete_count=len(athletes),
        gaps=gaps,
    )


__all__ = ["ReadinessTooLarge", "build_readiness"]
