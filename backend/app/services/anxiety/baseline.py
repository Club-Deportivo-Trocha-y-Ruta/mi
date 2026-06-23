"""Baseline establishment and trend comparison (FR-014, FR-022, research R3).

A baseline is stored per (athlete, subscale, instrument family). The first
qualifying assessment seeds it; an instrument change creates a new baseline
family (non-comparable across families). Interpretation compares each new
subscale vs. its baseline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anxiety_baseline import (
    AnxietyBaseline,
    BaselineInstrumentType,
    BaselineSubscale,
)

_SUBSCALES = ("cognitive", "somatic", "selfconfidence")


async def get_baselines(
    db: AsyncSession,
    athlete_id: int,
    instrument_type: str,
) -> dict[str, float | None]:
    """Return ``{subscale: baseline_value | None}`` for the instrument family."""
    result = await db.execute(
        select(AnxietyBaseline).where(
            AnxietyBaseline.athlete_id == athlete_id,
            AnxietyBaseline.instrument_type
            == BaselineInstrumentType(instrument_type),
        )
    )
    out: dict[str, float | None] = {s: None for s in _SUBSCALES}
    for row in result.scalars().all():
        out[row.subscale.value] = row.value
    return out


async def seed_baselines_if_first(
    db: AsyncSession,
    athlete_id: int,
    instrument_type: str,
    scores: dict[str, float | None],
    source_assessment_id: int,
    now: datetime | None = None,
) -> dict[str, float]:
    """Seed any missing baselines from ``scores``; return the newly seeded ones.

    Only subscales with a non-null score and no existing baseline (for this
    family) are seeded. Existing baselines are never overwritten.
    """
    now = now or datetime.now(timezone.utc)
    existing = await get_baselines(db, athlete_id, instrument_type)
    seeded: dict[str, float] = {}
    for subscale in _SUBSCALES:
        value = scores.get(subscale)
        if value is None or existing.get(subscale) is not None:
            continue
        db.add(
            AnxietyBaseline(
                athlete_id=athlete_id,
                subscale=BaselineSubscale(subscale),
                instrument_type=BaselineInstrumentType(instrument_type),
                value=value,
                source_assessment_id=source_assessment_id,
                established_at=now,
            )
        )
        seeded[subscale] = value
    if seeded:
        await db.flush()
    return seeded


def deltas(
    scores: dict[str, float | None],
    baselines: dict[str, float | None],
) -> dict[str, float | None]:
    """Return ``{subscale: score - baseline}`` (None when either is missing)."""
    out: dict[str, float | None] = {}
    for subscale in _SUBSCALES:
        score = scores.get(subscale)
        base = baselines.get(subscale)
        if score is None or base is None:
            out[subscale] = None
        else:
            out[subscale] = round(score - base, 2)
    return out
