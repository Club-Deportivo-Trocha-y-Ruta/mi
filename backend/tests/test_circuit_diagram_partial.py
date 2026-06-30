"""T021 — Jinja partial `circuit_diagram.svg.jinja` (feature 019 Phase A — US2).

Verifies that the server-side inline-SVG circuit renderer:
  1. Produces well-formed inline SVG for a fixture GymkhanaLayout.
  2. Contains `role="img"` (WCAG 2.1 AA / FR-017).
  3. Contains `<title>` and `<desc>` elements (FR-017 text alternative).
  4. Has NO external `<image>` SVG elements and NO external HTTP src/href
     attribute values — print-clean, offline (FR-005).
  5. The SVG namespace xmlns URI (`http://www.w3.org/2000/svg`) is NOT
     counted as an external fetch (it is a namespace identifier, not a URL
     that browsers resolve at render time).
  6. Omits the diagram section (empty output) when layout is None — the
     calling template uses an `{% if layout %}` guard (US2 AS3 / FR-010).
  7. Empty-elements layout still renders SVG but suppresses the legend
     (matching React CircuitDiagram behavior).
  8. Caption paragraph is in español neutro (FR-020).

Template location: `backend/templates/documents/pdf/charts/circuit_diagram.svg.jinja`
Loaded via Jinja2 FileSystemLoader — same pattern as test_pdf_render_percentile_curves.py.

No DB session required.  No AsyncClient required.  Pure template/schema test.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from defusedxml import ElementTree as DET
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ── Jinja2 environment pointing at the project templates root ──────────────
#    Mirrors the pattern used in test_pdf_render_percentile_curves.py.
#    parents[2] from tests/test_circuit_diagram_partial.py → backend/
_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates"

# ── Fixture GymkhanaLayout dict (covers cone, line-dashed, arrow) ─────────
#    Fictitious coordinates; no minor PII anywhere.
#    Width=100, height=60 → R = clamp(min(100,60)*0.05, 2.5, 7) = clamp(3.0, 2.5, 7) = 3.0
_FIXTURE_LAYOUT: dict = {
    "width": 100.0,
    "height": 60.0,
    "elements": [
        {"kind": "cone",  "x": 20.0, "y": 30.0},
        {"kind": "line",  "x": 10.0, "y": 30.0, "style": "dashed"},
        {"kind": "arrow", "x":  5.0, "y": 30.0, "rotation": 0.0},
    ],
}

_ALT_TEXT = "Tres conos en fila con trayecto de inicio (ficticio)."

# ── Import-string pattern (re-used across tests) ───────────────────────────
_IMPORT_PREFIX = (
    '{%- from "documents/pdf/charts/circuit_diagram.svg.jinja"'
    " import circuit_diagram -%}"
)


# ---------------------------------------------------------------------------
# Module-scoped Jinja environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html", "svg.jinja"]),
    )


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def _render(env: Environment, layout: dict | None, alt_text: str = _ALT_TEXT) -> str:
    """Render the circuit_diagram macro with the given layout and alt text."""
    tpl = env.from_string(
        _IMPORT_PREFIX + "{{ circuit_diagram(layout, alt_text) }}"
    )
    return tpl.render(layout=layout, alt_text=alt_text)


def _render_with_guard(env: Environment, layout: dict | None) -> str:
    """Render with the `{% if layout %}` guard that the calling template uses.

    This is the US2 AS3 pattern: when layout is None, the section is omitted.
    """
    tpl = env.from_string(
        _IMPORT_PREFIX
        + "{%- if layout -%}{{ circuit_diagram(layout) }}{%- endif -%}"
    )
    return tpl.render(layout=layout)


# ---------------------------------------------------------------------------
# T021-1: Output is inline SVG
# ---------------------------------------------------------------------------


def test_renders_inline_svg(jinja_env: Environment) -> None:
    """The macro produces an `<svg>` element for a valid GymkhanaLayout."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "<svg" in html, "Expected inline <svg> element in output"


def test_svg_contains_viewbox(jinja_env: Environment) -> None:
    """The SVG element carries a viewBox attribute sized to layout dimensions."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    # viewBox should be "0 0 100.0 60.0" (canvas units)
    assert 'viewBox="0 0 100.0 60.0"' in html, (
        "SVG viewBox must match layout width×height (canvas units)"
    )


def test_svg_output_is_parseable_xml(jinja_env: Environment) -> None:
    """Wrap in a root element and parse with defusedxml — must be well-formed."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    # defusedxml rejects malicious DTDs/entities; parsing success = well-formed.
    DET.fromstring(f"<root>{html}</root>")


# ---------------------------------------------------------------------------
# T021-2: role="img" (FR-017 / WCAG 2.1 AA)
# ---------------------------------------------------------------------------


def test_svg_has_role_img(jinja_env: Environment) -> None:
    """Every diagram SVG must carry role=\"img\" (FR-017 accessibility)."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert 'role="img"' in html, (
        "SVG must carry role=\"img\" for WCAG 2.1 AA compliance (FR-017)"
    )


# ---------------------------------------------------------------------------
# T021-3: <title> + <desc> text alternative (FR-017)
# ---------------------------------------------------------------------------


def test_svg_has_title_element(jinja_env: Environment) -> None:
    """The SVG must contain a <title> element (screen-reader landmark)."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "<title>" in html, "SVG must include <title> for SR text alternative (FR-017)"


def test_svg_has_desc_element(jinja_env: Environment) -> None:
    """The SVG must contain a <desc> element carrying the alt text."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "<desc>" in html, "SVG must include <desc> carrying alt_text (FR-017)"


def test_svg_desc_contains_alt_text(jinja_env: Environment) -> None:
    """The <desc> element includes the provided alt_text string."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert _ALT_TEXT in html, (
        f"<desc> must include the alt_text passed to the macro. "
        f"Expected to find: {_ALT_TEXT!r}"
    )


