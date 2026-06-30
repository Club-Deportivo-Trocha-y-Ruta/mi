"""T020 — Cross-renderer STRUCTURAL equivalence (feature 019 Phase A).

EQUIVALENCE CRITERION (FR-006)
──────────────────────────────
The React `<CircuitDiagram>` component (TypeScript, not runnable from Python) and
the Jinja `circuit_diagram.svg.jinja` partial share the *same* `GymkhanaLayout`
JSON schema as their only input.  Both renderers are required by the spec to
produce "visually equivalent" output for the same input (FR-006).

Because we cannot execute the TypeScript renderer from a pytest process, this
file treats the Jinja partial as the **authoritative contract proxy** and asserts
the following structural invariants, which are also the invariants that the React
component guarantees:

  1. **Element count**: the main SVG body contains exactly one
     `<g transform="translate(x, y)...">` group per element in
     `layout.elements`, in the same order and at the same (x, y) position.
     This is the "one primitive per element" contract shared by both renderers.

  2. **Kind→shape mapping**: each element kind renders to a specific SVG primitive —
       cone  → `<polygon ...>`       (amber triangle)
       line  → `<line ...>`          (dashed or solid — FR-017 shape cue)
       gate  → two `<rect ...>`      (sky-colored posts + crossbar)
       mine  → `<circle ...>` + X lines   (rose filled + cross)
       beam  → `<rect ...>` + hatch lines  (amber-dark bar)
       ring  → `<circle fill="none" ...>` (violet open circle)
       arrow → `<polygon ...>`       (emerald chevron)
     Both renderers must produce the same primitive type for the same kind.

  3. **Legend completeness**: for every distinct `kind` (and `line` style) present
     in `layout.elements`, a corresponding Spanish legend label must appear in the
     output (legend keys built by `buildLegendKeys()` in React /
     `legend_ns.seen` in Jinja are equivalent).

  4. **Order preservation**: the translate positions in the SVG body appear in the
     SAME order as `layout.elements` (declaration order → paint order; later
     elements are on top).

  5. **Unknown kinds silently skipped**: an unrecognised kind is not rendered and
     does not add a `<g transform="translate(...)">` to the main SVG.

These invariants are intentionally NOT "byte-identical output" — font metrics,
minor numeric-precision differences, and attribute ordering can legitimately
differ between the Jinja and React renderers without violating the equivalence
contract.  The contract is: same elements / same kinds / same positions / same
order / same legend coverage.

No DB session, no AsyncClient, no network required.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from defusedxml import ElementTree as DET
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.technique import GymkhanaLayout

# ── Jinja2 environment ────────────────────────────────────────────────────
_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates"

_IMPORT_PREFIX = (
    '{%- from "documents/pdf/charts/circuit_diagram.svg.jinja"'
    " import circuit_diagram -%}"
)


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html", "svg.jinja"]),
    )


# ── Fixture layouts ───────────────────────────────────────────────────────

# Full vocabulary fixture: one element of each kind (line appears twice —
# once dashed, once solid — to exercise both style variants).
# Fictitious coordinates; no minor PII.
# Width=100, height=60 → R = clamp(60*0.05, 2.5, 7) = clamp(3.0, 2.5, 7) = 3.0
_FULL_LAYOUT: dict[str, Any] = {
    "width": 100.0,
    "height": 60.0,
    "elements": [
        {"kind": "cone",  "x": 10.0, "y": 10.0},          # index 0
        {"kind": "line",  "x": 20.0, "y": 10.0, "style": "dashed"},  # index 1
        {"kind": "line",  "x": 30.0, "y": 10.0, "style": "solid"},   # index 2
        {"kind": "gate",  "x": 40.0, "y": 10.0},          # index 3
        {"kind": "mine",  "x": 50.0, "y": 10.0},          # index 4
        {"kind": "beam",  "x": 60.0, "y": 10.0},          # index 5
        {"kind": "ring",  "x": 70.0, "y": 10.0},          # index 6
        {"kind": "arrow", "x": 80.0, "y": 10.0, "rotation": 90.0},  # index 7
    ],
}

# Single-kind fixtures for focused shape assertions.
_CONE_ONLY    = {"width": 50.0, "height": 50.0, "elements": [{"kind": "cone",  "x": 25.0, "y": 25.0}]}
_LINE_DASHED  = {"width": 50.0, "height": 50.0, "elements": [{"kind": "line",  "x": 25.0, "y": 25.0, "style": "dashed"}]}
_LINE_SOLID   = {"width": 50.0, "height": 50.0, "elements": [{"kind": "line",  "x": 25.0, "y": 25.0, "style": "solid"}]}
_GATE_ONLY    = {"width": 50.0, "height": 50.0, "elements": [{"kind": "gate",  "x": 25.0, "y": 25.0}]}
_MINE_ONLY    = {"width": 50.0, "height": 50.0, "elements": [{"kind": "mine",  "x": 25.0, "y": 25.0}]}
_BEAM_ONLY    = {"width": 50.0, "height": 50.0, "elements": [{"kind": "beam",  "x": 25.0, "y": 25.0}]}
_RING_ONLY    = {"width": 50.0, "height": 50.0, "elements": [{"kind": "ring",  "x": 25.0, "y": 25.0}]}
_ARROW_ONLY   = {"width": 50.0, "height": 50.0, "elements": [{"kind": "arrow", "x": 25.0, "y": 25.0, "rotation": 45.0}]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render(env: Environment, layout: dict, alt_text: str = "Fixture alt text") -> str:
    tpl = env.from_string(_IMPORT_PREFIX + "{{ circuit_diagram(layout, alt_text) }}")
    return tpl.render(layout=layout, alt_text=alt_text)


def _main_svg(html: str) -> str:
    """Extract the main SVG element (the first <svg> block).

    The legend swatches are in separate nested <svg> tags; we want only the
    main diagram SVG for assertions about element groups.
    """
    start = html.index('<svg xmlns')
    end   = html.index('</svg>', start) + len('</svg>')
    return html[start:end]


def _translate_positions(main_svg: str) -> list[tuple[str, str]]:
    """Return (x, y) string pairs from all transform=\"translate(x, y)...\" in main_svg."""
    return re.findall(r'transform="translate\(([\d.]+),\s*([\d.]+)\)', main_svg)


