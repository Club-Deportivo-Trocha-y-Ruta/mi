"""Writer for IMDERTY's official monthly attendance workbook (FO-GDD-057 v006).

Fills the sanitized, committed template
``templates/documents/imderty/fo_gdd_057_v006.xlsx`` (12 month sheets plus
``SECTOR``) with openpyxl — research R1–R3 and R6 of feature 047:

* only the requested month sheets are kept, in chronological order, with
  ``SECTOR`` last;
* ``I7`` gets the first day of the month (the reference date of the ``EDAD``
  formula) and ``D7``–``D10`` the header texts;
* row 23 gets the day labels (``SA1``, ``DO2``…; weekday-only labels for the
  trailing columns of short months) and the Excel table column names are kept
  identical, otherwise Excel shows a repair prompt;
* participant values are written from row 24, upper-cased, never touching the
  formula columns (``F``, ``R``, ``AZ:BB``); column ``M`` (sexual orientation)
  is never written;
* ``SECTOR`` is rewritten from the barrio catalog plus a trailing
  ``OTRO MUNICIPIO`` row (blank zone), and the barrio list validation
  ``Q24:Q504`` is re-created against it;
* the header's ``programs`` get an ``"X"`` in ``PROGRAM_MARK_CELLS`` (T043),
  or `` X`` appended to the heading text for ``masificacion`` /
  ``competencia`` (``PROGRAM_HEADING_CELLS``);
* ``fullCalcOnLoad`` is forced so Excel/LibreOffice recompute the counters.

Row values are an input: a list of per-row dicts keyed by column letter. The
rows builder (router / T032) owns data assembly, including leaving the
sensitive columns blank without an authorization. This module never logs and
its errors never echo a cell value (Ley 1581).
"""
from __future__ import annotations

import calendar
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Protocol

from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table
from openpyxl.worksheet.worksheet import Worksheet

from app.models.imderty import OTHER_MUNICIPALITY_LABEL, ImdertyProgram
from app.schemas.imderty import ImdertySheetHeader

TEMPLATE_PATH: Path = (
    Path(__file__).parents[3]
    / "templates"
    / "documents"
    / "imderty"
    / "fo_gdd_057_v006.xlsx"
)

MONTH_SHEET_NAMES: tuple[str, ...] = (
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)
SECTOR_SHEET_NAME = "SECTOR"

# Monday..Sunday, as IMDERTY abbreviates them in the day header row.
WEEKDAY_LABELS: tuple[str, ...] = ("LU", "MA", "MI", "JU", "VI", "SA", "DO")

HEADER_ROW = 23
FIRST_DATA_ROW = 24
LAST_DATA_ROW = 504
MAX_ROWS = 480  # the format's cap (FR / contracts: > 480 → 422)

FIRST_DAY_COLUMN = "U"  # day 1
DAYS_IN_GRID = 31  # U..AY
_FIRST_DAY_INDEX = column_index_from_string(FIRST_DAY_COLUMN)

MONTH_DATE_CELL = "I7"
HEADER_CELLS: tuple[tuple[str, str], ...] = (
    ("contractor_name", "D7"),
    ("venue", "D8"),
    ("training_days", "D9"),
    ("schedule", "D10"),
)

# Program "X" marks (research T008/T009 layout notes). Row 13/17 hold the
# labels, row 14/18 the mark cell directly below each label — both located
# once against the committed template and pinned here as a constant so a
# future template edit is caught by ``test_program_mark_cells_are_adjacent_
# to_their_labels`` rather than silently drifting. ``masificacion`` and
# ``competencia`` are group headings (``C12:I12`` / ``C16:I16`` merges) with
# no "X" cell of their own in the official layout, so they are absent from
# ``PROGRAM_MARK_CELLS``; when selected, `` X`` is appended to the heading
# text instead (``PROGRAM_HEADING_CELLS``, research.md R3 addendum —
# orchestrator decision 2026-09-28, reversible).
PROGRAM_LABEL_CELLS: dict[ImdertyProgram, str] = {
    ImdertyProgram.masificacion: "C12",
    ImdertyProgram.educacion_fisica_deporte_escolar: "C13",
    ImdertyProgram.primera_infancia: "D13",
    ImdertyProgram.hevs: "E13",
    ImdertyProgram.recreacion: "F13",
    ImdertyProgram.deporte_social_comunitario: "H13",
    ImdertyProgram.lecyd_cda: "I13",
    ImdertyProgram.competencia: "C16",
    ImdertyProgram.conjunto: "C17",
    ImdertyProgram.individual: "E17",
    ImdertyProgram.adaptado: "H17",
}
PROGRAM_MARK_CELLS: dict[ImdertyProgram, str] = {
    ImdertyProgram.educacion_fisica_deporte_escolar: "C14",
    ImdertyProgram.primera_infancia: "D14",
    ImdertyProgram.hevs: "E14",
    ImdertyProgram.recreacion: "F14",
    ImdertyProgram.deporte_social_comunitario: "H14",
    ImdertyProgram.lecyd_cda: "I14",
    ImdertyProgram.conjunto: "C18",
    ImdertyProgram.individual: "E18",
    ImdertyProgram.adaptado: "H18",
}

