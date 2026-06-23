"""Unit tests for anxiety subscale scoring (US3, FR-009/011/012)."""
from __future__ import annotations

import pytest

from app.services.anxiety.scoring import score_assessment


def test_csai2r_full_mean_times_10_range():
    # All answers = 4 → every subscale mean = 4 → ×10 = 40 (top of 10–40).
    answers = {i: 4 for i in range(1, 18)}
    s = score_assessment("csai2r", answers)
    assert s.cognitive.value == 40.0
    assert s.somatic.value == 40.0
    assert s.selfconfidence.value == 40.0
    assert s.is_partial is False


def test_csai2r_all_ones_is_floor():
    answers = {i: 1 for i in range(1, 18)}
    s = score_assessment("csai2r", answers)
    assert s.cognitive.value == 10.0
    assert s.somatic.value == 10.0
    assert s.selfconfidence.value == 10.0


def test_csai2r_selfconfidence_not_reversed():
    # Self-confidence high answers must yield a HIGH self-confidence score,
    # i.e. it is a positive dimension, not inverted into anxiety.
    answers = {i: 1 for i in range(1, 18)}
    for item in (3, 7, 10, 13, 16):  # self-confidence items
        answers[item] = 4
    s = score_assessment("csai2r", answers)
    assert s.selfconfidence.value == 40.0
    assert s.cognitive.value == 10.0


def test_partial_is_averaged_and_flagged():
    # Answer only 3 of 7 somatic items, all = 3 → mean 3 → 30; flagged partial.
    answers = {1: 3, 4: 3, 6: 3}
    s = score_assessment("csai2r", answers)
    assert s.somatic.value == 30.0
    assert s.somatic.partial is True
    assert s.is_partial is True


def test_csai2_sum_range_and_reverse_item_14():
    # CSAI-2 uses sum (range 9–36 per 9-item subscale). Item 14 (somatic) is
    # reverse-keyed: an answer of 1 becomes 4.
    answers = {i: 4 for i in range(1, 28)}
    answers[14] = 1  # reverse → contributes 4
    s = score_assessment("csai2", answers)
    assert s.somatic.value == 36.0  # 8×4 + reverse(1)=4 = 36
    assert s.cognitive.value == 36.0


def test_sas2_has_no_selfconfidence():
    answers = {i: 2 for i in range(1, 16)}
    s = score_assessment("sas2", answers)
    assert s.selfconfidence.value is None
    assert s.cognitive.value is not None
    assert s.somatic.value is not None


def test_out_of_range_answer_raises():
    with pytest.raises(ValueError):
        score_assessment("csai2r", {1: 5})


def test_recompute_is_deterministic():
    answers = {i: (i % 4) + 1 for i in range(1, 18)}
    a = score_assessment("csai2r", answers)
    b = score_assessment("csai2r", answers)
    assert a.as_dict() == b.as_dict()