def _validate_layout_schema(layout: dict) -> GymkhanaLayout:
    """Run Pydantic validation on the layout dict (same path as the FastAPI server)."""
    return GymkhanaLayout.model_validate(layout)


# ---------------------------------------------------------------------------
# 0. Schema validation: fixture is accepted by Pydantic (server contract)
# ---------------------------------------------------------------------------


def test_fixture_layout_is_valid_pydantic_schema() -> None:
    """The full-vocabulary fixture must pass GymkhanaLayout Pydantic validation.

    This confirms the fixture is a valid contract input for both renderers —
    any renderer can assume a schema-valid layout.
    """
    layout = _validate_layout_schema(_FULL_LAYOUT)
    assert layout.width == 100.0
    assert layout.height == 60.0
    assert len(layout.elements) == 8


# ---------------------------------------------------------------------------
# 1. Element count — one translate group per element (equivalence invariant #1)
# ---------------------------------------------------------------------------


def test_element_count_equals_translate_count_in_main_svg(jinja_env: Environment) -> None:
    """STRUCTURAL EQUIVALENCE: for each element in layout.elements, the main SVG
    body contains exactly one `<g transform="translate(x, y)">` group.

    This is the primary "one primitive per element" invariant shared by both the
    Jinja renderer and the React CircuitDiagram component.
    """
    html = _render(jinja_env, _FULL_LAYOUT)
    main = _main_svg(html)
    positions = _translate_positions(main)
    assert len(positions) == len(_FULL_LAYOUT["elements"]), (
        f"Expected exactly {len(_FULL_LAYOUT['elements'])} translate groups in the "
        f"main SVG (one per element), found {len(positions)}: {positions}"
    )


def test_single_element_produces_one_group(jinja_env: Environment) -> None:
    """A layout with exactly one element produces exactly one translate group."""
    html = _render(jinja_env, _CONE_ONLY)
    main = _main_svg(html)
    assert len(_translate_positions(main)) == 1


def test_empty_elements_produces_no_groups(jinja_env: Environment) -> None:
    """Empty layout → zero translate groups in the main SVG.

    The SVG frame itself is rendered (background + border rects) but the
    element layer is empty.
    """
    empty = {"width": 50.0, "height": 50.0, "elements": []}
    html = _render(jinja_env, empty)
    main = _main_svg(html)
    assert _translate_positions(main) == []


