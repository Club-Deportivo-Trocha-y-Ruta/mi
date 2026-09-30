"""Per-row dicts for one IMDERTY month sheet (feature 047, US1 + US2).

``build_rows`` bridges ``attendance_grid.py`` (athletes + their per-day
``Mark``s) and ``workbook.py::build_sheet`` (which wants a
``Sequence[RowValues]`` per month, keyed by column letter). It fills:

- names: ``B`` first name; ``C``/``D`` the confirmed surname split, or the
  unsplit ``last_name`` in ``C`` while unconfirmed (FR-001a, research R7);
- identity: ``E`` birth date, ``G``/``H`` document label and number, ``I``
  sex, ``J`` school, ``K`` grade label;
- sensitive block: ``L`` disability, ``N`` victim, ``O`` ethnicity — only
  from an ``AthleteSensitiveData`` row backed by an *active* authorization
  (FR-007/FR-008). Column ``M`` is never produced (FR-009);
- address and contact: ``P`` address, ``Q`` barrio name or ``OTRO
  MUNICIPIO``, ``S`` EPS, ``T`` the FR-022 effective phone;
- the month's day marks (``U``..``AY``).

The athletes must come with ``imderty_profile`` (+ ``barrio``) and
``parents`` (+ ``parent``) already loaded, as
``attendance_grid.active_athletes_in_range`` does — ``build_rows`` is sync
and never triggers a lazy load. Sensitive rows are passed separately (see
``load_authorized_sensitive_data``).

Row numbering (column ``A``) is assigned by ``workbook.build_sheet`` itself,
so a row here never carries it. Nothing in this module logs a value — only
counts ever leave it (Ley 1581).
"""
from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.models.athlete import Athlete, Sex
from app.models.imderty import (
    DISABILITY_LABELS,
    DOCUMENT_TYPE_LABELS,
    ETHNICITY_LABELS,
    GRADE_LABELS,
    OTHER_MUNICIPALITY_LABEL,
    YES_NO_LABELS,
    AthleteImdertyProfile,
    AthleteSensitiveAuthorization,
    AthleteSensitiveData,
)
from app.services.imderty.attendance_grid import Mark, active_window
from app.services.imderty.profile import effective_phone
from app.services.imderty.surnames import rebuilds
from app.services.imderty.workbook import CellValue, RowValues, day_column_letter

# Sheet-mandated labels (T032 fixes the same mapping for column I).
SEX_LABELS: dict[Sex, str] = {
    Sex.M: "HOMBRE",
    Sex.F: "MUJER",
}

FIRST_NAME_COLUMN = "B"
FIRST_SURNAME_COLUMN = "C"
SECOND_SURNAME_COLUMN = "D"
BIRTH_DATE_COLUMN = "E"
DOCUMENT_TYPE_COLUMN = "G"
DOCUMENT_NUMBER_COLUMN = "H"
SEX_COLUMN = "I"
SCHOOL_COLUMN = "J"
GRADE_COLUMN = "K"
DISABILITY_COLUMN = "L"
# Column M (excluded category, FR-009) is deliberately never produced here.
VICTIM_COLUMN = "N"
ETHNICITY_COLUMN = "O"
ADDRESS_COLUMN = "P"
BARRIO_COLUMN = "Q"
EPS_COLUMN = "S"
PHONE_COLUMN = "T"


def _month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    last_day = calendar.monthrange(first.year, first.month)[1]
    return first, first.replace(day=last_day)


def _surname_cells(
    last_name: str, profile: AthleteImdertyProfile | None
) -> dict[str, CellValue]:
    """Confirmed split → ``C``/``D``; otherwise the unsplit ``last_name`` in ``C``.

    A confirmation only counts while the stored split still rebuilds the
    current ``last_name`` (research R7), mirroring ``profile.py``.
    """
    if (
        profile is not None
        and profile.surname_split_confirmed_at is not None
        and profile.first_surname
        and rebuilds(last_name, profile.first_surname, profile.second_surname)
    ):
        return {
            FIRST_SURNAME_COLUMN: profile.first_surname,
            SECOND_SURNAME_COLUMN: profile.second_surname,
        }
    return {FIRST_SURNAME_COLUMN: last_name, SECOND_SURNAME_COLUMN: None}


