"""T021 [US2] — token answer flow: form, submit, single-use, partial."""
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

# Full CSAI-2R answer set (items 1..17).
FULL_ANSWERS = {str(i): 2 for i in range(1, 18)}


async def _create_assessment(session) -> str:
    await seed_instruments(session)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await grant_consent(session, 100, 20)
    await session.commit()
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
    return resp.json()["token"]["token"]


@pytest.mark.asyncio
async def test_get_form_returns_items_and_scale(session):
    token = await _create_assessment(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"/api/anxiety/answer/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["instrument_type"] == "csai2r"
    assert len(body["items"]) == 17
    assert body["scale_min"] == 1 and body["scale_max"] == 4


@pytest.mark.asyncio
async def test_submit_completes_and_is_single_use(session):
    token = await _create_assessment(session)
    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"/api/anxiety/answer/{token}", json={"answers": FULL_ANSWERS}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"
        assert resp.json()["short_message"]

        # Re-using the consumed token → 410
        again = await client.post(
            f"/api/anxiety/answer/{token}", json={"answers": FULL_ANSWERS}
        )
        assert again.status_code == 410, again.text


@pytest.mark.asyncio
async def test_partial_submission_flagged(session):
    token = await _create_assessment(session)
    partial = {str(i): 2 for i in range(1, 10)}  # only 9 of 17
    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"/api/anxiety/answer/{token}", json={"answers": partial}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "partial"


@pytest.mark.asyncio
async def test_unknown_token_410(session):
    await seed_instruments(session)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.get("/api/anxiety/answer/does-not-exist")
    assert resp.status_code == 410
