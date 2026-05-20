"""Tests Pydantic ``app.schemas.race`` (Paso 7 — cobertura schemas).

Las pruebas existentes en ``test_ingestor.py`` instancian ``EventMeta`` con
valores válidos pero nunca ejercitan los validators de error. Aquí cubrimos:

- ``EventMeta.valida_num`` fuera de rango (8..98, 0, negativos).
- ``EventMeta.temperature_c`` fuera de [-10, 50].
- ``EventMeta.temperature_c`` ``None`` pasa el validator.
- ``MatchDecision.reason`` inválido vs whitelist.
- ``MatchDecision`` con datos válidos.
- ``IngestReport`` con campos por default vs custom.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.race_event import SurfaceCondition
from app.schemas.race import EventMeta, IngestReport, MatchDecision


# ===========================================================================
# EventMeta — valida_num
# ===========================================================================


class TestEventMetaValidaNum:
    def test_valida_num_99_is_cd(self):
        m = EventMeta(
            season=2026, valida_num=99, name="CD", event_date=date(2026, 6, 26),
            location="Ginebra",
        )
        assert m.valida_num == 99

    def test_valida_num_in_range_1_to_7(self):
        for n in range(1, 8):
            m = EventMeta(
                season=2026, valida_num=n, name=f"V-{n}",
                event_date=date(2026, 1, 1), location="X",
            )
            assert m.valida_num == n

    def test_valida_num_zero_rejected(self):
        # Pydantic Field(ge=1, le=99) atrapa primero
        with pytest.raises(ValidationError):
            EventMeta(
                season=2026, valida_num=0, name="X",
                event_date=date(2026, 1, 1), location="X",
            )

    def test_valida_num_8_rejected_by_validator(self):
        """``valida_num=8`` pasa el Field(le=99) pero falla el ``_check_valida_num``."""
        with pytest.raises(ValidationError) as exc:
            EventMeta(
                season=2026, valida_num=8, name="X",
                event_date=date(2026, 1, 1), location="X",
            )
        assert "valida_num inválido" in str(exc.value)

    def test_valida_num_100_rejected_by_field(self):
        """``valida_num=100`` excede ``le=99``."""
        with pytest.raises(ValidationError):
            EventMeta(
                season=2026, valida_num=100, name="X",
                event_date=date(2026, 1, 1), location="X",
            )

    def test_season_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            EventMeta(
                season=2019, valida_num=1, name="X",
                event_date=date(2019, 1, 1), location="X",
            )


# ===========================================================================
# EventMeta — temperature_c
# ===========================================================================


class TestEventMetaTemperature:
    def test_temperature_none_passes(self):
        m = EventMeta(
            season=2026, valida_num=1, name="X",
            event_date=date(2026, 1, 1), location="X",
            temperature_c=None,
        )
        assert m.temperature_c is None

    def test_temperature_in_range(self):
        for t in ("-10", "0", "27.5", "50"):
            m = EventMeta(
                season=2026, valida_num=1, name="X",
                event_date=date(2026, 1, 1), location="X",
                temperature_c=Decimal(t),
            )
            assert m.temperature_c == Decimal(t)

    def test_temperature_below_min_rejected(self):
        with pytest.raises(ValidationError) as exc:
            EventMeta(
                season=2026, valida_num=1, name="X",
                event_date=date(2026, 1, 1), location="X",
                temperature_c=Decimal("-10.1"),
            )
        assert "fuera de rango razonable" in str(exc.value)

    def test_temperature_above_max_rejected(self):
        with pytest.raises(ValidationError) as exc:
            EventMeta(
                season=2026, valida_num=1, name="X",
                event_date=date(2026, 1, 1), location="X",
                temperature_c=Decimal("50.1"),
            )
        assert "fuera de rango razonable" in str(exc.value)


# ===========================================================================
# EventMeta — defaults y campos opcionales
# ===========================================================================


class TestEventMetaOptionalFields:
    def test_minimal_valid_instance(self):
        m = EventMeta(
            season=2026, valida_num=1, name="X",
            event_date=date(2026, 1, 1), location="X",
        )
        assert m.copa_code == "copa_valle"
        assert m.climate is None
        assert m.surface_condition is None
        assert m.altitude_msnm is None
        assert m.weather_notes is None
        assert m.pdf_results_filename is None
        assert m.pdf_general_filename is None

    def test_altitude_msnm_range(self):
        m = EventMeta(
            season=2026, valida_num=1, name="X",
            event_date=date(2026, 1, 1), location="X",
            altitude_msnm=6000,
        )
        assert m.altitude_msnm == 6000

    def test_altitude_msnm_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            EventMeta(
                season=2026, valida_num=1, name="X",
                event_date=date(2026, 1, 1), location="X",
                altitude_msnm=6001,
            )

    def test_surface_condition_enum(self):
        m = EventMeta(
            season=2026, valida_num=1, name="X",
            event_date=date(2026, 1, 1), location="X",
            surface_condition=SurfaceCondition.barro,
        )
        assert m.surface_condition == SurfaceCondition.barro


# ===========================================================================
# MatchDecision
# ===========================================================================


class TestMatchDecision:
    def test_coach_confirmed(self):
        d = MatchDecision(bib="553", athlete_id=42, reason="coach_confirmed")
        assert d.athlete_id == 42

    def test_skipped_with_none(self):
        d = MatchDecision(bib="553", athlete_id=None, reason="skipped")
        assert d.athlete_id is None

    def test_new_athlete(self):
        d = MatchDecision(bib="553", reason="new_athlete")
        assert d.athlete_id is None

    def test_invalid_reason_rejected(self):
        with pytest.raises(ValidationError) as exc:
            MatchDecision(bib="553", reason="cualquier")
        assert "reason inválido" in str(exc.value)

    def test_empty_bib_rejected(self):
        with pytest.raises(ValidationError):
            MatchDecision(bib="", reason="skipped")

    def test_bib_too_long_rejected(self):
        with pytest.raises(ValidationError):
            MatchDecision(bib="A" * 11, reason="skipped")


# ===========================================================================
# IngestReport
# ===========================================================================


class TestIngestReport:
    def test_defaults(self):
        r = IngestReport(event_id=1, series_id=2)
        assert r.competitors_created == 0
        assert r.results_inserted == 0
        assert r.warnings == []

    def test_full_construction(self):
        r = IngestReport(
            event_id=10,
            series_id=20,
            competitors_created=5,
            competitors_updated=3,
            results_inserted=227,
            results_skipped=0,
            tyr_count=10,
            warnings=["w1", "w2"],
        )
        assert r.tyr_count == 10
        assert len(r.warnings) == 2

    def test_warnings_default_factory_isolated(self):
        r1 = IngestReport(event_id=1, series_id=2)
        r2 = IngestReport(event_id=3, series_id=4)
        r1.warnings.append("test")
        assert r2.warnings == []  # no shared mutable default
