"""Constructor de CSV/TSV sintéticos de resultados (amendment 2026-09-26,
T109).

Complementa ``results_pdf_builder``: algunos organizadores no publican un
PDF con tabla sino un archivo delimitado (research R-17/R-18 — el motor de
lectura offline debe entender ambos). Reusa ``CategorySpec``/``RowSpec``/
``FakeNameGenerator`` de ``results_pdf_builder`` para no duplicar el modelo
de datos ni el generador de nombres ficticios.

Dos formas de ubicar la categoría, controladas por ``categories_as_column``:

- ``False`` (por defecto): una fila separadora ``CAT: <encabezado>`` antes
  de cada bloque de categoría, cada bloque con su propia fila de encabezado
  de columnas — el patrón real de ``tests/fixtures/race/valida_i_2026_sevilla.csv``.
- ``True``: una sola tabla con una columna ``categoria`` al principio;
  todas las filas de todas las categorías, sin filas separadoras.

Privacidad: cada nombre/ciudad/club viene de ``FakeNameGenerator`` — nunca
un dato real de un corredor.
"""
from __future__ import annotations

import csv
import io
import itertools
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    _month_name,
    _roman,
    _time_cell,
)

_COLUMN_HEADER: tuple[str, ...] = (
    "POS", "N°", "CORREDOR", "CIUDAD", "CLUB / EQUIPO", "TIEMPO", "PUNTOS",
)


def _row_values(
    row, gen: FakeNameGenerator, bib_counter: "itertools.count[int]"
) -> list[str]:
    position = "" if row.position is None else str(row.position)
    bib = row.bib if row.bib is not None else str(next(bib_counter))
    name = row.name if row.name is not None else gen.next_name()
    city = row.city if row.city is not None else gen.next_city()
    if row.club is not None:
        club = row.club
    elif row.long_club:
        club = gen.next_long_club()
    else:
        club = gen.next_club()
    time_cell = _time_cell(row)
    points = "" if row.points is None else str(row.points)
    return [position, bib, name, city, club, time_cell, points]


def build_results_csv(
    path: str | Path,
    *,
    valida_num: int,
    location: str,
    event_date: date,
    categories: Sequence[CategorySpec],
    name_generator: Optional[FakeNameGenerator] = None,
    delimiter: str = ";",
    categories_as_column: bool = False,
) -> Path:
    """Renderiza un CSV/TSV sintético de resultados.

    ``delimiter`` acepta ``";"``, ``","`` o ``"\\t"`` (los tres pedidos por
    T109). El archivo se escribe en UTF-8, sin BOM.
    """
    out_path = Path(path)
    gen = name_generator if name_generator is not None else FakeNameGenerator()
    bib_counter = itertools.count(100)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")

    header_line = (
        f"VALIDA {_roman(valida_num)} {location.upper()} "
        f"{_month_name(event_date.month)} {event_date.day} DE {event_date.year}"
    )
    writer.writerow([header_line])
    writer.writerow([])

    if categories_as_column:
        writer.writerow(["CATEGORIA", *_COLUMN_HEADER])
        for category in categories:
            for row in category.rows:
                writer.writerow([category.header, *_row_values(row, gen, bib_counter)])
    else:
        for category in categories:
            writer.writerow([f"CAT: {category.header}"])
            writer.writerow(list(_COLUMN_HEADER))
            for row in category.rows:
                writer.writerow(_row_values(row, gen, bib_counter))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(buf.getvalue(), encoding="utf-8", newline="")
    return out_path
