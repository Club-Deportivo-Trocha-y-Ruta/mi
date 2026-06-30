"""T023 — Hoja imprimible por sesión con diagrama de circuito de gymkhana.

Tests for ``backend/templates/documents/pdf/training_session_sheet.html``
and the render helper
``app.services.technique.session_sheet.render_training_session_sheet``.

All tests are synchronous Jinja template renders — no DB, no async, no
WeasyPrint.  This mirrors the pattern used in ``test_document_generator.py``
and avoids the need for an aiosqlite fixture for pure template assertions.

Test matrix:
  1. Session with a gymkhana exercise WITH layout_json:
       - Output HTML contains ``<svg`` with ``role="img"`` (FR-017).
       - Output does NOT contain any ``http://`` or ``https://`` URL in
         attribute values (print-clean, FR-005) — the only exception is
         the SVG XML namespace ``http://www.w3.org/2000/svg`` which appears
         as an ``xmlns`` attribute value, not a resource fetch.
  2. Session with exercise that has NO layout_json:
       - Renders without error.
       - Output does NOT contain ``<svg`` for that exercise (circuit section
         is omitted; layout_ascii shown instead if present).
  3. Spanish copy present: at least one known Spanish label appears in the
     rendered sheet (FR-020 — copy in español neutro).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# Jinja environment (mirrors DocumentGenerator._build_jinja_env)
# ---------------------------------------------------------------------------

_TEMPLATES_ROOT = Path(__file__).parents[1] / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )


def _render_session_sheet(**overrides) -> str:
    """Render training_session_sheet.html with default context + overrides."""
    env = _get_jinja_env()
    template = env.get_template("documents/pdf/training_session_sheet.html")

    ctx = {
        "session": {
            "technical_focus": "Curvas en berma y técnica de slalom",
            "scheduled_date": "2026-07-15",
            "objectives": "Mejorar la trayectoria en curvas abiertas.",
            "session_kind": "entrenamiento",
            "duration_min": 90,
            "location": "Pista La Cumbre",
        },
        "exercises": [],
        "club_name": "Trocha y Ruta",
        "generated_at": "2026-07-15 08:00 COT",
    }
    ctx.update(overrides)
    return template.render(**ctx)


# ---------------------------------------------------------------------------
# Minimal valid GymkhanaLayout (same structure as used in technique tests)
# ---------------------------------------------------------------------------

_LAYOUT_WITH_ELEMENTS = {
    "width": 100.0,
    "height": 60.0,
    "elements": [
        {"kind": "cone", "x": 20.0, "y": 30.0},
        {"kind": "cone", "x": 50.0, "y": 30.0},
        {"kind": "cone", "x": 80.0, "y": 30.0},
        {"kind": "line", "x": 10.0, "y": 30.0, "style": "dashed"},
        {"kind": "arrow", "x": 10.0, "y": 30.0, "rotation": 0.0},
    ],
}

_EXERCISE_WITH_LAYOUT = {
    "segment": "principal",
    "position": 0,
    "name": "Slalom de conos",
    "how_to": "Dilo: miramos siempre el cono siguiente.\nMuéstralo: el entrenador recorre el slalom.",
    "is_gymkhana": True,
    "layout_json": _LAYOUT_WITH_ELEMENTS,
    "layout_ascii": None,
    "layout_alt": "Fila de conos alternados a izquierda y derecha; el ciclista recorre en zigzag.",
}

_EXERCISE_WITHOUT_LAYOUT = {
    "segment": "calentamiento",
    "position": 0,
    "name": "Pie abajo",
    "how_to": "Todos pedalean lento dentro de un círculo de conos.",
    "is_gymkhana": False,
    "layout_json": None,
    "layout_ascii": None,
    "layout_alt": None,
}

_GYMKHANA_NO_LAYOUT_JSON = {
    "segment": "principal",
    "position": 1,
    "name": "Limbo en bici",
    "how_to": "Pasar por debajo de la estaca sin tocarla.",
    "is_gymkhana": True,
    "layout_json": None,
    "layout_ascii": "⊓  LIMBO en bici  ▮━━━━━━▮",
    "layout_alt": "Estaca horizontal a baja altura.",
}


# ===========================================================================
# Test 1 — gymkhana exercise WITH layout_json
# ===========================================================================


def test_layout_json_renders_svg_with_role_img():
    """Gymkhana exercise with layout_json produces an inline SVG with role='img'."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITH_LAYOUT])

    assert "<svg" in html, "Expected inline <svg> for exercise with layout_json"
    assert 'role="img"' in html, "SVG must have role='img' for accessibility (FR-017)"


def test_layout_json_svg_is_print_clean():
    """No external http:// or https:// resource URLs in the rendered HTML.

    The SVG xmlns attribute value 'http://www.w3.org/2000/svg' is a namespace
    identifier, not a resource fetch — it is explicitly excluded from the check
    (FR-005: print-clean, no external fetches).
    """
    html = _render_session_sheet(exercises=[_EXERCISE_WITH_LAYOUT])

    # Strip the known SVG namespace declaration so it does not trigger a false positive.
    cleaned = html.replace('xmlns="http://www.w3.org/2000/svg"', "")

    # No remaining http:// or https:// in attribute values.
    external_urls = re.findall(r'https?://[^\s"\'<>]+', cleaned)
    assert external_urls == [], (
        f"Rendered HTML must contain no external URLs for print-clean output; "
        f"found: {external_urls}"
    )


