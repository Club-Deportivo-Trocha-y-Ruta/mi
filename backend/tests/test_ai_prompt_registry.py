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
        "arm_span_cm": 152.0,
    }


def test_system_prompt_loaded():
    r = PromptRegistry()
    sp = r.system_prompt()
    # Tras el rediseño de Ola 2, el system prompt define al LLM como
    # función analítica. Los principios pedagógicos del club (cero
    # suplementos, máx 5 días, ≥60 rpm, RPE primario, etc.) NO viven aquí:
    # están enforced por los guardrails de post-procesamiento. Por eso
    # solo validamos las reglas operativas de la capa IA.
    sp_lower = sp.lower()
    assert "función analítica" in sp_lower
    # Reglas operativas críticas de la capa IA:
    for needle in (
        "español",                # idioma
        "diagnósticos",           # bloqueo de etiquetas clínicas
        "comparaciones",          # bloqueo de comparativa poblacional
        "su hijo",                # bloqueo de nombres del menor
        "pediatra",               # derivación correcta de señales
    ):
        assert needle in sp_lower, f"Falta regla operativa: {needle}"


def test_system_prompt_excludes_pedagogical_rules():
    """Los 9 principios pedagógicos viven solo en `tone_guide.md`.

    Cualquier reaparición de esas frases en el system prompt rompe el
    contrato de Ola 2: el system debe ser corto, agnóstico al pedagogo y
    centrado en restricciones operativas de la capa IA.
    """
    r = PromptRegistry()
    sp_lower = r.system_prompt().lower()
    for forbidden in (
        "diversión primero",
        "potenciómetro",
        "rpm",
        "suplemento",  # cubre suplementos/suplemento
        "rpe",
        "conteo calórico",
        "habilidades",
    ):
        assert forbidden not in sp_lower, (
            f"El system prompt no debe mencionar '{forbidden}'; "
            f"esa regla está enforced por guardrails y documentada en tone_guide.md."
        )


def test_tone_guide_exists_but_is_not_loaded_as_system_prompt():
    """`tone_guide.md` debe existir como referencia humana pero NO ser cargado.

    El guía de tono mantiene los 9 principios pedagógicos históricos como
    documentación de auditoría humana. No se inyecta en ningún prompt; los
    principios están enforced por guardrails.
    """
    from pathlib import Path

    tone_guide = (
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "ai" / "prompts" / "tone_guide.md"
    )
    assert tone_guide.exists(), "tone_guide.md debe existir como referencia humana"

    content = tone_guide.read_text(encoding="utf-8")
    # Confirma que el tone guide contiene los principios pedagógicos
    assert "Diversión primero" in content
    assert "Cero suplementos" in content

    # Pero el system prompt cargado NO debe incluirlos
    r = PromptRegistry()
    sp = r.system_prompt()
    assert "Diversión primero" not in sp
    assert "Cero suplementos" not in sp


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
