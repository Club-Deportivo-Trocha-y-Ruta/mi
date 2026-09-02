"""Tests de ``_REC_BULLET_RE`` / ``_parse_recommendations`` (feature 037, T101).

Regresión: el bug de spec.md §problem 6 — bullets que terminan con "." o
";" (tras el paréntesis o tras las citas) eran rechazados en producción →
``recommendations_json = []`` en TODOS los insights persistidos. También
cubre los campos opcionales nuevos ``horizonte=`` y ``catálogo=`` dentro
del paréntesis (feature 037, formato de acciones catalog-linked de v3).
"""
from __future__ import annotations

from app.services.race.agents.analyst import _parse_recommendations


def test_bullet_with_trailing_period_parses():
    section = (
        "- Trabajar cadencia 80-90 rpm en plano 2x/semana "
        "(categoría=technique, prioridad=high)."
    )
    out = _parse_recommendations(section)
    assert len(out) == 1
    assert out[0].category.value == "technique"
    assert out[0].priority.value == "high"


def test_bullet_with_trailing_semicolon_parses():
    section = "- Volumen semanal estable (categoría=volume, prioridad=med);"
    out = _parse_recommendations(section)
    assert len(out) == 1


def test_bullet_with_citation_and_trailing_period_parses():
    section = "- Reco con cita (categoría=recovery, prioridad=low) [1]."
    out = _parse_recommendations(section)
    assert len(out) == 1


def test_bullet_with_horizonte_field_parses():
    section = (
        "- Bloque de fuerza funcional 2x/semana "
        "(categoría=volume, prioridad=high, horizonte=próximas 4 semanas)"
    )
    out = _parse_recommendations(section)
    assert len(out) == 1
    assert out[0].category.value == "volume"


def test_bullet_with_catalogo_field_parses():
    section = (
        "- Ejercicio de técnica en curvas "
        "(categoría=technique, prioridad=med, catálogo=TECH-CURVES-01)"
    )
    out = _parse_recommendations(section)
    assert len(out) == 1


def test_bullet_with_horizonte_and_catalogo_and_trailing_period_parses():
    section = (
        "- Intervalos aeróbicos suaves "
        "(categoría=volume, prioridad=high, horizonte=8 semanas, "
        "catálogo=INT-AER-02)."
    )
    out = _parse_recommendations(section)
    assert len(out) == 1


def test_bullet_without_terminator_still_parses():
    """No regression: el formato clásico (sin punto/coma final) sigue OK."""
    section = "- Reco válida (categoría=recovery, prioridad=low) [1]"
    out = _parse_recommendations(section)
    assert len(out) == 1


def test_bullet_with_invalid_category_still_dropped():
    section = "- Reco con categoría inválida (categoría=metaverse, prioridad=high)."
    out = _parse_recommendations(section)
    assert out == []