def test_svg_uses_default_alt_text_when_none_given(jinja_env: Environment) -> None:
    """When alt_text is not passed, the macro falls back to the default Spanish string."""
    tpl = jinja_env.from_string(
        _IMPORT_PREFIX + "{{ circuit_diagram(layout) }}"
    )
    html = tpl.render(layout=_FIXTURE_LAYOUT)
    # Default from the macro signature
    assert "Diagrama del circuito de gymkhana" in html, (
        "Default alt_text must be the generic Spanish fallback"
    )


# ---------------------------------------------------------------------------
# T021-4: No external <image> elements and no external HTTP src/href (FR-005)
# ---------------------------------------------------------------------------


def test_no_external_image_element(jinja_env: Environment) -> None:
    """The SVG output must NOT contain an SVG <image> element (no external fetch).

    FR-005: print-clean, offline rendering — the diagram ships inline only.
    """
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "<image" not in html.lower(), (
        "SVG must not use <image> elements (FR-005: no external image fetch)"
    )


def test_no_external_http_src_or_href(jinja_env: Environment) -> None:
    """No attribute value contains an external http(s):// URL (FR-005).

    The SVG xmlns URI (`http://www.w3.org/2000/svg`) is a namespace identifier
    consumed by the parser, NOT a URL browsers resolve at render time; it is
    explicitly excluded from this assertion.
    """
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    # Strip the xmlns namespace URI, then check for remaining http(s):// refs
    without_xmlns = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    external_refs = re.findall(r'(?:href|src)=["\']https?://', without_xmlns, re.IGNORECASE)
    assert not external_refs, (
        f"No external href/src values allowed in the SVG output (FR-005). "
        f"Found: {external_refs}"
    )


def test_svg_xmlns_namespace_uri_not_treated_as_external_fetch(jinja_env: Environment) -> None:
    """Confirm the xmlns URI is present (valid SVG) but is not in href/src attrs.

    This explicitly documents that xmlns=http://www.w3.org/2000/svg is an
    inert namespace identifier, not a network request.
    """
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    # Namespace URI must be present (it is required for valid SVG).
    assert 'xmlns="http://www.w3.org/2000/svg"' in html, (
        "SVG namespace declaration must be present in the output"
    )
    # It must NOT appear as an href/src value.
    assert 'href="http://www.w3.org/2000/svg"' not in html
    assert 'src="http://www.w3.org/2000/svg"' not in html


# ---------------------------------------------------------------------------
# T021-5: Graceful omission when layout is None (US2 AS3 / FR-010)
# ---------------------------------------------------------------------------


def test_none_layout_produces_empty_output_with_guard(jinja_env: Environment) -> None:
    """When the calling template guards with `{% if layout %}`, a None layout
    produces empty output — no broken image, no empty box (US2 AS3 / FR-010).

    This mirrors the convention every template that embeds circuit_diagram.svg.jinja
    MUST follow: wrap the macro call in `{% if layout %}...{% endif %}`.
    """
    html = _render_with_guard(jinja_env, layout=None)
    assert html.strip() == "", (
        "A None layout must yield empty output when the caller uses the "
        "{% if layout %} guard (US2 AS3 / FR-010)"
    )


def test_none_layout_guard_produces_no_svg_tag(jinja_env: Environment) -> None:
    """No <svg> element is emitted when layout is None."""
    html = _render_with_guard(jinja_env, layout=None)
    assert "<svg" not in html


# ---------------------------------------------------------------------------
# T021-6: Empty-elements layout — SVG rendered, legend suppressed
# ---------------------------------------------------------------------------


def test_empty_elements_layout_renders_svg(jinja_env: Environment) -> None:
    """A GymkhanaLayout with elements=[] still renders the outer <svg> frame.

    An empty layout is valid (data-model.md §Validation rule 1).
    """
    empty_layout = {"width": 50.0, "height": 50.0, "elements": []}
    html = _render(jinja_env, empty_layout)
    assert "<svg" in html, "Empty layout must still render the SVG frame"


def test_empty_elements_layout_has_no_legend(jinja_env: Environment) -> None:
    """When elements=[], the legend section is suppressed (no legend keys to show).

    Matches the React CircuitDiagram behavior: legend only renders when at least
    one element kind is present.
    """
    empty_layout = {"width": 50.0, "height": 50.0, "elements": []}
    html = _render(jinja_env, empty_layout)
    assert "Leyenda del circuito" not in html, (
        "Legend must be suppressed for empty-elements layouts"
    )


def test_empty_elements_layout_role_img_still_present(jinja_env: Environment) -> None:
    """Even with no elements, the SVG frame must carry role=\"img\" (FR-017)."""
    empty_layout = {"width": 50.0, "height": 50.0, "elements": []}
    html = _render(jinja_env, empty_layout)
    assert 'role="img"' in html


# ---------------------------------------------------------------------------
# T021-7: Caption in español neutro (FR-020)
# ---------------------------------------------------------------------------


def test_caption_paragraph_in_spanish(jinja_env: Environment) -> None:
    """The section caption must be the Spanish string 'Circuito de gymkhana' (FR-020)."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "Circuito de gymkhana" in html, (
        "Section caption must read 'Circuito de gymkhana' (español neutro, FR-020)"
    )


def test_legend_title_in_spanish(jinja_env: Environment) -> None:
    """The legend header must be 'Leyenda del circuito' (español neutro, FR-020)."""
    html = _render(jinja_env, _FIXTURE_LAYOUT)
    assert "Leyenda del circuito" in html, (
        "Legend header must read 'Leyenda del circuito' (español neutro, FR-020)"
    )
