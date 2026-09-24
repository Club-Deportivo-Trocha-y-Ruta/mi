"""Feature 046 (T066): body-composition sentence in the deterministic fallback.

`contracts/ai-body-composition-leaf.md` §4: when the qualitative leaf exists,
`build_fallback_insight` adds exactly one sentence per audience — family from
`FAMILY_COPY[family_band]` (never a rojo sentence), coach from
`COACH_REASON_COPY[band_reason_code]` — and never a body-composition number.
Synthetic fixtures only.
"""

from __future__ import annotations

import re

import pytest

from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.fallback import FALLBACK_DATA_GAP, build_fallback_insight
from app.services.body_composition import COACH_REASON_COPY, FAMILY_COPY

_NUMERIC_BODY_COMP = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm)\b")


def _leaf(**overrides) -> dict:
    leaf = {
        "sets_count": 2,
        "weeks_since_prev_set": 13,
        "sum_change_code": "down_real",
        "growth_explanation_code": "none",
        "ffm_trend_code": "flat",
        "band": "rojo",
        "band_reason_code": "energy_availability_pattern",
        "family_band": "ambar",
        "reference_context_code": "normal",
        "sites_declined_count": 0,
    }
    leaf.update(overrides)
    return leaf


def _context(audience: str, body_composition: dict | None) -> AnalysisContext:
    return AnalysisContext(
        identity={
            "audience": audience,
            "age_group": "13-15",
            "age_decimal": 13.1,
            "sex": "F",
            "category": "Infantil B femenino",
        },
        measurement_deltas=None,
        longitudinal_series=[],
        growth_summary={"stage": "Circa-PHV", "alerts": []},
        training_load_window=None,
        previous_analysis=None,
        body_composition=body_composition,
    )


def _all_text(insight) -> str:
    return " ".join(
        [insight.summary_line, *insight.changes, *insight.meaning, *insight.next_weeks]
    )


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_no_leaf_keeps_the_042_fallback_unchanged(audience: str) -> None:
    insight = build_fallback_insight(_context(audience, None))
    text = _all_text(insight)
    for copy in FAMILY_COPY.values():
        assert copy["family_sentence"] not in text
    for sentence in COACH_REASON_COPY.values():
        assert sentence not in text
    assert insight.data_gaps == [FALLBACK_DATA_GAP]


def test_family_coach_side_rojo_uses_the_ambar_family_sentence_only() -> None:
    insight = build_fallback_insight(_context("family", _leaf()))
    text = _all_text(insight)
    assert FAMILY_COPY["ambar"]["family_sentence"] in insight.meaning
    assert FAMILY_COPY["verde"]["family_sentence"] not in text
    # Coach-only reason copy never reaches the family.
    assert COACH_REASON_COPY["energy_availability_pattern"] not in text
    assert "profesional de salud" not in text
    assert not _NUMERIC_BODY_COMP.search(text)


def test_family_verde_uses_the_verde_family_sentence() -> None:
    leaf = _leaf(band="ambar", band_reason_code="reference_extreme", family_band="verde")
    insight = build_fallback_insight(_context("family", leaf))
    assert FAMILY_COPY["verde"]["family_sentence"] in insight.meaning
    assert FAMILY_COPY["ambar"]["family_sentence"] not in _all_text(insight)


def test_family_unexpected_rojo_family_band_is_projected_to_ambar() -> None:
    """Defensive: a (contract-violating) `family_band="rojo"` never produces
    a rojo sentence — there is no rojo family copy by design (§3c)."""
    insight = build_fallback_insight(_context("family", _leaf(family_band="rojo")))
    assert FAMILY_COPY["ambar"]["family_sentence"] in insight.meaning


def test_coach_uses_the_reason_copy_for_band_reason_code() -> None:
    insight = build_fallback_insight(_context("coach", _leaf()))
    text = _all_text(insight)
    assert COACH_REASON_COPY["energy_availability_pattern"] in insight.meaning
    for copy in FAMILY_COPY.values():
        assert copy["family_sentence"] not in text
    assert not _NUMERIC_BODY_COMP.search(text)


def test_coach_unknown_reason_code_adds_no_sentence() -> None:
    insight = build_fallback_insight(_context("coach", _leaf(band_reason_code="not_a_code")))
    text = _all_text(insight)
    for sentence in COACH_REASON_COPY.values():
        assert sentence not in text


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_exactly_one_body_composition_sentence_and_schema_limits(audience: str) -> None:
    ctx = _context(audience, _leaf())
    # Max out the other `meaning` lines (stage + alerts) to prove the leaf
    # sentence survives the 1-4 cardinality cap.
    ctx.growth_summary["alerts"] = ["x"]
    insight = build_fallback_insight(ctx)
    known = {c["family_sentence"] for c in FAMILY_COPY.values()} | set(COACH_REASON_COPY.values())
    assert sum(1 for line in insight.meaning if line in known) == 1
    assert 1 <= len(insight.meaning) <= 4
