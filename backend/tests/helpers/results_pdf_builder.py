"""Constructor de PDFs sintéticos de resultados Copa Valle (feature 044, T002).

Reproduce, con WeasyPrint, el defecto real medido en ``research.md`` R-01:
un valor largo de ``Club/Patrocinador`` no se recorta a su columna — se
imprime con ``white-space: nowrap`` sobre una celda de ancho fijo y se
desborda visualmente sobre la columna ``Tiempo``. Como ``pdfplumber``
ordena los caracteres por posición ``x`` al extraer texto, las letras del
club terminan intercaladas con los dígitos del tiempo y
``app.services.race.pdf_parser._RESULTS_ROW_RE`` deja de matchear esa
línea — exactamente la causa real de pérdida de filas descrita en R-01.

No se agrega ninguna dependencia nueva: WeasyPrint y pdfplumber ya están en
``requirements.txt``.

Privacidad: cada nombre generado proviene de ``FakeNameGenerator``, que
combina nombres de pila comunes con apellidos deliberadamente ficticios
(``Ficticio``, ``Ejemplar``, ``Simulado`` …, el mismo marcador que ya usan
otros fixtures del repo). Ciudades y clubes también salen de listas
ficticias — nunca de datos reales de un atleta o club real.
"""
from __future__ import annotations

import argparse
import itertools
import random
from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path
from typing import Literal, Optional, Sequence

from weasyprint import HTML

#: Los tres layouts que T109 pide: ``historical`` (el defecto de desborde
#: R-01, comportamiento por defecto de este módulo desde T002/T003),
#: ``2026`` (el layout fijo de la válida IV 2026 — mismas columnas, sin el
#: defecto de desborde: T122/la fase 13 lo usan para los golden de paridad)
#: y ``unruled`` (layout ficticio de un organizador distinto, sin rulings y
#: con otro orden de columnas — prueba que el motor de lectura de la fase 13
#: no está pensado solo para el layout de Copa Valle).
Layout = Literal["historical", "2026", "unruled"]

# ---------------------------------------------------------------------------
# Generador de nombres falsos
# ---------------------------------------------------------------------------

#: Nombres de pila — comunes, no identifican a nadie por sí solos.
FIRST_NAMES: tuple[str, ...] = (
    "Andres", "Camila", "Santiago", "Valentina", "Mateo", "Isabella",
    "Samuel", "Sofia", "Nicolas", "Luciana", "Emiliano", "Renata",
    "Tomas", "Antonella", "Gabriel", "Martina",
)

#: Apellidos deliberadamente ficticios — ningún apellido real de Colombia.
#: El marcador "Ficticio" sigue la misma convención ya usada en otros
#: fixtures del repo (ver ``tests/test_audit_athletes.py``).
LAST_NAMES: tuple[str, ...] = (
    "Ficticio", "Ejemplar", "Simulado", "Sintetico", "Prototipo",
    "Demostrativo", "Referencial", "Modelo", "Muestra", "Generico",
)

#: Ciudades ficticias — nunca un municipio real del Valle del Cauca, para
#: no dar ninguna pista de ubicación real de un menor.
CITY_POOL: tuple[str, ...] = (
    "Ciudad Ficticia Uno", "Ciudad Ficticia Dos", "Municipio Ejemplo",
    "Localidad Simulada", "Villa Demostrativa",
)

#: Clubes/patrocinadores ficticios de longitud "normal" — calibrados
#: empíricamente (ver historial de este archivo) para caber en la columna
#: Club/Patrocinador sin desbordarse, con las anchuras de ``_COL_WIDTHS_PX``
#: más abajo. Si se cambian esas anchuras, hay que recalibrar esta lista
#: (correr el builder y revisar ``page.extract_text()`` a mano).
CLUB_POOL: tuple[str, ...] = (
    "Ficticio FC", "Club Ejemplo", "Modelo FC", "Simulado FC",
)

#: Clubes/patrocinadores ficticios "largos" — calibrados empíricamente para
#: desbordarse sobre la columna Tiempo (letras intercaladas con los dígitos
#: del tiempo), reproduciendo el defecto real de R-01. Igual que
#: ``CLUB_POOL``: recalibrar si cambian las anchuras de columna.
LONG_CLUB_POOL: tuple[str, ...] = (
    "Fundacion Deportiva Ficticia Comunitaria",
    "Deportiva Ficticia Comunitaria del Valle",
    "Asociacion Ficticia Comunitaria del Sur",
    "Corporacion Ejemplo Comunitaria Simulada",
)

#: Semilla fija por defecto — determinística entre corridas, sin depender
#: de la fecha real de ejecución.
DEFAULT_SEED = 20260918


