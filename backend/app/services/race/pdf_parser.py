"""Parser de PDFs oficiales Copa Valle XCO (RESULTADOS y GENERAL).

Operación pura: lee ``Path`` y devuelve dataclasses. No toca DB.

Lectura **band-first** de RESULTADOS (feature 044, research R-01)
------------------------------------------------------------------
El camino por líneas de texto pierde entre 16 % y 25 % de las filas de los
archivos oficiales históricos (y 2 filas de la válida IV de 2026): cuando el
``Club/Patrocinador`` es largo no se recorta a su columna, se imprime
*encima* de la columna ``Tiempo``, y como ``page.extract_text()`` ordena los
caracteres por ``x`` las letras del club quedan intercaladas con los dígitos
del tiempo (``…AA0A:A2A2:15 3``). El regex de fila deja de matchear y la
fila se pierde en silencio.

Algoritmo vigente, por página:

1. ``page.find_tables(_TABLE_SETTINGS)`` entrega una **banda** (bbox) por
   fila. Los rulings son confiables para los LÍMITES de fila, pero no para
   las columnas club/tiempo/puntos (el club desbordado cruza el ruling), así
   que tiempo y puntos ya **no** se leen de las celdas.
2. Por cada banda, ``_band_text`` reconstruye el texto tomando los
   ``page.chars`` de la banda **en orden de flujo del PDF** — nunca ordenados
   por ``x``. En ese orden el club y el tiempo quedan contiguos y limpios
   aunque se superpongan visualmente.
3. Regex de fila relajado (``_RESULTS_ROW_RE``): hora de un solo dígito con
   lookbehind ``(?<![\\d:])`` y espacio opcional antes del tiempo.
4. Una banda que solo matchea ``pos bib body points``
   (``_RESULTS_ROW_NO_TIME_RE``) se conserva como **clasificada sin tiempo**
   (``time_raw=""``); una banda que no matchea nada se reporta como
   ``UnreadableRow`` con página y ordinal, nunca se descarta en silencio.
5. ``name``/``city``/``club`` salen de los **runs** de la banda asignados a
   las celdas 2–4 por el ``x`` donde arrancan (``_cells_from_runs``), no del
   texto que devuelve ``table.extract()``. Ese texto también está corrompido
   en las filas desbordadas: la ciudad llega truncada y el club llega
   intercalado con el desborde vecino. Respaldos: las celdas de la tabla y,
   por último, el cuerpo del regex.
6. Los encabezados ``CAT:`` se intercalan con las bandas por posición
   vertical (``extract_text_lines`` top vs top de la banda). La categoría
   **persiste entre páginas** (edge-cases.md §4.9 — INFANTIL B continúa
   entre p4 y p5).
7. El camino por líneas de texto se conserva como **respaldo** para páginas
   donde ``find_tables`` no devuelve tabla, y como verificación cruzada: si
   un camino encuentra una fila que el otro no, se emite un warning
   ``row_path_mismatch`` (solo conteos).

Descarte de cabeceras: líneas que matchean ``COPA VALLE``, ``VALIDA``,
``RESULTADOS``, ``CLASIFICACION``, ``GENERAL``, ``Ord N``, ``ORD N`` se
descartan. Línea espuria ``0 COPA VALLE…`` (§4.10) se tolera.

Logging: **solo** página, ordinal, dorsal y conteos. Nunca un nombre, una
ciudad ni un club — los archivos son actas de menores de edad.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

import pdfplumber

from app.services.race.normalizer import LAP_WORD_PATTERN, parse_category_header

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses de salida
# ---------------------------------------------------------------------------


@dataclass
class ResultsRow:
    """Una fila del PDF RESULTADOS (un corredor en una válida).

    ``time_raw == ""`` significa **clasificado sin tiempo**: la banda trae
    posición, dorsal y puntos pero la celda ``Tiempo`` vino vacía en el acta
    (research R-01 punto 4). No es lo mismo que ``DNF``/``DSQ``/``DNS``, que
    sí se conservan como texto.
    """

    position: Optional[int]
    bib: str
    name: str
    city: str  #: capturado para resolución de homónimos, no se persiste en `RaceCompetitor`.
    club: str
    time_raw: str
    points: int


@dataclass
class UnreadableRow:
    """Banda de fila que no pudo interpretarse (FR-001).

    Se reporta al coach en la previsualización en vez de descartarse en
    silencio. Solo lleva ubicación — ``page`` y el ordinal impreso cuando la
    celda 0 de la tabla es numérica — nunca texto de la fila.
    """

    page: int
    ordinal: Optional[int]


@dataclass
class ParsedCategory:
    """Una categoría del acta, en el orden en que aparece en el documento.

    ``code is None`` significa encabezado no reconocido: las filas **se
    conservan** igual (FR-002) y el commit queda bloqueado hasta que exista
    un mapeo en ``normalizer.HEADER_TO_CODE``.
    """

    header_raw: str  #: tal como se imprime, p. ej. "PREJUVENIL A DAMAS".
    code: Optional[str]
    rows: list[ResultsRow] = field(default_factory=list)


@dataclass
class ParsedResults:
    """Salida completa de ``parse_results_document``."""

    categories: list[ParsedCategory] = field(default_factory=list)
    unreadable_rows: list[UnreadableRow] = field(default_factory=list)


@dataclass
class GeneralRow:
    """Una fila del PDF GENERAL (acumulado temporada por corredor)."""

    overall_position: int
    bib: str
    name: str
    city: str
    club: str
    points_per_valida: list[int]  #: orden [I, II, III, IV, ...] según header detectado.
    total_points: int


@dataclass
class EventHeader:
    """Metadatos extraídos del header del PDF (3 primeras líneas típicas)."""

    valida_num: int  #: 1..7 para válidas regulares, 99 para CD.
    location: str
    event_date: date
    raw_text: str


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Settings para ``page.extract_tables`` que mejor preserva celdas separadas
#: en los PDFs Válida IV. La estrategia ``"lines"`` usa los rulings del PDF
#: y produce columnas correctas (con kerning ciudad/club ocasional, no
#: impactante porque ``city`` no se persiste y ``club`` para TyR siempre
#: queda limpio — el rider TyR vive en Yumbo, ciudad corta sin kerning).
_TABLE_SETTINGS: dict = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "intersection_tolerance": 3,
}

#: Fila RESULTADOS canónica: ``<pos> <bib> <name+city+club> <time|status> <points>``.
#: Captura los 4 grupos al final con regex no-greedy del medio. La separación
#: ``name`` vs ``city`` vs ``club`` se delega a la tabla; este regex sólo
#: garantiza ``position``, ``bib``, ``time_raw`` y ``points``.
#:
#: Relajado en la feature 044 (research R-01 punto 3), dos cambios:
#:
#: - **Hora de un solo dígito** con lookbehind ``(?<![\d:])``. Las carreras
#:   XCO duran menos de 10 h, así que la hora siempre es ``\d`` sola. El
#:   lookbehind es una guarda de corrección, no de recuperación: si el
#:   carácter previo es un dígito o dos puntos no se puede saber si ese
#:   dígito pertenece a la hora o al club, así que el parser prefiere
#:   declarar la fila "sin tiempo" antes que inventar un tiempo equivocado.
#: - **Espacio opcional antes del tiempo** (``\s*``), para el club que
#:   termina pegado a la hora (``…FICTICIOFC0:40:07``). Los tokens de estado
#:   sí siguen exigiendo un espacio previo (``(?<=\s)``) porque un club
#:   podría terminar en esas tres letras.
#:
#: El grupo se sigue llamando ``time`` y sigue capturando también los estados
#: (``DNF``/``DSQ``/``DNS``/``(-N VUELTAS)``) — el self-test del builder de
#: fixtures depende de esa forma.
#:
#: Ampliado en T024b (medido sobre los 15 archivos 2024–2025: 230 filas
#: llegaban con ``time_raw == ""``). El token de tiempo ahora también acepta:
#:
#: - **Hora de dos dígitos** y **``MM:SS``** sin horas, con el mismo
#:   lookbehind ``(?<![\d:])``. ``parse_time`` rechaza una hora ≥ 10 (errata
#:   del acta) y el ingestor conserva la fila con tiempo nulo.
#: - **Déficit de vueltas no canónico** (``_LAP_TOKEN``): ``-1 vuelta``,
#:   ``(1- VUELTA``, ``(- 1 VUELTA)``, ``(2 VUELTAS)``, ``(-2 VULETAS)``,
#:   ``-2 vueltas (lap)``… Exige un número **y** la palabra de vuelta
#:   (``normalizer.LAP_WORD_PATTERN``), más un signo o paréntesis, así que
#:   ni el dorsal ni los puntos pueden leerse como vuelta. No exige espacio
#:   previo: en las actas la vuelta perdida a veces queda pegada al club en
#:   el mismo run (``…CLUB(-1 VUELTA)``) — ``_row_from_match`` la despega.
#: - **``-N`` desnudo** con espacio previo.
#:
#: Todo sigue anclado al final de la banda (``\s+<puntos>$``): el token solo
#: puede ser lo que está justo antes de los puntos.
_LAP_TOKEN = (
    r"(?:\(\s*\)?\s*-?\s*\d{1,2}\s*-?|-\s*\d{1,2}\s*-?|\d{1,2}\s*-)\s*"
    + LAP_WORD_PATTERN
    + r"(?:\s*[)=\-])?(?:\s*\(\w+\))?"
)
_RESULTS_ROW_RE = re.compile(
    r"^(?P<pos>\d+)\s+(?P<bib>\d+)\s+(?P<body>.+?)\s*"
    r"(?P<time>(?<![\d:])\d{1,2}:\d{2}(?::'?\d{2})?"
    r"|(?<=\s)(?:DNF|DSQ|DNS)"
    r"|" + _LAP_TOKEN
    + r"|(?<=\s)-\d{1,2})\s+"
    r"(?P<points>\d+)\s*$",
    re.IGNORECASE,
)

#: Fila **clasificada sin tiempo**: ``<pos> <bib> <body> <points>`` desnudo,
#: sin token de tiempo ni de estado (research R-01 punto 4 — 2 filas en cada
#: archivo de 2025). Solo se intenta cuando ``_RESULTS_ROW_RE`` ya falló y la
#: línea no es una cabecera descartable, para que no se coma ruido.
_RESULTS_ROW_NO_TIME_RE = re.compile(
    r"^(?P<pos>\d+)\s+(?P<bib>\d+)\s+(?P<body>.+?)\s+(?P<points>\d+)\s*$"
)

#: Encabezado de categoría dentro de una línea: ``CAT: <NOMBRE>``. Captura el
#: nombre tal como se imprime (``header_raw``). Tolera un prefijo antes del
#: ``CAT:`` usando la última ocurrencia.
_CAT_LINE_RE = re.compile(r"CAT\s*:\s*(?P<header>\S.*)$", re.IGNORECASE)

#: Tolerancia (pt) del hueco horizontal a partir del cual ``_band_text``
#: inserta un espacio entre dos caracteres consecutivos (research R-01
#: punto 2). Dentro de una misma palabra los chars vienen pegados (gap ≈ 0).
_BAND_GAP_PT: float = 1.0

#: Líneas de cabecera fijas que se descartan. Tolera prefijo espurio
#: ``\d+\s*`` (línea ``0 COPA VALLE...`` del separador, §4.10).
_HEADER_DISCARD_RE = re.compile(
    r"^\s*\d*\s*(COPA\s+VALLE|VALIDA\s+|RESULTADOS|CLASIFICACION|GENERAL|ORD\s+N|Ord\s+N)",
    re.IGNORECASE,
)

#: Header tabla GENERAL: extrae los códigos de columnas (válidas + Total).
#: ``ORD N° Nombre completo Ciudad Club/Patrocinador <V1> <V2> ... Total``
_GENERAL_HEADER_RE = re.compile(
    r"^.+?Club/Patrocinador\s+(?P<valida_cols>.+?)\s+Total\s*$",
    re.IGNORECASE,
)

#: Header del evento: ``VALIDA IV CALI MAYO 17 DE 2026`` o ``VALIDA CD ...``.
#: Acepta ``I``–``XII`` y ``CD`` (research R-02: la válida de cierre de 2025
#: es ``VALIDA VIII`` y con la alternancia anterior, que paraba en VII, el
#: header devolvía ``None``).
#:
#: La alternancia va **de más largo a más corto** para que ``VIII`` no se lea
#: como ``VII`` seguido de una ubicación que empieza por ``I`` (el grupo
#: ``location`` acepta la letra ``I``).
_EVENT_HEADER_RE = re.compile(
    r"VALIDA\s+(?P<num>CD|XII|XI|IX|X|VIII|VII|VI|IV|V|III|II|I)\s+"
    r"(?P<location>[A-ZÁÉÍÓÚÑ ]+?)\s+"
    r"(?P<month>ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+"
    r"(?P<day>\d{1,2})\s+DE\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

#: Roman numeral → int. ``CD`` se mapea a 99 (Campeonato Departamental).
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "CD": 99,
}

#: Mes español → int.
_MONTH_TO_INT: dict[str, int] = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

# Indices de columnas para tablas RESULTADOS (8 columnas: Ord N° Nombre Ciudad Club Tiempo Puntos = 7).
# Algunos PDFs producen 7, otros 8 (depende de cómo pdfplumber separe).
_RES_COL_ORD = 0
_RES_COL_BIB = 1
_RES_COL_NAME = 2
_RES_COL_CITY = 3
_RES_COL_CLUB = 4
_RES_COL_TIME = 5
_RES_COL_POINTS = 6


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _is_discardable_line(line: str) -> bool:
    """Devuelve True si la línea es una cabecera/separador a descartar."""
    if not line.strip():
        return True
    return bool(_HEADER_DISCARD_RE.match(line))


def _build_table_index(
    tables: list[list[list[Optional[str]]]],
) -> dict[tuple[str, str], tuple[str, str, str]]:
    """Mapea ``(pos, bib)`` → ``(name, city, club)`` desde las tablas extraídas.

    pdfplumber a veces devuelve `None` para celdas vacías; los normalizamos
    a ``""``. La clave compuesta evita colisión si una posición se repite en
    distintas categorías de la misma página (mismo pos=1, distinto bib).
    """
    idx: dict[tuple[str, str], tuple[str, str, str]] = {}
    for table in tables:
        for row in table:
            if not row or len(row) < 7:
                continue
            cells = [(c or "").strip() for c in row]
            # Skip header rows (la primera celda no es numérica)
            if not cells[_RES_COL_ORD].isdigit():
                continue
            if not cells[_RES_COL_BIB].isdigit():
                continue
            key = (cells[_RES_COL_ORD], cells[_RES_COL_BIB])
            name = cells[_RES_COL_NAME] if len(cells) > _RES_COL_NAME else ""
            city = cells[_RES_COL_CITY] if len(cells) > _RES_COL_CITY else ""
            club = cells[_RES_COL_CLUB] if len(cells) > _RES_COL_CLUB else ""
            idx[key] = (name, city, club)
    return idx


def _split_body_fallback(body: str) -> tuple[str, str, str]:
    """Si la tabla no devolvió celdas separadas, intenta partir el body en
    ``(name, city, club)`` por la heurística "ciudad suele estar entre nombre y
    club". Es best-effort: el ingestor del Paso 4 puede reasignar manualmente.

    Estrategia simple: no intentamos magia — devolvemos ``(body, "", "")`` y
    dejamos que la persistencia capture el raw para revisión humana posterior.
    """
    return body.strip(), "", ""


# ---------------------------------------------------------------------------
# Lector por banda (research R-01)
# ---------------------------------------------------------------------------


def _band_text(chars: Sequence[dict], bbox: tuple[float, float, float, float]) -> str:
    """Reconstruye el texto de una banda de fila leyendo ``chars`` en orden de flujo.

    ``bbox`` es ``(x0, top, x1, bottom)`` — la convención de pdfplumber en
    ``Page.crop`` y ``Table.rows[i].bbox``.

    El filtrado es **solo vertical** (``top``/``bottom`` del char dentro de la
    banda): el ancho de ``bbox`` no recorta nada, porque el propósito mismo de
    la lectura por banda es capturar el texto que se desborda horizontalmente
    fuera de su columna nominal.

    Los caracteres se recorren en el orden en que el PDF los dibuja, **nunca
    ordenados por ``x``**. Se inserta un espacio cuando el hueco con el
    carácter anterior supera ``_BAND_GAP_PT`` o cuando ``x`` salta hacia atrás
    (el arranque del texto de la celda siguiente, que es lo que ocurre cuando
    un club largo se imprime encima de la columna ``Tiempo``).

    La función no inventa un espacio cuando el club queda pegado al tiempo sin
    hueco: reproduce el texto tal cual. La garantía de que el regex no se
    trague la hora vive en el lookbehind de ``_RESULTS_ROW_RE``, no aquí.
    """
    return " ".join(text for _, text in _band_runs(chars, bbox))


def _band_runs(
    chars: Sequence[dict], bbox: tuple[float, float, float, float]
) -> list[tuple[float, str]]:
    """Parte la banda en *runs* de texto: ``(x0 donde arranca, texto)``.

    Un run es una tirada de caracteres contiguos en el flujo del PDF. El corte
    es exactamente el mismo criterio con el que ``_band_text`` inserta un
    espacio (hueco > ``_BAND_GAP_PT`` o salto de ``x`` hacia atrás), así que
    ``_band_text`` es literalmente los runs unidos por un espacio y ambas
    funciones no pueden divergir.

    Medido sobre los archivos oficiales: **cada celda de la fila produce su
    propio run**, y el run de una celda siempre arranca dentro del rango
    horizontal de esa celda aunque la celda anterior se haya desbordado encima
    (el desborde va hacia la derecha, nunca mueve el arranque de la siguiente).
    Eso es lo que permite recuperar nombre, ciudad y club limpios sin confiar
    en el texto de las celdas — ver ``_cells_from_runs``.
    """
    _, top, _, bottom = bbox
    runs: list[tuple[float, str]] = []
    pieces: list[str] = []
    start_x = 0.0
    prev: Optional[dict] = None
    for char in chars:
        if not (char["top"] >= top and char["bottom"] <= bottom):
            continue
        if prev is None or (
            char["x0"] - prev["x1"] > _BAND_GAP_PT or char["x0"] < prev["x0"]
        ):
            if pieces:
                runs.append((start_x, "".join(pieces).strip()))
            pieces = []
            start_x = char["x0"]
        pieces.append(char["text"])
        prev = char
    if pieces:
        runs.append((start_x, "".join(pieces).strip()))
    return [(x, text) for x, text in runs if text]


def _cells_from_runs(
    runs: Sequence[tuple[float, str]],
    cell_boxes: Sequence[Optional[tuple[float, float, float, float]]],
) -> Optional[list[str]]:
    """Asigna cada run a su celda por el ``x`` donde **arranca**.

    Es la lectura correcta del defecto de R-01: cuando una celda se desborda,
    su texto invade la columna siguiente, pero la celda invadida sigue
    dibujando su propio texto desde su propio borde izquierdo. Por eso el
    arranque del run identifica la celda sin ambigüedad, mientras que el texto
    que ``table.extract()`` devuelve para esa celda ya viene contaminado.

    Medido sobre la válida IV de 2026: ``table.extract()`` entrega la ciudad
    truncada (``SANTANDER DE QUILICHAO`` → ``SANTANDER DE``) y el club como
    texto intercalado con el desborde vecino, en decenas de filas. Los runs
    los devuelven íntegros.

    Devuelve ``None`` si algún run arranca fuera de toda celda — señal de que
    el supuesto no se cumple en esa fila y hay que conservar lo que diga la
    tabla.
    """
    out = [""] * len(cell_boxes)
    for start_x, text in runs:
        index = next(
            (
                i
                for i, box in enumerate(cell_boxes)
                if box is not None and box[0] <= start_x < box[2]
            ),
            None,
        )
        if index is None:
            return None
        out[index] = f"{out[index]} {text}" if out[index] else text
    return out


def _chars_by_band(
    chars: Sequence[dict], bboxes: Sequence[tuple[float, float, float, float]]
) -> list[list[dict]]:
    """Reparte los chars de la página entre las bandas, en orden de flujo.

    Una sola pasada sobre ``page.chars`` en vez de una por banda; el orden
    relativo dentro de cada banda es el del content stream, que es justo lo
    que ``_band_text`` necesita.
    """
    buckets: list[list[dict]] = [[] for _ in bboxes]
    for char in chars:
        char_top = char["top"]
        char_bottom = char["bottom"]
        for idx, (_, top, _, bottom) in enumerate(bboxes):
            if char_top >= top and char_bottom <= bottom:
                buckets[idx].append(char)
                break
    return buckets


def _band_cells(
    runs: Sequence[tuple[float, str]],
    cell_boxes: Sequence[Optional[tuple[float, float, float, float]]],
) -> Optional[tuple[str, str, str]]:
    """``(name, city, club)`` de una banda a partir de sus runs, o ``None``."""
    texts = _cells_from_runs(runs, cell_boxes)
    if texts is None or len(texts) <= _RES_COL_CLUB:
        return None
    return (
        texts[_RES_COL_NAME],
        texts[_RES_COL_CITY],
        texts[_RES_COL_CLUB],
    )


def _row_from_match(
    match: re.Match,
    time_raw: str,
    table_idx: dict[tuple[str, str], tuple[str, str, str]],
    band_cells: Optional[tuple[str, str, str]] = None,
) -> ResultsRow:
    """Arma un ``ResultsRow`` desde un match de fila + los campos de texto.

    Orden de preferencia para ``name``/``city``/``club``:

    1. ``band_cells`` — los runs de la banda asignados a las celdas 2–4
       (``_cells_from_runs``). Es la única fuente que sobrevive a un desborde.
    2. Las celdas de ``table.extract()`` (research R-01 punto 6), cuando los
       runs no se pudieron asignar.
    3. El cuerpo completo del regex, cuando la tabla tampoco trajo la fila.
    """
    pos_str = match.group("pos")
    bib = match.group("bib")
    body = match.group("body")
    if band_cells is not None and band_cells[0]:
        name, city, club = band_cells
    else:
        cells = table_idx.get((pos_str, bib))
        if cells is not None and cells[0]:
            name, city, club = cells
        else:
            name, city, club = _split_body_fallback(body)
    if time_raw:
        # Vuelta perdida pegada al texto de la celda anterior en el mismo run
        # (T024b): el token ya es ``time_raw``, no puede quedarse también
        # dentro del club — ni de la ciudad, cuando el club vino vacío.
        if club.endswith(time_raw):
            club = club[: -len(time_raw)].rstrip()
        elif not club and city.endswith(time_raw):
            city = city[: -len(time_raw)].rstrip()
    return ResultsRow(
        position=int(pos_str),
        bib=bib,
        name=name,
        city=city,
        club=club,
        time_raw=time_raw,
        points=int(match.group("points")),
    )


def _match_row_text(text: str) -> tuple[Optional[re.Match], str]:
    """Intenta interpretar el texto de una banda/línea como fila de resultados.

    Devuelve ``(match, time_raw)``; ``(None, "")`` si no es una fila. Una fila
    sin token de tiempo ni de estado se acepta como clasificada sin tiempo
    (``time_raw == ""``).
    """
    match = _RESULTS_ROW_RE.match(text)
    if match is not None:
        return match, match.group("time")
    match = _RESULTS_ROW_NO_TIME_RE.match(text)
    if match is not None:
        return match, ""
    return None, ""


def _category_header_of(text: str) -> Optional[str]:
    """Devuelve el ``header_raw`` de una línea ``CAT: <NOMBRE>``, o ``None``.

    Tolera un prefijo espurio antes del ``CAT:`` — mismo criterio que el
    camino por líneas previo a la feature 044.
    """
    upper = text.upper()
    if not upper.startswith("CAT:") and " CAT:" not in upper:
        return None
    match = _CAT_LINE_RE.search(text)
    return match.group("header").strip() if match is not None else None


# ---------------------------------------------------------------------------
# API pública — RESULTADOS
# ---------------------------------------------------------------------------


def _parse_page(
    page,
    page_no: int,
    state: "_DocState",
) -> None:
    """Procesa una página: intercala encabezados ``CAT:`` y bandas de fila."""
    text = page.extract_text() or ""

    tables = []
    find_tables = getattr(page, "find_tables", None)
    if callable(find_tables):
        tables = find_tables(_TABLE_SETTINGS) or []

    if not tables:
        # Respaldo: páginas donde ``find_tables`` no devuelve tabla (o páginas
        # que no exponen la API, como los dobles de prueba).
        _parse_page_by_lines(text, page_no, state)
        return

    _parse_page_by_bands(page, text, tables, page_no, state)


def _parse_page_by_bands(page, text: str, tables, page_no: int, state: "_DocState") -> None:
    """Camino principal: una banda por fila, chars en orden de flujo."""
    table_idx = _build_table_index([table.extract() for table in tables])

    bboxes: list[tuple[float, float, float, float]] = []
    cell_ordinals: list[Optional[int]] = []
    cell_boxes: list[list] = []
    for table in tables:
        extracted = table.extract()
        for row, cells in zip(table.rows, extracted):
            bboxes.append(row.bbox)
            cell_boxes.append(list(row.cells))
            first = (cells[0] or "").strip() if cells else ""
            cell_ordinals.append(int(first) if first.isdigit() else None)

    buckets = _chars_by_band(page.chars, bboxes)

    # Eventos ordenados por posición vertical: encabezados CAT: y bandas.
    events: list[tuple[float, int, str, object]] = []
    extract_lines = getattr(page, "extract_text_lines", None)
    if callable(extract_lines):
        for line in extract_lines():
            header_raw = _category_header_of(line["text"].strip())
            if header_raw is not None:
                events.append((line["top"], 0, "cat", header_raw))
    for idx, bbox in enumerate(bboxes):
        events.append((bbox[1], 1, "band", idx))
    events.sort(key=lambda event: (event[0], event[1]))

    band_keys: set[tuple[str, str]] = set()
    for _, _, kind, payload in events:
        if kind == "cat":
            state.start_category(str(payload))
            continue

        idx = int(payload)  # type: ignore[arg-type]
        runs = _band_runs(buckets[idx], bboxes[idx])
        band = " ".join(run_text for _, run_text in runs)
        if not band or _is_discardable_line(band):
            continue

        match, time_raw = _match_row_text(band)
        if match is None:
            state.unreadable.append(UnreadableRow(page=page_no, ordinal=cell_ordinals[idx]))
            logger.warning(
                "Banda de fila ilegible en página %d (ordinal=%s)",
                page_no,
                cell_ordinals[idx],
            )
            continue

        band_keys.add((match.group("pos"), match.group("bib")))
        state.add_row(
            _row_from_match(
                match, time_raw, table_idx, _band_cells(runs, cell_boxes[idx])
            ),
            page_no,
        )

    _warn_on_path_mismatch(text, band_keys, page_no)


def _parse_page_by_lines(text: str, page_no: int, state: "_DocState") -> None:
    """Respaldo por líneas de texto (comportamiento previo a la feature 044)."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        header_raw = _category_header_of(stripped)
        if header_raw is not None:
            state.start_category(header_raw)
            continue

        if _is_discardable_line(stripped):
            continue

        match, time_raw = _match_row_text(stripped)
        if match is None:
            # Sub-header partido o ruido — no es una fila.
            continue

        state.add_row(_row_from_match(match, time_raw, {}), page_no)


