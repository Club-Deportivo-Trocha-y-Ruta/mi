"""Parser de PDFs oficiales Copa Valle XCO (RESULTADOS y GENERAL).

Operación pura: lee ``Path`` y devuelve dataclasses. No toca DB.

Estrategia (edge-cases.md §6.1):
1. **Primario por celda**: ``page.extract_tables(table_settings=...)`` con
   ``vertical_strategy="lines"`` — devuelve celdas separadas para ``name``,
   ``city`` y ``club`` evitando recurrir a heurísticas posicionales.
2. **Verificación textual**: ``page.extract_text()`` línea-por-línea + regex
   sobre el final (``status`` + ``points``) — es el camino más confiable para
   ``position``, ``bib``, ``time_raw`` y ``points`` porque esos campos están
   siempre delimitados por espacios al final de la línea. Si la tabla no
   produjo una fila para una posición que el regex sí detecta, **gana el
   regex** (datos faltantes en la tabla se enriquecen desde el texto).
3. **Persistencia de categoría**: si una página inicia con filas sin haber
   visto ``CAT:``, se reusa la última categoría detectada (edge-cases.md
   §4.9 — INFANTIL B continúa entre p4 y p5).
4. **Descarte de cabeceras**: líneas que matchean ``COPA VALLE``, ``VALIDA``,
   ``RESULTADOS``, ``CLASIFICACION``, ``GENERAL``, ``Ord N``, ``ORD N`` se
   descartan. Línea espuria ``0 COPA VALLE…`` (§4.10) se tolera.

Logging: solo ``warning`` cuando se descartan filas o se detectan anomalías,
sin nombres completos. Nivel ``debug`` permitido para troubleshoot local.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import pdfplumber

from app.services.race.normalizer import parse_category_header

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses de salida
# ---------------------------------------------------------------------------


@dataclass
class ResultsRow:
    """Una fila del PDF RESULTADOS (un corredor en una válida)."""

    position: Optional[int]
    bib: str
    name: str
    city: str  #: capturado para resolución de homónimos, no se persiste en `RaceCompetitor`.
    club: str
    time_raw: str
    points: int


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
_RESULTS_ROW_RE = re.compile(
    r"^(?P<pos>\d+)\s+(?P<bib>\d+)\s+(?P<body>.+?)\s+"
    r"(?P<time>\d+:\d{2}:\d{2}|DNF|DSQ|DNS|\(-\d+\s*VUELTAS?\))\s+"
    r"(?P<points>\d+)\s*$",
    re.IGNORECASE,
)

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
#: Acepta ``I``, ``II``, ``III``, ``IV``, ``V``, ``VI``, ``VII`` y ``CD``.
_EVENT_HEADER_RE = re.compile(
    r"VALIDA\s+(?P<num>I{1,3}|IV|VI{0,2}|V|CD)\s+(?P<location>[A-ZÁÉÍÓÚÑ ]+?)\s+"
    r"(?P<month>ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+"
    r"(?P<day>\d{1,2})\s+DE\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

#: Roman numeral → int. ``CD`` se mapea a 99 (Campeonato Departamental).
_ROMAN_TO_INT: dict[str, int] = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "CD": 99,
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
# API pública — RESULTADOS
# ---------------------------------------------------------------------------


def parse_results_pdf(path: Path) -> dict[str, list[ResultsRow]]:
    """Parsea un PDF RESULTADOS y devuelve ``{category_code: [ResultsRow, ...]}``.

    Excluye categorías desconocidas (no mapeadas en ``HEADER_TO_CODE``) con
    log warning. Mantiene orden de aparición de las filas dentro de cada
    categoría (que en el PDF coincide con la posición).
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {path}")

    out: dict[str, list[ResultsRow]] = {}
    current_cat: Optional[str] = None  # persiste entre páginas (edge-cases §4.9)
    unknown_categories: set[str] = set()

    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables(table_settings=_TABLE_SETTINGS) or []
            table_idx = _build_table_index(tables)

            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                # Detectar nuevo header CAT:
                if stripped.upper().startswith("CAT:") or " CAT:" in stripped.upper():
                    code = parse_category_header(stripped)
                    if code is None:
                        # Capturamos el raw para warning sin nombres
                        unknown_categories.add(stripped[:80])
                        current_cat = None
                        logger.warning(
                            "Header CAT desconocido en página %d: %r",
                            page_idx + 1,
                            stripped[:80],
                        )
                        continue
                    current_cat = code
                    out.setdefault(current_cat, [])
                    continue

                if _is_discardable_line(stripped):
                    continue

                m = _RESULTS_ROW_RE.match(stripped)
                if not m:
                    # No es fila válida — puede ser sub-header partido o ruido.
                    continue

                if current_cat is None:
                    # Tenemos fila pero no sabemos categoría — descartar con warning.
                    logger.warning(
                        "Fila sin categoría activa en página %d (bib=%s); descartada",
                        page_idx + 1,
                        m.group("bib"),
                    )
                    continue

                pos_str = m.group("pos")
                bib = m.group("bib")
                body = m.group("body")
                time_raw = m.group("time")
                points = int(m.group("points"))

                # Enriquecer name/city/club desde la tabla si está disponible
                key = (pos_str, bib)
                if key in table_idx:
                    name, city, club = table_idx[key]
                    # Si la tabla devolvió celdas vacías o muy cortas, fallback al body
                    if not name:
                        name, city, club = _split_body_fallback(body)
                else:
                    name, city, club = _split_body_fallback(body)

                row = ResultsRow(
                    position=int(pos_str),
                    bib=bib,
                    name=name,
                    city=city,
                    club=club,
                    time_raw=time_raw,
                    points=points,
                )
                out[current_cat].append(row)

    if unknown_categories:
        logger.warning(
            "Categorías desconocidas detectadas (no incluidas en resultado): %s",
            sorted(unknown_categories),
        )
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
