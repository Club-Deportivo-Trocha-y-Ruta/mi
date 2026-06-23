"""T013 [US1] — assessment creation: auth, consent gate, under-13 override."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.user import UserRole
from tests.anxiety.conftest import (
    coach_user,
    grant_consent,
    make_client,
    parent_user,
    seed_athlete,
    seed_instruments,
    seed_user,
)

SCHEDULED = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc).isoformat()


async def _setup(session, *, birth_date, consent=True):
    await seed_instruments(session)
    await seed_user(session, 10, UserRole.coach)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, birth_date, user_id=999)
    if consent:
        await grant_consent(session, 100, 20)
    await session.commit()


@pytest.mark.asyncio
async def test_create_happy_path_issues_token(session):
    await _setup(session, birth_date=date(2012, 6, 1))  # ~14y → csai2r
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["instrument_type"] == "csai2r"
    assert body["status"] == "pending"
    assert body["token"]["token"]  # raw token returned once


@pytest.mark.asyncio
async def test_consent_missing_returns_409(session):
    await _setup(session, birth_date=date(2012, 6, 1), consent=False)
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_under_13_override_requires_ack_422(session):
    await _setup(session, birth_date=date(2015, 1, 1))  # ~11y → sas2 default
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={
                "athlete_id": 100,
                "scheduled_at": SCHEDULED,
                "instrument_type": "csai2r",
            },
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_under_13_override_confirmed_succeeds(session):
    await _setup(session, birth_date=date(2015, 1, 1))
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={
                "athlete_id": 100,
                "scheduled_at": SCHEDULED,
                "instrument_type": "csai2r",
                "override": True,
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["instrument_type"] == "csai2r"
    assert body["instrument_override"] is True
    assert body["warning"]


@pytest.mark.asyncio
async def test_under_13_auto_selects_sas2(session):
    await _setup(session, birth_date=date(2015, 1, 1))
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["instrument_type"] == "sas2"


@pytest.mark.asyncio
async def test_parent_forbidden(session):
    await _setup(session, birth_date=date(2012, 6, 1))
    async with make_client(session, user=parent_user()) as client:
        resp = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_batch_flags_consent_without_failing(session):
    from datetime import date as _date

    from app.models.race_event import RaceEvent
    from app.models.race_series import RaceSeries

    await seed_instruments(session)
    await seed_user(session, 10, UserRole.coach)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await seed_athlete(session, 101, date(2012, 6, 1), user_id=902)
    await grant_consent(session, 100, 20)  # only athlete 100 consented
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
            event_date=_date(2026, 5, 17),
            created_by_user_id=10,
        )
    )
    await session.commit()

    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/assessments/batch",
            json={
                "athlete_ids": [100, 101],
                "event_id": 1,
                "scheduled_at": SCHEDULED,
            },
        )
    assert resp.status_code == 201, resp.text
    items = {i["athlete_id"]: i for i in resp.json()["items"]}
    assert items[100]["created"] is True
    assert items[101]["created"] is False  # consent missing, but batch succeeded
    assert items[101]["error"]
