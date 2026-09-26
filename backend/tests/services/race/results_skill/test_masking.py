"""``results_skill.masking`` (amendment 2026-09-26, T119).

Casos de ``contracts/masked-view.md`` § Tests.
"""
from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.race.results_skill.apply import apply_profile
from app.services.race.results_skill.masking import (
    ScannedPdfError,
    UnsupportedFileError,
    build_masked_view,
    leak_count,
    render_masked_view,
)
from app.services.race.results_skill.profile import load_profile
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
)
from tests.helpers.name_sweep import assert_no_fake_names
from tests.helpers.results_csv_builder import build_results_csv
from tests.helpers.results_pdf_builder import (
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)

_PROFILE = load_profile("copa-valle-results-pdf")


def _pdf_bytes(tmp_path, gen, categories, layout="historical") -> bytes:
    out = tmp_path / "sample.pdf"
    build_results_pdf(
        out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
        categories=categories, name_generator=gen, layout=layout,
    )
    return out.read_bytes()


class TestNoLeakAcrossLayouts:
    @pytest.mark.parametrize("layout", ["historical", "2026", "unruled"])
    def test_no_fake_name_word_anywhere_in_view(self, tmp_path, layout):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 4)]
        cats[0].rows[0].long_club = True
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout=layout)

        view = build_masked_view(file_bytes, "pdf")
        rendered = render_masked_view(view)

        assert_no_fake_names(rendered, gen)

    def test_no_fake_name_word_in_delimited_view(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 3)]
        out = tmp_path / "sample.csv"
        build_results_csv(
            out, valida_num=1, location="X", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, delimiter=";",
        )
        view = build_masked_view(out.read_bytes(), "csv")
        rendered = render_masked_view(view)
        assert_no_fake_names(rendered, gen)


class TestNoValueLeaksInContentLine:
    def test_no_bib_time_or_points_value_as_content_token(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 3)]
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))

        for line in rendered.splitlines():
            if " C " not in f" {line.split('|')[0]} ":
                continue
            for row in cats[0].rows:
                assert str(row.bib) not in line.split("|", 1)[-1] if row.bib else True


class TestLeakCheck:
    def test_leak_count_zero_on_normal_document(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 3)]
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))
        document = apply_profile(file_bytes, "pdf", _PROFILE)
        assert leak_count(rendered, document) == 0

    def test_leak_count_catches_a_vocabulary_only_continuation_line(self):
        """Una línea sintética hecha solo de palabras de vocabulario (nunca
        pasaría de un archivo real, pero ejerce la mecánica del chequeo):
        si una fila trae un nombre que por casualidad coincide con una
        palabra de vocabulario, ``leak_count`` debe contarla."""
        rendered = "L001 S | @0.0 CLUB ELITE\n"
        document = ParsedResults(
            categories=[
                ParsedCategory(
                    header_raw="ELITE",
                    code="ELITE_M",
                    rows=[
                        ResultsRow(
                            position=1, bib="1", name="Club Elite", city="",
                            club="", time_raw="0:40:00", points=50,
                        )
                    ],
                )
            ]
        )
        assert leak_count(rendered, document) == 2


class TestStructuralDetection:
    def test_category_header_line_is_structural(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 1)]
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))
        # La línea CAT: siempre contiene "S" como marca de línea estructural.
        assert any(" S " in ln for ln in rendered.splitlines())

    def test_header_with_unknown_word_renders_as_content(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 1)]
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))
        # La fila de títulos de columna del builder ("Ord N° Nombre completo...")
        # trae "N°" -- "N" solo no es palabra de vocabulario -- por lo tanto
        # esa línea se clasifica como contenido, no estructural.
        column_title_line = next(ln for ln in rendered.splitlines() if "⟨N" not in ln.split("|")[0] and "@43.0" in ln and ":" not in ln)
        assert " C " in column_title_line


class TestGluedTokensSplit:
    def test_club_glued_to_time_splits_into_word_and_time(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 2)]
        cats[0].rows[0].long_club = True
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="historical")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))
        # Ninguna línea de contenido debe mezclar un ⟨T⟩ con letras pegadas.
        for line in rendered.splitlines():
            assert "⟩⟨T" not in line.replace(" ", "")


class TestLapDeficitVariantsStayVerbatim:
    @pytest.mark.parametrize("minus_laps", [1, 2])
    def test_lap_deficit_rendered_verbatim(self, tmp_path, minus_laps):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 2)]
        cats[0].rows[0].minus_laps = minus_laps
        cats[0].rows[0].time_raw = None
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        rendered = render_masked_view(build_masked_view(file_bytes, "pdf"))
        unit = "VUELTA" if minus_laps == 1 else "VUELTAS"
        assert f"(-{minus_laps} {unit})" in rendered


class TestDeterminism:
    def test_same_bytes_give_same_view(self, tmp_path):
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 3)]
        file_bytes = _pdf_bytes(tmp_path, gen, cats, layout="2026")
        r1 = render_masked_view(build_masked_view(file_bytes, "pdf"))
        r2 = render_masked_view(build_masked_view(file_bytes, "pdf"))
        assert r1 == r2


class TestRefusals:
    def test_too_large_file_refused(self):
        with pytest.raises(UnsupportedFileError):
            build_masked_view(b"%PDF-" + b"0" * (8 * 1024 * 1024 + 1), "pdf")

    def test_not_pdf_not_utf8_refused(self):
        with pytest.raises(UnsupportedFileError):
            build_masked_view(b"esto no es un pdf", "pdf")

    def test_not_utf8_delimited_refused(self):
        with pytest.raises(UnsupportedFileError):
            build_masked_view(b"\xff\xfe\x80", "csv")

    def test_scanned_pdf_without_text_layer_refused(self):
        minimal_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
        )
        with pytest.raises(ScannedPdfError):
            build_masked_view(minimal_pdf, "pdf")


class TestHypothesisNamesEqualToVocabularyWords:
    @given(
        first=st.sampled_from(["ELITE", "MASTER", "DAMAS", "A"]),
        last=st.sampled_from(["ELITE", "MASTER", "DAMAS", "A"]),
    )
    @settings(max_examples=25, deadline=None)
    def test_content_line_never_reveals_a_name_equal_to_a_vocabulary_word(self, first, last):
        """Un corredor cuyo nombre/apellido *coincide por casualidad* con una
        palabra de vocabulario (``ELITE``, ``MASTER``, ``DAMAS``, ``A``) no
        debe filtrarse verbatim en una línea de CONTENIDO — solo puede
        aparecer verbatim si la línea entera es estructural, y una línea de
        datos con un valor numérico (tiempo/puntos) nunca lo es."""
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        gen = FakeNameGenerator()
        cats = [sequential_category("INFANTIL A", 1)]
        cats[0].rows[0].name = f"{first} {last}"
        out = tmp_dir / "sample.pdf"
        build_results_pdf(
            out, valida_num=1, location="Ciudad Ficticia", event_date=date(2026, 3, 1),
            categories=cats, name_generator=gen, layout="2026",
        )
        rendered = render_masked_view(build_masked_view(out.read_bytes(), "pdf"))
        for line in rendered.splitlines():
            head = line.split("|", 1)[0]
            if " C " not in f" {head} ":
                continue
            body = line.split("|", 1)[-1] if "|" in line else ""
            assert first not in body.split()
            assert last not in body.split()
