"""Tests del PromptRegistry."""

from __future__ import annotations

import pytest

from app.services.ai.prompts.registry import PromptRegistry


def _phv_context() -> dict:
    return {
        "age_group": "10-12",
        "age_decimal": 11.8,
        "sex": "M",
        "category": "Pre-juvenil A",
        "maturation_status": "Pre-PHV",
        "phv_offset": -1.5,
        "age_at_phv": 13.3,
        "mesocycle": 2,
    }


def test_system_prompt_loaded():
    r = PromptRegistry()
    sp = r.system_prompt()
    assert "Trocha y Ruta" in sp
    # Los 9 principios deben estar listados:
    for needle in (
        "Diversión primero",
        "Habilidades",
        "Edad biológica",
        "Máx 5 días",
        "suplementos",
        "conteo calórico",
        "Cadencia",
        "RPE",
        "Plan flexible",
    ):
        assert needle in sp, f"Falta principio: {needle}"


def test_system_prompt_is_cached():
    r = PromptRegistry()
    a = r.system_prompt()
    b = r.system_prompt()
    assert a is b


def test_get_spec_known_returns():
    r = PromptRegistry()
    spec = r.get_spec("phv_explainer")
    assert spec.template_id == "phv_explainer"
    assert "maturation_status" in spec.required_keys


def test_get_spec_unknown_raises():
    r = PromptRegistry()
    with pytest.raises(ValueError, match="phv_explainer"):
        r.get_spec("unknown_template")


def test_validate_context_ok():
    r = PromptRegistry()
    r.validate_context("phv_explainer", _phv_context())


def test_validate_context_missing_keys():
    r = PromptRegistry()
    with pytest.raises(ValueError, match="age_group"):
        r.validate_context("phv_explainer", {"sex": "M"})


def test_render_phv_template_produces_text():
    r = PromptRegistry()
    text = r.render("phv_explainer", _phv_context())
    assert "Pre-PHV" in text
    assert "10-12" in text
    assert "Pre-juvenil A" in text
    # No debe filtrar etiquetas de Jinja sin renderizar:
    assert "{{" not in text
    assert "{%" not in text


def test_render_undefined_var_fails_strict():
    """Una clave faltante en plantilla strict-undefined debe explotar al validar."""
    r = PromptRegistry()
    ctx = _phv_context()
    del ctx["age_group"]
    with pytest.raises(ValueError, match="age_group"):
        r.render("phv_explainer", ctx)