def _warn_on_path_mismatch(text: str, band_keys: set[tuple[str, str]], page_no: int) -> None:
    """Verificación cruzada banda ↔ línea de texto (research R-01 punto 7)."""
    line_keys: set[tuple[str, str]] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _is_discardable_line(stripped):
            continue
        match = _RESULTS_ROW_RE.match(stripped)
        if match is not None:
            line_keys.add((match.group("pos"), match.group("bib")))

    only_band = len(band_keys - line_keys)
    only_line = len(line_keys - band_keys)
    if only_band or only_line:
        logger.warning(
            "row_path_mismatch en página %d: %d fila(s) solo por banda, "
            "%d solo por línea de texto",
            page_no,
            only_band,
            only_line,
        )


@dataclass
class _DocState:
    """Estado mutable del recorrido del documento (categoría activa, salida)."""

    categories: list[ParsedCategory] = field(default_factory=list)
    unreadable: list[UnreadableRow] = field(default_factory=list)
    current: Optional[ParsedCategory] = None
    unknown_headers: set[str] = field(default_factory=set)

    def start_category(self, header_raw: str) -> None:
        """Abre una categoría. Un encabezado repetido de forma contigua
        (continuación entre páginas) sigue alimentando la misma categoría."""
        if self.current is not None and self.current.header_raw == header_raw:
            return
        code = parse_category_header(f"CAT: {header_raw}")
        if code is None:
            self.unknown_headers.add(header_raw[:80])
            logger.warning("Header CAT desconocido: %r", header_raw[:80])
        category = ParsedCategory(header_raw=header_raw, code=code, rows=[])
        self.categories.append(category)
        self.current = category

    def add_row(self, row: ResultsRow, page_no: int) -> None:
        if self.current is None:
            # Fila antes del primer ``CAT:`` — no se puede atribuir. Se reporta
            # al coach en vez de descartarse en silencio (FR-001).
            logger.warning(
                "Fila sin categoría activa en página %d (bib=%s); no atribuida",
                page_no,
                row.bib,
            )
            self.unreadable.append(UnreadableRow(page=page_no, ordinal=row.position))
            return
        self.current.rows.append(row)


