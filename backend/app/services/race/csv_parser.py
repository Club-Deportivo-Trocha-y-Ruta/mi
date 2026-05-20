"""Parser de exports CSV/XLSX de la Liga del Valle (Copa Valle XCO).

Cuando la federación publica resultados en formato tabular (no PDF), llega
un CSV con bloques apilados por categoría:

    RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA,,,,,
     - 31 de enero de 2026,,,,,
    ,,,,,
    CATEGORÍA: INFANTIL A,,,,,
    POS,N°,CORREDOR,CLUB / EQUIPO,TIEMPO,PUNTOS
    1,413,Thiago Manzano,Fundación Tourmalet,00:24:28,40
    ...

Este módulo provee dos funciones API públicas con la misma firma que
``pdf_parser`` para que el ingestor pueda intercambiar el parser según
el formato de origen sin ramificarse internamente:

    parse_results_csv(path)        -> dict[str, list[ResultsRow]]
    parse_event_header_csv(path)   -> Optional[EventHeader]

Reusa ``ResultsRow`` y ``EventHeader`` del módulo ``pdf_parser`` para
mantener un único shape de salida. La normalización de cabeceras de
categoría se delega a ``normalizer.parse_category_header`` (ampliado
para aceptar tanto ``CAT:`` como ``CATEGORÍA:``).

Logging: warnings sólo para categorías no mapeadas o filas malformadas.
Sin nombres completos (Ley 1581).
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from app.services.race.normalizer import parse_category_header
from app.services.race.pdf_parser import EventHeader, ResultsRow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Header de línea de tabla esperado tras "CATEGORÍA: ...". Se descarta.
_TABLE_HEADER_TOKEN: str = "pos"

#: Header de evento CSV — primera línea típica:
#: ``RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA``
_EVENT_HEADER_TITLE_RE = re.compile(
    r"RESULTADOS\s+OFICIALES\s*:\s*"
    r"(?P<num>I{1,3}|IV|VI{0,2}|V|CD)\s+VALIDA\s+COPA\s+VALLE\s*-\s*"
    r"(?P<location>[A-ZÁÉÍÓÚÑa-záéíóúñ\s]+?)\s*$",
    re.IGNORECASE,
)

#: Segunda línea del header (a veces precedida por " - "):
#: ``- 31 de enero de 2026`` o ``31 de enero de 2026``.
_EVENT_HEADER_DATE_RE = re.compile(
    r"\s*-?\s*(?P<day>\d{1,2})\s+de\s+"
    r"(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|"
    r"agosto|septiembre|octubre|noviembre|diciembre)\s+"
    r"de\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

#: Roman numeral → int (paridad con pdf_parser._ROMAN_TO_INT).
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "CD": 99,
}

#: Mes español → int (paridad con pdf_parser._MONTH_TO_INT, en minúsculas).
_MONTH_TO_INT: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}

#: Tokens que en columna ``TIEMPO`` representan "no completó" sin estado
#: explícito (típico CSV federación V-I: ``-`` significa DNF/DNS sin
#: distinción). Mantienen la fila con bib + posición + puntos para que el
#: ingestor decida el estado final.
_NO_TIME_TOKENS: frozenset[str] = frozenset({"-", "", "—", "–", "n/a", "na"})

#: Marcadores explícitos de status que el CSV puede traer literales.
_EXPLICIT_STATUS_TOKENS: frozenset[str] = frozenset(
    {"dnf", "dsq", "dns"}
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _is_blank_row(row: list[str]) -> bool:
    """Una fila CSV es vacía si todas sus celdas (strip) son ``""``."""
    return all((c or "").strip() == "" for c in row)


def _is_table_header_row(row: list[str]) -> bool:
    """Detecta línea ``POS,N°,CORREDOR,...`` (se descarta)."""
    if not row:
        return False
    return (row[0] or "").strip().lower() == _TABLE_HEADER_TOKEN


def _looks_like_category_row(row: list[str]) -> bool:
    """``CATEGORÍA: <NOMBRE>`` aparece en la primera celda (resto vacío)."""
    if not row:
        return False
    head = (row[0] or "").strip()
    if not head:
        return False
    upper = head.upper()
    return upper.startswith("CATEGORÍA:") or upper.startswith("CATEGORIA:") \
        or upper.startswith("CAT:")


def _coerce_int(s: str) -> Optional[int]:
    """``"5"`` → ``5``; ``""``, ``"-"``, no-numérico → ``None``.

    Acepta también valores con caracteres no dígito (``"5 "``, ``"5\xa0"``)
    porque el CSV a veces trae no-breaking spaces.
    """
    if not s:
        return None
    cleaned = re.sub(r"[^\d]", "", s)
    if not cleaned:
        return None
    return int(cleaned)


def _normalize_time_cell(raw: str) -> str:
    """Devuelve la cadena de tiempo lista para ``ResultsRow.time_raw``.

    - Si la celda es ``"-"`` o vacía → ``"DNF"`` (federación CSV no
      distingue; el coach puede corregir en la fase de match interactivo).
    - Si la celda es ``DNF``/``DSQ``/``DNS`` → mayúsculas.
    - Si es ``HH:MM:SS`` o ``MM:SS`` → tal cual (normalizer lo parsea).
    - Cualquier otro literal se devuelve sin tocar para que el ingestor
      lo loggee como warning.
    """
    if raw is None:
        return "DNF"
    stripped = raw.strip()
    if stripped.lower() in _NO_TIME_TOKENS:
        return "DNF"
    if stripped.lower() in _EXPLICIT_STATUS_TOKENS:
        return stripped.upper()
    return stripped


# ---------------------------------------------------------------------------
# API pública — RESULTADOS CSV
# ---------------------------------------------------------------------------


def parse_results_csv(path: Path) -> dict[str, list[ResultsRow]]:
    """Parsea CSV federación y devuelve ``{category_code: [ResultsRow, ...]}``.

    Diseñado para CSV con shape:

        POS, N°, CORREDOR, CLUB / EQUIPO, TIEMPO, PUNTOS

    Tolera:
    - Filas vacías entre bloques.
    - Cabeceras de tabla repetidas (descartadas).
    - Categorías desconocidas (loggea warning, no aborta).
    - Celda ``TIEMPO`` con ``"-"`` (mapea a ``DNF``).
    - Celda ``PUNTOS`` con ``""`` (mapea a ``0``).
    - BOM UTF-8 al inicio del archivo (``utf-8-sig``).

    El campo ``city`` queda ``""`` porque el CSV federación V-I no lo
    publica (es responsabilidad del coach completarlo en la fase de match
    si se quiere usar para desambiguar homónimos).
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV no encontrado: {path}")

    out: dict[str, list[ResultsRow]] = {}
    current_cat: Optional[str] = None
    unknown_categories: set[str] = set()
    skipped_rows = 0

    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for line_idx, row in enumerate(reader, start=1):
            if _is_blank_row(row):
                continue

            if _looks_like_category_row(row):
                code = parse_category_header(row[0])
                if code is None:
                    unknown_categories.add(row[0][:80])
                    logger.warning(
                        "Header categoría desconocido en línea %d: %r",
                        line_idx,
                        row[0][:80],
                    )
                    current_cat = None
                    continue
                current_cat = code
                out.setdefault(current_cat, [])
                continue

            if _is_table_header_row(row):
                continue

            if current_cat is None:
                # Línea con datos pero sin categoría activa — ruido.
                continue

            if len(row) < 6:
                skipped_rows += 1
                logger.warning(
                    "Fila CSV con menos de 6 columnas en línea %d (cat=%s); descartada",
                    line_idx,
                    current_cat,
                )
                continue

            pos_str, bib_str, name, club, time_raw, points_str = (
                (c or "").strip() for c in row[:6]
            )

            if not bib_str:
                skipped_rows += 1
                logger.warning(
                    "Fila CSV sin dorsal en línea %d (cat=%s); descartada",
                    line_idx,
                    current_cat,
                )
                continue

            position = _coerce_int(pos_str)
            bib_int = _coerce_int(bib_str)
            if bib_int is None:
                skipped_rows += 1
                logger.warning(
                    "Fila CSV con dorsal no numérico en línea %d (cat=%s); descartada",
                    line_idx,
                    current_cat,
                )
                continue
            points = _coerce_int(points_str) or 0

            results_row = ResultsRow(
                position=position,
                bib=str(bib_int),
                name=name,
                city="",  # CSV federación V-I no publica ciudad
                club=club,
                time_raw=_normalize_time_cell(time_raw),
                points=points,
            )
            out[current_cat].append(results_row)

    if unknown_categories:
        logger.warning(
            "Categorías desconocidas en CSV (excluidas del resultado): %s",
            sorted(unknown_categories),
        )
    if skipped_rows:
        logger.info("Filas CSV descartadas: %d", skipped_rows)

    return out