def _profile_cells(profile: AthleteImdertyProfile | None) -> dict[str, CellValue]:
    if profile is None:
        return {}
    if profile.other_municipality:
        barrio: str | None = OTHER_MUNICIPALITY_LABEL
    elif profile.barrio is not None:
        barrio = profile.barrio.name
    else:
        barrio = None
    return {
        DOCUMENT_TYPE_COLUMN: (
            DOCUMENT_TYPE_LABELS[profile.document_type]
            if profile.document_type is not None
            else None
        ),
        DOCUMENT_NUMBER_COLUMN: profile.document_number,
        SCHOOL_COLUMN: profile.school,
        GRADE_COLUMN: GRADE_LABELS[profile.grade] if profile.grade is not None else None,
        ADDRESS_COLUMN: profile.address,
        BARRIO_COLUMN: barrio,
        EPS_COLUMN: profile.eps,
    }


def _is_authorized(athlete_id: int, data: AthleteSensitiveData | None) -> bool:
    """Only a row of this athlete backed by an active authorization counts."""
    if data is None or data.athlete_id != athlete_id:
        return False
    authorization = data.authorization
    return (
        authorization is not None
        and authorization.athlete_id == athlete_id
        and authorization.is_active
    )


def _sensitive_cells(
    athlete_id: int, data: AthleteSensitiveData | None
) -> dict[str, CellValue]:
    if data is None or not _is_authorized(athlete_id, data):
        return {}
    return {
        DISABILITY_COLUMN: DISABILITY_LABELS[data.disability],
        VICTIM_COLUMN: (
            YES_NO_LABELS[data.conflict_victim]
            if data.conflict_victim is not None
            else None
        ),
        ETHNICITY_COLUMN: ETHNICITY_LABELS[data.ethnicity],
    }


def build_rows(
    athletes: Sequence[Athlete],
    grid: Mapping[int, Mapping[date, Mark]],
    month: date,
    *,
    sensitive: Mapping[int, AthleteSensitiveData] | None = None,
) -> list[RowValues]:
    """One row per athlete of ``athletes`` active at some point in ``month``.

    ``grid`` is the ``{athlete_id: {date: Mark}}`` mapping returned by
    ``build_attendance_grid`` (an :class:`AttendanceGrid` satisfies this, but
    any mapping with the same shape works). Only the day marks that fall
    inside ``month`` are written — the same athlete may be passed again for
    a different month of a multi-month request, and each call only ever
    touches that one month's day columns (``U``..``AY``).

    ``sensitive`` maps ``athlete_id`` to its ``AthleteSensitiveData`` with
    ``authorization`` loaded (``load_authorized_sensitive_data``). Columns
    ``L``/``N``/``O`` stay blank for an athlete without an entry or whose
    authorization is not active.

    An athlete with no active day in ``month`` (per
    ``attendance_grid.active_window``) is left out entirely, even if it
    appears in ``athletes`` because it was active elsewhere in a wider
    request range.
    """
    first, last = _month_bounds(month)
    sensitive_by_id = sensitive or {}
    rows: list[RowValues] = []
    for athlete in athletes:
        if active_window(athlete, first, last) is None:
            continue
        profile = athlete.imderty_profile
        phone, _source = effective_phone(athlete)
        row: dict[str, CellValue] = {
            FIRST_NAME_COLUMN: athlete.first_name,
            **_surname_cells(athlete.last_name, profile),
            BIRTH_DATE_COLUMN: athlete.birth_date,
            SEX_COLUMN: SEX_LABELS[athlete.sex],
            **_profile_cells(profile),
            **_sensitive_cells(athlete.id, sensitive_by_id.get(athlete.id)),
            PHONE_COLUMN: phone,
        }
        for day, mark in grid.get(athlete.id, {}).items():
            if first <= day <= last:
                row[day_column_letter(day.day)] = mark
        rows.append(row)
    return rows


async def load_authorized_sensitive_data(
    db: AsyncSession, athlete_ids: Sequence[int]
) -> dict[int, AthleteSensitiveData]:
    """Sensitive rows of ``athlete_ids`` backed by an active authorization.

    The authorization is eager-loaded (``contains_eager``) so ``build_rows``
    can re-check it without a lazy load. Never logs.
    """
    if not athlete_ids:
        return {}
    result = await db.execute(
        select(AthleteSensitiveData)
        .join(
            AthleteSensitiveAuthorization,
            AthleteSensitiveAuthorization.id == AthleteSensitiveData.authorization_id,
        )
        .where(
            AthleteSensitiveData.athlete_id.in_(list(athlete_ids)),
            AthleteSensitiveAuthorization.athlete_id == AthleteSensitiveData.athlete_id,
            AthleteSensitiveAuthorization.active_key.is_not(None),
            AthleteSensitiveAuthorization.withdrawn_at.is_(None),
        )
        .options(contains_eager(AthleteSensitiveData.authorization))
    )
    return {data.athlete_id: data for data in result.scalars().all()}


__all__ = ["SEX_LABELS", "build_rows", "load_authorized_sensitive_data"]