# ---------------------------------------------------------------------------
# 2. Element positions — translate coords match layout.elements (invariant #1 cont.)
# ---------------------------------------------------------------------------


def test_translate_positions_match_element_xy(jinja_env: Environment) -> None:
    """Every (x, y) in the translate groups corresponds to an element in the
    fixture layout (coord matching, not just count).

    This verifies the position-preservation contract shared by both renderers.
    """
    html = _render(jinja_env, _FULL_LAYOUT)
    main = _main_svg(html)
    positions = _translate_positions(main)
    # Build expected (x, y) string pairs from the fixture
    expected = [(str(el["x"]), str(el["y"])) for el in _FULL_LAYOUT["elements"]]
    assert positions == expected, (
        f"Translate positions must match element x/y in declaration order.\n"
        f"Expected: {expected}\n"
        f"Got:      {positions}"
    )


# ---------------------------------------------------------------------------
# 3. Order preservation — translate positions appear in declaration order (inv. #4)
# ---------------------------------------------------------------------------


def test_element_order_preserved_in_svg_output(jinja_env: Environment) -> None:
    """Translate groups appear in the same order as layout.elements (paint order).

    Both renderers iterate elements in declaration order so later elements
    are painted on top of earlier ones.
    """
    html = _render(jinja_env, _FULL_LAYOUT)
    main = _main_svg(html)
    positions = _translate_positions(main)
    # First element is cone at x=10; last is arrow at x=80.
    assert positions[0] == ("10.0", "10.0"), "Cone (element 0) must be first"
    assert positions[-1] == ("80.0", "10.0"), "Arrow (element 7) must be last"
    # x values must be strictly increasing in this fixture
    x_values = [float(p[0]) for p in positions]
    assert x_values == sorted(x_values), "Order must match declaration order (ascending x here)"


# ---------------------------------------------------------------------------
# 4. Kind → shape mapping (equivalence invariant #2)
# ---------------------------------------------------------------------------


def test_kind_cone_renders_as_polygon(jinja_env: Environment) -> None:
    """cone → amber triangle polygon (matches ConeShape in CircuitDiagram.tsx)."""
    html = _render(jinja_env, _CONE_ONLY)
    main = _main_svg(html)
    assert "<polygon" in main, "cone must render as <polygon>"
    assert "#F59E0B" in main, "cone fill must be amber (#F59E0B) — matches React"


def test_kind_line_dashed_renders_with_dasharray(jinja_env: Environment) -> None:
    """line (style=dashed) → dashed stroke (stroke-dasharray present).

    The dashed pattern is the SHAPE cue distinguishing free/guide path from
    technical/precision path (FR-017 — shape, not color alone).
    Matches LineShape in CircuitDiagram.tsx when style='dashed'.
    """
    html = _render(jinja_env, _LINE_DASHED)
    main = _main_svg(html)
    assert "<line" in main, "line element must render as <line>"
    assert "stroke-dasharray" in main, (
        "dashed line must carry stroke-dasharray (shape cue, FR-017)"
    )


def test_kind_line_solid_renders_without_dasharray_in_element_group(jinja_env: Environment) -> None:
    """line (style=solid) → solid stroke; stroke-dasharray must NOT appear in the
    main SVG element group (it may appear in the dashed legend swatch elsewhere,
    so we restrict the assertion to the main SVG body only).

    Matches LineShape in CircuitDiagram.tsx when style='solid'.
    """
    html = _render(jinja_env, _LINE_SOLID)
    main = _main_svg(html)
    assert "<line" in main, "solid line must render as <line>"
    # The element group for a solid line must NOT have stroke-dasharray
    assert "stroke-dasharray" not in main, (
        "solid line must NOT carry stroke-dasharray in the main SVG element group"
    )


def test_kind_gate_renders_two_post_rects(jinja_env: Environment) -> None:
    """gate → two sky-colored post rects + crossbar (matches GateShape in React).

    Both posts are <rect>; we count only the rects in the main SVG (excluding
    the background and border rects by colour).
    """
    html = _render(jinja_env, _GATE_ONLY)
    main = _main_svg(html)
    assert "#0EA5E9" in main, "gate posts must be sky blue (#0EA5E9) — matches React"
    # The main SVG contains: background rect + border rect + 2 post rects = 4 rects total
    rect_count = main.count("<rect")
    assert rect_count >= 4, (
        f"gate layout must have at least 4 <rect> in main SVG (bg + border + 2 posts); "
        f"found {rect_count}"
    )


