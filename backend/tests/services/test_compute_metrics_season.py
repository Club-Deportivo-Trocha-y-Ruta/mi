"""Unit tests for season_comparative and progression_assessment computation.

Feature 039 (season comparison groups) rewrites the contract of
``_compute_season_comparative`` — see ``research.md`` D9 and
``contracts/ai-context.md``:

- Records now carry ``series_id``/``series_kind``/``series_level`` and
  ``event_date`` (ISO string), in addition to the pre-existing
  ``result_id``/``event_id``/``valida_num``/``position``/``race_time_ms``/
  ``gap_to_winner_ms``/``gap_pct``/``status``.
- New signature: ``_compute_season_comparative(full_season_results,
  analyzed_valida_nums, *, anchored_event_id=None)``.
- The analyzed record is located by ``anchored_event_id`` when given; else
  by ``(series_kind == "cup", valida_num == min(analyzed_valida_nums))`` —
  a championship can never be picked as the analyzed record through the
  unanchored fallback (spec 014: a cup round and a championship can share
  ``sequence_number``).
- Priors are records with the SAME ``series_id`` as the analyzed record
  and an earlier ``event_date``, ordered by ``event_date`` ascending. A
  cup round never gets a championship (or a different cup) as a prior,
  and vice versa.
- A championship analyzed record always yields ``([], "first_reference")``
  — INV-2 (a championship series has exactly one race, so it can never
  have a same-series prior).
- ``event_label`` is built via ``race_labels.build_race_label`` — the
  retired ``valida_num == 99`` "Cto. Departamental" convention is gone,
  and so is the ``_event_label`` helper (do not import it: it may not
  exist once T033 lands).

The implementation lives in:
    app.services.race.ai.nodes.compute_metrics._compute_season_comparative
"""
from __future__ import annotations


from app.schemas.race_ai import ProgressionAssessment
from app.services.race.ai.nodes.compute_metrics import _compute_season_comparative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    valida_num: int,
    position: int | None,
    race_time_ms: int | None = None,
    status: str = "finished",
    *,
    event_id: int | None = None,
    series_id: int = 1,
    series_kind: str = "cup",
    series_level: str | None = "departmental",
    event_date: str | None = None,
) -> dict:
    """Build a minimal full_season_results record (feature 039 shape).

    Defaults keep every record on the same cup series (``series_id=1``)
    with an ``event_date`` that mirrors ``valida_num`` (day-of-month), so
    tests that don't care about cross-series/date edge cases behave like
    the pre-039 valida_num-ordered fixtures.
    """
    return {
        "result_id": valida_num * 100,
        "event_id": event_id if event_id is not None else valida_num * 10,
        "valida_num": valida_num,
        "series_id": series_id,
        "series_kind": series_kind,
        "series_level": series_level,
        "event_date": event_date or f"2026-01-{valida_num:02d}",
        "position": position,
        "race_time_ms": race_time_ms,
        "gap_to_winner_ms": None,
        "gap_pct": None,
        "status": status,
    }


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
# Championship analyzed record → always first_reference (INV-2)
# ---------------------------------------------------------------------------


def test_championship_analyzed_via_anchor_is_first_reference() -> None:
    """Anchoring to a championship event_id → ([], first_reference), even
    when an earlier cup round of a DIFFERENT series exists in the season
    (it must never leak in as a cross-series prior)."""
    records = [
        _make_record(
            valida_num=1, position=8, series_id=1, series_kind="cup",
            event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=1, position=3, series_id=2, series_kind="championship",
            series_level="departmental", event_id=90, event_date="2026-03-01",
        ),
    ]
    comparative, assessment = _compute_season_comparative(
        records, analyzed_valida_nums=[1], anchored_event_id=90
    )
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


# ---------------------------------------------------------------------------
# Resolution: anchored_event_id vs. (series_kind=='cup', valida_num) fallback
# ---------------------------------------------------------------------------


def test_analyzed_record_located_by_anchored_event_id() -> None:
    """Two records share valida_num=2 (a cup round and a championship);
    anchored_event_id picks the cup one unambiguously — verified via the
    delta computed against its own series' prior (a championship pick
    would use a completely different position/time)."""
    records = [
        _make_record(
            valida_num=1, position=8, race_time_ms=3_700_000,
            series_id=1, series_kind="cup", event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=2, position=5, race_time_ms=3_500_000,
            series_id=1, series_kind="cup", event_id=12, event_date="2026-03-01",
        ),
        _make_record(
            valida_num=2, position=1, race_time_ms=3_000_000,
            series_id=2, series_kind="championship", series_level="departmental",
            event_id=99, event_date="2026-03-05",
        ),
    ]
    comparative, assessment = _compute_season_comparative(
        records, analyzed_valida_nums=[2], anchored_event_id=12
    )
    assert len(comparative) == 1
    assert comparative[0]["valida_num"] == 1
    assert comparative[0]["position"] == 8
    # delta vs. the cup prior (3_500_000 - 3_700_000); a wrongly-picked
    # championship analyzed record (race_time_ms=3_000_000) would give -700_000.
    assert comparative[0]["delta_time_ms"] == -200_000
    assert assessment == ProgressionAssessment.improving.value


