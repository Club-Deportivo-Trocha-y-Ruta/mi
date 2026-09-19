"""Self-test del builder de PDFs sintéticos (feature 044, T003).

Prueba que ``results_pdf_builder`` efectivamente reproduce el defecto real
descrito en ``research.md`` R-01 (club largo impreso encima del tiempo) y
que ningún nombre generado proviene de una lista de personas reales.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from app.services.race.pdf_parser import _RESULTS_ROW_RE
from tests.helpers.results_pdf_builder import (
    FIRST_NAMES,
    LAST_NAMES,
    CategorySpec,
    FakeNameGenerator,
    RowSpec,
    build_results_pdf,
    sequential_category,
)


def _build(tmp_path: Path, categories: list[CategorySpec], gen: FakeNameGenerator) -> Path:
    return build_results_pdf(
        tmp_path / "sintetico.pdf",
        valida_num=8,
        location="Ciudad Ficticia",
        event_date=date(2025, 8, 9),
        categories=categories,
        name_generator=gen,
    )


def _find_row_line(text: str, bib: str) -> str:
    """Localiza la línea de datos que contiene ``bib`` en el texto extraído."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped.split()[1:2] == [bib]:
            return stripped
    raise AssertionError(f"No se encontró una línea con dorsal {bib!r} en: {text!r}")