@dataclass
class FakeNameGenerator:
    """Generador determinístico de nombres/ciudades/clubes ficticios.

    Expone ``generated`` (lista de nombres completos ya producidos) para
    que otros tests puedan barrerla y confirmar que cada token proviene de
    ``FIRST_NAMES``/``LAST_NAMES`` — nunca de una lista de personas reales.
    """

    seed: int = DEFAULT_SEED
    _rng: random.Random = field(init=False, repr=False)
    generated: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def next_name(self) -> str:
        given, surname = self.next_name_parts()
        return f"{given} {surname}"

    def next_name_parts(self) -> tuple[str, str]:
        """Como ``next_name`` pero separado en (nombre de pila, apellidos) —
        lo que pide el layout ``unruled`` (columnas "surname"/"given names"
        aparte, sin columna de dorsal). Agrega el nombre completo a
        ``generated`` igual que ``next_name``."""
        first = self._rng.choice(FIRST_NAMES)
        last1 = self._rng.choice(LAST_NAMES)
        last2 = self._rng.choice(LAST_NAMES)
        given, surname = first, f"{last1} {last2}"
        self.generated.append(f"{given} {surname}")
        return given, surname

    def next_city(self) -> str:
        return self._rng.choice(CITY_POOL)

    def next_club(self) -> str:
        return self._rng.choice(CLUB_POOL)

    def next_long_club(self) -> str:
        return self._rng.choice(LONG_CLUB_POOL)


# ---------------------------------------------------------------------------
# Especificación de filas y categorías
# ---------------------------------------------------------------------------


@dataclass
class RowSpec:
    """Una fila de la tabla RESULTADOS, tal como debe imprimirse.

    ``time_raw`` acepta directamente el string ``H:MM:SS`` (el builder no
    calcula tiempos). Precedencia en la celda Tiempo:
    ``status`` > ``minus_laps`` > ``time_raw`` > celda vacía.

    ``long_club=True`` fuerza el uso de un club de ``LONG_CLUB_POOL`` (o de
    ``club``, si se dio explícito) con ``white-space: nowrap`` para
    reproducir el desborde sobre Tiempo — ver el docstring del módulo.

    Una fila "clasificada sin tiempo" (R-01 punto 4 / R-05: banda que sólo
    matchea ``pos bib body points``) se logra con ``time_raw=None``,
    ``status=None`` y ``minus_laps=None`` — la celda Tiempo queda vacía
    pero posición, dorsal, nombre y puntos siguen presentes.
    """

    position: Optional[int] = None
    bib: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    club: Optional[str] = None
    time_raw: Optional[str] = None
    status: Optional[str] = None  # "DNF" | "DSQ" | "DNS"
    minus_laps: Optional[int] = None
    points: Optional[int] = None
    long_club: bool = False


@dataclass
class CategorySpec:
    """Una categoría del documento: encabezado tal como se imprime + filas."""

    header: str
    rows: list[RowSpec] = field(default_factory=list)


def sequential_category(
    header: str,
    n: int,
    *,
    start_points: int = 50,
    base_minutes: int = 40,
    minutes_step: int = 1,
) -> CategorySpec:
    """Atajo: categoría con ``n`` filas normales, posiciones 1..n.

    Pensado para que otros tests (band reader, parser histórico) puedan
    partir de una categoría "sana" y luego mutar ``category.rows`` para
    provocar los casos borde: quitar una posición (``del rows[i]``),
    duplicarla (``rows[i].position = rows[i - 1].position``), o marcar
    ``rows[i].long_club = True`` en cualquier fila.
    """
    rows = [
        RowSpec(
            position=i,
            time_raw=(
                f"0:{base_minutes + (i - 1) * minutes_step:02d}:{(i * 7) % 60:02d}"
            ),
            points=max(1, start_points - (i - 1)),
        )
        for i in range(1, n + 1)
    ]
    return CategorySpec(header=header, rows=rows)


# ---------------------------------------------------------------------------
# Layout / render
# ---------------------------------------------------------------------------

#: Meses en español, mayúsculas y sin tilde — igual que
#: ``app.services.race.pdf_parser._MONTH_TO_INT`` (el header debe poder
#: parsearse con el regex real del parser).
_MONTHS: tuple[str, ...] = (
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
    "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
)

#: I..XII — cubre de sobra los números de válida usados hoy (hasta VII) y
#: el caso de prueba pedido explícitamente para esta feature (VIII).
_ROMAN: tuple[str, ...] = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
)


