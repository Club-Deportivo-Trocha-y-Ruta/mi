"""Deterministic subscale scoring for the anxiety instruments.

Scores are computed strictly from the loaded official key (FR-004) and stored
item-by-item answers (FR-010), so they are always recomputable. Higher
cognitive/somatic = more anxiety; self-confidence is a positive dimension and
is NOT inverted (FR-009). Missing answers are averaged over answered items and
the result is flagged partial (FR-011).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.anxiety.instrument_keys import InstrumentKey, Subscale, load_key


@dataclass(frozen=True)
class SubscaleScore:
    value: float | None  # None when the subscale does not exist (e.g. SAS-2 self-confidence)
    answered: int
    expected: int
    partial: bool


@dataclass(frozen=True)
class AssessmentScores:
    cognitive: SubscaleScore
    somatic: SubscaleScore
    selfconfidence: SubscaleScore
    is_partial: bool

    def as_dict(self) -> dict[str, float | None]:
        return {
            "cognitive": self.cognitive.value,
            "somatic": self.somatic.value,
            "selfconfidence": self.selfconfidence.value,
        }


def _reverse(value: int, likert: tuple[int, int]) -> int:
    lo, hi = likert
    return (lo + hi) - value


def _score_subscale(
    subscale: Subscale | None,
    answers: dict[int, int],
    key: InstrumentKey,
) -> SubscaleScore:
    if subscale is None:
        return SubscaleScore(value=None, answered=0, expected=0, partial=False)

    expected = len(subscale.items)
    collected: list[int] = []
    for item in subscale.items:
        raw = answers.get(item)
        if raw is None:
            continue
        lo, hi = key.likert
        if not (lo <= raw <= hi):
            raise ValueError(
                f"Answer for item {item} out of range {key.likert}: {raw}"
            )
        collected.append(_reverse(raw, key.likert) if item in subscale.reverse else raw)

    answered = len(collected)
    partial = answered < expected
    if answered == 0:
        return SubscaleScore(value=None, answered=0, expected=expected, partial=True)

    if key.scoring_method == "mean_times_10":
        value = (sum(collected) / answered) * 10
    elif key.scoring_method == "sum":
        # Prorate over answered items when partial so the score stays on the
        # subscale's natural range instead of being deflated by gaps.
        value = (sum(collected) / answered) * expected
    else:  # pragma: no cover - guarded by key validation
        raise ValueError(f"Unknown scoring method: {key.scoring_method!r}")

    return SubscaleScore(
        value=round(value, 2),
        answered=answered,
        expected=expected,
        partial=partial,
    )


def score_assessment(
    instrument_type: str,
    answers: dict[int, int],
) -> AssessmentScores:
    """Compute the three subscale scores for ``answers`` under ``instrument_type``.

    ``answers`` maps 1-based item number → Likert value. Missing items are
    allowed (partial). Raises ``ValueError`` on out-of-range answers.
    """
    key = load_key(instrument_type)
    cognitive = _score_subscale(key.subscale("cognitive"), answers, key)
    somatic = _score_subscale(key.subscale("somatic"), answers, key)
    selfconf = _score_subscale(key.subscale("selfconfidence"), answers, key)
    is_partial = any(s.partial for s in (cognitive, somatic, selfconf) if s.expected)
    return AssessmentScores(
        cognitive=cognitive,
        somatic=somatic,
        selfconfidence=selfconf,
        is_partial=is_partial,
    )
