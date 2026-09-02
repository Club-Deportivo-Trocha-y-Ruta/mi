"""Tests de :func:`compute_confidence_v3` (feature 037, T202)."""

from __future__ import annotations

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.ai.confidence import compute_confidence_v3
from app.services.race.ai.prechecks import PrecheckCategory, PrecheckIssue
from app.services.race.schemas import CriticIssue


def _issue(category: PrecheckCategory) -> PrecheckIssue:
    return PrecheckIssue(
        category=category,
        issue=CriticIssue(section="x", problem="problema", suggested_fix="fix"),
    )


def test_fallback_is_low_regardless_of_everything_else():
    result = compute_confidence_v3(
        is_fallback=True,
        must_block=False,
        issues=[],
        has_training_window=True,
        has_anthro=True,
        season_n=5,
    )
    assert result == InsightConfidence.low


def test_must_block_is_low():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=True,
        issues=[],
        has_training_window=True,
        has_anthro=True,
        season_n=5,
    )
    assert result == InsightConfidence.low


def test_grounding_issue_is_low_even_without_must_block():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[_issue(PrecheckCategory.GROUNDING)],
        has_training_window=True,
        has_anthro=True,
        season_n=5,
    )
    assert result == InsightConfidence.low


def test_style_issue_caps_to_medium():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[_issue(PrecheckCategory.STYLE)],
        has_training_window=True,
        has_anthro=True,
        season_n=5,
    )
    assert result == InsightConfidence.medium


def test_missing_training_window_caps_to_medium():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[],
        has_training_window=False,
        has_anthro=True,
        season_n=5,
    )
    assert result == InsightConfidence.medium


def test_missing_anthro_caps_to_medium():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[],
        has_training_window=True,
        has_anthro=False,
        season_n=5,
    )
    assert result == InsightConfidence.medium


def test_season_n_le_1_caps_to_medium():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[],
        has_training_window=True,
        has_anthro=True,
        season_n=1,
    )
    assert result == InsightConfidence.medium


def test_clean_and_complete_is_high():
    result = compute_confidence_v3(
        is_fallback=False,
        must_block=False,
        issues=[],
        has_training_window=True,
        has_anthro=True,
        season_n=3,
    )
    assert result == InsightConfidence.high
