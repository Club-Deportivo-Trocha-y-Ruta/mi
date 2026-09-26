"""Vista enmascarada (amendment 2026-09-26, T126). Ver ``contracts/masked-view.md``.

La vista enmascarada es el **único** contenido de un archivo oficial de
resultados que un LLM llega a leer (FR-046, SC-013). Estas funciones son
puras: no tocan la base de datos, no hacen red, y no registran en ningún
log el contenido de una fila — solo se les llama con el archivo en memoria
y devuelven texto/estructuras que un router nunca ve (``results_skill`` no
lo importa ningún router).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import pdfplumber

from app.services.race.normalizer import LAP_WORD_PATTERN
from app.services.race.results_skill.pdf_runs import (
    DEFAULT_RUN_GAP_PT,
    band_runs,
    chars_by_band,
    table_bands,
)
from app.services.race.results_skill.vocabulary import is_vocabulary_word

#: Límite de tamaño (contracts/masked-view.md § Refusals).
MAX_FILE_BYTES = 8 * 1024 * 1024

#: Firmas de status verbatim (contracts/masked-view.md § Token classes).
_STATUS_WORDS = frozenset({"DNF", "DNS", "DSQ", "DQ"})

_TIME_HMS_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_TIME_MS_RE = re.compile(r"^\d{1,2}:\d{2}$")
_LAP_DEFICIT_RE = re.compile(
    r"^\(?\s*\)?\s*-?\s*\d{1,2}\s*-?\s*" + LAP_WORD_PATTERN + r"[)=\-]?\s*(?:\(\w+\))?$",
    re.IGNORECASE,
)
_INT_RE = re.compile(r"^\d+$")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")

#: Frontera letra/dígito o dígito/letra usada para separar tokens pegados
#: (contracts/masked-view.md § Token classes: ``CLUB1:23:45`` -> ``CLUB`` + ``1:23:45``).
_GLUE_SPLIT_RE = re.compile(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=\d)|(?<=\d)(?=[A-Za-zÀ-ÖØ-öø-ÿ])")


class UnsupportedFileError(Exception):
    """Refusal — formato/tamaño/capa de texto no admitidos (§ Refusals)."""


class ScannedPdfError(UnsupportedFileError):
    """PDF sin capa de texto (posible escaneo)."""


#: Separa letras/dígitos de la puntuación circundante — ``"CAT:"`` -> ``["CAT", ":"]``,
#: ``"(-2"`` -> ``["(", "-", "2"]`` — una vez que ya no puede ser una palabra
#: de estado/vuelta completa (esas se detectan primero, sobre el texto
#: completo del run, porque pueden llevar un espacio interno: ``"(-1 VUELTA)"``).
_FINE_SPLIT_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+|\d+|[^\sA-Za-zÀ-ÖØ-öø-ÿ\d]")


def _split_glued_tokens(raw: str) -> list[str]:
    """Separa un token pegado en la frontera letra/dígito antes de clasificar."""
    pieces = [p for p in _GLUE_SPLIT_RE.split(raw) if p]
    return pieces if pieces else [raw]


def _classify_whole(text: str) -> tuple[str, str, str] | None:
    """Intenta clasificar ``text`` (ya sea un token o el texto completo de un
    run) como un único ``STATUS``/``TIME`` — antes de partirlo en palabras,
    porque un déficit de vueltas puede llevar un espacio interno
    (``"(-1 VUELTA)"``, T024b) que la tokenización por espacios rompería."""
    stripped = text.strip()
    if not stripped:
        return None
    upper = stripped.upper()
    if upper in _STATUS_WORDS or _LAP_DEFICIT_RE.match(stripped):
        return "STATUS", stripped, upper
    if _TIME_HMS_RE.match(stripped):
        return "TIME", stripped, "⟨T h:mm:ss⟩"
    if _TIME_MS_RE.match(stripped):
        return "TIME", stripped, "⟨T mm:ss⟩"
    return None


def _classify_token(token: str) -> tuple[str, str]:
    """``(clase, forma_masking)`` de un sub-token ya limpio (solo letras,
    solo dígitos, o un único carácter de puntuación)."""
    if _INT_RE.match(token):
        return "INT", f"⟨N{len(token)}⟩"
    if _WORD_RE.fullmatch(token):
        return "WORD", "⟨W⟩"
    return "PUNCT", token


def _tokenize(text: str) -> list[tuple[str, str, str]]:
    """``[(clase, raw, forma_masking), ...]`` del texto completo de un run/celda.

    Orden de clasificación (evita que ``"CAT:"`` pierda su ``":"`` como parte
    de una palabra de vocabulario, y que un déficit de vueltas con espacio
    interno se rompa en dos tokens sin relación):

    1. ¿El texto completo es, por sí solo, un ``STATUS``/``TIME``? (cubre
       ``"(-1 VUELTA)"`` cuando llegó como un único run — el caso normal en
       los PDFs oficiales, medido en R-01/T024b).
    2. Si no, se tokeniza por espacios; cada palabra se separa primero en la
       frontera letra/dígito (tokens pegados) y ``STATUS``/``TIME`` se
       reintenta por palabra (cubre ``"DNF"``/``"0:40:07"`` sueltos).
    3. Lo que sigue sin clasificar se parte en letras/dígitos/puntuación y
       se clasifica como ``WORD``/``INT``/``PUNCT``.
    """
    whole = _classify_whole(text)
    if whole is not None:
        return [whole]

    out: list[tuple[str, str, str]] = []
    for raw_token in text.split():
        for piece in _split_glued_tokens(raw_token):
            single = _classify_whole(piece)
            if single is not None:
                out.append(single)
                continue
            for sub in _FINE_SPLIT_RE.findall(piece):
                cls, masked = _classify_token(sub)
                out.append((cls, sub, masked))
    return out


def _is_structural(tokens: Sequence[tuple[str, str, str]]) -> bool:
    """Regla de línea estructural (contracts/masked-view.md § Token classes)."""
    for cls, raw, _masked in tokens:
        if cls in ("TIME", "STATUS"):
            return False
        if cls == "INT" and len(raw) >= 5:
            return False
        if cls == "WORD" and not is_vocabulary_word(raw):
            return False
    return True


@dataclass
class MaskedRun:
    position: float  #: start-x (pt) para PDF, índice de columna para delimitado.
    tokens: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class MaskedLine:
    label: str
    kind: Literal["S", "C"]
    y: float | None
    runs: list[MaskedRun] = field(default_factory=list)


@dataclass
class MaskedPage:
    number: int | None
    width: float | None
    rulings_x: list[float]
    lines: list[MaskedLine] = field(default_factory=list)


@dataclass
class MaskedView:
    format: Literal["pdf", "delimited"]
    sha256: str
    pages: list[MaskedPage] = field(default_factory=list)


def _sha256_prefix(file_bytes: bytes, n: int = 8) -> str:
    return hashlib.sha256(file_bytes).hexdigest()[:n]


def _looks_like_pdf(file_bytes: bytes) -> bool:
    return file_bytes[:5] == b"%PDF-"


def _looks_like_utf8_text(file_bytes: bytes) -> bool:
    try:
        file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _build_masked_view_pdf(file_bytes: bytes) -> MaskedView:
    import io

    pages: list[MaskedPage] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        has_any_text = any((page.extract_text() or "").strip() for page in pdf.pages)
        if not has_any_text:
            raise ScannedPdfError("PDF sin capa de texto")

        for page_no, page in enumerate(pdf.pages, start=1):
            bboxes = table_bands(page)
            find_tables = getattr(page, "find_tables", None)
            rulings_x: list[float] = []
            if callable(find_tables):
                tables = find_tables() or []
                xs: set[float] = set()
                for table in tables:
                    for row in table.rows:
                        x0, _, x1, _ = row.bbox
                        xs.add(round(x0, 1))
                        xs.add(round(x1, 1))
                rulings_x = sorted(xs)

            lines: list[MaskedLine] = []
            if bboxes:
                buckets = chars_by_band(page.chars, bboxes)
                events: list[tuple[float, int, object]] = []
                for idx, bbox in enumerate(bboxes):
                    events.append((bbox[1], 1, ("band", idx, bbox)))

                # Líneas fuera de toda banda de tabla (encabezado ``CAT:``,
                # título del documento): el layout con rulings no las lee
                # como fila, pero SIGUEN siendo parte del archivo — deben
                # aparecer en la vista (ver ejemplo en contracts/masked-view.md,
                # línea ``CAT:``). Se detectan por no solaparse verticalmente
                # con ninguna banda de tabla.
                extract_lines = getattr(page, "extract_text_lines", None)
                if callable(extract_lines):
                    for line in extract_lines():
                        covered = any(
                            top <= line["top"] and line["bottom"] <= bottom
                            for _, top, _, bottom in bboxes
                        )
                        if not covered:
                            events.append((line["top"], 0, ("text", line["text"])))

                events.sort(key=lambda event: (event[0], event[1]))

                for _, _, payload in events:
                    if payload[0] == "text":
                        tokens = _tokenize(payload[1])
                        kind = "S" if _is_structural(tokens) else "C"
                        lines.append(
                            MaskedLine(
                                label=f"L{len(lines) + 1:03d}",
                                kind=kind,
                                y=None,
                                runs=[MaskedRun(position=0.0, tokens=tokens)],
                            )
                        )
                        continue

                    idx, bbox = payload[1], payload[2]
                    runs = band_runs(buckets[idx], bbox, DEFAULT_RUN_GAP_PT)
                    tokenized_runs = [
                        MaskedRun(position=start_x, tokens=_tokenize(text))
                        for start_x, text in runs
                    ]
                    all_tokens = [t for run in tokenized_runs for t in run.tokens]
                    kind = "S" if _is_structural(all_tokens) else "C"
                    lines.append(
                        MaskedLine(
                            label=f"L{len(lines) + 1:03d}",
                            kind=kind,
                            y=bbox[1],
                            runs=tokenized_runs,
                        )
                    )
            else:
                # Sin tabla (layout sin rulings): una línea por texto de página,
                # un único "run" por línea (no hay columnas que asignar).
                extract_lines = getattr(page, "extract_text_lines", None)
                text_lines = extract_lines() if callable(extract_lines) else []
                for line in text_lines:
                    tokens = _tokenize(line["text"])
                    kind = "S" if _is_structural(tokens) else "C"
                    lines.append(
                        MaskedLine(
                            label=f"L{len(lines) + 1:03d}",
                            kind=kind,
                            y=line["top"],
                            runs=[MaskedRun(position=0.0, tokens=tokens)],
                        )
                    )

            pages.append(
                MaskedPage(number=page_no, width=page.width, rulings_x=rulings_x, lines=lines)
            )

    return MaskedView(format="pdf", sha256=_sha256_prefix(file_bytes), pages=pages)


def _build_masked_view_delimited(file_bytes: bytes) -> MaskedView:
    import csv
    import io

    text = file_bytes.decode("utf-8")
    sniff_sample = text[:2048]
    delimiter = ";"
    for candidate in (";", ",", "\t"):
        if candidate in sniff_sample:
            delimiter = candidate
            break
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    lines: list[MaskedLine] = []
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        runs = []
        tokens_for_line: list[tuple[str, str, str]] = []
        for col_idx, cell in enumerate(row):
            tokens = _tokenize(cell)
            runs.append(MaskedRun(position=float(col_idx), tokens=tokens))
            tokens_for_line.extend(tokens)
        kind = "S" if _is_structural(tokens_for_line) else "C"
        lines.append(
            MaskedLine(label=f"R{len(lines) + 1:04d}", kind=kind, y=None, runs=runs)
        )

    page = MaskedPage(number=None, width=None, rulings_x=[], lines=lines)
    return MaskedView(format="delimited", sha256=_sha256_prefix(file_bytes), pages=[page])


def build_masked_view(file_bytes: bytes, results_ext: Literal["pdf", "csv"]) -> MaskedView:
    """Construye la vista enmascarada. Ver refusals en contracts/masked-view.md."""
    if len(file_bytes) > MAX_FILE_BYTES:
        raise UnsupportedFileError("El archivo supera 8 MB.")

    if results_ext == "pdf":
        if not _looks_like_pdf(file_bytes):
            raise UnsupportedFileError(
                "Formato no admitido: se espera PDF con texto o CSV/TSV en UTF-8."
            )
        return _build_masked_view_pdf(file_bytes)

    if not _looks_like_utf8_text(file_bytes):
        raise UnsupportedFileError(
            "Formato no admitido: se espera PDF con texto o CSV/TSV en UTF-8."
        )
    return _build_masked_view_delimited(file_bytes)


def _render_run(run: MaskedRun, *, is_pdf: bool) -> str:
    body = " ".join(masked for _, _, masked in run.tokens)
    if is_pdf:
        return f"@{run.position:.1f} {body}"
    return f"[{int(run.position)}] {body}"


def render_masked_view(view: MaskedView) -> str:
    """El texto exacto que se escribe en ``masked/view.txt``."""
    is_pdf = view.format == "pdf"
    out: list[str] = [
        f"# masked-view v1 · format={view.format} · sha256={view.sha256}"
    ]
    for page in view.pages:
        if is_pdf:
            rulings = ", ".join(f"{x:.1f}" for x in page.rulings_x)
            out.append(f"## page {page.number} · width={page.width:.1f} · rulings_x=[{rulings}]")
        for line in page.lines:
            y_part = f"y={line.y:.1f} " if line.y is not None else ""
            runs_part = " | ".join(_render_run(run, is_pdf=is_pdf) for run in line.runs)
            out.append(f"{line.label} {y_part}{line.kind} | {runs_part}")
    return "\n".join(out) + "\n"


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def leak_count(rendered: str, document) -> int:
    """SC-013 leak check (contracts/masked-view.md § Leak check).

    ``document`` es un ``ParsedResults`` (``staged_document.ParsedResults``):
    para cada fila extraída, cuenta cuántas palabras de 3+ letras de
    ``name``/``club``/``city`` aparecen como token **verbatim de una línea
    estructural** de ``rendered``. Las líneas de contenido no pueden
    contener una palabra de corredor por construcción (siempre se
    enmascaran), así que solo se comparan contra las estructurales.
    """
    structural_words: set[str] = set()
    for raw_line in rendered.splitlines():
        parts = raw_line.split("|")
        if len(parts) < 2:
            continue
        head = parts[0]
        if " S " not in f" {head} " and not head.rstrip().endswith(" S"):
            continue
        for token in _WORD_RE.findall(raw_line):
            structural_words.add(_fold(token))

    leaked = 0
    for category in document.categories:
        for row in category.rows:
            for field_value in (row.name, row.club, row.city):
                for word in _WORD_RE.findall(field_value or ""):
                    if len(word) < 3:
                        continue
                    if _fold(word) in structural_words:
                        leaked += 1
    return leaked
