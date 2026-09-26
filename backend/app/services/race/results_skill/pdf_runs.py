"""Primitivas de lectura de bandas y *runs* de un PDF (amendment 2026-09-26, T124).

Movidas sin cambio de comportamiento desde el parser de PDFs oficial
retirado en T153 (``_band_text``/``_band_runs``/``_chars_by_band``/
``_cells_from_runs``, research R-01): leen los caracteres de una banda
vertical de la página **en orden de flujo del PDF** (nunca ordenados por
``x``), porque un ``Club/Patrocinador`` largo se desborda visualmente sobre
la columna ``Tiempo`` y ordenar por ``x`` intercalaría letras del club con
dígitos del tiempo.

``table_bands``/``baseline_bands`` son nuevos en la fase 13 (contracts/
reading-profile.md § Engine, punto 1): dan la lista de bandas (bbox) por
fila según ``pdf.rows`` del perfil — ``"table_bands"`` para layouts con
rulings (``find_tables``) y ``"baselines"`` para layouts sin rulings
(``extract_text_lines``). Ambos devuelven solo bboxes; el motor de
aplicación (``apply.py``) decide qué hacer con cada banda.

Sin logging de contenido — estas funciones no ven la fila ya clasificada,
solo caracteres sueltos y coordenadas.
"""
from __future__ import annotations

from collections.abc import Sequence

#: Gap horizontal (pt) por defecto que abre un run nuevo cuando el perfil no
#: da un ``run_gap_pt`` explícito (paridad con el valor histórico del
#: parser retirado, ``_BAND_GAP_PT``).
DEFAULT_RUN_GAP_PT: float = 1.0


def band_runs(
    chars: Sequence[dict],
    bbox: tuple[float, float, float, float],
    run_gap_pt: float = DEFAULT_RUN_GAP_PT,
) -> list[tuple[float, str]]:
    """Parte la banda en *runs*: ``(x0 donde arranca, texto)``.

    Filtrado **solo vertical** (``top``/``bottom`` del char dentro de
    ``bbox``): el ancho de ``bbox`` no recorta nada, porque el propósito de
    la lectura por banda es capturar texto que se desborda horizontalmente
    fuera de su columna nominal.

    Un run se corta cuando el hueco horizontal con el carácter anterior
    supera ``run_gap_pt`` o cuando ``x`` salta hacia atrás (arranque del
    texto de la celda siguiente, que es lo que ocurre cuando una celda larga
    se imprime encima de la columna vecina).
    """
    _, top, _, bottom = bbox
    runs: list[tuple[float, str]] = []
    pieces: list[str] = []
    start_x = 0.0
    prev: dict | None = None
    for char in chars:
        if not (char["top"] >= top and char["bottom"] <= bottom):
            continue
        if prev is None or (
            char["x0"] - prev["x1"] > run_gap_pt or char["x0"] < prev["x0"]
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


def band_text(
    chars: Sequence[dict],
    bbox: tuple[float, float, float, float],
    run_gap_pt: float = DEFAULT_RUN_GAP_PT,
) -> str:
    """``" ".join`` de los runs de ``band_runs`` — texto reconstruido de la banda."""
    return " ".join(text for _, text in band_runs(chars, bbox, run_gap_pt))


def chars_by_band(
    chars: Sequence[dict], bboxes: Sequence[tuple[float, float, float, float]]
) -> list[list[dict]]:
    """Reparte los chars de la página entre las bandas, en orden de flujo.

    Una sola pasada sobre ``page.chars`` en vez de una por banda; el orden
    relativo dentro de cada banda es el del content stream.
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


def cells_from_runs(
    runs: Sequence[tuple[float, str]],
    cell_boxes: Sequence[tuple[float, float, float, float] | None],
) -> list[str] | None:
    """Asigna cada run a la celda cuyo rango ``[x0, x1)`` contiene su ``start_x``.

    Devuelve ``None`` si algún run arranca fuera de toda celda.
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


#: Settings de ``find_tables`` compartidos por el motor de perfiles — igual
#: que ``_TABLE_SETTINGS`` del parser retirado, calibrados contra los PDFs
#: oficiales.
TABLE_SETTINGS: dict = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "intersection_tolerance": 3,
}


def table_bands(
    page, table_settings: dict | None = None
) -> list[tuple[float, float, float, float]]:
    """Bandas (bbox) por fila desde ``page.find_tables`` (layouts con rulings).

    Una banda por fila de cada tabla encontrada, en el orden en que
    ``find_tables`` las entrega (orden de documento dentro de cada tabla,
    tablas en el orden en que ``find_tables`` las descubre en la página).
    """
    find_tables = getattr(page, "find_tables", None)
    if not callable(find_tables):
        return []
    tables = find_tables(table_settings or TABLE_SETTINGS) or []
    bboxes: list[tuple[float, float, float, float]] = []
    for table in tables:
        for row in table.rows:
            bboxes.append(row.bbox)
    return bboxes


def baseline_bands(page) -> list[tuple[float, float, float, float]]:
    """Bandas (bbox) por línea de texto desde ``page.extract_text_lines``
    (layouts sin rulings — R-19 "baselines"). El ancho de la banda cubre
    toda la página: el filtrado horizontal no aplica en ``band_runs``, solo
    el vertical, así que basta con acotar ``top``/``bottom``.
    """
    extract_lines = getattr(page, "extract_text_lines", None)
    if not callable(extract_lines):
        return []
    width = getattr(page, "width", 10_000.0)
    return [(0.0, line["top"], width, line["bottom"]) for line in extract_lines()]
