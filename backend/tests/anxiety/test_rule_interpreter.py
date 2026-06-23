"""Unit tests for the rule-based interpretation fallback (US4, FR-014/015/016)."""
from __future__ import annotations

from app.services.anxiety.rule_interpreter import interpret

_SCHEMA_KEYS = {"resumen", "por_dimension", "estrategias", "mensaje_para_el_atleta", "banderas"}
_DIAGNOSTIC_TERMS = ("trastorno", "diagnóstic", "patológic", "enfermedad")


def test_schema_shape():
    out = interpret(
        instrument_type="csai2r",
        scores={"cognitive": 20.0, "somatic": 20.0, "selfconfidence": 25.0},
    )
    assert set(out) == _SCHEMA_KEYS
    assert set(out["por_dimension"]) == {"cognitiva", "somatica", "autoconfianza"}
    assert 2 <= len(out["estrategias"]) <= 3


def test_no_diagnostic_language():
    out = interpret(
        instrument_type="csai2r",
        scores={"cognitive": 38.0, "somatic": 39.0, "selfconfidence": 11.0},
    )
    blob = " ".join(
        [out["resumen"], out["mensaje_para_el_atleta"], *out["estrategias"], *out["banderas"]]
    ).lower()
    for term in _DIAGNOSTIC_TERMS:
        assert term not in blob


def test_high_anxiety_low_confidence_raises_flag():
    out = interpret(
        instrument_type="csai2r",
        scores={"cognitive": 38.0, "somatic": 39.0, "selfconfidence": 11.0},
    )
    assert out["banderas"], "expected an alert flag"
    assert "profesional" in out["banderas"][0].lower()


def test_favorable_profile_no_flag():
    out = interpret(
        instrument_type="csai2r",
        scores={"cognitive": 15.0, "somatic": 15.0, "selfconfidence": 35.0},
    )
    assert out["banderas"] == []


def test_no_baseline_is_noted():
    out = interpret(
        instrument_type="csai2r",
        scores={"cognitive": 20.0, "somatic": 20.0, "selfconfidence": 25.0},
        baseline=None,
    )
    assert "línea base" in out["por_dimension"]["cognitiva"].lower()


def test_sas2_selfconfidence_no_data():
    out = interpret(
        instrument_type="sas2",
        scores={"cognitive": 25.0, "somatic": 12.0, "selfconfidence": None},
    )
    assert "sin dato" in out["por_dimension"]["autoconfianza"].lower()