#: Merged group headings (``MASIFICACIÓN`` C12, ``COMPETENCIA`` C16) have no
#: "X" cell in the official format. Owner decision 2026-09-29: they are left
#: unmarked (empty map = selecting them is a no-op) — research.md R3 addendum.
#: To mark them by appending ``" X"`` to the heading, map the program to its
#: heading cell here.
PROGRAM_HEADING_CELLS: dict[ImdertyProgram, str] = {}
HEADING_MARK_SUFFIX = " X"

ROW_NUMBER_COLUMN = "A"
BIRTH_DATE_COLUMN = "E"
SEXUAL_ORIENTATION_COLUMN = "M"
FORMULA_COLUMNS: frozenset[str] = frozenset({"F", "R", "AZ", "BA", "BB"})
# Participant data columns the rows builder may fill (B..T minus formulas,
# minus column M, which the platform never collects).
PARTICIPANT_COLUMNS: frozenset[str] = frozenset(
    get_column_letter(i)
    for i in range(column_index_from_string("B"), column_index_from_string("T") + 1)
) - FORMULA_COLUMNS - {SEXUAL_ORIENTATION_COLUMN}

BARRIO_COLUMN = "Q"
#: Zone cell of the trailing ``OTRO MUNICIPIO`` row of ``SECTOR``: an
#: empty-text formula so the column-``R`` ``VLOOKUP`` yields blank, not 0.
OTHER_MUNICIPALITY_ZONE_FORMULA = '=""'
VALID_MARKS: frozenset[str] = frozenset({"A", "E", "F"})

CellValue = str | int | date | datetime | None
RowValues = Mapping[str, CellValue]


class BarrioEntry(Protocol):
    """Anything with a barrio ``name`` and its comuna/zone (ORM row or DTO)."""

    @property
    def name(self) -> str: ...

    @property
    def zone(self) -> str: ...


class SheetTooLarge(Exception):
    """A month has more participants than the format's rows (480)."""

    def __init__(self, row_count: int, limit: int = MAX_ROWS) -> None:
        self.row_count = row_count
        self.limit = limit
        super().__init__("Too many participants for one IMDERTY month sheet")


# ---------------------------------------------------------------------------
# Day columns
# ---------------------------------------------------------------------------


def day_column_letter(day: int) -> str:
    """Column letter of a day of the month (1 → ``U`` … 31 → ``AY``)."""
    if not 1 <= day <= DAYS_IN_GRID:
        raise ValueError("Day of month out of range")
    return get_column_letter(_FIRST_DAY_INDEX + day - 1)


def day_labels(month: date) -> list[str]:
    """The 31 row-23 labels of a month (R3).

    Existing days get weekday + day number (``SA1``). The trailing columns of
    short months get the weekday abbreviation only; at most three
    consecutive weekdays, so the labels stay unique within the table.
    """
    first = month.replace(day=1)
    last_day = calendar.monthrange(first.year, first.month)[1]
    start_weekday = first.weekday()
    labels: list[str] = []
    for offset in range(DAYS_IN_GRID):
        weekday = WEEKDAY_LABELS[(start_weekday + offset) % 7]
        day = offset + 1
        labels.append(f"{weekday}{day}" if day <= last_day else weekday)
    return labels


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _clean_text(value: str, *, upper: bool) -> str | None:
    text = ILLEGAL_CHARACTERS_RE.sub("", value).strip()
    if not text:
        return None
    return text.upper() if upper else text


def _set_cell(cell: Cell, value: CellValue, *, upper: bool = True) -> None:
    """Write one value: text upper-cased and always stored as text (a leading
    ``=`` never becomes a formula), datetimes as dates."""
    if value is None:
        cell.value = None
        return
    if isinstance(value, datetime):
        cell.value = value.date()
        return
    if isinstance(value, date):
        cell.value = value
        return
    if isinstance(value, bool):
        raise ValueError("Unsupported cell value type")
    if isinstance(value, int):
        cell.value = value
        return
    if isinstance(value, str):
        text = _clean_text(value, upper=upper)
        cell.value = text
        if text is not None:
            cell.data_type = "s"
        return
    raise ValueError("Unsupported cell value type")


