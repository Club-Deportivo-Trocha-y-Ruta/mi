"""T038 [US5] — individual series + group triage buckets."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.race_event import RaceEvent
from app.models.race_series import RaceSeries
from app.models.user import UserRole
from tests.anxiety.conftest import (
    grant_consent,
    make_client,
    seed_athlete,
    seed_instruments,
    seed_user,
)

SCHEDULED = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc).isoformat()
FULL = {str(i): 2 for i in range(1, 18)}


async def _seed_event(session) -> None:
    session.add(
        RaceSeries(
            id=1,
            name="Copa Valle",
            season_year=2026,
            organizer="Liga",
            points_scheme_code="copa_valle_2026",
        )
    )
    await session.flush()
    session.add(
        RaceEvent(
            id=1,
            series_id=1,
            sequence_number=4,
            name="Válida IV Cali",
            event_date=date(2026, 5, 17),
            created_by_user_id=10,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_athlete_series_has_points_and_baseline(session):
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
    async with make_client(session, authed=False) as client:
        await client.post(f"/api/anxiety/answer/{token}", json={"answers": FULL})
    async with make_client(session) as client:
        resp = await client.get(
            "/api/anxiety/athletes/100/series?instrument_type=csai2r"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["points"]) == 1
    assert body["baseline_cognitive"] == 20.0


@pytest.mark.asyncio
async def test_group_triage_buckets(session):
    await seed_instruments(session)
    await seed_user(session, 10, UserRole.coach)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await grant_consent(session, 100, 20)
    await _seed_event(session)
    await session.commit()

    async with make_client(session) as client:
        created = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "event_id": 1, "scheduled_at": SCHEDULED},
        )
        token = created.json()["token"]["token"]
    async with make_client(session, authed=False) as client:
        await client.post(f"/api/anxiety/answer/{token}", json={"answers": FULL})

    async with make_client(session) as client:
        resp = await client.get("/api/anxiety/groups/by-event/1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["buckets"]) == {
        "somatic_high",
        "cognitive_high",
        "confidence_low",
        "favorable",
    }
    total = sum(len(v) for v in body["buckets"].values())
    assert total == 1