def test_without_anchor_valida_num_resolves_only_among_cup_rows() -> None:
    """No anchor: valida_num resolution must skip a championship sharing
    the same valida_num as the analyzed set and pick the cup round."""
    records = [
        _make_record(
            valida_num=1, position=8, race_time_ms=3_700_000,
            series_id=1, series_kind="cup", event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=2, position=5, race_time_ms=3_500_000,
            series_id=1, series_kind="cup", event_id=12, event_date="2026-03-01",
        ),
        _make_record(
            valida_num=2, position=1, race_time_ms=3_000_000,
            series_id=2, series_kind="championship", series_level="departmental",
            event_id=99, event_date="2026-03-05",
        ),
    ]
    comparative, assessment = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert len(comparative) == 1
    assert comparative[0]["position"] == 8
    assert comparative[0]["delta_time_ms"] == -200_000  # confirms the cup was picked
    assert assessment == ProgressionAssessment.improving.value


# ---------------------------------------------------------------------------
# Priors: same series_id + earlier event_date, ordered by event_date
# ---------------------------------------------------------------------------


def test_priors_restricted_to_same_series_id() -> None:
    """A record from a DIFFERENT series_id is never a prior, even with an
    earlier event_date than the analyzed record.

    The cross-series record shares valida_num with the legit same-series
    prior and is listed FIRST — this pins down that the filter really
    checks series_id and not just "first record seen for this valida_num"
    (which would silently pick the wrong one and still pass).
    """
    records = [
        _make_record(
            valida_num=1, position=3, series_id=2, series_kind="cup",
            event_id=21, event_date="2026-01-01",
        ),  # different cup, earlier date, listed first — must be excluded
        _make_record(
            valida_num=1, position=8, series_id=1, series_kind="cup",
            event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=2, position=5, series_id=1, series_kind="cup",
            event_id=12, event_date="2026-03-01",
        ),  # analyzed
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert len(comparative) == 1
    assert comparative[0]["position"] == 8


def test_priors_ordered_by_event_date_ascending() -> None:
    """Priors are ordered by event_date, not by list insertion order."""
    records = [
        _make_record(
            valida_num=3, position=7, series_id=1, event_id=13, event_date="2026-03-15",
        ),
        _make_record(
            valida_num=1, position=9, series_id=1, event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=5, position=5, series_id=1, event_id=15, event_date="2026-05-01",
        ),  # analyzed
        _make_record(
            valida_num=2, position=6, series_id=2, event_id=21, event_date="2026-02-15",
        ),  # different series, excluded regardless of date
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[5])
    assert [c["valida_num"] for c in comparative] == [1, 3]


def test_two_cups_never_share_priors() -> None:
    """Two distinct cup series in the same season: an earlier round of the
    OTHER cup is never a prior of the analyzed cup's round.

    Cup B's round is listed FIRST and shares valida_num=1 with cup A's
    legit prior, so a naive "first record seen per valida_num" grouping
    (without checking series_id) would silently pick cup B's position and
    still pass — reordering pins the bug down.
    """
    records = [
        _make_record(
            valida_num=1, position=3, series_id=2, series_kind="cup",
            event_id=31, event_date="2026-01-01",
        ),  # cup B, earlier date, listed first — must be excluded
        _make_record(
            valida_num=1, position=8, series_id=1, series_kind="cup",
            event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=2, position=5, series_id=1, series_kind="cup",
            event_id=12, event_date="2026-03-01",
        ),  # analyzed (cup A)
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])
    assert len(comparative) == 1
    assert comparative[0]["position"] == 8


