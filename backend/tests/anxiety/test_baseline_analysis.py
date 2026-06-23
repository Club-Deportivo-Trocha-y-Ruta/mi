"""Service-level tests for baseline seeding/deltas (T029) and analysis (US5)."""
from __future__ import annotations

import pytest

from app.services.anxiety import baseline as baseline_svc
from app.services.anxiety.analysis import (
    HIGH_ANX_LOW_CONF_FLAG,
    compute_flags,
    dominant_pattern,
)
from tests.anxiety.conftest import seed_athlete, seed_instruments, seed_user
from app.models.anxiety_assessment import AnxietyAssessment, AssessmentStatus
from app.models.user import UserRole
from datetime import date, datetime, timezone


def test_deltas_handles_missing():
    d = baseline_svc.deltas(
        {"cognitive": 30.0, "somatic": None, "selfconfidence": 25.0},
        {"cognitive": 20.0, "somatic": 18.0, "selfconfidence": None},
    )
    assert d["cognitive"] == 10.0
    assert d["somatic"] is None  # score missing
    assert d["selfconfidence"] is None  # baseline missing


def test_dominant_pattern_favorable():
    scores = {"cognitive": 15.0, "somatic": 15.0, "selfconfidence": 35.0}
    assert dominant_pattern("csai2r", scores) == "favorable"


def test_dominant_pattern_somatic_high():
    scores = {"cognitive": 15.0, "somatic": 38.0, "selfconfidence": 30.0}
    assert dominant_pattern("csai2r", scores) == "somatic_high"


def test_compute_flags_high_anx_low_conf():
    scores = {"cognitive": 38.0, "somatic": 38.0, "selfconfidence": 12.0}
    flags = compute_flags("csai2r", scores)
    assert HIGH_ANX_LOW_CONF_FLAG in flags


def test_compute_flags_clean_when_favorable():
    scores = {"cognitive": 15.0, "somatic": 15.0, "selfconfidence": 35.0}
    assert compute_flags("csai2r", scores) == []


@pytest.mark.asyncio
async def test_seed_baselines_only_once(session):
    await seed_instruments(session)
    await seed_user(session, 10, UserRole.coach)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    instrument_id = 1
    a = AnxietyAssessment(
        athlete_id=100,
        instrument_id=instrument_id,
        scheduled_at=now,
        status=AssessmentStatus.completed,
        created_by_user_id=10,
        created_at=now,
        updated_at=now,
    )
    session.add(a)
    await session.flush()

    seeded = await baseline_svc.seed_baselines_if_first(
        session,
        athlete_id=100,
        instrument_type="csai2r",
        scores={"cognitive": 20.0, "somatic": 22.0, "selfconfidence": 30.0},
        source_assessment_id=a.id,
        now=now,
    )
    assert set(seeded) == {"cognitive", "somatic", "selfconfidence"}

    # Second call does NOT overwrite the existing baseline.
    seeded2 = await baseline_svc.seed_baselines_if_first(
        session,
        athlete_id=100,
        instrument_type="csai2r",
        scores={"cognitive": 99.0, "somatic": 99.0, "selfconfidence": 99.0},
        source_assessment_id=a.id,
        now=now,
    )
    assert seeded2 == {}
    baselines = await baseline_svc.get_baselines(session, 100, "csai2r")
    assert baselines["cognitive"] == 20.0