def test_kind_mine_renders_as_filled_circle_with_cross(jinja_env: Environment) -> None:
    """mine → rose filled circle + X cross (matches MineShape in React, FR-017 shape cue)."""
    html = _render(jinja_env, _MINE_ONLY)
    main = _main_svg(html)
    assert "<circle" in main, "mine must render as <circle>"
    assert "#F43F5E" in main, "mine circle fill must be rose (#F43F5E) — matches React"
    # X cross: two <line> elements with white stroke inside the mine group
    assert "#FFFFFF" in main, "mine X-cross must use white stroke (#FFFFFF)"


def test_kind_beam_renders_as_rect_with_hatch_lines(jinja_env: Environment) -> None:
    """beam → wide amber-dark rect + 5 diagonal hatch lines (matches BeamShape in React).

    The flat-bar + hatch pattern is the SHAPE cue (FR-017, not color alone).
    """
    html = _render(jinja_env, _BEAM_ONLY)
    main = _main_svg(html)
    assert "#D97706" in main, "beam rect fill must be amber (#D97706) — matches React"
    # 5 hatch lines are rendered; with background + border + beam-rect in main SVG
    # we expect at least 5 <line> elements in the main SVG
    line_count = main.count("<line")
    assert line_count >= 5, (
        f"beam must render with at least 5 hatch lines; found {line_count} <line> in main SVG"
    )


def test_kind_ring_renders_as_open_circle(jinja_env: Environment) -> None:
    """ring → open violet circle (fill=\"none\"), matches RingShape in React.

    The open-circle shape distinguishes ring from mine (filled+cross) per FR-017.
    """
    html = _render(jinja_env, _RING_ONLY)
    main = _main_svg(html)
    assert "<circle" in main, "ring must render as <circle>"
    assert "fill=\"none\"" in main, "ring must be an open circle (fill='none')"
    assert "#7C3AED" in main, "ring stroke must be violet (#7C3AED) — matches React"


def test_kind_arrow_renders_as_polygon(jinja_env: Environment) -> None:
    """arrow → emerald chevron polygon (matches ArrowShape in React)."""
    html = _render(jinja_env, _ARROW_ONLY)
    main = _main_svg(html)
    assert "<polygon" in main, "arrow must render as <polygon>"
    assert "#10B981" in main, "arrow fill must be emerald (#10B981) — matches React"


def test_rotation_appears_in_transform_attribute(jinja_env: Environment) -> None:
    """When rotation is set, the element group carries rotate(rot) in its transform.

    Both renderers apply `transform="translate(x, y) rotate(rot)"` consistently.
    """
    html = _render(jinja_env, _ARROW_ONLY)
    main = _main_svg(html)
    # _ARROW_ONLY has rotation=45.0
    assert "rotate(45.0)" in main, (
        "Element group must include rotate(45.0) in the transform attribute "
        "when rotation=45.0 is specified"
    )


# ---------------------------------------------------------------------------
# 5. Legend completeness (equivalence invariant #3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind, expected_label", [
    ("cone",  "Cono"),
    ("gate",  "Puerta"),
    ("mine",  "Mina"),
    ("beam",  "Equilibrio"),
    ("ring",  "Círculo de la muerte"),
    ("arrow", "Dirección de recorrido"),
])
def test_legend_label_present_for_kind(jinja_env: Environment, kind: str, expected_label: str) -> None:
    """For each element kind present in the layout, the Spanish legend label must
    appear in the output.

    Legend labels are controlled (español neutro, FR-004/FR-020) and must match
    the LEGEND_LABELS constant in CircuitDiagram.tsx — that is the equivalence
    contract: same labels, same kinds.
    """
    single_layout = {"width": 50.0, "height": 50.0, "elements": [{"kind": kind, "x": 25.0, "y": 25.0}]}
    html = _render(jinja_env, single_layout)
    assert expected_label in html, (
        f"Spanish legend label '{expected_label}' must appear for kind='{kind}'"
    )


