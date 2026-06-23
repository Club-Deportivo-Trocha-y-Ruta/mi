"""T027 [US3] — read + recompute reproduce deterministic scores."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.user import UserRole
from tests.anxiety.conftest import (
    grant_consent,
    make_client,
    seed_athlete,
    seed_instruments,
    seed_user,
)

SCHEDULED = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc).isoformat()
FULL = {str(i): 3 for i in range(1, 18)}  # csai2r → every subscale (3/n)*10 = 30


async def _completed_assessment(session) -> int:
    await seed_instruments(session)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await grant_consent(session, 100, 20)
    await session.commit()
    async with make_client(session) as client:
        created = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
        token = created.json()["token"]["token"]
        aid = created.json()["id"]
    async with make_client(session, authed=False) as client:
        await client.post(f"/api/anxiety/answer/{token}", json={"answers": FULL})
    return aid


@pytest.mark.asyncio
async def test_read_returns_scores_and_baseline(session):
    aid = await _completed_assessment(session)
    async with make_client(session) as client:
        resp = await client.get(f"/api/anxiety/assessments/{aid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["cognitive"]["score"] == 30.0
    assert body["somatic"]["score"] == 30.0
    assert body["selfconfidence"]["score"] == 30.0
    # First assessment seeded the baseline → delta 0
    assert body["cognitive"]["baseline"] == 30.0
    assert body["cognitive"]["delta"] == 0.0


@pytest.mark.asyncio
async def test_recompute_is_idempotent(session):
    aid = await _completed_assessment(session)
    async with make_client(session) as client:
        before = (await client.get(f"/api/anxiety/assessments/{aid}")).json()
        recomputed = await client.post(
            f"/api/anxiety/assessments/{aid}/recompute"
        )
    assert recomputed.status_code == 200, recomputed.text
    after = recomputed.json()
    for sub in ("cognitive", "somatic", "selfconfidence"):
        assert after[sub]["score"] == before[sub]["score"]