def _is_blank(value: CellValue) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _sort_text(value: CellValue) -> str:
    """Collation key: case- and accent-insensitive, with Ñ after N."""
    if not isinstance(value, str):
        return ""
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", value.strip().lower()):
        if unicodedata.combining(ch):
            if ch == "̃" and out and out[-1] == "n":  # ñ
                out.append("\x7f")
            continue
        out.append(ch)
    return "".join(out)


def _row_sort_key(row: RowValues) -> tuple[str, str, str]:
    # first surname, second surname, first name
    return (_sort_text(row.get("C")), _sort_text(row.get("D")), _sort_text(row.get("B")))


def _validate_row(row: RowValues, day_columns: Mapping[str, int], last_day: int) -> None:
    for key, value in row.items():
        if _is_blank(value):
            continue
        if key in PARTICIPANT_COLUMNS:
            continue
        day = day_columns.get(key)
        if day is None:
            raise ValueError(f"Column {key!r} is not writable in the IMDERTY sheet")
        if day > last_day:
            raise ValueError(f"Column {key!r} is outside the month")
        if not isinstance(value, str) or value.strip().upper() not in VALID_MARKS:
            raise ValueError(f"Invalid attendance mark in column {key!r}")


# ---------------------------------------------------------------------------
# Sheet filling
# ---------------------------------------------------------------------------


def _month_table(ws: Worksheet) -> Table:
    tables = list(ws.tables.values())
    if len(tables) != 1:
        raise RuntimeError("IMDERTY template month sheet must hold exactly one table")
    return tables[0]


def _write_day_headers(ws: Worksheet, month: date) -> None:
    for day, label in enumerate(day_labels(month), start=1):
        ws[f"{day_column_letter(day)}{HEADER_ROW}"].value = label
    table = _month_table(ws)
    min_col = column_index_from_string("A")
    for index, table_column in enumerate(table.tableColumns):
        header = ws.cell(row=HEADER_ROW, column=min_col + index).value
        table_column.name = "" if header is None else str(header)


def _write_header(ws: Worksheet, month: date, header: ImdertySheetHeader | None) -> None:
    ws[MONTH_DATE_CELL].value = month
    for field, ref in HEADER_CELLS:
        raw = getattr(header, field, None) if header is not None else None
        _set_cell(ws[ref], raw if isinstance(raw, str) else None, upper=False)
    for ref in PROGRAM_MARK_CELLS.values():
        ws[ref].value = None
    programs = header.programs if header is not None else []
    for program in programs:
        ref = PROGRAM_MARK_CELLS.get(program)
        if ref is not None:
            _set_cell(ws[ref], "X")
    for program, ref in PROGRAM_HEADING_CELLS.items():
        if program not in programs:
            continue
        heading = ws[ref].value
        if isinstance(heading, str) and not heading.endswith(HEADING_MARK_SUFFIX):
            ws[ref].value = f"{heading.rstrip()}{HEADING_MARK_SUFFIX}"


def _validate_month_rows(month: date, rows: Sequence[RowValues]) -> None:
    if len(rows) > MAX_ROWS:
        raise SheetTooLarge(len(rows))
    last_day = calendar.monthrange(month.year, month.month)[1]
    day_columns = {day_column_letter(d): d for d in range(1, DAYS_IN_GRID + 1)}
    for row in rows:
        _validate_row(row, day_columns, last_day)


def _write_rows(ws: Worksheet, rows: Sequence[RowValues]) -> None:
    """Write already-validated rows (see ``_validate_month_rows``)."""
    for number, row in enumerate(sorted(rows, key=_row_sort_key), start=1):
        excel_row = FIRST_DATA_ROW + number - 1
        ws[f"{ROW_NUMBER_COLUMN}{excel_row}"].value = number
        for key, value in row.items():
            if _is_blank(value):
                continue
            _set_cell(ws[f"{key}{excel_row}"], value)
        # Privacy invariant: sexual orientation is never collected.
        ws[f"{SEXUAL_ORIENTATION_COLUMN}{excel_row}"].value = None


