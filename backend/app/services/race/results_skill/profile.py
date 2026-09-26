"""``ReadingProfile`` — esquema v1 y utilidades (amendment 2026-09-26, T127).

Ver ``contracts/reading-profile.md``. El perfil describe cómo se lee el
layout de un organizador; lo escribe la sesión con el LLM a partir de la
vista enmascarada (``masking.py``) — nunca del archivo real — y lo aplica
``apply.apply_profile`` localmente, sin LLM.

Ninguna clave ni cadena de este esquema puede llevar un dato de un
corredor: ``extra="forbid"`` rechaza cualquier clave no listada, y los
validadores de ``category_aliases``/``skip_structural_lines_starting_with``
exigen palabras del vocabulario cerrado de ``vocabulary.py``.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.race.results_skill.vocabulary import is_vocabulary_word

#: Directorio de perfiles committeados (contracts/reading-profile.md § Where profiles live).
PROFILES_DIR = Path(__file__).resolve().parents[4] / "race_reading_profiles"

_PROFILE_ID_RE = re.compile(r"^[a-z0-9-]{3,64}$")
_FIELD_NAMES = {"position", "bib", "name", "city", "club", "time_or_status", "points"}
_REQUIRED_FIELDS = {"position", "name", "club", "time_or_status"}
_DELIMITERS = {",", ";", "\t"}


def _fold_upper(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).upper()


def _assert_vocabulary_words(text: str, *, where: str) -> None:
    for word in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", text):
        if not is_vocabulary_word(word):
            raise ValueError(
                f"{where}: {word!r} no está en el vocabulario cerrado de vocabulary.py"
            )


class PdfColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "position", "bib", "name", "city", "club", "time_or_status", "points"
    ]
    x_from: float
    x_to: float

    @model_validator(mode="after")
    def _x_from_before_x_to(self) -> PdfColumn:
        if self.x_from >= self.x_to:
            raise ValueError("x_from debe ser menor que x_to")
        return self


class CategoryHeaderPrefix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str

    @field_validator("prefix")
    @classmethod
    def _prefix_is_vocabulary(cls, value: str) -> str:
        _assert_vocabulary_words(value, where="pdf.category_header.prefix")
        return value


class CategoryHeaderPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str

    @field_validator("pattern")
    @classmethod
    def _pattern_is_vocabulary_and_valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"pattern no es un regex válido: {exc}") from exc
        # Solo palabras de vocabulario, dígitos y sintaxis de regex.
        letters_only = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]+", " ", value)
        _assert_vocabulary_words(letters_only, where="pdf.category_header.pattern")
        return value


class CategoryHeaderStructuralXTo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structural_x_to: float


CategoryHeader = CategoryHeaderPrefix | CategoryHeaderPattern | CategoryHeaderStructuralXTo


class PdfBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: Literal["table_bands", "baselines"]
    run_gap_pt: float = Field(ge=0.3, le=5.0)
    columns: list[PdfColumn]
    category_header: CategoryHeader
    skip_structural_lines_starting_with: list[str] = Field(default_factory=list)

    @field_validator("skip_structural_lines_starting_with")
    @classmethod
    def _skip_lines_are_vocabulary(cls, value: list[str]) -> list[str]:
        for line in value:
            _assert_vocabulary_words(line, where="pdf.skip_structural_lines_starting_with")
        return value

    @model_validator(mode="after")
    def _has_required_fields(self) -> PdfBlock:
        present = {column.field for column in self.columns}
        missing = _REQUIRED_FIELDS - present
        if missing:
            raise ValueError(f"pdf.columns falta campo(s) requerido(s): {sorted(missing)}")
        return self


class DelimitedCategoryColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: int = Field(ge=0)


class DelimitedCategorySeparatorRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class _Inner(BaseModel):
        model_config = ConfigDict(extra="forbid")
        first_cell_prefix: str

        @field_validator("first_cell_prefix")
        @classmethod
        def _prefix_is_vocabulary(cls, value: str) -> str:
            _assert_vocabulary_words(value, where="delimited.category.separator_rows.first_cell_prefix")
            return value

    separator_rows: _Inner


DelimitedCategory = DelimitedCategoryColumn | DelimitedCategorySeparatorRows


class DelimitedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delimiter: Literal[",", ";", "\t"]
    header_rows: int = Field(ge=0, le=5)
    columns: dict[str, int | list[int]]
    category: DelimitedCategory

    @field_validator("columns")
    @classmethod
    def _columns_known_fields(cls, value: dict) -> dict:
        unknown = set(value) - _FIELD_NAMES
        if unknown:
            raise ValueError(f"delimited.columns tiene campo(s) desconocido(s): {sorted(unknown)}")
        return value

    @model_validator(mode="after")
    def _has_required_fields(self) -> DelimitedBlock:
        missing = _REQUIRED_FIELDS - set(self.columns)
        if missing:
            raise ValueError(f"delimited.columns falta campo(s) requerido(s): {sorted(missing)}")
        return self


class ReadingProfile(BaseModel):
    """Esquema v1 (contracts/reading-profile.md § Schema v1)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal[1] = Field(alias="schema")
    profile_id: str
    description: str = Field(max_length=120)
    format: Literal["pdf", "delimited"]
    pdf: PdfBlock | None = None
    delimited: DelimitedBlock | None = None
    category_aliases: dict[str, str] = Field(default_factory=dict)
    name_parts_separator: Literal[" "] = " "

    @field_validator("profile_id")
    @classmethod
    def _profile_id_pattern(cls, value: str) -> str:
        if not _PROFILE_ID_RE.match(value):
            raise ValueError(r"profile_id debe matchear ^[a-z0-9-]{3,64}$")
        return value

    @field_validator("description")
    @classmethod
    def _description_digits_only_year_range(cls, value: str) -> str:
        # "no digits except a year range": tolera secuencias de 4 dígitos
        # (opcionalmente en rango "2024-2026"); rechaza cualquier otro dígito
        # suelto (un dorsal, una edad...).
        stripped = re.sub(r"\b\d{4}(-\d{4})?\b", "", value)
        if re.search(r"\d", stripped):
            raise ValueError("description solo admite dígitos como rango de años")
        return value

    @field_validator("category_aliases")
    @classmethod
    def _aliases_keys_are_vocabulary(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            _assert_vocabulary_words(key, where="category_aliases key")
        return value

    @model_validator(mode="after")
    def _format_matches_block(self) -> ReadingProfile:
        if self.format == "pdf":
            if self.pdf is None or self.delimited is not None:
                raise ValueError('format="pdf" exige "pdf" y prohíbe "delimited"')
        else:
            if self.delimited is None or self.pdf is not None:
                raise ValueError('format="delimited" exige "delimited" y prohíbe "pdf"')
        return self


def load_profile(id_or_path: str | Path) -> ReadingProfile:
    """Carga y valida un perfil por ``profile_id`` (busca en ``PROFILES_DIR``)
    o por ruta directa a un ``.json``."""
    path = Path(id_or_path)
    if not path.suffix:
        path = PROFILES_DIR / f"{id_or_path}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReadingProfile.model_validate(payload)


def profile_sha256(path: str | Path) -> str:
    """SHA-256 hexadecimal del contenido en bytes del archivo del perfil
    (``race_import_staged_documents.profile_sha256``)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