def test_layout_json_svg_contains_canvas_background():
    """The rendered SVG includes a canvas background rect (structural sanity check)."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITH_LAYOUT])

    # The macro renders a background rect with fill="#F8FAFC" (mirrors CircuitDiagram.tsx).
    assert 'fill="#F8FAFC"' in html, (
        "SVG canvas background (fill=#F8FAFC) must be present"
    )


# ===========================================================================
# Test 2 — exercise WITHOUT layout_json
# ===========================================================================


def test_no_layout_json_renders_without_error():
    """Session with exercise that has no layout_json renders without error."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITHOUT_LAYOUT])
    assert html  # Non-empty render is sufficient
    assert "Pie abajo" in html, "Exercise name must appear in the sheet"


def test_no_layout_json_does_not_include_svg_for_that_exercise():
    """Non-gymkhana exercise without layout_json must not produce an <svg> element."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITHOUT_LAYOUT])
    assert "<svg" not in html, (
        "No <svg> should be rendered for an exercise with layout_json=None and is_gymkhana=False"
    )


def test_gymkhana_no_layout_json_shows_ascii_croquis():
    """Gymkhana exercise without layout_json but with layout_ascii shows the ASCII croquis."""
    html = _render_session_sheet(exercises=[_GYMKHANA_NO_LAYOUT_JSON])

    assert "<svg" not in html, (
        "No <svg> should be rendered when layout_json is None, even for a gymkhana exercise"
    )
    # The ASCII layout should be shown inside a <pre> element.
    assert "LIMBO en bici" in html, (
        "ASCII croquis content must be visible when layout_json is absent"
    )


def test_gymkhana_no_layout_json_shows_circuit_header():
    """ASCII fallback section includes 'Circuito de gymkhana' caption."""
    html = _render_session_sheet(exercises=[_GYMKHANA_NO_LAYOUT_JSON])
    assert "Circuito de gymkhana" in html


# ===========================================================================
# Test 3 — Spanish copy present (FR-020)
# ===========================================================================


def test_spanish_copy_present_in_header():
    """At least one known Spanish label appears in the rendered sheet."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITH_LAYOUT])

    # Any of these strings must be present — they come from the template/macro copy.
    spanish_markers = [
        "Hoja de Sesión",
        "Entrenamiento",
        "Circuito de gymkhana",
        "Leyenda del circuito",
        "Parte principal",
        "Club Deportivo Trocha y Ruta",
    ]
    found = [m for m in spanish_markers if m in html]
    assert found, (
        f"No Spanish copy markers found in the sheet. Expected at least one of: "
        f"{spanish_markers}"
    )


def test_legend_labels_in_spanish():
    """Legend labels rendered by the circuit_diagram macro are in Spanish (FR-020)."""
    html = _render_session_sheet(exercises=[_EXERCISE_WITH_LAYOUT])

    # The macro renders legend labels matching LEGEND_LABELS in CircuitDiagram.tsx.
    # With cones, dashed line, and arrow in the layout we expect these labels:
    assert "Cono" in html, "Legend label 'Cono' must be present"
    assert "Trayecto libre" in html, "Legend label 'Trayecto libre' must be present (dashed line)"
    assert "Dirección de recorrido" in html, "Legend label 'Dirección de recorrido' must be present (arrow)"


# ===========================================================================
# Additional edge cases
# ===========================================================================


def test_empty_exercises_renders_placeholder():
    """Session with no exercises renders the empty-state placeholder."""
    html = _render_session_sheet(exercises=[])
    assert "no tiene ejercicios de técnica asignados" in html


def test_session_objectives_appear_when_set():
    """Session objectives field is rendered when provided."""
    html = _render_session_sheet(exercises=[])
    # Default ctx has objectives set.
    assert "Mejorar la trayectoria" in html


def test_session_objectives_omitted_when_none():
    """The objectives row is omitted when objectives is None/empty."""
    html = _render_session_sheet(
        session={
            "technical_focus": "Frenada técnica",
            "scheduled_date": "2026-07-15",
            "objectives": None,
            "session_kind": "entrenamiento",
            "duration_min": 60,
            "location": "Pista La Cumbre",
        },
        exercises=[],
    )
    assert "Objetivos" not in html


def test_multiple_exercises_all_present():
    """All exercises are rendered when the list has multiple items."""
    html = _render_session_sheet(
        exercises=[_EXERCISE_WITHOUT_LAYOUT, _GYMKHANA_NO_LAYOUT_JSON, _EXERCISE_WITH_LAYOUT]
    )
    assert "Pie abajo" in html
    assert "Limbo en bici" in html
    assert "Slalom de conos" in html


def test_segment_headers_appear_in_correct_order():
    """Segment section headers are present and ordered: calentamiento before principal."""
    html = _render_session_sheet(
        exercises=[_EXERCISE_WITHOUT_LAYOUT, _EXERCISE_WITH_LAYOUT]
    )
    idx_calentamiento = html.find("Calentamiento")
    idx_principal = html.find("Parte principal")
    assert idx_calentamiento != -1, "'Calentamiento' section header missing"
    assert idx_principal != -1, "'Parte principal' section header missing"
    assert idx_calentamiento < idx_principal, (
        "Calentamiento section must appear before Parte principal"
    )
