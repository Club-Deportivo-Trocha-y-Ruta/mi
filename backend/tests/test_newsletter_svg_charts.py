"""Tests R10 (specs/024-newsletter-audit-fixes) — clipping de labels SVG en
los tres macros de gráficos del boletín mensual individual
(``templates/documents/pdf/charts/{line_positions,gap_pct,points_accumulated}.svg.jinja``).

Los labels de valor se dibujan en offsets fijos (``cy-5``/``cy-6``) relativos
a cada punto; para puntos cerca del borde superior del área de dibujo
(posición 1, gap mínimo 0%, punto que toca el máximo del eje Y) ese offset
puede salir del ``viewBox`` (``y`` negativo). Cada macro debe clampear el
label con ``max(pad_top - 2, cy - N)`` — este archivo ejercita exactamente
ese borde con un punto en el extremo superior para cada gráfico y verifica:

  1. Ningún atributo ``y`` de ``<text>`` es negativo.
  2. Ningún atributo ``y`` de ``<text>`` excede el ``height`` declarado en
     el ``viewBox`` (o el ``height`` del macro).
  3. No aparecen ``<title>``/``<desc>``/``<metadata>`` (invariante de
     privacidad ya cubierto en ``test_newsletter_privacy.py`` para
     ``percentile_curves`` — aquí se extiende a los tres macros de
     evolución/temporada).

Renderizado aislado del macro contra un ``Environment`` Jinja2 mínimo (mismo
patrón que ``test_newsletter_privacy.py::TestPercentileCurvesPdfOnly``).
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates"

_TEXT_Y_RE = re.compile(r'<text\b[^>]*\by="(-?[\d.]+)"')
_FORBIDDEN_TAGS = ("<title", "<desc", "<metadata")


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html", "svg.jinja"]),
    )


def _render_macro(macro_file: str, macro_name: str, **kwargs) -> str:
    tpl = _env().from_string(
        '{%% from "documents/pdf/charts/%s" import %s %%}'
        "{{ %s(%s) }}"
        % (
            macro_file,
            macro_name,
            macro_name,
            ", ".join(f"{k}=kwargs['{k}']" for k in kwargs) if kwargs else "",
        )
    )
    return tpl.render(kwargs=kwargs)


def _assert_labels_in_viewbox(html: str, height: int) -> None:
    matches = _TEXT_Y_RE.findall(html)
    assert matches, "Debe haber al menos un <text y=...> en el SVG renderizado"
    for raw_y in matches:
        y = float(raw_y)
        assert y >= 0, f"<text> con y negativo ({y}) fuera del viewBox:\n{html}"
        assert y <= height, f"<text> con y={y} excede height={height} del viewBox:\n{html}"


def _assert_no_metadata_tags(html: str) -> None:
    for tag in _FORBIDDEN_TAGS:
        assert tag not in html, f"Tag '{tag}' prohibido por privacidad en SVG:\n{html[:300]}"
    assert "data-" not in html, "Atributos data-* prohibidos en SVG del boletín"


# ---------------------------------------------------------------------------
# line_positions — borde: posición 1 (mejor posible, top del área de dibujo)
# ---------------------------------------------------------------------------


class TestLinePositionsTopEdge:
    _HEIGHT = 160

    def _points_position_one(self) -> list[dict]:
        return [
            {"x": 1, "y": 1, "label": "V I"},
            {"x": 2, "y": 5, "label": "V II"},
        ]

    def test_no_negative_or_out_of_viewbox_text_y(self):
        html = _render_macro(
            "line_positions.svg.jinja",
            "line_positions",
            points=self._points_position_one(),
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)

    def test_no_metadata_tags(self):
        html = _render_macro(
            "line_positions.svg.jinja",
            "line_positions",
            points=self._points_position_one(),
            height=self._HEIGHT,
        )
        _assert_no_metadata_tags(html)

    def test_single_point_at_position_one(self):
        """Caso degenerado: un solo punto, justo en la posición 1."""
        html = _render_macro(
            "line_positions.svg.jinja",
            "line_positions",
            points=[{"x": 1, "y": 1, "label": "V I"}],
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)
        _assert_no_metadata_tags(html)


# ---------------------------------------------------------------------------
# gap_pct — borde: gap mínimo (0%, empatado/ganador del P1)
# ---------------------------------------------------------------------------


class TestGapPctTopEdge:
    _HEIGHT = 160

    def _points_min_gap(self) -> list[dict]:
        return [
            {"x": 1, "y": 0.0, "label": "V I"},
            {"x": 2, "y": 3.4, "label": "V II"},
        ]

    def test_no_negative_or_out_of_viewbox_text_y(self):
        html = _render_macro(
            "gap_pct.svg.jinja",
            "gap_pct",
            points=self._points_min_gap(),
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)

    def test_no_metadata_tags(self):
        html = _render_macro(
            "gap_pct.svg.jinja",
            "gap_pct",
            points=self._points_min_gap(),
            height=self._HEIGHT,
        )
        _assert_no_metadata_tags(html)

    def test_single_point_at_zero_gap(self):
        """Caso degenerado: un solo punto con gap 0% (ganó la válida)."""
        html = _render_macro(
            "gap_pct.svg.jinja",
            "gap_pct",
            points=[{"x": 1, "y": 0.0, "label": "V I"}],
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)
        _assert_no_metadata_tags(html)


# ---------------------------------------------------------------------------
# points_accumulated — borde: punto que toca el máximo del eje Y (tope)
# ---------------------------------------------------------------------------


class TestPointsAccumulatedTopEdge:
    _HEIGHT = 160

    def _points_at_max(self) -> list[dict]:
        # El último punto define max_y (100) — su cy queda pegado a pad_top.
        return [
            {"x": 1, "y": 40, "label": "V I"},
            {"x": 2, "y": 100, "label": "V II"},
        ]

    def test_no_negative_or_out_of_viewbox_text_y(self):
        html = _render_macro(
            "points_accumulated.svg.jinja",
            "points_accumulated",
            points=self._points_at_max(),
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)

    def test_no_metadata_tags(self):
        html = _render_macro(
            "points_accumulated.svg.jinja",
            "points_accumulated",
            points=self._points_at_max(),
            height=self._HEIGHT,
        )
        _assert_no_metadata_tags(html)

    def test_single_point_at_axis_max(self):
        """Caso degenerado: un solo punto, que por definición ES el máximo."""
        html = _render_macro(
            "points_accumulated.svg.jinja",
            "points_accumulated",
            points=[{"x": 1, "y": 50, "label": "V I"}],
            height=self._HEIGHT,
        )
        _assert_labels_in_viewbox(html, self._HEIGHT)
        _assert_no_metadata_tags(html)
