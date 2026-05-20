"""Tests del módulo ``app.services.race.csv_parser``.

Cubren:
- Detección del header de evento (título + fecha en dos líneas).
- Mapeo de categorías textuales CSV (``CATEGORÍA: ...``) a códigos canon.
- Tolerancia a guión interno (``PRE-INFANTIL`` vs ``PREINFANTIL``).
- No colisión substring entre ``PRE-JUVENIL A`` y ``PRE-JUVENIL A FEMENINO``.
- Manejo de ``-`` en columna TIEMPO → ``DNF``.
- Status explícito ``DNF`` preservado.
- Filas en blanco entre bloques.
- Categorías desconocidas: warning + omisión silenciosa.
- Filas malformadas (sin dorsal numérico): warning + descartadas.
- Variantes de capitalización en club Trocha y Ruta detectadas por fuzzy.

Fixture: ``backend/tests/fixtures/race/valida_i_2026_sevilla.csv`` (sintético
anonimizado — los nombres no son reales para evitar dependencia de un PDF
de menores en el repo de tests).
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest

from app.services.race.csv_parser import (
    parse_event_header_csv,
    parse_results_csv,
)
from app.services.race.normalizer import is_trocha_y_ruta
from app.services.race.pdf_parser import EventHeader, ResultsRow

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "race"


@pytest.fixture(scope="session")
def sevilla_csv() -> Path:
    p = _FIXTURES / "valida_i_2026_sevilla.csv"
    assert p.exists(), f"Fixture faltante: {p}"
    return p


# ===========================================================================
# parse_event_header_csv
# ===========================================================================


class TestParseEventHeaderCsv:
    def test_returns_event_header_for_valida_i_sevilla(self, sevilla_csv: Path):
        hdr = parse_event_header_csv(sevilla_csv)
        assert isinstance(hdr, EventHeader)
        assert hdr.valida_num == 1
        assert hdr.location == "SEVILLA"
        assert hdr.event_date == date(2026, 1, 31)

    def test_raw_text_preserves_first_lines(self, sevilla_csv: Path):
        hdr = parse_event_header_csv(sevilla_csv)
        assert "SEVILLA" in hdr.raw_text
        assert "31 de enero" in hdr.raw_text

    def test_raises_file_not_found_when_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_event_header_csv(tmp_path / "nope.csv")

    def test_returns_none_when_header_not_found(self, tmp_path: Path):
        bogus = tmp_path / "sin_header.csv"
        bogus.write_text(
            "alguna linea,,,,,\n"
            "otra linea,,,,,\n"
            "ni titulo ni fecha,,,,,\n",
            encoding="utf-8",
        )
        assert parse_event_header_csv(bogus) is None


# ===========================================================================
# parse_results_csv — estructura y categorías
# ===========================================================================


class TestParseResultsCsvStructure:
    def test_returns_dict_keyed_by_category_code(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        assert isinstance(out, dict)
        assert all(isinstance(rows, list) for rows in out.values())

    def test_parses_known_categories_only(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        # Fixture tiene 8 cabeceras, 1 desconocida ("CATEGORIA INEXISTENTE XYZ")
        # → 7 categorías válidas en el resultado.
        expected = {
            "INF_A",
            "PRE_A_F",
            "PRE_A",
            "PJUV_A",
            "PJUV_A_F",
            "ELITE_M",
            "MAS_C1",
        }
        assert set(out.keys()) == expected

    def test_unknown_category_logged_as_warning(
        self, sevilla_csv: Path, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(logging.WARNING, logger="app.services.race.csv_parser")
        parse_results_csv(sevilla_csv)
        msgs = [r.getMessage() for r in caplog.records]
        assert any("desconocido" in m.lower() for m in msgs)


# ===========================================================================
# parse_results_csv — filas y campos
# ===========================================================================


class TestParseResultsCsvRows:
    def test_returns_results_row_dataclass(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        for row in out["INF_A"]:
            assert isinstance(row, ResultsRow)

    def test_position_and_bib_coerced_to_int_and_str(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        first = out["INF_A"][0]
        assert first.position == 1
        assert first.bib == "413"
        assert isinstance(first.bib, str)

    def test_dash_in_time_column_maps_to_dnf(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        dnf_rows = [r for r in out["INF_A"] if r.time_raw == "DNF"]
        # Fila INF_A pos 25 con tiempo ``-``
        assert any(r.bib == "426" for r in dnf_rows)

    def test_explicit_dnf_preserved(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        # PJUV_A_F pos 2 lleva ``DNF`` literal en la columna tiempo
        target = [r for r in out["PJUV_A_F"] if r.bib == "904"]
        assert target and target[0].time_raw == "DNF"

    def test_points_zero_when_missing(self, tmp_path: Path):
        f = tmp_path / "pts.csv"
        f.write_text(
            "CATEGORÍA: INFANTIL A,,,,,\n"
            "POS,N°,CORREDOR,CLUB / EQUIPO,TIEMPO,PUNTOS\n"
            "10,500,Algun Nombre,Otro,00:30:00,\n",
            encoding="utf-8",
        )
        out = parse_results_csv(f)
        assert out["INF_A"][0].points == 0

    def test_city_is_empty_string(self, sevilla_csv: Path):
        """CSV federación no publica columna ciudad — ``city`` debe ser ``''``."""
        out = parse_results_csv(sevilla_csv)
        assert all(r.city == "" for rows in out.values() for r in rows)

    def test_normal_time_preserved_verbatim(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        first = out["INF_A"][0]
        assert first.time_raw == "00:24:28"


# ===========================================================================
# parse_results_csv — robustez
# ===========================================================================


class TestParseResultsCsvRobustness:
    def test_blank_rows_between_blocks_are_skipped(self, sevilla_csv: Path):
        # Si no se saltan, el conteo INF_A sería >5 o aparecerían rows sin cat.
        out = parse_results_csv(sevilla_csv)
        # Fixture INF_A tiene exactamente 5 filas de datos.
        assert len(out["INF_A"]) == 5

    def test_malformed_row_without_numeric_bib_skipped_with_warning(
        self, sevilla_csv: Path, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(logging.WARNING, logger="app.services.race.csv_parser")
        out = parse_results_csv(sevilla_csv)
        # MAS_C1 fixture incluye 1 fila legítima + 1 malformada (sin dorsal)
        assert len(out["MAS_C1"]) == 1
        msgs = [r.getMessage() for r in caplog.records]
        assert any("sin dorsal" in m.lower() or "no numérico" in m.lower() for m in msgs)

    def test_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_results_csv(tmp_path / "no_existe.csv")

    def test_handles_utf8_bom(self, tmp_path: Path):
        """Excel a veces exporta CSV con BOM UTF-8 — el parser usa ``utf-8-sig``."""
        f = tmp_path / "bom.csv"
        content = (
            "CATEGORÍA: INFANTIL A,,,,,\n"
            "POS,N°,CORREDOR,CLUB / EQUIPO,TIEMPO,PUNTOS\n"
            "1,100,Alguien,Otro,00:30:00,40\n"
        )
        f.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        out = parse_results_csv(f)
        assert out["INF_A"][0].position == 1


# ===========================================================================
# Mapeo de cabeceras críticas (regresión colisión + guión)
# ===========================================================================


class TestCategoryHeaderMappingRegressions:
    def test_pre_juvenil_a_femenino_no_collision_with_pre_juvenil_a(
        self, sevilla_csv: Path
    ):
        """``PRE-JUVENIL A`` no debe absorber filas de ``PRE-JUVENIL A FEMENINO``."""
        out = parse_results_csv(sevilla_csv)
        # PJUV_A tiene exactamente las 2 filas masculinas del fixture.
        assert len(out["PJUV_A"]) == 2
        # PJUV_A_F tiene exactamente las 2 filas femeninas del fixture.
        assert len(out["PJUV_A_F"]) == 2
        # Disjoint bibs entre ambas categorías.
        bibs_m = {r.bib for r in out["PJUV_A"]}
        bibs_f = {r.bib for r in out["PJUV_A_F"]}
        assert bibs_m.isdisjoint(bibs_f)

    def test_pre_infantil_with_dash_resolves_to_pre_a(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        # PRE_A en fixture tiene 2 filas, PRE_A_F tiene 2 filas.
        assert len(out["PRE_A"]) == 2
        assert len(out["PRE_A_F"]) == 2

    def test_master_with_diacritic_resolves(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        # ``MÁSTER C1`` debe matchear ``MAS_C1`` después de unidecode.
        assert "MAS_C1" in out

    def test_elite_with_diacritic_resolves(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        assert "ELITE_M" in out


# ===========================================================================
# Integración con normalizer (fuzzy TyR sobre clubes detectados por CSV)
# ===========================================================================


class TestCsvIntegrationWithNormalizer:
    def test_uppercase_trocha_y_ruta_detected_as_tyr(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        # En PJUV_A el club aparece como ``CLUB TROCHA Y RUTA`` (mayúsculas).
        tyr = [r for r in out["PJUV_A"] if is_trocha_y_ruta(r.club)]
        assert len(tyr) == 1
        assert tyr[0].bib == "609"

    def test_total_tyr_rows_across_all_categories(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        n = sum(1 for rows in out.values() for r in rows if is_trocha_y_ruta(r.club))
        # Fixture: 6 filas TyR distribuidas (2 INF_A, 1 PRE_A, 1 PJUV_A, 1
        # PJUV_A_F, 1 ELITE_M). PRE_A_F no tiene TyR — sirve para garantizar
        # que detección no marca falsos positivos en categorías sin club TyR.
        assert n == 6

    def test_non_tyr_clubs_not_detected_as_tyr(self, sevilla_csv: Path):
        out = parse_results_csv(sevilla_csv)
        for rows in out.values():
            for r in rows:
                if not r.club:
                    continue
                normalized = r.club.lower()
                if "trocha" not in normalized:
                    assert not is_trocha_y_ruta(r.club), (
                        f"Falso positivo TyR para club {r.club!r}"
                    )


# ===========================================================================
# Cobertura de ramas defensivas
# ===========================================================================


class TestDefensiveBranches:
    def test_row_with_fewer_than_six_columns_skipped_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "short.csv"
        f.write_text(
            "CATEGORÍA: INFANTIL A,,,,,\n"
            "POS,N°,CORREDOR,CLUB / EQUIPO,TIEMPO,PUNTOS\n"
            "1,100,Alguien\n"  # solo 3 columnas
            "2,200,Otra Persona,Otro,00:30:00,36\n",
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING, logger="app.services.race.csv_parser")
        out = parse_results_csv(f)
        assert len(out["INF_A"]) == 1
        assert any("menos de 6" in r.getMessage() for r in caplog.records)

    def test_row_with_empty_bib_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        f = tmp_path / "empty_bib.csv"
        f.write_text(
            "CATEGORÍA: INFANTIL A,,,,,\n"
            "POS,N°,CORREDOR,CLUB / EQUIPO,TIEMPO,PUNTOS\n"
            "1,,Sin Dorsal,Otro,00:30:00,40\n",
            encoding="utf-8",
        )
        caplog.set_level(logging.WARNING, logger="app.services.race.csv_parser")
        out = parse_results_csv(f)
        assert out.get("INF_A", []) == []
        assert any("sin dorsal" in r.getMessage().lower() for r in caplog.records)

    def test_normalize_time_cell_handles_none(self):
        from app.services.race.csv_parser import _normalize_time_cell

        assert _normalize_time_cell(None) == "DNF"

    def test_header_with_unknown_roman_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """Roman ``X`` no está en el mapping → ``None`` + warning."""
        f = tmp_path / "bad_roman.csv"
        f.write_text(
            "RESULTADOS OFICIALES: X VALIDA COPA VALLE - SEVILLA,,,,,\n"
            " - 31 de enero de 2026,,,,,\n",
            encoding="utf-8",
        )
        # El regex sólo acepta romans específicos, así que ``X`` no matchea —
        # la rama ``num_roman not in _ROMAN_TO_INT`` requiere alteración manual.
        # Probamos via header sin date para forzar None + cobertura del else.
        caplog.set_level(logging.WARNING, logger="app.services.race.csv_parser")
        assert parse_event_header_csv(f) is None

    def test_header_stops_after_five_inspected_lines(self, tmp_path: Path):
        """Si las 5 primeras líneas no vacías no contienen el header, retorna None."""
        f = tmp_path / "deep_header.csv"
        f.write_text(
            "linea 1,,,,,\n"
            "linea 2,,,,,\n"
            "linea 3,,,,,\n"
            "linea 4,,,,,\n"
            "linea 5,,,,,\n"
            "RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA,,,,,\n"
            " - 31 de enero de 2026,,,,,\n",
            encoding="utf-8",
        )
        assert parse_event_header_csv(f) is None

    def test_header_skips_blank_rows_before_counting(self, tmp_path: Path):
        f = tmp_path / "blank_then_header.csv"
        f.write_text(
            ",,,,,\n"
            ",,,,,\n"
            "RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA,,,,,\n"
            " - 31 de enero de 2026,,,,,\n",
            encoding="utf-8",
        )
        hdr = parse_event_header_csv(f)
        assert hdr is not None
        assert hdr.valida_num == 1

    def test_empty_first_cell_in_category_row_check_returns_false(self):
        from app.services.race.csv_parser import _looks_like_category_row

        assert _looks_like_category_row(["", "", ""]) is False
        assert _looks_like_category_row([]) is False

    def test_empty_first_cell_in_table_header_check_returns_false(self):
        from app.services.race.csv_parser import _is_table_header_row

        assert _is_table_header_row([]) is False

    def test_header_with_unknown_month_returns_none(self, tmp_path: Path):
        """Mes inválido (``manolo``) — el regex no lo acepta, así que también ``None``."""
        f = tmp_path / "bad_month.csv"
        f.write_text(
            "RESULTADOS OFICIALES: I VALIDA COPA VALLE - SEVILLA,,,,,\n"
            " - 31 de manolo de 2026,,,,,\n",
            encoding="utf-8",
        )
        assert parse_event_header_csv(f) is None
