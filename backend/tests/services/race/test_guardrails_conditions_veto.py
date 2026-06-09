"""US1 (feature 011): deterministic guardrail veto on fabricated conditions.

When the válida has no recorded conditions, any clima/pista/terreno mention in
the model output is fabrication → flagged and stripped.
"""
from __future__ import annotations

from app.services.ai.guardrails import Guardrails, check_conditions_fabrication


def test_flags_and_strips_climate_when_no_conditions():
    text = (
        "## Qué pasó en esta válida\n"
        "La deportista finalizó en la posición 2. El día estuvo soleado y la "
        "pista seca permitió buen ritmo."
    )
    g = Guardrails(use_case="race_analyst_v2", has_recorded_conditions=False)
    report = g.scrub_with_report(text)
    assert "conditions_fabricated" in report.violations
    assert "soleado" not in report.text
    assert "pista seca" not in report.text


def test_no_flag_when_conditions_recorded():
    text = (
        "## Qué pasó en esta válida\n"
        "La deportista finalizó en la posición 2 con clima nublado y pista húmeda."
    )
    g = Guardrails(use_case="race_analyst_v2", has_recorded_conditions=True)
    report = g.scrub_with_report(text)
    assert "conditions_fabricated" not in report.violations
    # Recorded conditions stay in the text.
    assert "nublado" in report.text.lower()


def test_check_conditions_fabrication_detects_terms():
    hits = check_conditions_fabrication("estuvo soleado, 24 °C y terreno seco")
    assert hits  # non-empty list of detected terms