def test_cup_a_first_round_has_no_priors_despite_cup_b_earlier_rounds() -> None:
    """Mirrors ``tests/fixtures/race_groups.py::race_groups_two_cups``: cup B
    ("Liga Departamental") has THREE rounds, all dated before cup A's very
    first round. Analyzing cup A's own first round (which itself has no
    same-series prior) must yield an EMPTY comparative — not just "cup B's
    position gets filtered out" (as in ``test_two_cups_never_share_priors``,
    where cup A already had a legit prior of its own), but a real
    ``first_reference`` outcome, proving cup B's rounds never leak in even
    when they are the ONLY earlier records available.

    Both cup A and cup B number their own rounds starting at 1, so the
    unanchored ``valida_num`` fallback would be ambiguous between them —
    same reason real runs always anchor via ``anchored_event_id`` (see
    ``test_analyzed_record_located_by_anchored_event_id``).
    """
    records = [
        _make_record(
            valida_num=1, position=2, series_id=2, series_kind="cup",
            event_id=201, event_date="2026-01-05",
        ),  # cup B — Liga Departamental V1
        _make_record(
            valida_num=2, position=1, series_id=2, series_kind="cup",
            event_id=202, event_date="2026-02-05",
        ),  # cup B — Liga Departamental V2
        _make_record(
            valida_num=3, position=3, series_id=2, series_kind="cup",
            event_id=203, event_date="2026-03-05",
        ),  # cup B — Liga Departamental V3
        _make_record(
            valida_num=1, position=4, series_id=1, series_kind="cup",
            event_id=101, event_date="2026-01-15",
        ),  # cup A — Copa Valle V1 (analyzed; its own first round)
    ]
    comparative, assessment = _compute_season_comparative(
        records, analyzed_valida_nums=[1], anchored_event_id=101
    )
    assert comparative == []
    assert assessment == ProgressionAssessment.first_reference.value


# ---------------------------------------------------------------------------
# event_label — race_labels.build_race_label, no retired 99 convention
# ---------------------------------------------------------------------------


def test_event_label_cup_round_uses_build_race_label() -> None:
    """A cup prior's event_label follows build_race_label's roman-numeral
    convention ('Válida II'), not a hand-rolled f-string."""
    records = [
        _make_record(
            valida_num=2, position=8, series_id=1, series_kind="cup",
            event_id=11, event_date="2026-02-01",
        ),
        _make_record(
            valida_num=5, position=5, series_id=1, series_kind="cup",
            event_id=15, event_date="2026-05-01",
        ),  # analyzed
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[5])
    assert comparative[0]["event_label"] == "Válida II"


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
    """event_label is derived from valida_num via build_race_label."""
    records = [
        _make_record(valida_num=3, position=4, race_time_ms=3_600_000),
        _make_record(valida_num=5, position=3, race_time_ms=3_400_000),
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[5])
    assert comparative[0]["event_label"] == "Válida III"


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
# Only PRIOR válidas (by event_date) are included
# ---------------------------------------------------------------------------


def test_only_prior_validas_included() -> None:
    """season has V1 (earlier date), V2 (analyzed), V3 (later date).

    Only V1 counts as prior — V3 is chronologically AFTER the analyzed
    válida, even though its sequence_number is higher too (both signals
    agree here; test_priors_ordered_by_event_date_ascending covers the
    date-vs-list-order distinction).
    """
    records = [
        _make_record(
            valida_num=1, position=8, race_time_ms=3_700_000, event_date="2026-02-01",
        ),  # prior
        _make_record(
            valida_num=2, position=5, race_time_ms=3_500_000, event_date="2026-03-01",
        ),  # analyzed
        _make_record(
            valida_num=3, position=4, race_time_ms=3_300_000, event_date="2026-04-01",
        ),  # future — excluded
    ]
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2])

    # Only V1 should appear as a prior (V3 is future).
    valida_nums_in_comparative = [c["valida_num"] for c in comparative]
    assert valida_nums_in_comparative == [1]


def test_comparatives_sorted_ascending() -> None:
    """Comparatives are sorted by event_date (and therefore valida_num
    ascending, in this same-series fixture)."""
    records = [
        _make_record(valida_num=3, position=7, event_date="2026-03-01"),
        _make_record(valida_num=1, position=9, event_date="2026-01-01"),
        _make_record(valida_num=4, position=5, event_date="2026-04-01"),  # analyzed
        _make_record(valida_num=2, position=8, event_date="2026-02-01"),
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
        _make_record(
            valida_num=1, position=10, event_date="2026-01-01",
        ),  # prior to both 2 and 3
        _make_record(
            valida_num=2, position=7, event_date="2026-02-01",
        ),  # min(analyzed)
        _make_record(
            valida_num=3, position=5, event_date="2026-03-01",
        ),  # second analyzed — NOT a prior
    ]
    # Analyzing V2 and V3 together; min is V2 → only V1 is prior.
    comparative, _ = _compute_season_comparative(records, analyzed_valida_nums=[2, 3])
    nums = [c["valida_num"] for c in comparative]
    assert nums == [1]
    # Analyzed result is V2 (min), position=7; delta vs prior V1 (position=10): 7-10=-3.
    assert comparative[0]["delta_position"] == -3
