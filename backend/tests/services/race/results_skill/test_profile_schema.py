"""Esquema v1 de ``ReadingProfile`` (amendment 2026-09-26, T121).

Casos de rechazo listados en ``contracts/reading-profile.md`` § Keys and rules.
"""
from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from app.services.race.results_skill.profile import ReadingProfile

_VALID_PDF: dict = {
    "schema": 1,
    "profile_id": "copa-valle-results-pdf",
    "description": "Copa Valle XCO, resultados por valida, diseno 2024-2026",
    "format": "pdf",
    "pdf": {
        "rows": "table_bands",
        "run_gap_pt": 1.0,
        "columns": [
            {"field": "position", "x_from": 45.0, "x_to": 76.5},
            {"field": "bib", "x_from": 76.5, "x_to": 109.9},
            {"field": "name", "x_from": 109.9, "x_to": 257.4},
            {"field": "city", "x_from": 257.4, "x_to": 327.6},
            {"field": "club", "x_from": 327.6, "x_to": 466.0},
            {"field": "time_or_status", "x_from": 466.0, "x_to": 539.0},
            {"field": "points", "x_from": 539.0, "x_to": 600.0},
        ],
        "category_header": {"prefix": "CAT:"},
        "skip_structural_lines_starting_with": ["POS", "RESULTADOS"],
    },
    "category_aliases": {},
    "name_parts_separator": " ",
}


def _with(**overrides):
    payload = {**_VALID_PDF, **overrides}
    return payload


class TestSchemaAcceptsContractExample:
    def test_valid_example_is_accepted(self):
        profile = ReadingProfile.model_validate(_VALID_PDF)
        assert profile.profile_id == "copa-valle-results-pdf"
        assert profile.pdf is not None


class TestRejectsUnknownKeys:
    def test_unknown_top_level_key(self):
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate({**_VALID_PDF, "unexpected": True})

    def test_unknown_pdf_key(self):
        payload = _with(pdf={**_VALID_PDF["pdf"], "unexpected": 1})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    def test_unknown_column_key(self):
        columns = [dict(_VALID_PDF["pdf"]["columns"][0], extra="x")] + _VALID_PDF["pdf"]["columns"][1:]
        payload = _with(pdf={**_VALID_PDF["pdf"], "columns": columns})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)


class TestRunGapRange:
    @pytest.mark.parametrize("value", [0.0, 0.29, 5.01, 10.0])
    def test_out_of_range_rejected(self, value):
        payload = _with(pdf={**_VALID_PDF["pdf"], "run_gap_pt": value})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    @pytest.mark.parametrize("value", [0.3, 1.0, 5.0])
    def test_in_range_accepted(self, value):
        payload = _with(pdf={**_VALID_PDF["pdf"], "run_gap_pt": value})
        ReadingProfile.model_validate(payload)


class TestProfileIdPattern:
    @pytest.mark.parametrize("bad_id", ["AB", "ab", "Copa-Valle", "a b c", "a_b_c", ""])
    def test_rejects_bad_profile_id(self, bad_id):
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(_with(profile_id=bad_id))

    def test_accepts_good_profile_id(self):
        ReadingProfile.model_validate(_with(profile_id="a1-b2-copa-valle"))


class TestDescriptionLength:
    def test_rejects_over_120_chars(self):
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(_with(description="x" * 121))

    def test_accepts_year_range_digits(self):
        ReadingProfile.model_validate(_with(description="Copa Valle 2024-2026"))

    def test_rejects_non_year_digits(self):
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(_with(description="Perfil version 2"))


class TestVocabularyOnlyWords:
    def test_rejects_non_vocabulary_alias_key(self):
        payload = _with(category_aliases={"NOMBREDECORREDOR": "X"})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    def test_accepts_vocabulary_alias_key(self):
        payload = _with(category_aliases={"ELITE DAMAS": "ELITE_F"})
        ReadingProfile.model_validate(payload)

    def test_rejects_non_vocabulary_skip_line(self):
        payload = _with(pdf={**_VALID_PDF["pdf"], "skip_structural_lines_starting_with": ["FICTICIO"]})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    def test_accepts_vocabulary_skip_line(self):
        payload = _with(pdf={**_VALID_PDF["pdf"], "skip_structural_lines_starting_with": ["POS"]})
        ReadingProfile.model_validate(payload)


class TestMissingRequiredField:
    @pytest.mark.parametrize("required", ["position", "name", "club", "time_or_status"])
    def test_missing_required_field_rejected(self, required):
        columns = [c for c in _VALID_PDF["pdf"]["columns"] if c["field"] != required]
        payload = _with(pdf={**_VALID_PDF["pdf"], "columns": columns})
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    def test_optional_fields_may_be_absent(self):
        columns = [c for c in _VALID_PDF["pdf"]["columns"] if c["field"] not in ("bib", "city", "points")]
        payload = _with(pdf={**_VALID_PDF["pdf"], "columns": columns})
        ReadingProfile.model_validate(payload)


class TestDelimitedSchema:
    _VALID_DELIMITED: ClassVar[dict] = {
        "schema": 1,
        "profile_id": "fictional-delimited",
        "description": "CSV ficticio",
        "format": "delimited",
        "delimited": {
            "delimiter": ";",
            "header_rows": 1,
            "columns": {
                "position": 0, "bib": 1, "name": [2, 3], "city": 4,
                "club": 5, "time_or_status": 6, "points": 7,
            },
            "category": {"column": 8},
        },
        "category_aliases": {},
        "name_parts_separator": " ",
    }

    def test_valid_delimited_is_accepted(self):
        ReadingProfile.model_validate(self._VALID_DELIMITED)

    def test_separator_rows_variant_is_accepted(self):
        payload = {
            **self._VALID_DELIMITED,
            "delimited": {
                **self._VALID_DELIMITED["delimited"],
                "category": {"separator_rows": {"first_cell_prefix": "CAT:"}},
            },
        }
        ReadingProfile.model_validate(payload)

    def test_format_mismatch_rejected(self):
        payload = {**self._VALID_DELIMITED, "format": "pdf"}
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)

    def test_unknown_delimiter_rejected(self):
        payload = {
            **self._VALID_DELIMITED,
            "delimited": {**self._VALID_DELIMITED["delimited"], "delimiter": "|"},
        }
        with pytest.raises(ValidationError):
            ReadingProfile.model_validate(payload)