def parse_results_document(path: Path) -> ParsedResults:
    """Parsea un PDF RESULTADOS completo con el lector por banda (research R-01).

    Devuelve las categorías **en orden de documento**, incluidas las de
    encabezado no reconocido (``code is None``) con todas sus filas, más las
    bandas que no pudo interpretar (``unreadable_rows``).
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {path}")

    state = _DocState()
    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # La categoría activa persiste entre páginas (edge-cases §4.9).
            _parse_page(page, page_idx + 1, state)

    if state.unknown_headers:
        logger.warning(
            "Categorías con encabezado desconocido: %d",
            len(state.unknown_headers),
        )
    if state.unreadable:
        logger.warning("Filas ilegibles o no atribuidas: %d", len(state.unreadable))

    return ParsedResults(categories=state.categories, unreadable_rows=state.unreadable)


def parse_results_pdf(path: Path) -> dict[str, list[ResultsRow]]:
    """Parsea un PDF RESULTADOS y devuelve ``{category_code: [ResultsRow, ...]}``.

    Wrapper de retrocompatibilidad sobre ``parse_results_document``: conserva
    la forma de retorno de siempre y excluye las categorías de encabezado no
    reconocido. Una categoría reconocida sin filas sigue apareciendo con lista
    vacía.
    """
    parsed = parse_results_document(path)
    out: dict[str, list[ResultsRow]] = {}
    for category in parsed.categories:
        if category.code is None:
            continue
        out.setdefault(category.code, []).extend(category.rows)
    return out


# ---------------------------------------------------------------------------
# API pública — GENERAL
# ---------------------------------------------------------------------------


def _build_general_row_regex(num_validas: int) -> re.Pattern:
    """Construye regex para fila GENERAL según número de válidas + total.

    Estructura: ``<pos> <bib> <body> <V1> <V2> ... <VN> <total>`` — exactamente
    ``num_validas + 1`` enteros al final.
    """
    nums_pattern = (r"\d+\s+" * num_validas) + r"\d+"
    return re.compile(
        rf"^(?P<pos>\d+)\s+(?P<bib>\d+)\s+(?P<body>.+?)\s+(?P<nums>{nums_pattern})\s*$"
    )


def _detect_general_columns(pdf: pdfplumber.PDF) -> int:
    """Inspecciona la primera página para descubrir cuántas columnas de válidas hay.

    Default 4 si no logra detectar — corresponde a V-IV con I, II, III, IV.
    """
    p1 = pdf.pages[0]
    text = p1.extract_text() or ""
    for ln in text.splitlines():
        if "Total" not in ln or "Club/Patrocinador" not in ln:
            continue
        m = _GENERAL_HEADER_RE.match(ln)
        if m:
            cols = m.group("valida_cols").split()
            return len(cols)
    logger.warning("No se detectó header de columnas GENERAL; usando default=4")
    return 4


def parse_general_pdf(path: Path) -> dict[str, list[GeneralRow]]:
    """Parsea un PDF GENERAL y devuelve ``{category_code: [GeneralRow, ...]}``.

    Auto-detecta número de columnas (válidas + Total) desde el header de p1.
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {path}")

    out: dict[str, list[GeneralRow]] = {}
    current_cat: Optional[str] = None

    with pdfplumber.open(path) as pdf:
        num_validas = _detect_general_columns(pdf)
        row_re = _build_general_row_regex(num_validas)

        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables(table_settings=_TABLE_SETTINGS) or []

            # Index por (pos, bib) → (name, city, club) desde tablas
            table_idx: dict[tuple[str, str], tuple[str, str, str]] = {}
            for table in tables:
                for r in table:
                    if not r or len(r) < 5:
                        continue
                    cells = [(c or "").strip() for c in r]
                    if not cells[0].isdigit() or not cells[1].isdigit():
                        continue
                    table_idx[(cells[0], cells[1])] = (
                        cells[2] if len(cells) > 2 else "",
                        cells[3] if len(cells) > 3 else "",
                        cells[4] if len(cells) > 4 else "",
                    )

            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.upper().startswith("CAT:"):
                    code = parse_category_header(stripped)
                    if code is None:
                        logger.warning(
                            "Header CAT desconocido en GENERAL p%d: %r",
                            page_idx + 1,
                            stripped[:80],
                        )
                        current_cat = None
                        continue
                    current_cat = code
                    out.setdefault(current_cat, [])
                    continue

                if _is_discardable_line(stripped):
                    continue

                m = row_re.match(stripped)
                if not m:
                    continue

                if current_cat is None:
                    logger.warning(
                        "Fila GENERAL sin categoría activa p%d (bib=%s)",
                        page_idx + 1,
                        m.group("bib"),
                    )
                    continue

                pos_str = m.group("pos")
                bib = m.group("bib")
                body = m.group("body")
                nums_raw = m.group("nums").split()
                # Últimos num_validas+1 enteros: V1..VN luego Total
                puntos = [int(x) for x in nums_raw[:num_validas]]
                total = int(nums_raw[num_validas])

                key = (pos_str, bib)
                if key in table_idx:
                    name, city, club = table_idx[key]
                    if not name:
                        name, city, club = body, "", ""
                else:
                    name, city, club = body, "", ""

                row = GeneralRow(
                    overall_position=int(pos_str),
                    bib=bib,
                    name=name,
                    city=city,
                    club=club,
                    points_per_valida=puntos,
                    total_points=total,
                )
                out[current_cat].append(row)

    return out