def _write_barrio_validation(ws: Worksheet, sector_rows: int) -> None:
    """Re-create the ``Q24:Q504`` list validation over the ``sector_rows``
    data rows of ``SECTOR`` (catalog plus the trailing ``OTRO MUNICIPIO``)."""
    target = f"{BARRIO_COLUMN}{FIRST_DATA_ROW}:{BARRIO_COLUMN}{LAST_DATA_ROW}"
    kept = [
        dv
        for dv in ws.data_validations.dataValidation
        if f"{BARRIO_COLUMN}{FIRST_DATA_ROW}" not in str(dv.sqref)
    ]
    ws.data_validations.dataValidation = kept
    last = max(sector_rows + 1, 2)
    validation = DataValidation(
        type="list",
        formula1=f"{SECTOR_SHEET_NAME}!$A$2:$A${last}",
        allow_blank=True,
    )
    validation.add(target)
    ws.add_data_validation(validation)


def _write_sector(ws: Worksheet, barrios: Sequence[BarrioEntry]) -> int:
    """Rewrite ``SECTOR`` from the catalog and return its data-row count.

    ``OTRO MUNICIPIO`` (the column-``Q`` value of an athlete living outside
    Yumbo) is appended as the last row so Excel's list validation accepts
    it. Its zone is the formula ``=""`` rather than an empty cell: a
    ``VLOOKUP`` onto a truly empty cell returns ``0``, while ``=""`` keeps
    column ``R`` blank for that row.
    """
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    row = 1
    has_other = False
    for barrio in barrios:
        row += 1
        _set_cell(ws.cell(row=row, column=1), barrio.name)
        _set_cell(ws.cell(row=row, column=2), barrio.zone)
        if _sort_text(barrio.name) == _sort_text(OTHER_MUNICIPALITY_LABEL):
            has_other = True
    if not has_other:
        row += 1
        _set_cell(ws.cell(row=row, column=1), OTHER_MUNICIPALITY_LABEL)
        ws.cell(row=row, column=2).value = OTHER_MUNICIPALITY_ZONE_FORMULA
    return row - 1


def _normalize_months(months: Iterable[date]) -> list[date]:
    firsts = sorted({m.replace(day=1) for m in months})
    if not firsts:
        raise ValueError("At least one month is required")
    if len(firsts) > len(MONTH_SHEET_NAMES):
        raise ValueError("At most 12 months per workbook")
    names = [MONTH_SHEET_NAMES[m.month - 1] for m in firsts]
    if len(set(names)) != len(names):
        raise ValueError("The same calendar month cannot appear twice in one workbook")
    return firsts


def _load_template() -> Workbook:
    return load_workbook(BytesIO(TEMPLATE_PATH.read_bytes()))


def build_sheet(
    months: list[date],
    rows_by_month: Mapping[date, Sequence[RowValues]],
    header: ImdertySheetHeader | None,
    barrios: Sequence[BarrioEntry],
) -> bytes:
    """Build the FO-GDD-057 workbook and return the ``.xlsx`` bytes.

    ``months`` are any dates inside the wanted months (normalized to the
    first day); ``rows_by_month`` is keyed by the first day of each month,
    and a missing month yields an empty sheet. ``barrios`` is the active
    catalog, written to ``SECTOR`` in the given order.

    Raises ``SheetTooLarge`` when a month has more than 480 rows and
    ``ValueError`` for rows that target a non-writable column (formulas,
    column M, days outside the month) or carry an invalid mark.
    """
    firsts = _normalize_months(months)
    wanted = {MONTH_SHEET_NAMES[m.month - 1]: m for m in firsts}

    # Validate everything before touching the template.
    normalized_rows: dict[date, Sequence[RowValues]] = {}
    for key, rows in rows_by_month.items():
        normalized_rows[key.replace(day=1)] = rows
    for month in firsts:
        _validate_month_rows(month, normalized_rows.get(month, ()))

    wb = _load_template()
    for name in MONTH_SHEET_NAMES:
        if name not in wanted:
            wb.remove(wb[name])

    order = [MONTH_SHEET_NAMES[m.month - 1] for m in firsts] + [SECTOR_SHEET_NAME]
    wb._sheets = [wb[name] for name in order]
    wb.active = 0
    # The template selects ENERO; exactly one selected tab avoids Excel
    # opening the file in "grouped sheets" mode.
    for index, sheet in enumerate(wb.worksheets):
        sheet.sheet_view.tabSelected = index == 0

    sector_rows = _write_sector(wb[SECTOR_SHEET_NAME], list(barrios))

    for month in firsts:
        ws = wb[MONTH_SHEET_NAMES[month.month - 1]]
        _write_header(ws, month, header)
        _write_day_headers(ws, month)
        _write_rows(ws, normalized_rows.get(month, ()))
        _write_barrio_validation(ws, sector_rows)

    wb.calculation.fullCalcOnLoad = True
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
