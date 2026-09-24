"""Golden-eval judge context (feature 046, T068).

The judge treats ``context_json`` as the only grounding source, so it must carry
the qualitative body-composition leaf the analyst saw — projected to the
audience exactly like ``context._render_body_composition_block`` (family never
sees the coach-only ``band``/``band_reason_code``).
"""

from __future__ import annotations

import json

from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.eval.judge import _render_context_json

_LEAF = {
    "band": "rojo",
    "band_reason_code": "energy_availability_pattern",
    "family_band": "ambar",
    "sets_count": 2,
    "weeks_since_prev_set": 12,
    "sum_change_code": "down_sustained",
    "growth_explanation_code": "none",
    "ffm_trend_code": "stable",
    "reference_context_code": "within_reference",
    "sites_declined_count": 0,
}


def _context(audience: str, leaf: dict | None) -> AnalysisContext:
    return AnalysisContext(
        identity={"age_decimal": 13.0, "age_group": "13-15", "sex": "F", "category": "X", "audience": audience},
        measurement_deltas=None,
        longitudinal_series=[],
        growth_summary={"stage": "Circa-PHV"},
        training_load_window=None,
        previous_analysis=None,
        body_composition=leaf,
    )


def test_judge_context_includes_full_leaf_for_coach() -> None:
    payload = json.loads(_render_context_json(_context("coach", dict(_LEAF))))
    assert payload["body_composition"] == _LEAF


def test_judge_context_projects_leaf_for_family() -> None:
    payload = json.loads(_render_context_json(_context("family", dict(_LEAF))))
    leaf = payload["body_composition"]
    assert "band" not in leaf
    assert "band_reason_code" not in leaf
    assert leaf["family_band"] == "ambar"


def test_judge_context_omits_leaf_when_absent() -> None:
    payload = json.loads(_render_context_json(_context("family", None)))
    assert "body_composition" not in payload
