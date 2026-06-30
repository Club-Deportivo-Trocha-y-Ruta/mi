"""T009 — Pydantic validation for GymkhanaLayout and CircuitElement (feature 019 Phase A).

Pure schema tests — no AsyncClient, no DB session required.
Validates the invariants documented in data-model.md §Validation & invariant rules:
  1. Reject unknown element kind.
  2. Reject out-of-bounds coordinate (x > width, y > height).
  3. Reject non-finite coordinate (inf, -inf, NaN) on x, y, and rotation.
  4. Reject width <= 0 / height <= 0.
  5. Reject free-text label (FR-023 Phase A controlled-set guard).
  6. Accept empty elements list (layout with no elements is valid).
  7. Accept a valid multi-element layout including a line with a style.

All cases exercise GymkhanaLayout (and CircuitElement through it) via
model_validate() — the same path used by FastAPI on incoming request bodies.
"""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.schemas.technique import CircuitElement, GymkhanaLayout

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_LAYOUT: dict = {
    "width": 10.0,
    "height": 8.0,
    "elements": [],
}


def _build(**overrides) -> dict:
    """Return a valid layout dict with optional overrides applied."""
    return {**_VALID_LAYOUT, **overrides}


def _element(**overrides) -> dict:
    """Return a valid single element dict with optional overrides applied."""
    base = {"kind": "cone", "x": 1.0, "y": 1.0}
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# 1. Reject unknown element kind
# ---------------------------------------------------------------------------


def test_reject_unknown_kind():
    """kind must be one of the controlled vocabulary; any other value is rejected."""
    payload = _build(elements=[_element(kind="barril")])
    with pytest.raises(ValidationError) as exc_info:
        GymkhanaLayout.model_validate(payload)
    errors = exc_info.value.errors()
    # At least one error must mention the elements field.
    assert any("elements" in str(e["loc"]) for e in errors), errors


def test_reject_kind_empty_string():
    """Empty string is also not a valid kind."""
    payload = _build(elements=[_element(kind="")])
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


def test_all_valid_kinds_accepted():
    """Every kind from the controlled vocabulary must be accepted."""
    valid_kinds = ["cone", "line", "gate", "mine", "arrow", "beam", "ring"]
    for kind in valid_kinds:
        layout = GymkhanaLayout.model_validate(
            _build(elements=[_element(kind=kind, x=0.0, y=0.0)])
        )
        assert layout.elements[0].kind == kind


# ---------------------------------------------------------------------------
# 2. Reject out-of-bounds coordinates
# ---------------------------------------------------------------------------


def test_reject_x_greater_than_width():
    """Element x exceeds canvas width — must raise ValidationError."""
    payload = _build(elements=[_element(x=10.1, y=1.0)])  # width=10.0
    with pytest.raises(ValidationError) as exc_info:
        GymkhanaLayout.model_validate(payload)
    assert "x=" in str(exc_info.value) or "rango" in str(exc_info.value)


def test_reject_y_greater_than_height():
    """Element y exceeds canvas height — must raise ValidationError."""
    payload = _build(elements=[_element(x=1.0, y=8.1)])  # height=8.0
    with pytest.raises(ValidationError) as exc_info:
        GymkhanaLayout.model_validate(payload)
    assert "y=" in str(exc_info.value) or "rango" in str(exc_info.value)


def test_reject_negative_x():
    """Negative x is below the canvas lower bound (0)."""
    payload = _build(elements=[_element(x=-0.1, y=1.0)])
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


def test_reject_negative_y():
    """Negative y is below the canvas lower bound (0)."""
    payload = _build(elements=[_element(x=1.0, y=-0.5)])
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


def test_accept_x_exactly_at_width():
    """Element x == width is the boundary — should be accepted."""
    layout = GymkhanaLayout.model_validate(_build(elements=[_element(x=10.0, y=0.0)]))
    assert layout.elements[0].x == 10.0


def test_accept_y_exactly_at_height():
    """Element y == height is the boundary — should be accepted."""
    layout = GymkhanaLayout.model_validate(_build(elements=[_element(x=0.0, y=8.0)]))
    assert layout.elements[0].y == 8.0


