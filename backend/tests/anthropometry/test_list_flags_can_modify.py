"""Feature 048 (T021): ``GET /api/athletes/{id}/anthropometry`` expone
``can_modify`` (evaluador o admin) y ``plausibility_flags`` solo a coach/admin;
para padres las dos claves se OMITEN (no llegan como null).
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.anthropometry.conftest import ATHLETE_ID, COACH2_ID, COACH_ID, seed_record

pytestmark = pytest.mark.asyncio

URL = f"/api/athletes/{ATHLETE_ID}/anthropometry"


async def _seed_two(factory) -> tuple[int, int]:
    mine = await seed_record(
        factory, evaluation_date=date(2026, 1, 10), evaluated_by=COACH_ID
    )
    # Talla 2 cm menor que la anterior → height_decreased.
    theirs = await seed_record(
        factory,
        evaluation_date=date(2026, 5, 1),
        evaluated_by=COACH2_ID,
        standing="148.0",
        sitting="75.0",
    )
    return mine, theirs


async def test_evaluator_sees_can_modify_only_on_own_records(make_client, anthro_factory):
    mine, theirs = await _seed_two(anthro_factory)
    async with make_client("coach") as c:
        resp = await c.get(URL)
    assert resp.status_code == 200
    by_id = {item["id"]: item for item in resp.json()}
    assert by_id[mine]["can_modify"] is True
    assert by_id[theirs]["can_modify"] is False


async def test_admin_can_modify_every_record(make_client, anthro_factory):
    mine, theirs = await _seed_two(anthro_factory)
    async with make_client("admin") as c:
        resp = await c.get(URL)
    assert resp.status_code == 200
    assert all(item["can_modify"] is True for item in resp.json())


async def test_flags_are_computed_against_previous_record(make_client, anthro_factory):
    mine, theirs = await _seed_two(anthro_factory)
    async with make_client("coach2") as c:
        resp = await c.get(URL)
    by_id = {item["id"]: item for item in resp.json()}
    assert by_id[mine]["plausibility_flags"] == []
    assert by_id[theirs]["plausibility_flags"] == ["height_decreased"]


async def test_parent_payload_omits_both_keys(make_client, anthro_factory):
    await _seed_two(anthro_factory)
    async with make_client("parent") as c:
        resp = await c.get(URL)
    assert resp.status_code == 200
    items = resp.json()
    assert items
    for item in items:
        assert "can_modify" not in item
        assert "plausibility_flags" not in item
