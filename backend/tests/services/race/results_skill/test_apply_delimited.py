"""``apply_profile`` sobre texto delimitado (amendment 2026-09-26, T123).

Cubre columna de categoría, filas separadoras, nombres multi-columna y los
delimitadores ``;`` y tab (contracts/reading-profile.md § Delimited text).
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.race.results_skill.apply import apply_profile
from app.services.race.results_skill.profile import ReadingProfile
from tests.helpers.results_csv_builder import build_results_csv
from tests.helpers.results_pdf_builder import FakeNameGenerator, sequential_category


def _column_profile(delimiter: str) -> ReadingProfile:
    return ReadingProfile.model_validate(
        {
            "schema": 1,
            "profile_id": "fictional-delimited-column",
            "description": "CSV ficticio, categoria como columna",
            "format": "delimited",
            "delimited": {
                "delimiter": delimiter,
                "header_rows": 3,
                "columns": {
                    "position": 1, "bib": 2, "name": 3, "city": 4,
                    "club": 5, "time_or_status": 6, "points": 7,
                },
                "category": {"column": 0},
            },
            "category_aliases": {},
            "name_parts_separator": " ",
        }
    )


def _separator_profile(delimiter: str) -> ReadingProfile:
    return ReadingProfile.model_validate(
        {
            "schema": 1,
            "profile_id": "fictional-delimited-separator",
            "description": "CSV ficticio, categoria en fila separadora",
            "format": "delimited",
            "delimited": {
                "delimiter": delimiter,
                "header_rows": 2,
                "columns": {
                    "position": 0, "bib": 1, "name": 2, "city": 3,
                    "club": 4, "time_or_status": 5, "points": 6,
                },
                "category": {"separator_rows": {"first_cell_prefix": "CAT:"}},
            },
            "category_aliases": {},
            "name_parts_separator": " ",
        }
    )


class TestCategoryColumn:
    @pytest.mark.parametrize("delimiter", [",", ";", "\t"])
    def test_full_recovery_with_category_column(self, tmp_path, delimiter):
        gen = FakeNameGenerator()
        cats = [
            sequential_category("INFANTIL A", 3),
            sequential_category("PREJUVENIL A DAMAS", 2),
        ]
        out = tmp_path / "col.csv"
        build_results_csv(
            out, valida_num=1, location="X", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, delimiter=delimiter,
            categories_as_column=True,
        )
        got = apply_profile(out.read_bytes(), "csv", _column_profile(delimiter))

        assert [c.header_raw for c in got.categories] == ["INFANTIL A", "PREJUVENIL A DAMAS"]
        assert [c.code for c in got.categories] == ["INF_A", "PJUV_A_F"]
        assert len(got.categories[0].rows) == 3
        assert len(got.categories[1].rows) == 2
        row = got.categories[0].rows[0]
        assert row.position == 1
        assert row.bib == "100"
        assert row.name
        assert row.time_raw == "0:40:07"
        assert row.points == 50


class TestSeparatorRows:
    @pytest.mark.parametrize("delimiter", [";", "\t"])
    def test_full_recovery_with_separator_rows(self, tmp_path, delimiter):
        gen = FakeNameGenerator()
        cats = [
            sequential_category("INFANTIL A", 3),
            sequential_category("PREJUVENIL A DAMAS", 2),
        ]
        out = tmp_path / "sep.csv"
        build_results_csv(
            out, valida_num=1, location="X", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, delimiter=delimiter,
            categories_as_column=False,
        )
        got = apply_profile(out.read_bytes(), "csv", _separator_profile(delimiter))

        assert [c.header_raw for c in got.categories] == ["INFANTIL A", "PREJUVENIL A DAMAS"]
        assert [c.code for c in got.categories] == ["INF_A", "PJUV_A_F"]
        assert len(got.categories[0].rows) == 3
        assert len(got.categories[1].rows) == 2
        # La fila de encabezado de columnas repetida por bloque nunca se lee
        # como fila de datos.
        for category in got.categories:
            for row in category.rows:
                assert row.position is not None


class TestMultiColumnName:
    def test_name_spans_two_columns_joined_by_separator(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 2)]
        out = tmp_path / "multiname.csv"
        build_results_csv(
            out, valida_num=1, location="X", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, delimiter=";",
            categories_as_column=False,
        )
        text = out.read_text(encoding="utf-8")
        # Reescribe "CORREDOR" (nombre completo) en dos columnas: apellidos;nombres.
        lines = text.splitlines()
        out_lines = []
        for line in lines:
            if line.startswith("POS;"):
                out_lines.append("POS;N°;APELLIDOS;NOMBRES;CIUDAD;CLUB / EQUIPO;TIEMPO;PUNTOS")
                continue
            parts = line.split(";")
            if len(parts) == 7 and parts[0].strip().isdigit():
                given, _, surname = parts[2].partition(" ")
                out_lines.append(
                    ";".join([parts[0], parts[1], surname, given, parts[3], parts[4], parts[5], parts[6]])
                )
                continue
            out_lines.append(line)
        out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

        profile = ReadingProfile.model_validate(
            {
                "schema": 1,
                "profile_id": "fictional-delimited-multiname",
                "description": "CSV ficticio, nombre en dos columnas",
                "format": "delimited",
                "delimited": {
                    "delimiter": ";",
                    "header_rows": 2,
                    "columns": {
                        "position": 0, "bib": 1, "name": [2, 3], "city": 4,
                        "club": 5, "time_or_status": 6, "points": 7,
                    },
                    "category": {"separator_rows": {"first_cell_prefix": "CAT:"}},
                },
                "category_aliases": {},
                "name_parts_separator": " ",
            }
        )
        got = apply_profile(out.read_bytes(), "csv", profile)

        assert len(got.categories[0].rows) == 2
        given0, _, surname0 = gen.generated[0].partition(" ")
        row0 = got.categories[0].rows[0]
        assert row0.name == f"{surname0} {given0}"
