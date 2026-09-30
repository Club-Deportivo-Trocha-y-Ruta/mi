"""Workbook writer tests for feature 047 (T015; single month, plus ordering).

The writer (``app.services.imderty.workbook``) fills the sanitized, committed
FO-GDD-057 v006 template. Row values are an input: a list of per-row dicts
keyed by column letter. Every name, date and document here is fictitious
(CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pytest
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.models.imderty import ImdertyProgram
from app.schemas.imderty import ImdertySheetHeader
from app.services.imderty.barrios_seed import BARRIOS_YUMBO
from app.services.imderty.workbook import (
    FIRST_DATA_ROW,
    MAX_ROWS,
    PROGRAM_HEADING_CELLS,
    PROGRAM_LABEL_CELLS,
    PROGRAM_MARK_CELLS,
    TEMPLATE_PATH,
    SheetTooLarge,
    build_sheet,
    day_column_letter,
    day_labels,
)

AUG_2026 = date(2026, 8, 1)
SEP_2026 = date(2026, 9, 1)


@dataclass(frozen=True)
class _Barrio:
    name: str
    zone: str


CATALOG: list[_Barrio] = [_Barrio(name, zone) for name, zone in BARRIOS_YUMBO]


def _rows() -> list[dict[str, Any]]:
    """Five fictitious participants, deliberately out of order."""
    return [
        {"B": "ana", "C": "zapata", "D": "ruiz", "E": date(2014, 3, 2), "U": "A"},
        {"B": "luis", "C": "peña", "D": "gómez", "E": date(2013, 5, 6)},
        {"B": "andrés", "C": "peña", "D": "gómez", "E": date(2015, 7, 8), "V": "E"},
        {"B": "marta", "C": "pena", "D": None, "E": None, "W": "F"},
        {"B": "sofía", "C": "álvarez", "E": datetime(2012, 1, 9, 0, 0)},
    ]


def _open(content: bytes) -> Any:
    return load_workbook(BytesIO(content))


def _build(
    month: date = AUG_2026,
    rows: list[dict[str, Any]] | None = None,
    header: ImdertySheetHeader | None = None,
    barrios: list[_Barrio] | None = None,
) -> Any:
    content = build_sheet(
        [month],
        {month: _rows() if rows is None else rows},
        header,
        CATALOG if barrios is None else barrios,
    )
    assert isinstance(content, bytes)
    return _open(content)


@pytest.fixture(scope="module")
def aug_wb() -> Any:
    """One August build shared by the read-only assertions (building takes
    about a second, dominated by loading the 13-sheet template)."""
    return _build()


def _row23(ws: Worksheet) -> list[Any]:
    return [c.value for c in ws[23]][: 54]


def _table(ws: Worksheet) -> Any:
    tables = list(ws.tables.values())
    assert len(tables) == 1
    return tables[0]


# ---------------------------------------------------------------------------
# Structure and header
# ---------------------------------------------------------------------------


def test_single_month_has_one_month_sheet_plus_sector(aug_wb: Any) -> None:
    wb = aug_wb
    assert wb.sheetnames == ["AGOSTO", "SECTOR"]
    assert wb.active.title == "AGOSTO"
    assert [ws.sheet_view.tabSelected for ws in wb.worksheets] == [True, False]


def test_header_first_day_of_month_and_logo() -> None:
    header = ImdertySheetHeader(
        contractor_name="Contratista Ficticio",
        venue="Pista de prueba",
        training_days="Martes y jueves",
        schedule="4:00 p. m. a 6:00 p. m.",
    )
    ws = _build(header=header)["AGOSTO"]
    assert ws["I7"].value == datetime(2026, 8, 1)
    assert ws["I7"].is_date
    assert len(ws._images) == 1
    assert ws["D7"].value == "Contratista Ficticio"
    assert ws["D8"].value == "Pista de prueba"
    assert ws["D9"].value == "Martes y jueves"
    assert ws["D10"].value == "4:00 p. m. a 6:00 p. m."
    # The official identification block stays untouched.
    assert ws["I3"].value == "FO-GDD-057"
    assert ws["I4"].value == "006"


def test_header_blank_when_absent(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    for ref in ("D7", "D8", "D9", "D10"):
        assert ws[ref].value is None


# ---------------------------------------------------------------------------
# Program "X" marks (T043)
# ---------------------------------------------------------------------------


def test_program_mark_cells_are_adjacent_to_their_labels() -> None:
    """Every mapped mark cell sits one row directly below the template cell
    holding its own label (``PROGRAM_LABEL_CELLS``), same column."""
    from openpyxl.utils.cell import coordinate_from_string

    wb = load_workbook(BytesIO(TEMPLATE_PATH.read_bytes()))
    ws = wb["ENERO"]
    assert set(PROGRAM_MARK_CELLS) <= set(PROGRAM_LABEL_CELLS)
    for program, mark_ref in PROGRAM_MARK_CELLS.items():
        label_ref = PROGRAM_LABEL_CELLS[program]
        assert ws[label_ref].value, f"No label text at {label_ref} for {program}"
        label_col, label_row = coordinate_from_string(label_ref)
        mark_col, mark_row = coordinate_from_string(mark_ref)
        assert mark_col == label_col
        assert mark_row == label_row + 1
        # The template ships this cell blank; the writer must not find text
        # already sitting there.
        assert ws[mark_ref].value is None


def test_program_marks_written_for_selected_programs() -> None:
    header = ImdertySheetHeader(
        programs=[ImdertyProgram.recreacion, ImdertyProgram.individual]
    )
    ws = _build(header=header)["AGOSTO"]
    assert ws[PROGRAM_MARK_CELLS[ImdertyProgram.recreacion]].value == "X"
    assert ws[PROGRAM_MARK_CELLS[ImdertyProgram.individual]].value == "X"
    unselected = set(PROGRAM_MARK_CELLS) - {
        ImdertyProgram.recreacion,
        ImdertyProgram.individual,
    }
    for program in unselected:
        assert ws[PROGRAM_MARK_CELLS[program]].value is None


def test_program_marks_absent_when_no_programs(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    for ref in PROGRAM_MARK_CELLS.values():
        assert ws[ref].value is None


def test_masificacion_and_competencia_have_no_mark_cell() -> None:
    """Group headings (``C12:I12``, ``C16:I16``) — no dedicated "X" cell in
    the official layout; they are marked on their own heading instead
    (research.md R3 addendum)."""
    assert ImdertyProgram.masificacion not in PROGRAM_MARK_CELLS
    assert ImdertyProgram.competencia not in PROGRAM_MARK_CELLS
    # Owner decision 2026-09-29: the two group headings are never marked.
    assert PROGRAM_HEADING_CELLS == {}


def test_heading_programs_are_left_unmarked_when_selected() -> None:
    header = ImdertySheetHeader(
        programs=[ImdertyProgram.masificacion, ImdertyProgram.competencia]
    )
    ws = _build(header=header)["AGOSTO"]
    assert ws["C12"].value == "MASIFICACIÓN"
    assert ws["C16"].value == "COMPETENCIA"
    for ref in PROGRAM_MARK_CELLS.values():
        assert ws[ref].value is None


def test_heading_programs_untouched_when_not_selected(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    assert ws["C12"].value == "MASIFICACIÓN"
    assert ws["C16"].value == "COMPETENCIA"


def test_only_one_heading_program_selected() -> None:
    header = ImdertySheetHeader(
        programs=[ImdertyProgram.competencia, ImdertyProgram.individual]
    )
    ws = _build(header=header)["AGOSTO"]
    assert ws["C12"].value == "MASIFICACIÓN"
    assert ws["C16"].value == "COMPETENCIA"
    assert ws[PROGRAM_MARK_CELLS[ImdertyProgram.individual]].value == "X"


# ---------------------------------------------------------------------------
# Day headers and table
# ---------------------------------------------------------------------------


def test_day_labels_august_2026() -> None:
    labels = day_labels(AUG_2026)
    assert len(labels) == 31
    assert labels[:2] == ["SA1", "DO2"]
    assert labels[-1] == "LU31"


def test_day_labels_short_month_keeps_weekday_only_trailing_label() -> None:
    labels = day_labels(SEP_2026)
    assert labels[29] == "MI30"
    assert labels[30] == "JU"
    feb = day_labels(date(2027, 2, 1))  # 28 days, starts on a Monday
    assert feb[27] == "DO28"
    assert feb[28:] == ["LU", "MA", "MI"]
    assert len(set(feb)) == 31


def test_row23_and_table_columns_august(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    assert ws["U23"].value == "SA1"
    assert ws["V23"].value == "DO2"
    assert ws["AY23"].value == "LU31"
    table = _table(ws)
    assert table.ref == "A23:BB504"
    assert [tc.name for tc in table.tableColumns] == _row23(ws)


def test_row23_and_table_columns_september() -> None:
    ws = _build(SEP_2026)["SEPTIEMBRE"]
    assert ws["U23"].value == "MA1"
    assert ws["AX23"].value == "MI30"
    assert ws["AY23"].value == "JU"
    names = [tc.name for tc in _table(ws).tableColumns]
    assert names == _row23(ws)
    assert len({n.upper() for n in names}) == len(names)


# ---------------------------------------------------------------------------
# Participant rows
# ---------------------------------------------------------------------------


def test_rows_sorted_numbered_and_upper_case(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    got = [
        (ws.cell(row=r, column=1).value, ws[f"C{r}"].value, ws[f"D{r}"].value, ws[f"B{r}"].value)
        for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + 5)
    ]
    assert got == [
        (1, "ÁLVAREZ", None, "SOFÍA"),
        (2, "PENA", None, "MARTA"),
        (3, "PEÑA", "GÓMEZ", "ANDRÉS"),
        (4, "PEÑA", "GÓMEZ", "LUIS"),
        (5, "ZAPATA", "RUIZ", "ANA"),
    ]
    # Nothing is written past the last participant.
    assert ws[f"A{FIRST_DATA_ROW + 5}"].value is None
    assert ws[f"B{FIRST_DATA_ROW + 5}"].value is None


def test_dates_are_real_dates_and_formulas_intact(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    first = FIRST_DATA_ROW
    assert ws[f"E{first}"].value == datetime(2012, 1, 9)
    assert ws[f"E{first}"].is_date
    assert ws[f"E{first + 1}"].value is None
    for r in (first, first + 4, 504):
        assert ws[f"F{r}"].value == f'=IF(E{r}="","",DATEDIF(E{r},$I$7,"Y"))'
        assert str(ws[f"R{r}"].value).startswith("=IFERROR(VLOOKUP(")
        assert ws[f"AZ{r}"].value == f'=COUNTIF(U{r}:AY{r},"A")'
        assert ws[f"BA{r}"].value == f'=COUNTIF(U{r}:AY{r},"F")'
        assert ws[f"BB{r}"].value == f'=COUNTIF(U{r}:AY{r},"E")'


def test_day_marks_land_in_their_day_columns(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    first = FIRST_DATA_ROW
    # ÁLVAREZ (row 1) has no marks; PENA (row 2) has F on day 3;
    # PEÑA ANDRÉS (row 3) E on day 2; ZAPATA (row 5) A on day 1.
    assert ws[f"W{first + 1}"].value == "F"
    assert ws[f"V{first + 2}"].value == "E"
    assert ws[f"U{first + 4}"].value == "A"
    assert all(ws.cell(row=first, column=c).value is None for c in range(21, 52))


def test_sexual_orientation_column_always_blank(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    for r in range(FIRST_DATA_ROW, 505):
        assert ws[f"M{r}"].value is None


def test_sexual_orientation_value_is_rejected() -> None:
    rows = [{"B": "ana", "C": "zapata", "M": "cualquier"}]
    with pytest.raises(ValueError) as exc:
        build_sheet([AUG_2026], {AUG_2026: rows}, None, CATALOG)
    assert "cualquier" not in str(exc.value).lower()


def test_sensitive_columns_blank_without_authorization(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + 5):
        for col in ("L", "N", "O"):
            assert ws[f"{col}{r}"].value is None


def test_formula_like_text_is_written_as_text() -> None:
    rows = [{"B": "ana", "C": "zapata", "P": "=1+1 calle ficticia"}]
    ws = _build(rows=rows)["AGOSTO"]
    cell = ws[f"P{FIRST_DATA_ROW}"]
    assert cell.data_type == "s"
    assert cell.value == "=1+1 CALLE FICTICIA"


def test_formula_and_unknown_columns_are_rejected() -> None:
    for key in ("F", "R", "AZ", "BA", "BB", "BC", "ZZ"):
        with pytest.raises(ValueError):
            build_sheet([AUG_2026], {AUG_2026: [{"B": "ana", key: "x"}]}, None, CATALOG)


def test_mark_in_trailing_day_column_is_rejected() -> None:
    col = day_column_letter(31)
    assert col == "AY"
    with pytest.raises(ValueError):
        build_sheet([SEP_2026], {SEP_2026: [{"B": "ana", col: "A"}]}, None, CATALOG)


def test_invalid_mark_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_sheet([AUG_2026], {AUG_2026: [{"B": "ana", "U": "X"}]}, None, CATALOG)


# ---------------------------------------------------------------------------
# Validations, SECTOR and calculation
# ---------------------------------------------------------------------------


def test_barrio_validation_references_sector(aug_wb: Any) -> None:
    ws = aug_wb["AGOSTO"]
    matches = [
        dv for dv in ws.data_validations.dataValidation if "Q24" in str(dv.sqref)
    ]
    assert len(matches) == 1
    dv = matches[0]
    assert str(dv.sqref) == "Q24:Q504"
    assert dv.type == "list"
    # Catalog rows plus the trailing OTRO MUNICIPIO row.
    assert dv.formula1 == f"SECTOR!$A$2:$A${len(CATALOG) + 2}"


def test_sector_rewritten_from_catalog() -> None:
    catalog = [_Barrio("BARRIO FICTICIO UNO", "1"), _Barrio("VEREDA FICTICIA", "ZONA SUR")]
    wb = _build(barrios=catalog)
    sector = wb["SECTOR"]
    assert sector.max_row == 4
    assert [c.value for c in sector[1]][:2] == ["BARRRIO/SECTOR", "COMUNA/ CORREGIMIENTO"]
    assert [[c.value for c in row][:2] for row in sector.iter_rows(min_row=2)] == [
        ["BARRIO FICTICIO UNO", "1"],
        ["VEREDA FICTICIA", "ZONA SUR"],
        ["OTRO MUNICIPIO", '=""'],
    ]
    dv = next(d for d in wb["AGOSTO"].data_validations.dataValidation if "Q24" in str(d.sqref))
    assert dv.formula1 == "SECTOR!$A$2:$A$4"


def test_sector_ends_with_otro_municipio_and_blank_zone(aug_wb: Any) -> None:
    """``OTRO MUNICIPIO`` is the last SECTOR row so Excel's list validation
    accepts it in column Q; its zone is the empty-text formula ``=""`` so the
    column-R ``VLOOKUP`` returns blank (an empty cell would yield ``0``)."""
    sector = aug_wb["SECTOR"]
    last = sector.max_row
    assert sector.cell(row=last, column=1).value == "OTRO MUNICIPIO"
    assert sector.cell(row=last, column=2).value == '=""'
    names = [r[0].value for r in sector.iter_rows(min_row=2)]
    assert names.count("OTRO MUNICIPIO") == 1
    # The R-column formula still looks the barrio up in SECTOR and wraps it
    # in IFERROR(..., "").
    formula = aug_wb["AGOSTO"]["R24"].value
    assert "VLOOKUP" in formula and "SECTOR!$A:$B" in formula


def test_sector_does_not_duplicate_otro_municipio() -> None:
    catalog = [_Barrio("BARRIO FICTICIO UNO", "1"), _Barrio("Otro Municipio", "")]
    sector = _build(barrios=catalog)["SECTOR"]
    names = [r[0].value for r in sector.iter_rows(min_row=2)]
    assert names == ["BARRIO FICTICIO UNO", "OTRO MUNICIPIO"]


def test_otro_municipio_row_value_is_accepted_by_validation() -> None:
    rows = [{"B": "ana", "C": "zapata", "Q": "OTRO MUNICIPIO"}]
    wb = _build(rows=rows)
    ws = wb["AGOSTO"]
    assert ws[f"Q{FIRST_DATA_ROW}"].value == "OTRO MUNICIPIO"
    dv = next(d for d in ws.data_validations.dataValidation if "Q24" in str(d.sqref))
    last = int(dv.formula1.rsplit("$", 1)[1])
    assert wb["SECTOR"].cell(row=last, column=1).value == "OTRO MUNICIPIO"


def test_sector_rows_equal_full_active_catalog(aug_wb: Any) -> None:
    sector = aug_wb["SECTOR"]
    got = [(r[0].value, r[1].value) for r in sector.iter_rows(min_row=2)]
    assert got == [(b.name, b.zone) for b in CATALOG] + [("OTRO MUNICIPIO", '=""')]


def test_full_calc_on_load(aug_wb: Any) -> None:
    wb = aug_wb
    assert wb.calculation.fullCalcOnLoad is True


# ---------------------------------------------------------------------------
# Limit and months
# ---------------------------------------------------------------------------


def test_max_rows_accepted() -> None:
    rows = [{"B": "atleta", "C": f"apellido{i:03d}"} for i in range(MAX_ROWS)]
    ws = _build(rows=rows)["AGOSTO"]
    assert ws[f"A{FIRST_DATA_ROW + MAX_ROWS - 1}"].value == MAX_ROWS


def test_481_rows_raise_sheet_too_large() -> None:
    assert MAX_ROWS == 480
    rows = [{"B": "atleta", "C": f"apellido{i:03d}"} for i in range(481)]
    with pytest.raises(SheetTooLarge) as exc:
        build_sheet([AUG_2026], {AUG_2026: rows}, None, CATALOG)
    assert "apellido" not in str(exc.value).lower()


def test_months_kept_in_chronological_order_across_year_boundary() -> None:
    nov, jan = date(2026, 11, 1), date(2027, 1, 1)
    content = build_sheet([jan, nov], {nov: [], jan: []}, None, CATALOG)
    wb = _open(content)
    assert wb.sheetnames == ["NOVIEMBRE", "ENERO", "SECTOR"]
    assert wb["ENERO"]["I7"].value == datetime(2027, 1, 1)
    assert wb["NOVIEMBRE"]["I7"].value == datetime(2026, 11, 1)


def test_empty_or_duplicate_months_rejected() -> None:
    with pytest.raises(ValueError):
        build_sheet([], {}, None, CATALOG)
    with pytest.raises(ValueError):
        build_sheet([AUG_2026, date(2027, 8, 1)], {}, None, CATALOG)


# ---------------------------------------------------------------------------
# US4 — several months in one workbook (T047)
# ---------------------------------------------------------------------------

OCT_2026 = date(2026, 10, 1)


def _sheet_values(ws: Worksheet) -> list[tuple[Any, ...]]:
    return [tuple(c.value for c in row) for row in ws.iter_rows()]


def _period_rows() -> dict[date, list[dict[str, Any]]]:
    """Different fictitious participants per month (September 30 days,
    October 31)."""
    return {
        AUG_2026: _rows(),
        SEP_2026: [
            {"B": "ana", "C": "zapata", "D": "ruiz", "E": date(2014, 3, 2), "X": "A"},
            {"B": "tomás", "C": "ñáñez", "E": date(2013, 2, 1), "AX": "E"},
        ],
        OCT_2026: [{"B": "irene", "C": "oso", "AY": "F"}],
    }


def test_period_sheets_match_single_month_builds() -> None:
    header = ImdertySheetHeader(
        contractor_name="Contratista Ficticio",
        venue="Pista de prueba",
        programs=[ImdertyProgram.individual],
    )
    rows_by_month = _period_rows()
    months = [OCT_2026, AUG_2026, SEP_2026]
    period = _open(build_sheet(months, rows_by_month, header, CATALOG))
    assert period.sheetnames == ["AGOSTO", "SEPTIEMBRE", "OCTUBRE", "SECTOR"]
    assert period.active.title == "AGOSTO"
    assert [ws.sheet_view.tabSelected for ws in period.worksheets] == [
        True,
        False,
        False,
        False,
    ]

    for month, name in (
        (AUG_2026, "AGOSTO"),
        (SEP_2026, "SEPTIEMBRE"),
        (OCT_2026, "OCTUBRE"),
    ):
        single = _open(
            build_sheet([month], {month: rows_by_month[month]}, header, CATALOG)
        )
        assert _sheet_values(period[name]) == _sheet_values(single[name]), name
        assert [c.name for c in _table(period[name]).tableColumns] == [
            c.name for c in _table(single[name]).tableColumns
        ]
    assert _sheet_values(period["SECTOR"]) == _sheet_values(single["SECTOR"])


def test_period_rows_are_per_month() -> None:
    rows_by_month = _period_rows()
    wb = _open(
        build_sheet([AUG_2026, SEP_2026, OCT_2026], rows_by_month, None, CATALOG)
    )
    firsts = {
        name: [
            wb[name][f"B{r}"].value
            for r in range(FIRST_DATA_ROW, FIRST_DATA_ROW + 6)
            if wb[name][f"B{r}"].value is not None
        ]
        for name in ("AGOSTO", "SEPTIEMBRE", "OCTUBRE")
    }
    assert len(firsts["AGOSTO"]) == 5
    assert firsts["SEPTIEMBRE"] == ["TOMÁS", "ANA"]  # Ñ sorts after N, before Z
    assert firsts["OCTUBRE"] == ["IRENE"]
    assert wb["OCTUBRE"]["AY24"].value == "F"
    assert wb["SEPTIEMBRE"]["I7"].value == datetime(2026, 9, 1)


def test_period_missing_month_yields_empty_sheet() -> None:
    wb = _open(build_sheet([AUG_2026, SEP_2026], {AUG_2026: _rows()}, None, CATALOG))
    assert wb["SEPTIEMBRE"][f"B{FIRST_DATA_ROW}"].value is None
    assert wb["SEPTIEMBRE"][f"A{FIRST_DATA_ROW}"].value is None


def test_period_november_to_february_order() -> None:
    months = [date(2027, 2, 1), date(2026, 11, 1), date(2027, 1, 1), date(2026, 12, 1)]
    wb = _open(build_sheet(months, {}, None, CATALOG))
    assert wb.sheetnames == ["NOVIEMBRE", "DICIEMBRE", "ENERO", "FEBRERO", "SECTOR"]
    assert wb["FEBRERO"]["I7"].value == datetime(2027, 2, 1)
    # February 2027 has 28 days: columns for 29–31 carry weekday-only labels.
    assert wb["FEBRERO"][f"{day_column_letter(29)}23"].value == "LU"


def test_twelve_months_accepted_thirteen_rejected() -> None:
    twelve = [date(2026 + (m + 7) // 12, (m + 7) % 12 + 1, 1) for m in range(12)]
    wb = _open(build_sheet(twelve, {}, None, CATALOG))
    assert wb.sheetnames[:2] == ["AGOSTO", "SEPTIEMBRE"]
    assert wb.sheetnames[-2:] == ["JULIO", "SECTOR"]
    assert len(wb.sheetnames) == 13
    with pytest.raises(ValueError):
        build_sheet(twelve + [date(2027, 8, 1)], {}, None, CATALOG)


def test_period_too_large_month_rejected_before_building() -> None:
    rows = [{"B": "atleta", "C": f"apellido{i:03d}"} for i in range(481)]
    with pytest.raises(SheetTooLarge):
        build_sheet([AUG_2026, SEP_2026], {AUG_2026: [], SEP_2026: rows}, None, CATALOG)
