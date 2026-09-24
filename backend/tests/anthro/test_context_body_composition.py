"""Tests for the feature 046 `body_composition` context leaf (T060).

Covers `app/services/ai/anthro/context.py::_build_body_composition_dict` /
`_render_body_composition_block` against
`specs/046-body-composition-skinfolds/contracts/ai-body-composition-leaf.md`
§1-§2: the leaf is `None` without a counted skinfold set, has exactly the ten
qualitative keys when present, the family-audience rendering never leaks
`band`/`band_reason_code` or the word "profesional", `sanitize_insight_context`
keeps every one of the ten keys, an adversarial numeric key (`sum4_mm`) is
dropped by the allow-list, and the renderer never emits a digit immediately
followed by `%`/`mm`.

All fixtures are synthetic (`SimpleNamespace` records, no athlete/club data).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.schemas.body_composition import BodyCompositionReading, ReferenceContext
from app.services.ai.anthro import context as anthro_context
from app.services.ai.context_builders import sanitize_insight_context

_TEN_LEAF_KEYS = frozenset(
    {
        "sets_count",
        "weeks_since_prev_set",
        "sum_change_code",
        "growth_explanation_code",
        "ffm_trend_code",
        "band",
        "band_reason_code",
        "family_band",
        "reference_context_code",
        "sites_declined_count",
    }
)

_NUMERIC_UNIT_LEAK_PATTERN = __import__("re").compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm)")


def _reading(**overrides) -> BodyCompositionReading:
    defaults = dict(
        sets_count=2,
        sum4_change_mm=None,
        sum6_change_mm=None,
        sum_change_code="within_noise",
        weight_change_code="up",
        height_growth_code="growing",
        velocity_code="within_or_above",
        bmi_z_change_code="ok",
        reference_triceps=ReferenceContext(percentile=None, code="unavailable"),
        reference_subscapular=ReferenceContext(percentile=None, code="unavailable"),
        ffm_trend_code="flat",
        sites_declined_count=0,
        band="verde",
        family_band="verde",
        band_reason_code="no_real_change",
        legs_missing=[],
        next_due_date=None,
        days_until_due=None,
    )
    defaults.update(overrides)
    return BodyCompositionReading(**defaults)


def _record(evaluation_date: date) -> SimpleNamespace:
    return SimpleNamespace(evaluation_date=evaluation_date)


# ---------------------------------------------------------------------------
# Leaf presence / absence
# ---------------------------------------------------------------------------


def test_leaf_is_none_without_a_counted_set():
    result = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), None, None
    )
    assert result is None


def test_leaf_has_exactly_the_ten_contract_keys_when_present():
    reading = _reading()
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    assert leaf is not None
    assert set(leaf.keys()) == _TEN_LEAF_KEYS


def test_leaf_never_carries_a_numeric_mm_pct_kg_key():
    reading = _reading()
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    assert leaf is not None
    for key in leaf:
        assert not key.endswith("_mm")
        assert not key.endswith("_pct")
        assert not key.endswith("_kg")


def test_weeks_since_prev_set_is_none_without_a_previous_record():
    reading = _reading(sets_count=1, band_reason_code="first_set")
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), None, reading
    )
    assert leaf is not None
    assert leaf["weeks_since_prev_set"] is None


def test_weeks_since_prev_set_is_computed_from_the_two_records():
    reading = _reading()
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 5, 4)), reading
    )
    assert leaf is not None
    assert leaf["weeks_since_prev_set"] == 4


# ---------------------------------------------------------------------------
# `sanitize_insight_context` keeps every one of the ten keys.
# ---------------------------------------------------------------------------


def test_sanitize_insight_context_keeps_all_ten_leaf_keys():
    reading = _reading()
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    sanitized = sanitize_insight_context(leaf)
    assert set(sanitized.keys()) == _TEN_LEAF_KEYS


def test_sanitize_insight_context_drops_an_adversarial_numeric_key():
    reading = _reading()
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    adversarial = {**leaf, "sum4_mm": 12.3}
    sanitized = sanitize_insight_context(adversarial)
    assert "sum4_mm" not in sanitized
    assert set(sanitized.keys()) == _TEN_LEAF_KEYS


# ---------------------------------------------------------------------------
# Renderer — family audience never leaks coach-only band/reason or numbers.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("band", "family_band", "band_reason_code"),
    [
        ("rojo", "ambar", "energy_availability_pattern"),
        ("ambar", "ambar", "sum_up_unexplained"),
        ("verde", "verde", "no_real_change"),
    ],
)
def test_family_block_never_contains_band_or_reason_or_profesional(
    band, family_band, band_reason_code
):
    reading = _reading(band=band, family_band=family_band, band_reason_code=band_reason_code)
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    block = anthro_context._render_body_composition_block(leaf, "family")
    assert block is not None
    assert "rojo" not in block
    assert band_reason_code not in block
    assert "profesional" not in block.lower()


def test_coach_block_does_render_band_and_reason():
    reading = _reading(band="ambar", family_band="ambar", band_reason_code="sum_up_unexplained")
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    block = anthro_context._render_body_composition_block(leaf, "coach")
    assert block is not None
    assert "ambar" in block


def test_renderer_returns_none_without_a_leaf():
    assert anthro_context._render_body_composition_block(None, "family") is None
    assert anthro_context._render_body_composition_block(None, "coach") is None


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_renderer_never_emits_a_digit_followed_by_percent_or_mm(audience):
    reading = _reading(
        sites_declined_count=3,
        reference_triceps=ReferenceContext(percentile=None, code="high_extreme"),
        reference_subscapular=ReferenceContext(percentile=None, code="low_extreme"),
    )
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    block = anthro_context._render_body_composition_block(leaf, audience)
    assert block is not None
    assert _NUMERIC_UNIT_LEAK_PATTERN.search(block) is None


def test_reference_context_code_is_worst_of_the_two_sites_with_extremes_collapsed():
    reading = _reading(
        reference_triceps=ReferenceContext(percentile=None, code="high_extreme"),
        reference_subscapular=ReferenceContext(percentile=None, code="normal"),
    )
    leaf = anthro_context._build_body_composition_dict(
        _record(date(2026, 6, 1)), _record(date(2026, 4, 1)), reading
    )
    assert leaf is not None
    assert leaf["reference_context_code"] == "high"