# ---------------------------------------------------------------------------
# 3. Reject non-finite coordinates and rotation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [math.inf, -math.inf, math.nan],
    ids=["inf", "-inf", "nan"],
)
def test_reject_non_finite_x(bad_value):
    """Non-finite x (inf / -inf / NaN) must be rejected."""
    payload = _build(elements=[_element(x=bad_value, y=0.0)])
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


@pytest.mark.parametrize(
    "bad_value",
    [math.inf, -math.inf, math.nan],
    ids=["inf", "-inf", "nan"],
)
def test_reject_non_finite_y(bad_value):
    """Non-finite y (inf / -inf / NaN) must be rejected."""
    # Use a large canvas to isolate the finiteness check (not the bounds check).
    payload = _build(
        width=1e308,
        height=1e308,
        elements=[_element(x=0.0, y=bad_value)],
    )
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


@pytest.mark.parametrize(
    "bad_value",
    [math.inf, -math.inf, math.nan],
    ids=["inf", "-inf", "nan"],
)
def test_reject_non_finite_rotation(bad_value):
    """Non-finite rotation must be rejected."""
    payload = _build(elements=[_element(x=1.0, y=1.0, rotation=bad_value)])
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate(payload)


@pytest.mark.parametrize(
    "bad_value",
    [math.inf, -math.inf, math.nan],
    ids=["inf", "-inf", "nan"],
)
def test_reject_non_finite_width(bad_value):
    """Non-finite width must be rejected even if it passes Field(gt=0) for +inf."""
    # math.inf passes gt=0 but must be caught by the explicit finiteness check.
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate({"width": bad_value, "height": 8.0, "elements": []})


@pytest.mark.parametrize(
    "bad_value",
    [math.inf, -math.inf, math.nan],
    ids=["inf", "-inf", "nan"],
)
def test_reject_non_finite_height(bad_value):
    """Non-finite height must be rejected."""
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate({"width": 10.0, "height": bad_value, "elements": []})


# ---------------------------------------------------------------------------
# 4. Reject width <= 0 / height <= 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_width", [0.0, -1.0, -100.0], ids=["zero", "neg-1", "neg-100"])
def test_reject_nonpositive_width(bad_width):
    """width must be strictly greater than 0 (Field gt=0)."""
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate({"width": bad_width, "height": 8.0, "elements": []})


@pytest.mark.parametrize("bad_height", [0.0, -1.0, -100.0], ids=["zero", "neg-1", "neg-100"])
def test_reject_nonpositive_height(bad_height):
    """height must be strictly greater than 0 (Field gt=0)."""
    with pytest.raises(ValidationError):
        GymkhanaLayout.model_validate({"width": 10.0, "height": bad_height, "elements": []})


# ---------------------------------------------------------------------------
# 5. Reject free-text label (FR-023 Phase A controlled-set guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_label",
    [
        "María García",      # athlete name — PII violation
        "paso 1",            # unrecognized prefix
        "Cono",              # capitalized (case-sensitive match required)
        "cone#2",            # missing space before #
        "cone #2 extra",     # trailing text
        "cone #",            # # without digits
        "arrow # 3",         # space between # and digit
        " cone",             # leading whitespace
        "cone ",             # trailing whitespace
    ],
)
def test_reject_free_text_label(bad_label):
    """Phase A: free-text or malformed labels are rejected (FR-023)."""
    payload = _build(elements=[_element(label=bad_label)])
    with pytest.raises(ValidationError) as exc_info:
        GymkhanaLayout.model_validate(payload)
    assert "FR-023" in str(exc_info.value) or "label" in str(exc_info.value).lower()


def test_accept_label_none():
    """label=None (omitted) is always valid in Phase A."""
    layout = GymkhanaLayout.model_validate(_build(elements=[_element(label=None)]))
    assert layout.elements[0].label is None


