"""Tests del módulo ``app.services.race.pdf_parser``.

Estos tests usan los PDFs fixture de Válida IV (Cali, 17-may-2026). El
oracle (esperado) está inline en este archivo; ajustar aquí cuando cambie
el contrato del parser.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.models.race_result import ResultStatus
from app.services.race.normalizer import is_trocha_y_ruta, parse_time
from app.services.race.pdf_parser import (
    EventHeader,
    GeneralRow,
    ResultsRow,
    parse_event_header,
    parse_general_pdf,
    parse_results_pdf,
)

#: Conjunto canónico de bibs TyR observados en RESULTADOS V-IV (edge-cases §5).
ORACLE_TYR_BIBS_RESULTS: frozenset[int] = frozenset(
    {553, 718, 1257, 1259, 407, 426, 362, 906, 904, 10}
)

#: Conjunto canónico de bibs TyR únicos en GENERAL temporada (edge-cases §5.1).
ORACLE_TYR_BIBS_GENERAL: frozenset[int] = frozenset(
    {1414, 1410, 553, 808, 718, 1257, 1259, 407, 426, 362, 906, 904, 609, 611, 1319, 10}
)


# ===========================================================================
# parse_results_pdf — Válida IV
# ===========================================================================


class TestParseResultsPdf:
    def test_returns_26_categories(self, valida_iv_resultados_pdf: Path):
        """edge-cases §1: 26 categorías observadas en V-IV."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        assert len(out) == 26

    def test_total_rows_is_227(self, valida_iv_resultados_pdf: Path):
        """edge-cases §1: 227 finalistas totales V-IV."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        total = sum(len(rows) for rows in out.values())
        assert total == 227

    def test_teteros_sp_has_11_rows(self, valida_iv_resultados_pdf: Path):
        """edge-cases §1: TET_SP = 11 corredores."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        assert "TET_SP" in out
        assert len(out["TET_SP"]) == 11

    def test_rows_are_dataclass_instances(self, valida_iv_resultados_pdf: Path):
        out = parse_results_pdf(valida_iv_resultados_pdf)
        first_cat = next(iter(out))
        assert isinstance(out[first_cat][0], ResultsRow)

    def test_tyr_oracle_bibs_match(self, valida_iv_resultados_pdf: Path):
        """Los 10 corredores TyR del oracle deben aparecer (edge-cases §5)."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        detected = {
            int(r.bib)
            for rows in out.values()
            for r in rows
            if is_trocha_y_ruta(r.club)
        }
        assert detected == set(ORACLE_TYR_BIBS_RESULTS)

    def test_tyr_count_is_10(self, valida_iv_resultados_pdf: Path):
        """Exactamente 10 corredores TyR en RESULTADOS V-IV."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        tyr_count = sum(
            1 for rows in out.values() for r in rows if is_trocha_y_ruta(r.club)
        )
        assert tyr_count == 10

    def test_bib_424_matias_sabogal_anomalous_time(
        self, valida_iv_resultados_pdf: Path
    ):
        """edge-cases §4.2: bib 424 INF_A debe parsearse, tiempo capturado raw.
        ``0:04:33`` → 273_000 ms (anomalía documentada — el ingestor lo flag)."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        inf_a = out.get("INF_A", [])
        bib_424 = next((r for r in inf_a if int(r.bib) == 424), None)
        assert bib_424 is not None, "bib 424 debe estar en INF_A"
        assert bib_424.time_raw == "0:04:33"
        status, ms, laps = parse_time(bib_424.time_raw)
        assert status == ResultStatus.FINISHED
        assert ms == 273_000
        assert laps == 0

    def test_bib_426_dnf_status(self, valida_iv_resultados_pdf: Path):
        """Bib 426 Matías Montoya INF_A TyR — DNF con 1 punto."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        inf_a = out.get("INF_A", [])
        bib_426 = next((r for r in inf_a if int(r.bib) == 426), None)
        assert bib_426 is not None
        assert bib_426.time_raw == "DNF"
        assert bib_426.points == 1
        assert is_trocha_y_ruta(bib_426.club) is True
        status, ms, laps = parse_time(bib_426.time_raw)
        assert status == ResultStatus.DNF
        assert ms is None
        assert laps == 0

    def test_bib_10_juan_diego_minus_laps(self, valida_iv_resultados_pdf: Path):
        """Bib 10 Juan Diego Garcia ELITE TyR — (-1 VUELTA) con 9 puntos.

        Test crítico porque ``(-1 VUELTA)`` es el caso más sensible al regex
        (paréntesis + número + texto + paréntesis cerrado)."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        elite = out.get("ELITE_M", [])
        bib_10 = next((r for r in elite if int(r.bib) == 10), None)
        assert bib_10 is not None, "bib 10 debe estar en ELITE_M"
        assert bib_10.time_raw == "(-1 VUELTA)"
        assert bib_10.points == 9
        assert is_trocha_y_ruta(bib_10.club) is True
        status, ms, laps = parse_time(bib_10.time_raw)
        assert status == ResultStatus.MINUS_LAPS
        assert ms is None
        assert laps == 1

    def test_position_is_int(self, valida_iv_resultados_pdf: Path):
        """Todas las posiciones son enteros >= 1."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        for rows in out.values():
            for r in rows:
                assert isinstance(r.position, int)
                assert r.position >= 1

    def test_points_are_ints(self, valida_iv_resultados_pdf: Path):
        out = parse_results_pdf(valida_iv_resultados_pdf)
        for rows in out.values():
            for r in rows:
                assert isinstance(r.points, int)
                assert r.points >= 0

    def test_pdf_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_results_pdf(tmp_path / "nonexistent.pdf")

    def test_tyr_sum_of_points_is_200(self, valida_iv_resultados_pdf: Path):
        """edge-cases §5: suma puntos TyR V-IV = 200 (30+7+25+23+27+1+15+33+30+9)."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        tyr_points = sum(
            r.points for rows in out.values() for r in rows if is_trocha_y_ruta(r.club)
        )
        assert tyr_points == 200

    def test_tyr_status_breakdown(self, valida_iv_resultados_pdf: Path):
        """edge-cases §5: 8 FINISHED, 1 DNF, 1 MINUS_LAPS, 0 DSQ."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        from collections import Counter

        counts: Counter[ResultStatus] = Counter()
        for rows in out.values():
            for r in rows:
                if not is_trocha_y_ruta(r.club):
                    continue
                status, _, _ = parse_time(r.time_raw)
                counts[status] += 1
        assert counts[ResultStatus.FINISHED] == 8
        assert counts[ResultStatus.DNF] == 1
        assert counts[ResultStatus.MINUS_LAPS] == 1
        assert counts[ResultStatus.DSQ] == 0


