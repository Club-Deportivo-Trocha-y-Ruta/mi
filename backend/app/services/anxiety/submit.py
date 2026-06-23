"""Apply item answers to an assessment: score, flag, seed baseline (US2/US3).

Shared by the token-answer endpoint and the historical importer so both paths
score identically and seed baselines the same way.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anxiety_assessment import AnxietyAssessment, AssessmentStatus
from app.services.anxiety import baseline as baseline_svc
from app.services.anxiety.analysis import compute_flags
from app.services.anxiety.scoring import score_assessment


async def apply_answers(
    db: AsyncSession,
    assessment: AnxietyAssessment,
    instrument_type: str,
    answers: dict[int, int],
    now: datetime | None = None,
) -> dict[str, float | None]:
    """Score ``answers``, persist on ``assessment``, seed baseline, set flags.

    Returns the subscale score dict. Raises ``ValueError`` on out-of-range
    answers (propagated by the scoring layer).
    """
    now = now or datetime.now(timezone.utc)
    scores = score_assessment(instrument_type, answers)
    score_dict = scores.as_dict()

    assessment.answers_json = {str(k): v for k, v in answers.items()}
    assessment.score_cognitive = score_dict["cognitive"]
    assessment.score_somatic = score_dict["somatic"]
    assessment.score_selfconfidence = score_dict["selfconfidence"]
    assessment.is_partial = scores.is_partial
    assessment.status = (
        AssessmentStatus.partial if scores.is_partial else AssessmentStatus.completed
    )
    assessment.flags_json = compute_flags(instrument_type, score_dict)
    assessment.updated_at = now

    await baseline_svc.seed_baselines_if_first(
        db,
        athlete_id=assessment.athlete_id,
        instrument_type=instrument_type,
        scores=score_dict,
        source_assessment_id=assessment.id,
        now=now,
    )
    return score_dict
