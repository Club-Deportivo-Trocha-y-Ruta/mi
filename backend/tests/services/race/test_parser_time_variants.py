"""Variantes de la celda ``Tiempo`` en los PDFs históricos (feature 044, T024b).

Medido sobre los 15 archivos oficiales 2024–2025 (solo conteos): 230 filas
llegaban al ingestor con ``time_raw == ""`` y se perdían. La celda ``Tiempo``
de esas filas casi nunca estaba vacía: traía una vuelta perdida escrita
fuera de la forma canónica ``(-N VUELTA[S])`` —``-1 vuelta`` sin paréntesis
(la mayoría), ``(1- VUELTA``, ``(- 1 VUELTA)``, ``(2 VUELTAS)``,
``(-2 VULETAS)``, ``-2 vueltas (lap)``— o una vuelta perdida **pegada al
club** en el mismo run (``…CLUB(-1 VUELTA)``). También se reconoce
``MM:SS`` y la hora de dos dígitos, y un déficit desnudo ``-N``.

Los PDFs se generan con ``results_pdf_builder`` — nombres y clubes
ficticios, nunca datos reales.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.race.pdf_parser import ResultsRow, parse_results_document
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    RowSpec,
    build_results_pdf,
)


def _parse(tmp_path: Path, rows: list[RowSpec]) -> dict[str, ResultsRow]:
    pdf = build_results_pdf(
        tmp_path / "variantes.pdf",
        valida_num=6,
        location="Ciudad Ficticia",
        event_date=date(2025, 7, 12),
        categories=[CategorySpec(header="INFANTIL A", rows=rows)],
        name_generator=FakeNameGenerator(),
    )
    parsed = parse_results_document(pdf)
    assert parsed.unreadable_rows == []
    assert len(parsed.categories) == 1
    got = parsed.categories[0].rows
    assert len(got) == len(rows)
    return {row.bib: row for row in got}


@pytest.mark.parametrize(
    "cell",
    [
        "-1 vuelta",
        "-2 VUELTAS",
        "-1 vuelta-",
        "(1- VUELTA",
        "(- 1 VUELTA)",
        "(2 VUELTAS)",
        "(-3 VUELTAS=",
        "()-1 VUELTA)",
        "(-2 VULETAS)",
        "(-3 VIELTAS)",
        "-2 vueltas (lap)",
        "-1",
    ],
)
def test_lap_deficit_variants_are_read_as_time_cell(tmp_path: Path, cell: str):
    rows = _parse(
        tmp_path,
        [
            RowSpec(position=1, bib="901", time_raw="0:40:07", points=50),
            RowSpec(position=2, bib="902", time_raw=cell, points=45),
        ],
    )
    assert rows["902"].time_raw == cell
    assert rows["902"].position == 2
    assert rows["902"].points == 45


@pytest.mark.parametrize("cell", ["13:07", "9:58", "12:02:00"])
def test_short_and_two_digit_hour_times(tmp_path: Path, cell: str):
    rows = _parse(
        tmp_path,
        [
            RowSpec(position=1, bib="911", time_raw=cell, points=50),
            RowSpec(position=2, bib="912", time_raw="0:40:07", points=45),
        ],
    )
    assert rows["911"].time_raw == cell
    assert rows["911"].points == 50


def test_lap_deficit_glued_to_club_is_split_from_club(tmp_path: Path):
    """``…CLUB(-1 VUELTA)`` en un solo run: la celda Tiempo queda vacía y la
    vuelta perdida viaja dentro del club. Se separa, el club queda limpio."""
    rows = _parse(
        tmp_path,
        [
            RowSpec(position=1, bib="921", time_raw="0:40:07", points=50),
            RowSpec(position=2, bib="922", club="CLUB FICTICIO(-1 VUELTA)", points=45),
            RowSpec(position=3, bib="923", club="CLUB FICTICIO -2 VUELTAS", points=40),
        ],
    )
    assert rows["922"].time_raw == "(-1 VUELTA)"
    assert rows["922"].club == "CLUB FICTICIO"
    assert rows["923"].time_raw == "-2 VUELTAS"
    assert rows["923"].club == "CLUB FICTICIO"


def test_lap_deficit_glued_to_city_when_club_is_empty(tmp_path: Path):
    rows = _parse(
        tmp_path,
        [
            RowSpec(position=1, bib="941", time_raw="0:40:07", points=50),
            RowSpec(
                position=2, bib="942", city="CIUDAD FICTICIA(-1 VUELTA)", club="",
                points=45,
            ),
        ],
    )
    assert rows["942"].time_raw == "(-1 VUELTA)"
    assert rows["942"].city == "CIUDAD FICTICIA"


def test_points_and_bib_are_never_taken_as_time(tmp_path: Path):
    """Una fila de verdad sin tiempo sigue siendo ``time_raw == ""`` — los
    puntos y el dorsal no se confunden con ``-N`` ni con ``MM:SS``."""
    rows = _parse(
        tmp_path,
        [
            RowSpec(position=1, bib="931", time_raw="0:40:07", points=50),
            RowSpec(position=2, bib="932", points=1),
            RowSpec(position=3, bib="933", club="CLUB 2", points=12),
        ],
    )
    assert rows["932"].time_raw == ""
    assert rows["932"].points == 1
    assert rows["933"].time_raw == ""
    assert rows["933"].points == 12
    assert rows["933"].club == "CLUB 2"
