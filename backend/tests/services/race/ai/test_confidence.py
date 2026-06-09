"""US4 (feature 011): deterministic compute_confidence rule branches."""
from __future__ import annotations

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.ai.confidence import DataCompleteness, compute_confidence
from app.services.race.schemas import CriticFeedback, CriticIssueSeverity


def _verdict(severity=CriticIssueSeverity.LOW, must_block=False, approved=True):
    return CriticFeedback(approved=approved, severity=severity, must_block=must_block)


_FULL = DataCompleteness(has_conditions=True, has_maturation=True, season_n=3)


def test_fallback_is_low():
    c = DataCompleteness(True, True, 3, is_fallback=True)
    assert compute_confidence(_verdict(), c) == InsightConfidence.low


def test_must_block_is_low():
    assert compute_confidence(_verdict(must_block=True), _FULL) == InsightConfidence.low


def test_high_issue_is_low():
    assert (
        compute_confidence(_verdict(severity=CriticIssueSeverity.HIGH), _FULL)
        == InsightConfidence.low
    )


def test_med_issue_is_medium():
    assert (
        compute_confidence(_verdict(severity=CriticIssueSeverity.MED), _FULL)
        == InsightConfidence.medium
    )


def test_none_verdict_is_medium():
    assert compute_confidence(None, _FULL) == InsightConfidence.medium


def test_missing_conditions_caps_to_medium():
    c = DataCompleteness(has_conditions=False, has_maturation=True, season_n=3)
    assert compute_confidence(_verdict(), c) == InsightConfidence.medium


def test_missing_maturation_caps_to_medium():
    c = DataCompleteness(has_conditions=True, has_maturation=False, season_n=3)
    assert compute_confidence(_verdict(), c) == InsightConfidence.medium


def test_n1_caps_to_medium():
    c = DataCompleteness(has_conditions=True, has_maturation=True, season_n=1)
    assert compute_confidence(_verdict(), c) == InsightConfidence.medium


def test_clean_and_complete_is_high():
    assert compute_confidence(_verdict(), _FULL) == InsightConfidence.high