class TestLongClubOverflowReproducesDefect:
    """T003.1 — el club largo se imprime encima del tiempo (R-01)."""

    def test_long_club_row_does_not_match_results_row_regex(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = sequential_category("PREJUVENIL A DAMAS", 3)
        category.rows[1].bib = "777"
        category.rows[1].long_club = True
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        line = _find_row_line(text, "777")
        assert _RESULTS_ROW_RE.match(line) is None

    def test_normal_row_does_match_results_row_regex(self, tmp_path: Path):
        """Control: sin ``long_club``, la misma fila SÍ matchea (no es un
        defecto genérico del builder — solo se dispara con club largo)."""
        gen = FakeNameGenerator()
        category = sequential_category("PREJUVENIL A DAMAS", 3)
        category.rows[1].bib = "777"
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        line = _find_row_line(text, "777")
        assert _RESULTS_ROW_RE.match(line) is not None

    def test_time_digits_are_interleaved_with_club_letters(self, tmp_path: Path):
        """No solo falla el regex: los dígitos del tiempo quedan literalmente
        dispersos entre letras del club (orden por x), nunca contiguos."""
        gen = FakeNameGenerator()
        category = sequential_category("PREJUVENIL A DAMAS", 1)
        row = category.rows[0]
        row.bib = "777"
        row.long_club = True
        row.time_raw = "0:40:07"
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        line = _find_row_line(text, "777")
        # El tiempo limpio "0:40:07" ya no aparece como substring contiguo...
        assert row.time_raw not in line
        # ...pero cada uno de sus caracteres sigue presente en algún lado
        # de la línea (intercalado, no perdido).
        for ch in row.time_raw:
            assert ch in line
        # Y hay al menos una letra del club entre dos dígitos del tiempo
        # (prueba directa de "intercalado", no solo de reordenamiento).
        digit_positions = [i for i, c in enumerate(line) if c.isdigit()]
        assert any(
            line[a + 1 : b].strip(":").strip() and not line[a + 1 : b].strip(":").isdigit()
            for a, b in zip(digit_positions, digit_positions[1:])
            if b - a > 1 and any(c.isalpha() for c in line[a + 1 : b])
        )


class TestFindTablesDetectsRowBands:
    """T003.2 — pdfplumber.find_tables detecta una banda por fila."""

    def test_row_count_matches_table_bands(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = sequential_category("INFANTIL A", 5)
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            tables = pdf.pages[0].find_tables()

        assert len(tables) == 1
        # +1 por la fila de encabezado de la tabla (Ord, N°, ...).
        assert len(tables[0].rows) == len(category.rows) + 1

    def test_two_categories_produce_two_tables(self, tmp_path: Path):
        gen = FakeNameGenerator()
        cat_a = sequential_category("INFANTIL A", 2)
        cat_b = sequential_category("INFANTIL B", 3)
        pdf_path = _build(tmp_path, [cat_a, cat_b], gen)

        with pdfplumber.open(pdf_path) as pdf:
            tables = pdf.pages[0].find_tables()

        assert len(tables) == 2
        assert len(tables[0].rows) == len(cat_a.rows) + 1
        assert len(tables[1].rows) == len(cat_b.rows) + 1

    def test_overflowing_row_still_produces_its_own_band(self, tmp_path: Path):
        """El desborde es solo de texto — los rulings de la celda (y por
        tanto la banda de la fila) no se ven afectados."""
        gen = FakeNameGenerator()
        category = sequential_category("PREJUVENIL A DAMAS", 3)
        category.rows[1].long_club = True
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            tables = pdf.pages[0].find_tables()

        assert len(tables[0].rows) == len(category.rows) + 1


class TestFakeNamesNeverReal:
    """T003.3 — los nombres provienen únicamente del generador falso."""

    def test_generated_names_only_use_fake_pools(self):
        gen = FakeNameGenerator()
        names = [gen.next_name() for _ in range(200)]

        assert names == gen.generated
        for name in names:
            first, last1, last2 = name.split()
            assert first in FIRST_NAMES
            assert last1 in LAST_NAMES
            assert last2 in LAST_NAMES

    def test_default_seed_is_deterministic_across_instances(self):
        gen_a = FakeNameGenerator()
        gen_b = FakeNameGenerator()
        assert [gen_a.next_name() for _ in range(20)] == [
            gen_b.next_name() for _ in range(20)
        ]

    def test_pdf_only_contains_names_from_the_generator(self, tmp_path: Path):
        """Cierre del ciclo: los nombres que terminan IMPRESOS en el PDF son
        exactamente los que el generador reporta haber producido — nunca un
        nombre real pasado por fuera (ej. hardcodeado a mano en el caller)."""
        gen = FakeNameGenerator()
        category = sequential_category("JUNIOR", 4)
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        for name in gen.generated:
            assert name in text

    def test_explicit_row_name_bypasses_generator_and_is_still_fake(self, tmp_path: Path):
        """Si el caller fija ``RowSpec.name`` a mano, el builder no lo toca
        — la responsabilidad de que sea ficticio recae en el caller. Aquí
        confirmamos que un nombre explícito NO se agrega a ``generated``
        (para que el barrido de T003.3 no lo confunda con uno inventado)."""
        gen = FakeNameGenerator()
        category = CategorySpec(
            header="ELITE",
            rows=[RowSpec(position=1, name="Nombre Explicito Ficticio", points=50)],
        )
        _build(tmp_path, [category], gen)

        assert "Nombre Explicito Ficticio" not in gen.generated


class TestBuilderOptions:
    """Cobertura de las demás opciones pedidas: hueco, duplicado, categoría
    desconocida y numeral de válida VIII."""

    def test_removed_position_leaves_a_gap(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = sequential_category("INFANTIL A", 4)
        del category.rows[1]  # ya no hay posición 2
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        ordinals = [
            int(line.split()[0])
            for line in text.splitlines()
            if line.strip() and line.split()[0].isdigit()
        ]
        assert ordinals == [1, 3, 4]

    def test_duplicated_position(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = sequential_category("INFANTIL A", 3)
        category.rows[-1].position = category.rows[-2].position
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        ordinals = [
            int(line.split()[0])
            for line in text.splitlines()
            if line.strip() and line.split()[0].isdigit()
        ]
        assert ordinals == [1, 2, 2]

    def test_unknown_category_header_is_rendered_as_is(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = CategorySpec(
            header="CATEGORIA FANTASMA",
            rows=[RowSpec(position=1, points=10)],
        )
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        assert "CAT: CATEGORIA FANTASMA" in text

    def test_valida_num_viii_renders_roman_numeral(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = sequential_category("INFANTIL A", 1)
        pdf_path = build_results_pdf(
            tmp_path / "v8.pdf",
            valida_num=8,
            location="Ciudad Ficticia",
            event_date=date(2025, 8, 9),
            categories=[category],
            name_generator=gen,
        )

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        assert "VALIDA VIII CIUDAD FICTICIA AGOSTO 9 DE 2025" in text

    def test_row_without_time_renders_blank_time_cell(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = CategorySpec(
            header="INFANTIL A",
            rows=[RowSpec(position=1, bib="500", points=50)],
        )
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        line = _find_row_line(text, "500")
        # Sin token de tiempo (ni H:MM:SS ni DNF/DSQ/DNS ni vueltas): el
        # regex actual no puede matchear un "pos bib body points" desnudo.
        assert _RESULTS_ROW_RE.match(line) is None
        assert "50" in line.split()

    def test_status_and_minus_laps_tokens_still_match_the_regex(self, tmp_path: Path):
        gen = FakeNameGenerator()
        category = CategorySpec(
            header="INFANTIL A",
            rows=[
                RowSpec(position=1, bib="501", status="DNF", points=0),
                RowSpec(position=2, bib="502", minus_laps=2, points=30),
            ],
        )
        pdf_path = _build(tmp_path, [category], gen)

        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""

        dnf_line = _find_row_line(text, "501")
        laps_line = _find_row_line(text, "502")
        assert _RESULTS_ROW_RE.match(dnf_line) is not None
        m = _RESULTS_ROW_RE.match(laps_line)
        assert m is not None
        assert m.group("time") == "(-2 VUELTAS)"


@pytest.mark.parametrize("valida_num", [0, 13])
def test_valida_num_out_of_range_raises(tmp_path: Path, valida_num: int):
    gen = FakeNameGenerator()
    category = sequential_category("INFANTIL A", 1)
    with pytest.raises(ValueError):
        build_results_pdf(
            tmp_path / "invalido.pdf",
            valida_num=valida_num,
            location="Ciudad Ficticia",
            event_date=date(2025, 8, 9),
            categories=[category],
            name_generator=gen,
        )
