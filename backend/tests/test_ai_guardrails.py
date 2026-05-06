"""Tests de Guardrails — enforce principios no negociables del CLAUDE.md."""

from __future__ import annotations

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import Guardrails


# ---------------------------------------------------------------------------
# Suplementos
# ---------------------------------------------------------------------------


def test_supplement_keyword_replaced():
    g = Guardrails()
    out = g.scrub("Recomendamos creatina antes del entrenamiento.")
    assert "creatina" not in out.lower()
    assert "comida real" in out


def test_protein_powder_replaced():
    g = Guardrails()
    out = g.scrub("Le sugiero proteína en polvo después del esfuerzo.")
    assert "proteína" not in out.lower() or "polvo" not in out.lower()


# ---------------------------------------------------------------------------
# Días por semana
# ---------------------------------------------------------------------------


def test_six_days_replaced():
    g = Guardrails()
    out = g.scrub("Entrena 6 días por semana para progresar.")
    assert "6 días" not in out
    assert "máximo 5 días" in out


def test_seven_days_replaced():
    g = Guardrails()
    out = g.scrub("El plan será 7 días a la semana.")
    assert "7 días" not in out
    assert "máximo 5 días" in out


def test_five_days_unchanged():
    g = Guardrails()
    text = "Entrena 5 días por semana, descansa los demás."
    out = g.scrub(text)
    # No debe activar la regla — máximo permitido.
    assert "5 días" in out


# ---------------------------------------------------------------------------
# Cadencia
# ---------------------------------------------------------------------------


def test_low_cadence_corrected():
    g = Guardrails()
    out = g.scrub("Pedalea a 55 rpm para fortalecer.")
    assert "55 rpm" not in out
    assert "≥60 rpm" in out


def test_high_cadence_unchanged():
    g = Guardrails()
    text = "Mantén una cadencia de 80 rpm."
    out = g.scrub(text)
    assert "80 rpm" in out


# ---------------------------------------------------------------------------
# Calorías con atleta
# ---------------------------------------------------------------------------


def test_calorie_counting_replaced():
    g = Guardrails()
    out = g.scrub("Pídele al atleta llevar un conteo de calorías diario.")
    assert "calorías" not in out.lower() or "conteo" not in out.lower()
    assert "variedad y calidad" in out


# ---------------------------------------------------------------------------
# Potenciómetro según grupo de edad
# ---------------------------------------------------------------------------


def test_powermeter_blocked_for_10_12():
    g = Guardrails(age_group="10-12")
    out = g.scrub("Usa el potenciómetro para medir vatios.")
    assert "potenciómetro" not in out.lower()
    assert "vatios" not in out.lower()


def test_powermeter_allowed_for_13_15():
    g = Guardrails(age_group="13-15")
    text = "Usa el potenciómetro con supervisión."
    out = g.scrub(text)
    assert "potenciómetro" in out.lower()


# ---------------------------------------------------------------------------
# Texto limpio pasa intacto
# ---------------------------------------------------------------------------


def test_clean_text_passes_through():
    g = Guardrails()
    text = (
        "Tu hijo está en Pre-PHV. Recomendamos sesiones técnicas y juego, "
        "5 días por semana con cadencia de 80 rpm."
    )
    out = g.scrub(text)
    assert out == text.strip()


# ---------------------------------------------------------------------------
# Demasiadas violaciones → rechazo
# ---------------------------------------------------------------------------


def test_too_many_violations_raises():
    g = Guardrails()
    text = (
        "Toma creatina y proteína en polvo. "
        "Entrena 6 días por semana a 50 rpm."
    )
    with pytest.raises(LLMSchemaError):
        g.scrub(text)


def test_report_lists_violations():
    g = Guardrails()
    report = g.scrub_with_report("Toma creatina hoy.")
    assert "suplements" in report.violations
    assert not report.rejected