@pytest.mark.parametrize(
    "valid_label",
    [
        "cone",
        "line",
        "gate",
        "mine",
        "arrow",
        "beam",
        "ring",
        "cone #1",
        "line #2",
        "gate #10",
        "ring #99",
    ],
)
def test_accept_controlled_set_label(valid_label):
    """Phase A: bare kind names and 'kind #n' labels are accepted."""
    # Ensure we use the matching kind so bounds/style checks are orthogonal.
    kind = valid_label.split()[0]  # 'cone #1' → 'cone'
    layout = GymkhanaLayout.model_validate(
        _build(elements=[_element(kind=kind, label=valid_label)])
    )
    assert layout.elements[0].label == valid_label


# ---------------------------------------------------------------------------
# 6. Accept empty elements list
# ---------------------------------------------------------------------------


def test_accept_empty_elements():
    """A layout with no elements is explicitly valid (data-model.md §Validation)."""
    layout = GymkhanaLayout.model_validate({"width": 5.0, "height": 5.0, "elements": []})
    assert layout.elements == []
    assert layout.width == 5.0
    assert layout.height == 5.0


def test_accept_missing_elements_key():
    """elements defaults to an empty list when omitted entirely."""
    layout = GymkhanaLayout.model_validate({"width": 5.0, "height": 5.0})
    assert layout.elements == []


# ---------------------------------------------------------------------------
# 7. Accept a valid multi-element layout with line style
# ---------------------------------------------------------------------------


def test_accept_valid_multi_element_layout_with_line_style():
    """Happy-path: a realistic gymkhana layout with several element kinds and a dashed line."""
    payload = {
        "width": 20.0,
        "height": 15.0,
        "elements": [
            {"kind": "cone", "x": 2.0, "y": 2.0, "rotation": 0.0},
            {"kind": "cone", "x": 18.0, "y": 2.0},
            {"kind": "gate", "x": 10.0, "y": 7.5, "rotation": 90.0},
            {"kind": "line", "x": 2.0, "y": 2.0, "style": "dashed"},
            {"kind": "line", "x": 10.0, "y": 7.5, "style": "solid"},
            {"kind": "mine", "x": 5.0, "y": 10.0},
            {"kind": "arrow", "x": 10.0, "y": 14.0, "rotation": 270.0},
            {"kind": "beam", "x": 10.0, "y": 7.5, "rotation": 45.0},
            {"kind": "ring", "x": 10.0, "y": 7.5},
        ],
    }
    layout = GymkhanaLayout.model_validate(payload)
    assert len(layout.elements) == 9
    # Verify the dashed line preserved its style.
    dashed = next(e for e in layout.elements if e.kind == "line" and e.style == "dashed")
    assert dashed.x == 2.0
    solid = next(e for e in layout.elements if e.kind == "line" and e.style == "solid")
    assert solid.x == 10.0


def test_accept_valid_layout_with_rotation_values():
    """Finite rotation in any degree range (including >360) is valid."""
    payload = _build(
        elements=[
            _element(kind="arrow", x=1.0, y=1.0, rotation=0.0),
            _element(kind="arrow", x=2.0, y=2.0, rotation=359.9),
            _element(kind="arrow", x=3.0, y=3.0, rotation=720.0),
            _element(kind="arrow", x=4.0, y=4.0, rotation=-90.0),
        ]
    )
    layout = GymkhanaLayout.model_validate(payload)
    assert len(layout.elements) == 4


def test_model_round_trip():
    """model_dump → model_validate round-trip preserves all fields."""
    original_payload = {
        "width": 12.5,
        "height": 9.0,
        "elements": [
            {"kind": "cone", "x": 0.0, "y": 0.0, "rotation": 45.0, "label": "cone #1"},
            {"kind": "line", "x": 12.5, "y": 9.0, "style": "dashed", "label": None},
        ],
    }
    layout = GymkhanaLayout.model_validate(original_payload)
    dumped = layout.model_dump()
    layout2 = GymkhanaLayout.model_validate(dumped)
    assert layout2.width == layout.width
    assert layout2.height == layout.height
    assert len(layout2.elements) == 2
    assert layout2.elements[0].label == "cone #1"
    assert layout2.elements[1].style == "dashed"