def test_legend_line_dashed_label(jinja_env: Environment) -> None:
    """Dashed line → 'Trayecto libre' in the legend (FR-004 / FR-020)."""
    html = _render(jinja_env, _LINE_DASHED)
    assert "Trayecto libre" in html, (
        "Legend must show 'Trayecto libre' for a dashed line element"
    )


def test_legend_line_solid_label(jinja_env: Environment) -> None:
    """Solid line → 'Trayecto técnico' in the legend (FR-004 / FR-020)."""
    html = _render(jinja_env, _LINE_SOLID)
    assert "Trayecto técnico" in html, (
        "Legend must show 'Trayecto técnico' for a solid line element"
    )


def test_legend_deduplicates_kinds(jinja_env: Environment) -> None:
    """If the same kind appears multiple times, its legend entry appears only once.

    Both renderers deduplicate legend entries (React `buildLegendKeys()` tracks
    seen keys; Jinja `legend_ns.seen` does the same).
    """
    two_cones = {
        "width": 50.0,
        "height": 50.0,
        "elements": [
            {"kind": "cone", "x": 10.0, "y": 25.0},
            {"kind": "cone", "x": 40.0, "y": 25.0},
        ],
    }
    html = _render(jinja_env, two_cones)
    # "Cono" should appear exactly once in the legend (one deduped entry)
    assert html.count("Cono") == 1, (
        "Legend must deduplicate: 'Cono' should appear exactly once even with two cone elements"
    )


def test_full_vocabulary_produces_all_legend_labels(jinja_env: Environment) -> None:
    """The full-vocabulary fixture (8 elements, 8 distinct legend keys) must
    produce all 8 Spanish legend labels.

    This is the ultimate legend-completeness assertion for the equivalence contract.
    """
    expected_labels = [
        "Cono",
        "Trayecto libre",
        "Trayecto técnico",
        "Puerta",
        "Mina",
        "Equilibrio",
        "Círculo de la muerte",
        "Dirección de recorrido",
    ]
    html = _render(jinja_env, _FULL_LAYOUT)
    for label in expected_labels:
        assert label in html, (
            f"Legend must include Spanish label '{label}' for the full-vocabulary layout"
        )


# ---------------------------------------------------------------------------
# 6. Unknown kinds silently skipped (equivalence invariant #5)
# ---------------------------------------------------------------------------


def test_unknown_kind_does_not_add_translate_group(jinja_env: Environment) -> None:
    """An element with an unknown kind is silently skipped in the Jinja renderer.

    The Jinja template has a defensive `{%- if el.kind == 'cone' -%}...{%- endif -%}`
    chain — any unmatched kind emits no SVG and no `<g transform="translate">`.

    Note: the Pydantic schema rejects unknown kinds at the API boundary (T009),
    but the Jinja renderer is designed defensively so a stale/cached payload
    with an unknown kind does not corrupt the diagram.
    """
    # Inject an unknown kind directly into a raw dict (bypass Pydantic)
    layout_with_unknown = {
        "width": 50.0,
        "height": 50.0,
        "elements": [
            {"kind": "cone",    "x": 10.0, "y": 25.0},   # valid
            {"kind": "barril",  "x": 40.0, "y": 25.0},   # unknown → skipped
        ],
    }
    html = _render(jinja_env, layout_with_unknown)
    main = _main_svg(html)
    # Only the valid cone should produce a translate group
    positions = _translate_positions(main)
    assert len(positions) == 1, (
        f"Unknown kind 'barril' must be silently skipped; expected 1 translate group, "
        f"found {len(positions)}: {positions}"
    )
    assert positions[0] == ("10.0", "25.0"), "Only the cone group must be present"


# ---------------------------------------------------------------------------
# 7. SVG is parseable XML (structural sanity for both renderers)
# ---------------------------------------------------------------------------


def test_full_vocabulary_output_is_parseable_xml(jinja_env: Environment) -> None:
    """The full-vocabulary output is well-formed XML when wrapped in a root element.

    If the Jinja renderer produces malformed markup it would also break the
    WeasyPrint PDF pipeline and likely the React hydration as well.
    """
    html = _render(jinja_env, _FULL_LAYOUT)
    # defusedxml rejects malicious DTDs/entities; parsing success = well-formed
    DET.fromstring(f"<root>{html}</root>")