# ===========================================================================
# parse_general_pdf — Válida IV acumulado temporada
# ===========================================================================


class TestParseGeneralPdf:
    def test_returns_26_categories(self, valida_iv_general_pdf: Path):
        """GENERAL también cubre las 26 categorías (edge-cases §3)."""
        out = parse_general_pdf(valida_iv_general_pdf)
        assert len(out) == 26

    def test_rows_are_dataclass_instances(self, valida_iv_general_pdf: Path):
        out = parse_general_pdf(valida_iv_general_pdf)
        first_cat = next(iter(out))
        row = out[first_cat][0]
        assert isinstance(row, GeneralRow)
        assert len(row.points_per_valida) == 4  # I, II, III, IV

    def test_tyr_unique_in_season_is_16(self, valida_iv_general_pdf: Path):
        """edge-cases §5.1: 16 riders TyR únicos en la temporada."""
        out = parse_general_pdf(valida_iv_general_pdf)
        detected = {
            int(r.bib)
            for rows in out.values()
            for r in rows
            if is_trocha_y_ruta(r.club)
        }
        assert detected == set(ORACLE_TYR_BIBS_GENERAL)
        assert len(detected) == 16

    def test_bib_1411_present_in_general(self, valida_iv_general_pdf: Path):
        """edge-cases §4.1: bib 1411 está en GENERAL aunque no corrió V-IV."""
        out = parse_general_pdf(valida_iv_general_pdf)
        all_bibs = {int(r.bib) for rows in out.values() for r in rows}
        assert 1411 in all_bibs

    def test_bib_1411_not_in_results(self, valida_iv_resultados_pdf: Path):
        """Verificación complementaria: bib 1411 NO debe estar en RESULTADOS."""
        out = parse_results_pdf(valida_iv_resultados_pdf)
        all_bibs = {int(r.bib) for rows in out.values() for r in rows}
        assert 1411 not in all_bibs

    def test_bib_1411_iv_points_zero(self, valida_iv_general_pdf: Path):
        """edge-cases §4.1: columna IV = 0 para bib 1411 (no participó V-IV)."""
        out = parse_general_pdf(valida_iv_general_pdf)
        target = None
        for rows in out.values():
            for r in rows:
                if int(r.bib) == 1411:
                    target = r
                    break
        assert target is not None
        # Índice 3 = válida IV
        assert target.points_per_valida[3] == 0
        # Total = 27 según oracle
        assert target.total_points == 27

    def test_total_equals_sum_of_validas_for_known_riders(
        self, valida_iv_general_pdf: Path
    ):
        """Sanity: el total debe igualar la suma de columnas I+II+III+IV."""
        out = parse_general_pdf(valida_iv_general_pdf)
        mismatches = []
        for cat, rows in out.items():
            for r in rows:
                if r.total_points != sum(r.points_per_valida):
                    mismatches.append((cat, r.bib, r.points_per_valida, r.total_points))
        # Toleramos algunas discrepancias por edge cases del PDF, pero no más de 5%
        assert len(mismatches) / max(sum(len(rs) for rs in out.values()), 1) < 0.05, (
            f"Demasiadas filas con total != suma: {mismatches[:5]}"
        )


# ===========================================================================
# parse_event_header — extracción de metadata del PDF
# ===========================================================================


class TestParseEventHeader:
    def test_valida_iv_header(self, valida_iv_resultados_pdf: Path):
        """Header esperado: ``VALIDA IV CALI MAYO 17 DE 2026`` → V=4, CALI, 2026-05-17."""
        hdr = parse_event_header(valida_iv_resultados_pdf)
        assert hdr is not None
        assert isinstance(hdr, EventHeader)
        assert hdr.valida_num == 4
        assert hdr.location == "CALI"
        assert hdr.event_date == date(2026, 5, 17)
        assert "VALIDA IV" in hdr.raw_text

    def test_general_pdf_also_has_header(self, valida_iv_general_pdf: Path):
        """El header se detecta también en el GENERAL (mismos 3 primeros renglones)."""
        hdr = parse_event_header(valida_iv_general_pdf)
        assert hdr is not None
        assert hdr.valida_num == 4
        assert hdr.event_date == date(2026, 5, 17)

    def test_missing_pdf_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_event_header(tmp_path / "ghost.pdf")