# ---------------------------------------------------------------------------
# API pública — Header CSV
# ---------------------------------------------------------------------------


def parse_event_header_csv(path: Path) -> Optional[EventHeader]:
    """Detecta y parsea las dos primeras líneas no vacías del CSV.

    Espera:
        Línea 1: ``RESULTADOS OFICIALES: <ROMAN> VALIDA COPA VALLE - <LOCATION>``
        Línea 2: ``- DD de <mes> de YYYY``  (puede o no tener el ``-``)

    Retorna ``None`` si no encuentra el patrón en las primeras 5 filas
    no vacías. No avanza el resto del archivo.

    Ej:
        ``RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA``
        `` - 31 de enero de 2026``
            →
        ``EventHeader(valida_num=1, location='SEVILLA', event_date=date(2026,1,31), raw_text=...)``
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV no encontrado: {path}")

    title_match = None
    date_match = None
    inspected = 0
    raw_lines: list[str] = []

    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if _is_blank_row(row):
                continue
            inspected += 1
            if inspected > 5:
                break
            head = (row[0] or "").strip()
            raw_lines.append(head)
            if title_match is None:
                title_match = _EVENT_HEADER_TITLE_RE.search(head)
            if date_match is None:
                date_match = _EVENT_HEADER_DATE_RE.search(head)
            if title_match and date_match:
                break

    if not title_match or not date_match:
        logger.warning(
            "Header de evento no detectado en CSV %s (primeras líneas: %r)",
            path.name,
            raw_lines,
        )
        return None

    num_roman = title_match.group("num").upper()
    if num_roman not in _ROMAN_TO_INT:
        logger.warning("Roman numeral desconocido en header CSV: %r", num_roman)
        return None

    location = title_match.group("location").strip().upper()
    month = date_match.group("month").lower()
    if month not in _MONTH_TO_INT:
        logger.warning("Mes desconocido en header CSV: %r", month)
        return None

    event_dt = date(
        int(date_match.group("year")),
        _MONTH_TO_INT[month],
        int(date_match.group("day")),
    )
    return EventHeader(
        valida_num=_ROMAN_TO_INT[num_roman],
        location=location,
        event_date=event_dt,
        raw_text=" | ".join(raw_lines),
    )
