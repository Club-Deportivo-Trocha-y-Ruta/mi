"""Motor de aplicación de un ``ReadingProfile`` (amendment 2026-09-26, T128).

``apply_profile`` es la única función que convierte un archivo real de
resultados (PDF o texto delimitado) en un ``ParsedResults``, guiada por un
perfil ya validado (``profile.py``). Nunca parsea el tiempo — ``time_raw``
se conserva tal cual para que ``normalizer.parse_time`` lo interprete en el
ingestor, exactamente igual que el parser retirado (contracts/
reading-profile.md § Engine).

Sin logging de contenido: solo se registran conteos (categorías, filas,
ilegibles), nunca un nombre, ciudad o club.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import pdfplumber

from app.services.race.normalizer import HEADER_TO_CODE, LAP_WORD_PATTERN
from app.services.race.results_skill.pdf_runs import (
    band_runs,
    baseline_bands,
    chars_by_band,
    table_bands,
)
from app.services.race.results_skill.profile import (
    CategoryHeaderPattern,
    CategoryHeaderPrefix,
    CategoryHeaderStructuralXTo,
    DelimitedCategoryColumn,
    DelimitedCategorySeparatorRows,
    ReadingProfile,
)
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    UnreadableRow,
)

logger = logging.getLogger(__name__)

#: Nombre de la categoría pseudo asignada a filas anteriores al primer
#: encabezado ``CAT:`` (contracts/reading-profile.md § PDF, punto 7).
UNCATEGORIZED_HEADER = "SIN CATEGORÍA"

_STATUS_WORDS = frozenset({"DNF", "DNS", "DSQ", "DQ"})
_LAP_RE = re.compile(LAP_WORD_PATTERN, re.IGNORECASE)


def _fold(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def _looks_like_time_or_status(value: str) -> bool:
    """Guarda contra tratar un encabezado de columna (``"Tiempo"``) como si
    fuera un valor de tiempo real: exige un dígito o una palabra de status/
    vuelta reconocida."""
    stripped = value.strip()
    if not stripped:
        return False
    if any(ch.isdigit() for ch in stripped):
        return True
    if stripped.upper() in _STATUS_WORDS:
        return True
    return bool(_LAP_RE.search(stripped))


def _resolve_category_code(header_raw: str, aliases: dict[str, str]) -> str | None:
    folded = _fold(header_raw.strip())
    if folded in {_fold(key) for key in aliases}:
        for key, code in aliases.items():
            if _fold(key) == folded:
                return code
    normalized = folded.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return HEADER_TO_CODE.get(normalized)


@dataclass
class _DocState:
    categories: list[ParsedCategory] = field(default_factory=list)
    unreadable: list[UnreadableRow] = field(default_factory=list)
    current: ParsedCategory | None = None

    def start_category(self, header_raw: str, aliases: dict[str, str]) -> None:
        if self.current is not None and self.current.header_raw == header_raw:
            return
        code = _resolve_category_code(header_raw, aliases)
        category = ParsedCategory(header_raw=header_raw, code=code, rows=[])
        self.categories.append(category)
        self.current = category

    def _ensure_current(self) -> ParsedCategory:
        if self.current is None:
            self.start_category(UNCATEGORIZED_HEADER, {})
        return self.current  # type: ignore[return-value]

    def add_row(self, row: ResultsRow) -> None:
        self._ensure_current().rows.append(row)

    def add_unreadable(self, page: int, ordinal: int | None) -> None:
        self.unreadable.append(UnreadableRow(page=page, ordinal=ordinal))


def _match_category_header(text: str, rule) -> str | None:
    if isinstance(rule, CategoryHeaderPrefix):
        idx = text.upper().find(rule.prefix.upper())
        if idx == -1:
            return None
        header = text[idx + len(rule.prefix) :].strip()
        return header or None
    if isinstance(rule, CategoryHeaderPattern):
        m = re.search(rule.pattern, text, re.IGNORECASE)
        if not m:
            return None
        return (m.group(1) if m.groups() else m.group(0)).strip() or None
    if isinstance(rule, CategoryHeaderStructuralXTo):
        return None
    return None


def _column_for(x: float, columns) -> str | None:
    for column in columns:
        if column.x_from <= x < column.x_to:
            return column.field
    return None


def _assign_runs_to_pdf_columns(
    runs: Sequence[tuple[float, str]], columns
) -> dict[str, str]:
    out: dict[str, str] = {}
    for start_x, text in runs:
        field_name = _column_for(start_x, columns)
        if field_name is None:
            continue
        out[field_name] = f"{out[field_name]} {text}" if field_name in out else text
    return out


def _row_from_fields(fields: dict[str, str], *, page: int, state: _DocState) -> None:
    position_text = fields.get("position", "").strip()
    position = int(position_text) if position_text.isdigit() else None
    time_raw = fields.get("time_or_status", "").strip()
    has_time = _looks_like_time_or_status(time_raw)
    name = fields.get("name", "").strip()
    city = fields.get("city", "").strip()
    club = fields.get("club", "").strip()
    bib = fields.get("bib", "").strip()
    points_text = fields.get("points", "").strip()
    points = int(points_text) if points_text.isdigit() else 0
    has_content = bool(name or club or city or bib or points_text)

    if has_time or (position is not None and has_content):
        state.add_row(
            ResultsRow(
                position=position,
                bib=bib,
                name=name,
                city=city,
                club=club,
                time_raw=time_raw if has_time else "",
                points=points,
            )
        )
        return
    if position is not None or has_content:
        state.add_unreadable(page, position)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _apply_pdf(file_bytes: bytes, profile: ReadingProfile) -> ParsedResults:
    pdf_block = profile.pdf
    assert pdf_block is not None
    state = _DocState()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            if pdf_block.rows == "table_bands":
                bboxes = table_bands(page)
            else:
                bboxes = baseline_bands(page)

            events: list[tuple[float, int, str, object]] = []
            for bbox in bboxes:
                events.append((bbox[1], 1, "band", bbox))

            if pdf_block.rows == "table_bands":
                # Los encabezados CAT: no son filas de tabla — se leen por
                # línea de texto y se intercalan por posición vertical
                # (paridad con el parser retirado, research R-01 punto 6).
                extract_lines = getattr(page, "extract_text_lines", None)
                if callable(extract_lines):
                    for line in extract_lines():
                        header_raw = _match_category_header(
                            line["text"].strip(), pdf_block.category_header
                        )
                        if header_raw is not None:
                            events.append((line["top"], 0, "cat", header_raw))

            events.sort(key=lambda event: (event[0], event[1]))

            buckets = chars_by_band(page.chars, bboxes) if bboxes else []

            for _, _, kind, payload in events:
                if kind == "cat":
                    state.start_category(str(payload), profile.category_aliases)
                    continue

                bbox = payload
                idx = bboxes.index(bbox)
                runs = band_runs(buckets[idx], bbox, pdf_block.run_gap_pt)
                band_text = " ".join(text for _, text in runs)
                if not band_text:
                    continue

                header_raw = _match_category_header(band_text, pdf_block.category_header)
                if header_raw is not None:
                    state.start_category(header_raw, profile.category_aliases)
                    continue

                folded = _fold(band_text)
                if any(
                    folded.startswith(_fold(prefix))
                    for prefix in pdf_block.skip_structural_lines_starting_with
                ):
                    continue

                fields = _assign_runs_to_pdf_columns(runs, pdf_block.columns)
                _row_from_fields(fields, page=page_idx, state=state)

    return ParsedResults(categories=state.categories, unreadable_rows=state.unreadable)


# ---------------------------------------------------------------------------
# Delimitado
# ---------------------------------------------------------------------------


def _delimited_field_value(row: list[str], idx_or_list, *, separator: str) -> str:
    if isinstance(idx_or_list, list):
        parts = [row[i].strip() for i in idx_or_list if i < len(row) and row[i]]
        return separator.join(parts)
    idx = idx_or_list
    if idx < len(row):
        return row[idx].strip()
    return ""


def _apply_delimited(file_bytes: bytes, profile: ReadingProfile) -> ParsedResults:
    block = profile.delimited
    assert block is not None
    text = file_bytes.decode("utf-8")
    reader = csv.reader(io.StringIO(text), delimiter=block.delimiter)
    rows = [row for row in reader]

    state = _DocState()
    skip_next_as_header = False

    for idx, row in enumerate(rows):
        if idx < block.header_rows:
            continue
        if not any(cell.strip() for cell in row):
            continue

        if isinstance(block.category, DelimitedCategorySeparatorRows):
            first_cell = row[0].strip() if row else ""
            prefix = block.category.separator_rows.first_cell_prefix
            if first_cell.upper().startswith(prefix.upper()):
                header_raw = first_cell[len(prefix) :].strip()
                state.start_category(header_raw, profile.category_aliases)
                skip_next_as_header = True
                continue
            if skip_next_as_header:
                skip_next_as_header = False
                continue

        fields: dict[str, str] = {}
        for field_name, idx_or_list in block.columns.items():
            fields[field_name] = _delimited_field_value(
                row, idx_or_list, separator=profile.name_parts_separator
            )

        if isinstance(block.category, DelimitedCategoryColumn):
            category_idx = block.category.column
            header_raw = row[category_idx].strip() if category_idx < len(row) else ""
            if header_raw:
                state.start_category(header_raw, profile.category_aliases)

        _row_from_fields(fields, page=1, state=state)

    return ParsedResults(categories=state.categories, unreadable_rows=state.unreadable)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def apply_profile(
    file_bytes: bytes, results_ext: Literal["pdf", "csv"], profile: ReadingProfile
) -> ParsedResults:
    """Aplica ``profile`` a ``file_bytes`` y devuelve un ``ParsedResults``.

    ``results_ext`` debe coincidir con ``profile.format`` (``"pdf"`` con
    ``format="pdf"``, ``"csv"`` con ``format="delimited"``); no se valida
    aquí — el caller (la fase 15) ya conoce el tipo de archivo que subió.
    """
    if profile.format == "pdf":
        document = _apply_pdf(file_bytes, profile)
    else:
        document = _apply_delimited(file_bytes, profile)

    n_categories = len(document.categories)
    n_rows = sum(len(category.rows) for category in document.categories)
    logger.info(
        "apply_profile profile_id=%s categories=%d rows=%d unreadable=%d",
        profile.profile_id,
        n_categories,
        n_rows,
        len(document.unreadable_rows),
    )
    return document