# ---------------------------------------------------------------------------
# API pública — EventHeader
# ---------------------------------------------------------------------------


def parse_event_header(path: Path) -> Optional[EventHeader]:
    """Detecta y parsea el header de evento del PDF.

    Busca línea ``VALIDA <NUM> <LOCATION> <MONTH> <DAY> DE <YEAR>`` en las
    primeras páginas. Retorna ``None`` si no encuentra patrón.

    Ej: ``"VALIDA IV CALI MAYO 17 DE 2026"`` →
    ``EventHeader(valida_num=4, location="CALI", event_date=date(2026, 5, 17), raw_text=...)``.
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {path}")

    with pdfplumber.open(path) as pdf:
        # Inspecciona hasta las primeras 3 páginas — el header es siempre p1
        # pero damos margen por si el primer ``extract_text`` falla en alguna.
        for page in pdf.pages[:3]:
            text = page.extract_text() or ""
            for line in text.splitlines():
                m = _EVENT_HEADER_RE.search(line)
                if not m:
                    continue
                num_roman = m.group("num").upper()
                if num_roman not in _ROMAN_TO_INT:
                    logger.warning("Roman numeral desconocido en header: %r", num_roman)
                    continue
                valida_num = _ROMAN_TO_INT[num_roman]
                location = m.group("location").strip()
                month_str = m.group("month").upper()
                if month_str not in _MONTH_TO_INT:
                    logger.warning("Mes desconocido en header: %r", month_str)
                    continue
                event_dt = date(
                    int(m.group("year")), _MONTH_TO_INT[month_str], int(m.group("day"))
                )
                return EventHeader(
                    valida_num=valida_num,
                    location=location,
                    event_date=event_dt,
                    raw_text=line.strip(),
                )
    return None