def _roman(n: int) -> str:
    if not 1 <= n <= len(_ROMAN):
        raise ValueError(f"valida_num fuera de rango I-XII: {n}")
    return _ROMAN[n - 1]


def _month_name(month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError(f"mes fuera de rango 1-12: {month}")
    return _MONTHS[month - 1]


#: Anchuras de columna (px) calibradas contra WeasyPrint real (ver
#: historial de este archivo) para que:
#: - una fila normal (nombre/ciudad/club de las listas ficticias por
#:   defecto, incluida la combinación más larga de nombre+ciudad) quede en
#:   una sola línea, con espacio limpio entre columnas, y matchee
#:   ``_RESULTS_ROW_RE``;
#: - una fila ``long_club=True`` con un club de ``LONG_CLUB_POOL`` se
#:   desborde sobre la columna Tiempo, intercalando letras del club con
#:   los dígitos del tiempo, y deje de matchear ese regex.
_COL_WIDTHS_PX: dict[str, int] = {
    "ord": 30,
    "bib": 40,
    "name": 230,
    "city": 130,
    "club": 100,
    "time": 90,
    "points": 50,
}
_TABLE_WIDTH_PX = sum(_COL_WIDTHS_PX.values())

#: Columnas del layout ``unruled`` (T109): "position, surname, given names,
#: club, city, time, points" — sin dorsal, con el nombre partido en dos
#: columnas y en orden apellidos-antes-que-nombre.
_UNRULED_COL_WIDTHS_PX: dict[str, int] = {
    "ord": 30,
    "surname": 140,
    "given": 110,
    "club": 100,
    "city": 130,
    "time": 90,
    "points": 50,
}
_UNRULED_TABLE_WIDTH_PX = sum(_UNRULED_COL_WIDTHS_PX.values())


def _css(*, ruled: bool, table_width_px: int) -> str:
    border = "1px solid black" if ruled else "none"
    return f"""
@page {{ size: Letter; margin: 1.2cm; }}
body {{ font-family: sans-serif; font-size: 9pt; }}
p.event-header {{ font-weight: bold; margin: 0 0 8px 0; }}
p.cat-header {{ font-weight: bold; margin: 10px 0 2px 0; }}
table {{
    border-collapse: collapse;
    table-layout: fixed;
    width: {table_width_px}px;
    margin-bottom: 4px;
}}
th, td {{
    border: {border};
    padding: 2px 3px;
    white-space: nowrap;
    overflow: visible;
    font-size: 8.5pt;
}}
"""


#: Layouts ruled (``historical``/``2026``) comparten CSS y columnas; solo
#: ``unruled`` (sin rulings, columnas propias) difiere.
_CSS = _css(ruled=True, table_width_px=_TABLE_WIDTH_PX)
_UNRULED_CSS = _css(ruled=False, table_width_px=_UNRULED_TABLE_WIDTH_PX)


def _colgroup_html(layout: Layout) -> str:
    widths = _UNRULED_COL_WIDTHS_PX if layout == "unruled" else _COL_WIDTHS_PX
    cols = "".join(f'<col style="width:{width}px">' for width in widths.values())
    return f"<colgroup>{cols}</colgroup>"


def _time_cell(row: RowSpec) -> str:
    if row.status:
        return row.status
    if row.minus_laps is not None:
        unit = "VUELTA" if row.minus_laps == 1 else "VUELTAS"
        return f"(-{row.minus_laps} {unit})"
    if row.time_raw:
        return row.time_raw
    return ""


def _name_parts(row: RowSpec, gen: FakeNameGenerator) -> tuple[str, str]:
    """``(given, surname)`` — de ``row.name`` si vino explícito (se parte en
    el primer espacio) o del generador si no."""
    if row.name is not None:
        given, _, surname = row.name.partition(" ")
        return given, surname
    return gen.next_name_parts()


def _render_row_html(
    row: RowSpec,
    gen: FakeNameGenerator,
    bib_counter: "itertools.count[int]",
    *,
    layout: Layout,
) -> str:
    position = "" if row.position is None else str(row.position)
    city = row.city if row.city is not None else gen.next_city()
    if row.club is not None:
        club = row.club
    elif row.long_club:
        club = gen.next_long_club()
    else:
        club = gen.next_club()
    time_cell = _time_cell(row)
    points = "" if row.points is None else str(row.points)

    if layout == "unruled":
        given, surname = _name_parts(row, gen)
        cells = [
            position, escape(surname), escape(given), escape(club), escape(city),
            time_cell, points,
        ]
    else:
        bib = row.bib if row.bib is not None else str(next(bib_counter))
        name = row.name if row.name is not None else gen.next_name()
        cells = [
            position, bib, escape(name), escape(city), escape(club), time_cell, points,
        ]
    tds = "".join(f"<td>{c}</td>" for c in cells)
    return f"<tr>{tds}</tr>"


def _render_html(
    *,
    valida_num: int,
    location: str,
    event_date: date,
    categories: Sequence[CategorySpec],
    name_generator: FakeNameGenerator,
    layout: Layout,
) -> str:
    header_line = (
        f"VALIDA {_roman(valida_num)} {location.upper()} "
        f"{_month_name(event_date.month)} {event_date.day} DE {event_date.year}"
    )

    bib_counter = itertools.count(100)
    blocks: list[str] = [f'<p class="event-header">{escape(header_line)}</p>']

    if layout == "unruled":
        header_row = (
            "<tr><th>Ord</th><th>Apellidos</th><th>Nombres</th>"
            "<th>Club/Patrocinador</th><th>Ciudad</th><th>Tiempo</th>"
            "<th>Puntos</th></tr>"
        )
        css = _UNRULED_CSS
    else:
        header_row = (
            "<tr><th>Ord</th><th>N°</th><th>Nombre completo</th>"
            "<th>Ciudad</th><th>Club/Patrocinador</th><th>Tiempo</th>"
            "<th>Puntos</th></tr>"
        )
        css = _CSS

    for category in categories:
        blocks.append(f'<p class="cat-header">CAT: {escape(category.header)}</p>')
        rows_html = "".join(
            _render_row_html(row, name_generator, bib_counter, layout=layout)
            for row in category.rows
        )
        blocks.append(
            f"<table>{_colgroup_html(layout)}{header_row}{rows_html}</table>"
        )

    body = "\n".join(blocks)
    return f"<html><head><style>{css}</style></head><body>{body}</body></html>"


def build_results_pdf(
    path: str | Path,
    *,
    valida_num: int,
    location: str,
    event_date: date,
    categories: Sequence[CategorySpec],
    name_generator: Optional[FakeNameGenerator] = None,
    layout: Layout = "historical",
) -> Path:
    """Renderiza un PDF sintético de resultados.

    ``categories`` documenta el orden de aparición en el documento (todas
    las categorías se imprimen en una sola tabla por categoría; WeasyPrint
    pagina automáticamente si el contenido no cabe en una página).

    ``name_generator`` es opcional — si no se pasa uno, se crea uno propio
    con ``DEFAULT_SEED`` (determinístico). Pásalo explícitamente si el
    test necesita inspeccionar ``generator.generated`` después.

    ``layout`` (T109, amendment 2026-09-26): ``"historical"`` (por defecto,
    sin cambios de comportamiento respecto a T002/T003), ``"2026"`` (mismas
    columnas, para los golden de paridad de T122) o ``"unruled"`` (sin
    rulings, columnas "position, surname, given names, club, city, time,
    points" — sin dorsal).
    """
    out_path = Path(path)
    gen = name_generator if name_generator is not None else FakeNameGenerator()
    html = _render_html(
        valida_num=valida_num,
        location=location,
        event_date=event_date,
        categories=categories,
        name_generator=gen,
        layout=layout,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# CLI (T109, quickstart §9.4): genera un PDF sintético de muestra para
# probar el motor de lectura de la fase 13 a mano, sin escribir un test.
# ---------------------------------------------------------------------------


def _default_categories() -> list[CategorySpec]:
    return [
        sequential_category("INFANTIL A", 6),
        sequential_category("PREJUVENIL A DAMAS", 4),
    ]


def _build_cli(argv: Optional[Sequence[str]] = None) -> Path:
    parser = argparse.ArgumentParser(
        prog="python -m tests.helpers.results_pdf_builder",
        description=(
            "Genera un PDF sintético de resultados (nombres/ciudades/clubes "
            "ficticios) en el layout indicado, para probar a mano el motor "
            "de lectura offline de la fase 13."
        ),
    )
    parser.add_argument(
        "--layout",
        choices=("historical", "2026", "unruled"),
        default="historical",
    )
    parser.add_argument("--out", required=True, help="Ruta del PDF a escribir.")
    parser.add_argument("--valida-num", type=int, default=1)
    parser.add_argument("--location", default="Ciudad Ficticia")
    args = parser.parse_args(argv)

    return build_results_pdf(
        args.out,
        valida_num=args.valida_num,
        location=args.location,
        event_date=date(2026, 3, 1),
        categories=_default_categories(),
        layout=args.layout,
    )


if __name__ == "__main__":  # pragma: no cover — atajo manual, sin test dedicado
    written = _build_cli()
    print(f"PDF sintético escrito en: {written}")
