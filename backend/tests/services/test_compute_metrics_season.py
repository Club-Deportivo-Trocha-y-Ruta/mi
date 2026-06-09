"""Unit tests for season_comparative and progression_assessment computation.

Tests cover:
- Delta computation correctness (position and time).
- Progression assessment matrix (improving / declining / stable / mixed).
- Single-válida → first_reference with empty comparatives.
- DNF/minus_laps prior → delta_time_ms None (no time in prior record).
- Analyzed válida earlier than some season results (only PRIOR válidas count).

The implementation lives in:
    app.services.race.ai.nodes.compute_metrics._compute_season_comparative
"""
from __future__ import annotations


from app.schemas.race_ai import ProgressionAssessment
from app.services.race.ai.nodes.compute_metrics import (
    _compute_season_comparative,
    _event_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    valida_num: int,
    position: int | None,
    race_time_ms: int | None = None,
    status: str = "finished",
) -> dict:
    """Build a minimal full_season_results record."""
    return {
        "result_id": valida_num * 100,
        "event_id": valida_num * 10,
        "valida_num": valida_num,
        "position": position,
        "race_time_ms": race_time_ms,
        "gap_to_winner_ms": None,
        "gap_pct": None,
        "status": status,
    }


# ---------------------------------------------------------------------------
# event_label helper
# ---------------------------------------------------------------------------


def test_event_label_regular() -> None:
    assert _event_label(1) == "Válida 1"
    assert _event_label(7) == "Válida 7"


def test_event_label_championship() -> None:
    assert _event_label(99) == "Cto. Departamental"


# ---------------------------------------------------------------------------
# first_reference: no prior válidas
# ---------------------------------------------------------------------------


def test_first_reference_empty_season() -> None:
    """No season results → first_reference, empty comparatives."""
    comparative, assessment = _compute_season_comparative([], [1])
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


def test_first_reference_single_valida() -> None:
    """Only the analyzed válida exists in full_season_results → first_reference."""
    records = [_make_record(valida_num=1, position=5, race_time_ms=3_600_000)]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[1])
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


def test_first_reference_empty_analyzed_valida_nums() -> None:
    """Empty analyzed_valida_nums → first_reference."""
    records = [_make_record(valida_num=1, position=5)]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[])
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


def test_first_reference_no_analyzed_result_in_season() -> None:
    """Analyzed válida not in full_season_results → first_reference."""
    # Season has válida 1, but analyzed is válida 3 (no result for it).
    records = [_make_record(valida_num=1, position=5, race_time_ms=3_600_000)]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[3])
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


# ---------------------------------------------------------------------------
# Delta computation correctness
# ---------------------------------------------------------------------------


def test_delta_position_and_time() -> None:
    """Deltas: (analyzed_position - prior_position) and (analyzed_time - prior_time)."""
    records = [
        _make_record(valida_num=1, position=8, race_time_ms=3_700_000),
        _make_record(valida_num=2, position=5, race_time_ms=3_500_000),  # analyzed
    ]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])

    assert len(comparative) == 1
    entry = comparative[0]

    # Prior: válida 1 → position=8, time=3_700_000
    # Analyzed: válida 2 → position=5, time=3_500_000
    # delta_position = 5 - 8 = -3 (better position)
    # delta_time_ms  = 3_500_000 - 3_700_000 = -200_000 (faster)
    assert entry["valida_num"] == 1
    assert entry["position"] == 8
    assert entry["race_time_ms"] == 3_700_000
    assert entry["delta_position"] == -3
    assert entry["delta_time_ms"] == -200_000


def test_delta_field_size_always_none() -> None:
    """field_size is always None — not available without category-wide query."""
    records = [
        _make_record(valida_num=1, position=3, race_time_ms=3_600_000),
        _make_record(valida_num=2, position=2, race_time_ms=3_400_000),
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert comparative[0]["field_size"] is None


def test_event_label_in_comparative() -> None:
    """event_label is derived from valida_num."""
    records = [
        _make_record(valida_num=3, position=4, race_time_ms=3_600_000),
        _make_record(valida_num=5, position=3, race_time_ms=3_400_000),
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[5])
    assert comparative[0]["event_label"] == "Válida 3"


# ---------------------------------------------------------------------------
# DNF / missing time → delta_time_ms = None
# ---------------------------------------------------------------------------


def test_delta_time_none_when_prior_has_no_time() -> None:
    """Prior result with no race_time_ms → delta_time_ms is None."""
    records = [
        _make_record(valida_num=1, position=6, race_time_ms=None),  # DNF prior
        _make_record(valida_num=2, position=4, race_time_ms=3_500_000),
    ]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])

    assert len(comparative) == 1
    entry = comparative[0]
    assert entry["delta_time_ms"] is None
    # delta_position is still computed since both positions are available.
    assert entry["delta_position"] == 4 - 6  # -2


