"""Tests del TypedDict :class:`RaceAnalystState`."""
from __future__ import annotations

from app.services.race.ai.state import RaceAnalystState


def test_state_is_typeddict():
    # Smoke test: el TypedDict acepta dicts heterogéneos por total=False.
    s: RaceAnalystState = {"athlete_id": 1, "season": 2026}
    assert s["athlete_id"] == 1
    assert s["season"] == 2026


def test_state_accepts_all_documented_keys():
    s: RaceAnalystState = {
        "athlete_id": 1,
        "season": 2026,
        "valida_nums": [1, 2],
        "coach_id": 99,
        "explain_mode": True,
        "raw_data": [],
        "competitor_id": 11,
        "category_id": 7,
        "anonymized_data": {},
        "mapping": {},
        "metrics": {},
        "principles": [],
        "memory": [],
        "draft_analysis": None,
        "critic_feedback": None,
        "final_analysis": None,
        "hitl_decision": None,
        "run_id": "abc",
        "errors": [],
        "events": [],
        "aggregate_metrics": {},
        "rendered_markdown": "",
        "notified": False,
    }
    assert s["coach_id"] == 99
    assert s["valida_nums"] == [1, 2]
