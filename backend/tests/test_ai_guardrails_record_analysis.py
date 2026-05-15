"""Tests específicos de los guardrails anti-diagnóstico para el use case
`anthropometric_record_analysis`."""

from __future__ import annotations

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import Guardrails


def test_diagnostic_word_replaced():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report("El diagnóstico es retraso puberal")
    # "diagnóstico" → "observación"; "retraso puberal" → eliminado
    assert "diagnóstico" not in out.text.lower()
    assert "retraso puberal" not in out.text.lower()
    assert "diagnostic_language" in out.violations
    assert "puberty_delay" in out.violations


def test_pathology_word_replaced():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report("Hay una patología en los datos")
    assert "patología" not in out.text.lower()
    assert "situación a revisar" in out.text


def test_red_s_term_removed():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report("Su hijo podría tener RED-S según los datos")
    assert "RED-S" not in out.text
    assert "red-s" not in out.text.lower()


def test_red_s_long_form_removed():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report(
        "Detectamos síndrome de deficiencia energética relativa"
    )
    assert "deficiencia energética" not in out.text.lower()


def test_energy_deficit_terms_removed():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report(
        "Su hijo presenta déficit energético y posible desnutrición"
    )
    assert "déficit" not in out.text.lower()
    assert "desnutrición" not in out.text.lower()


def test_abnormal_replaced():
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report("Esto es totalmente anormal")
    assert "anormal" not in out.text.lower()
    assert "fuera del rango esperado" in out.text


def test_too_many_violations_rejected():
    g = Guardrails(use_case="anthropometric_record_analysis")
    with pytest.raises(LLMSchemaError):
        g.scrub("patología y diagnóstico de RED-S con retraso puberal")


def test_phv_use_case_does_not_apply_record_rules():
    """El use case PHV global no aplica las reglas anti-diagnóstico extra."""
    g = Guardrails(use_case="phv_explainer")
    # "diagnóstico" no está en _RULES (suplementos/días/cadencia/calorías).
    # Sin las reglas extra del record analysis, no se toca.
    out = g.scrub_with_report("El diagnóstico es normal")
    assert "diagnóstico" in out.text.lower()


def test_no_use_case_means_only_global_rules():
    """Sin use_case explícito, solo reglas globales."""
    g = Guardrails()
    out = g.scrub_with_report("La patología es leve")
    # Sin use_case "anthropometric_record_analysis", "patología" no se reemplaza.
    assert "patología" in out.text.lower()


def test_global_rules_still_applied_in_record_analysis():
    """Suplementos siguen bloqueados también en record analysis."""
    g = Guardrails(use_case="anthropometric_record_analysis")
    out = g.scrub_with_report("Recomendamos creatina como suplemento")
    assert "creatina" not in out.text.lower()