def test_delta_time_none_when_analyzed_has_no_time() -> None:
    """Analyzed result with no race_time_ms → delta_time_ms is None."""
    records = [
        _make_record(valida_num=1, position=6, race_time_ms=3_700_000),
        _make_record(valida_num=2, position=4, race_time_ms=None),  # no time for analyzed
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])

    entry = comparative[0]
    assert entry["delta_time_ms"] is None
    assert entry["delta_position"] == 4 - 6  # -2


def test_delta_position_none_when_prior_has_no_position() -> None:
    """Prior result with no position → delta_position is None."""
    records = [
        _make_record(valida_num=1, position=None, race_time_ms=3_700_000),
        _make_record(valida_num=2, position=4, race_time_ms=3_500_000),
    ]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])

    entry = comparative[0]
    assert entry["delta_position"] is None


# ---------------------------------------------------------------------------
# Progression assessment matrix
# ---------------------------------------------------------------------------


def test_assessment_improving_strictly_better() -> None:
    """All prior positions worse than analyzed → improving."""
    records = [
        _make_record(valida_num=1, position=10),
        _make_record(valida_num=2, position=8),
        _make_record(valida_num=3, position=5),  # analyzed (better than 10 AND 8)
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[3])
    assert assessment == ProgressionAssessment.improving.value


def test_assessment_declining_strictly_worse() -> None:
    """All prior positions better than analyzed → declining."""
    records = [
        _make_record(valida_num=1, position=3),
        _make_record(valida_num=2, position=4),
        _make_record(valida_num=3, position=8),  # analyzed (worse than 3 AND 4)
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[3])
    assert assessment == ProgressionAssessment.declining.value


def test_assessment_stable_all_equal() -> None:
    """All prior positions equal to analyzed → stable."""
    records = [
        _make_record(valida_num=1, position=5),
        _make_record(valida_num=2, position=5),
        _make_record(valida_num=3, position=5),  # analyzed
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[3])
    assert assessment == ProgressionAssessment.stable.value


def test_assessment_mixed_signals() -> None:
    """Some prior positions better, some worse → mixed."""
    records = [
        _make_record(valida_num=1, position=3),   # better than analyzed
        _make_record(valida_num=2, position=10),  # worse than analyzed
        _make_record(valida_num=3, position=6),   # analyzed
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[3])
    assert assessment == ProgressionAssessment.mixed.value


def test_assessment_single_prior_improving() -> None:
    """Single prior, analyzed strictly better → improving."""
    records = [
        _make_record(valida_num=1, position=9),
        _make_record(valida_num=2, position=5),  # analyzed
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert assessment == ProgressionAssessment.improving.value


def test_assessment_single_prior_declining() -> None:
    """Single prior, analyzed strictly worse → declining."""
    records = [
        _make_record(valida_num=1, position=3),
        _make_record(valida_num=2, position=7),  # analyzed
    ]
    _, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert assessment == ProgressionAssessment.declining.value


# ---------------------------------------------------------------------------
# Only PRIOR válidas are included (sequence_number < analyzed)
# ---------------------------------------------------------------------------


def test_only_prior_validas_included() -> None:
    """season has V1, V2 (analyzed), V3 (future). Only V1 counts as prior."""
    records = [
        _make_record(valida_num=1, position=8, race_time_ms=3_700_000),  # prior
        _make_record(valida_num=2, position=5, race_time_ms=3_500_000),  # analyzed
        _make_record(valida_num=3, position=4, race_time_ms=3_300_000),  # future — excluded
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])

    # Only V1 should appear as a prior (V3 is future).
    valida_nums_in_comparative = [c["valida_num"] for c in comparative]
    assert valida_nums_in_comparative == [1]


def test_comparatives_sorted_ascending() -> None:
    """Comparatives are sorted by valida_num ascending."""
    records = [
        _make_record(valida_num=3, position=7),
        _make_record(valida_num=1, position=9),
        _make_record(valida_num=4, position=5),  # analyzed
        _make_record(valida_num=2, position=8),
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[4])
    nums = [c["valida_num"] for c in comparative]
    assert nums == sorted(nums)
    assert nums == [1, 2, 3]


# ---------------------------------------------------------------------------
# Analyzed set has multiple valida_nums → use minimum as reference
# ---------------------------------------------------------------------------


def test_minimum_analyzed_valida_used_as_reference() -> None:
    """When multiple valida_nums analyzed, only priors of min(valida_nums) count."""
    records = [
        _make_record(valida_num=1, position=10),  # prior to both 2 and 3
        _make_record(valida_num=2, position=7),   # min(analyzed)
        _make_record(valida_num=3, position=5),   # second analyzed — NOT a prior
    ]
    # Analyzing V2 and V3 together; min is V2 → only V1 is prior.
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2, 3])
    nums = [c["valida_num"] for c in comparative]
    assert nums == [1]
    # Analyzed result is V2 (min), position=7; delta vs prior V1 (position=10): 7-10=-3.
    assert comparative[0]["delta_position"] == -3
