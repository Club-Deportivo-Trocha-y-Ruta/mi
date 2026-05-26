"""Tests del macro Jinja ``percentile_curves`` en
``templates/documents/pdf/charts/percentile_curves.svg.jinja``.

Render aislado del macro contra fixtures de ``chart``. Parseamos el HTML con
``defusedxml`` envuelto en un root para verificar:

- Render exitoso (XML well-formed)
- 5 paths para las curvas
- 1 polyline + N circles para el atleta
- Marker PHV opcional (line + texto "PHV")
- Sin SVG cuando enough_data=False
- Ausencia de tags <title>/<desc>/<metadata> y atributos data-*
- Sin nombre del atleta en el output (no se inyecta porque el macro no lo recibe)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from defusedxml import ElementTree as DET
from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "templates"


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html", "svg.jinja"]),
    )


def _chart_full(with_phv: bool = False) -> dict:
    """Chart fixture con enough_data=True y 3 puntos del atleta."""
    chart = {
        "enough_data": True,
        "reason_no_data": None,
        "indicator": "height",
        "indicator_label_es": "Talla (cm)",
        "sex": "M",
        "viewbox": "0 0 400 260",
        "width": 400,
        "height": 260,
        "x_axis": {"min_months": 120.0, "max_months": 180.0, "ticks": [132.0, 144.0, 156.0]},
        "y_axis": {"min": 130.0, "max": 170.0, "ticks": [130.0, 140.0, 150.0, 160.0, 170.0]},
        "curves": {
            "p3":  {"path": "M 42,200.0 L 100,180.0 L 200,160.0", "stroke_dasharray": "2,2", "color": "#e74c3c"},
            "p25": {"path": "M 42,180.0 L 100,160.0 L 200,140.0", "stroke_dasharray": "6,2", "color": "#f39c12"},
            "p50": {"path": "M 42,160.0 L 100,140.0 L 200,120.0", "stroke_dasharray": "",    "color": "#27ae60"},
            "p75": {"path": "M 42,140.0 L 100,120.0 L 200,100.0", "stroke_dasharray": "6,2", "color": "#f39c12"},
            "p97": {"path": "M 42,120.0 L 100,100.0 L 200, 80.0", "stroke_dasharray": "2,2", "color": "#e74c3c"},
        },
        "athlete": {
            "polyline_points": "60.0,200.0 120.0,180.0 180.0,160.0",
            "points": [
                {"x": 60.0, "y": 200.0},
                {"x": 120.0, "y": 180.0},
                {"x": 180.0, "y": 160.0},
            ],
        },
        "phv_marker": {"x": 150.0, "label": "PHV"} if with_phv else None,
    }
    return chart


def _render(env: Environment, chart: dict) -> str:
    """Renderiza el macro con un wrapper Jinja inline."""
    tpl = env.from_string(
        '{% from "documents/pdf/charts/percentile_curves.svg.jinja" import percentile_curves %}'
        "{{ percentile_curves(chart) }}"
    )
    return tpl.render(chart=chart)


# ---------------------------------------------------------------------------
# C.1 SVG válido y parseable
# ---------------------------------------------------------------------------


def test_renders_valid_svg(jinja_env: Environment):
    html = _render(jinja_env, _chart_full())
    # Envuelvo en root porque la salida es <div>...</div> + posiblemente texto
    wrapped = f"<root>{html}</root>"
    # defusedxml rechazaría DTDs/entities — perfecto
    DET.fromstring(wrapped)
    # Sanity: tiene un SVG dentro
    assert "<svg" in html


# ---------------------------------------------------------------------------
# C.2 5 curvas (paths)
# ---------------------------------------------------------------------------


def test_contains_5_curves(jinja_env: Environment):
    html = _render(jinja_env, _chart_full())
    # 5 <path d="..."> de las curvas (no hay otros paths en este macro)
    assert html.count("<path d=") == 5


# ---------------------------------------------------------------------------
# C.3 Polyline del atleta + 3 circles
# ---------------------------------------------------------------------------


def test_contains_athlete_polyline(jinja_env: Environment):
    html = _render(jinja_env, _chart_full())
    assert "<polyline points=" in html
    # Tres puntos del atleta → tres circles principales en el body del SVG.
    # La leyenda tiene 1 circle más, así que esperamos exactamente 4.
    assert html.count("<circle") == 4


# ---------------------------------------------------------------------------
# C.4 Marker PHV renderiza cuando está
# ---------------------------------------------------------------------------


def test_phv_marker_renders_when_present(jinja_env: Environment):
    html = _render(jinja_env, _chart_full(with_phv=True))
    # Línea punteada con dasharray 3,3 + texto "PHV"
    assert 'stroke-dasharray="3,3"' in html
    assert ">PHV<" in html


def test_phv_marker_absent_when_none(jinja_env: Environment):
    html = _render(jinja_env, _chart_full(with_phv=False))
    # No debe aparecer el texto "PHV" si no hay marker (la leyenda PHV tampoco)
    assert ">PHV<" not in html


# ---------------------------------------------------------------------------
# C.5 Sin SVG cuando enough_data=False
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason,expected_text",
    [
        ("insufficient_records", "al menos 2 mediciones"),
        ("age_out_of_range", "5-19 años"),
        ("missing_sex", "sexo no registrada"),
        ("growth_chart_unavailable", "no disponibles"),
    ],
)
def test_no_svg_when_insufficient_data(jinja_env: Environment, reason: str, expected_text: str):
    chart = {
        "enough_data": False,
        "reason_no_data": reason,
        "indicator": "height",
        "indicator_label_es": "Talla (cm)",
    }
    html = _render(jinja_env, chart)
    assert "<svg" not in html
    assert "<p" in html
    assert expected_text in html


# ---------------------------------------------------------------------------
# C.6 Sin tags de metadata ni data-*
# ---------------------------------------------------------------------------


def test_no_metadata_tags(jinja_env: Environment):
    html = _render(jinja_env, _chart_full(with_phv=True))
    forbidden_tags = ["<title", "<desc", "<metadata"]
    for tag in forbidden_tags:
        assert tag not in html, f"Tag prohibido '{tag}' presente en el SVG"
    # Atributos data-*
    assert "data-" not in html, "Atributos data-* prohibidos por privacidad"


# ---------------------------------------------------------------------------
# C.7 Sin nombre del atleta
# ---------------------------------------------------------------------------


def test_no_athlete_name_in_output(jinja_env: Environment):
    """El macro no acepta nombre como input — sanity check de que el render
    NO contiene strings tipo nombre."""
    html = _render(jinja_env, _chart_full(with_phv=True))
    suspicious_names = ["Juan", "Pérez", "Ficticio", "Atleta Test"]
    for name in suspicious_names:
        assert name not in html, f"Nombre '{name}' apareció en SVG"
