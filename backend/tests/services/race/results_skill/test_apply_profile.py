"""``apply_profile`` sobre ``copa-valle-results-pdf`` (amendment 2026-09-26, T122).

Regresión de paridad: ``apply_profile`` debe reproducir, fila por fila, lo
que el parser retirado (``pdf_parser.parse_results_document``) producía
sobre el mismo PDF sintético. El golden (``tests/fixtures/race/parity/
{historical,2026}.json``) se generó **antes** de que T153 borre el parser
(ver ``tests/fixtures/race/parity/generate_golden.py``); este test no vuelve
a llamar al parser retirado — solo compara ``apply_profile`` contra el JSON
ya congelado.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.services.race.results_skill.apply import apply_profile
from app.services.race.results_skill.profile import load_profile
from app.services.race.staged_document import (
    UnreadableRow,
    document_from_json,
    document_to_json,
)
from tests.helpers.results_pdf_builder import (
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)
from tests.services.race.results_skill.golden_fixtures import build_parity_categories

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "race" / "parity"
_PROFILE = load_profile("copa-valle-results-pdf")


def _build_pdf(tmp_path: Path, layout: str) -> Path:
    gen = FakeNameGenerator()
    categories = build_parity_categories()
    out = tmp_path / f"{layout}.pdf"
    build_results_pdf(
        out,
        valida_num=3,
        location="Ciudad Ficticia",
        event_date=date(2026, 3, 1),
        categories=categories,
        name_generator=gen,
        layout=layout,
    )
    return out


class TestParityWithRetiredParser:
    @pytest.mark.parametrize("layout", ["historical", "2026"])
    def test_apply_profile_matches_golden_row_by_row(self, tmp_path, layout):
        pdf_path = _build_pdf(tmp_path, layout)
        golden = document_from_json(
            json.loads((_FIXTURES / f"{layout}.json").read_text(encoding="utf-8"))
        )

        got = apply_profile(pdf_path.read_bytes(), "pdf", _PROFILE)

        assert document_to_json(got) == document_to_json(golden)


class TestUnknownHeader:
    def test_unrecognised_category_keeps_its_rows_with_code_none(self, tmp_path):
        cats = [sequential_category("CATEGORIA RARA XYZ", 2)]
        gen = FakeNameGenerator()
        out = tmp_path / "unknown.pdf"
        build_results_pdf(
            out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, layout="2026",
        )
        got = apply_profile(out.read_bytes(), "pdf", _PROFILE)
        assert len(got.categories) == 1
        assert got.categories[0].code is None
        assert len(got.categories[0].rows) == 2


class TestLapDeficitVariants:
    @pytest.mark.parametrize("minus_laps", [1, 2])
    def test_lap_deficit_kept_as_time_raw(self, tmp_path, minus_laps):
        cats = [sequential_category("INFANTIL A", 2)]
        cats[0].rows[0].minus_laps = minus_laps
        cats[0].rows[0].time_raw = None
        gen = FakeNameGenerator()
        out = tmp_path / "laps.pdf"
        build_results_pdf(
            out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, layout="2026",
        )
        got = apply_profile(out.read_bytes(), "pdf", _PROFILE)
        row = got.categories[0].rows[0]
        unit = "VUELTA" if minus_laps == 1 else "VUELTAS"
        assert row.time_raw == f"(-{minus_laps} {unit})"


class TestPositionWithoutTime:
    def test_row_without_time_has_empty_time_raw(self, tmp_path):
        cats = [sequential_category("INFANTIL A", 2)]
        cats[0].rows[1].time_raw = None
        cats[0].rows[1].status = None
        cats[0].rows[1].minus_laps = None
        gen = FakeNameGenerator()
        out = tmp_path / "notime.pdf"
        build_results_pdf(
            out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, layout="2026",
        )
        got = apply_profile(out.read_bytes(), "pdf", _PROFILE)
        row = got.categories[0].rows[1]
        assert row.position == 2
        assert row.time_raw == ""


class TestCategoryAcrossPageBreak:
    def test_same_header_repeated_stays_one_category(self, tmp_path):
        # Muchas filas para forzar la paginación de WeasyPrint (categoría
        # única que se repite el encabezado ``CAT:`` en la página siguiente
        # se colapsa en la misma categoría — edge-cases.md §4.9).
        cats = [sequential_category("INFANTIL A", 60)]
        gen = FakeNameGenerator()
        out = tmp_path / "pagebreak.pdf"
        build_results_pdf(
            out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, layout="2026",
        )
        got = apply_profile(out.read_bytes(), "pdf", _PROFILE)
        assert len(got.categories) == 1
        assert len(got.categories[0].rows) == 60


class TestUnreadableRow:
    def test_ordinal_with_nothing_else_readable_is_unreadable(self):
        """Una banda con posición pero sin ningún otro campo legible se
        reporta como ``UnreadableRow``, nunca se descarta en silencio
        (contracts/reading-profile.md § PDF, punto 6). El engine no exige
        un PDF real para esta garantía — se ejerce a nivel de ``_row_from_fields``,
        que es donde vive la regla."""
        from app.services.race.results_skill.apply import _DocState, _row_from_fields

        state = _DocState()
        state.start_category("INFANTIL A", {})
        _row_from_fields({"position": "1"}, page=1, state=state)

        assert state.current.rows == []
        assert state.unreadable == [UnreadableRow(page=1, ordinal=1)]


class TestRowsBeforeFirstHeader:
    def test_rows_before_any_cat_header_go_to_sin_categoria(self, tmp_path):
        from weasyprint import HTML

        from tests.helpers.results_pdf_builder import _render_html

        # Construye el HTML a mano: una fila de tabla sin ningún "CAT:" antes.
        gen = FakeNameGenerator()
        cats = sequential_category("SIN ENCABEZADO", 1)
        html = _render_html(
            valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=[cats], name_generator=gen, layout="2026",
        )
        html = html.replace('<p class="cat-header">CAT: SIN ENCABEZADO</p>', "")
        out = tmp_path / "nohead.pdf"
        HTML(string=html).write_pdf(str(out))

        got = apply_profile(out.read_bytes(), "pdf", _PROFILE)
        assert len(got.categories) == 1
        assert got.categories[0].header_raw == "SIN CATEGORÍA"
        assert got.categories[0].code is None
        assert len(got.categories[0].rows) == 1
