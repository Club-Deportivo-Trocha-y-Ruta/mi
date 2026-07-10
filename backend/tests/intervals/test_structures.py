"""T009 — Interval structure CRUD endpoints (feature 026, US1).

Covers (contracts/api.md §Structures):
  - POST /api/intervals/structures: creates the session's 1:1 structure,
    persisting blocks (including repeat-group fields) in the submitted order.
  - GET  /api/intervals/sessions/{id}/structure: reads back a structure by
    session id, echoing ``repeat_group``/``repeat_count`` exactly.
  - PUT  /api/intervals/structures/{id}: full replace of band + blocks.
  - DELETE /api/intervals/structures/{id}: 204, structure gone afterward.
  - 409: a session that already has a structure rejects a second POST.
  - 422 ``invalid_repeat_group``: a block with ``repeat_group`` set but
    ``repeat_count`` missing (data-model.md §2 — both or neither).
  - RBAC: parent → 403 on create.

All tests run on aiosqlite in-memory — no live MySQL, no real network.
"""
from __future__ import annotations

import pytest

from tests.intervals.conftest import (
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_training_session,
)

BASE = "/api/intervals"


# ---------------------------------------------------------------------------
# Shared setup / payload helpers
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club 1, its coach, and a bare training session; commit."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    ts = await seed_training_session(session, club_id=1, created_by_user_id=10)
    await session.commit()
    return {"training_session_id": ts.id}


def _blocks_with_repeat_group() -> list[dict]:
    """Warmup / work+recovery repeated x2 / cooldown — api.md example shape."""
    return [
        {
            "position": 1,
            "block_type": "warmup",
            "duration_s": 300,
            "target_zone": "Z1",
            "target_cadence_rpm": 70,
            "repeat_group": None,
            "repeat_count": None,
        },
        {
            "position": 2,
            "block_type": "work",
            "duration_s": 120,
            "target_zone": "Z2",
            "target_cadence_rpm": 75,
            "repeat_group": 1,
            "repeat_count": 2,
        },
        {
            "position": 3,
            "block_type": "recovery",
            "duration_s": 60,
            "target_zone": "Z1",
            "target_cadence_rpm": 65,
            "repeat_group": 1,
            "repeat_count": 2,
        },
        {
            "position": 4,
            "block_type": "cooldown",
            "duration_s": 300,
            "target_zone": "Z1",
            "target_cadence_rpm": 65,
            "repeat_group": None,
            "repeat_count": None,
        },
    ]


def _structure_payload(
    *,
    training_session_id: int,
    target_age_band: str = "13-15",
    age_gate_confirmed: bool = False,
    blocks: list[dict] | None = None,
) -> dict:
    return {
        "training_session_id": training_session_id,
        "target_age_band": target_age_band,
        "age_gate_confirmed": age_gate_confirmed,
        "blocks": blocks if blocks is not None else _blocks_with_repeat_group(),
    }


# ===========================================================================
# POST /structures — create (happy path)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_structure_happy_path(session):
    """A 13-15 structure with valid blocks is created and echoed back."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["training_session_id"] == ctx["training_session_id"]
    assert body["target_age_band"] == "13-15"
    assert body["age_gate_confirmed"] is False
    assert len(body["blocks"]) == 4
    # total_planned_duration_s counts the repeat group's runs, not just the
    # 4 authored rows: 300 + (120+60)*2 + 300 = 960 (api.md example).
    assert body["total_planned_duration_s"] == 960


# ===========================================================================
# GET /sessions/{id}/structure — read (happy path)
# ===========================================================================


@pytest.mark.asyncio
async def test_get_structure_by_session_happy_path(session):
    """GET by session id returns the structure just created."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    structure_id = create_resp.json()["id"]

    async with make_client(session) as client:
        get_resp = await client.get(
            f"{BASE}/sessions/{ctx['training_session_id']}/structure"
        )
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == structure_id
    assert body["training_session_id"] == ctx["training_session_id"]


@pytest.mark.asyncio
async def test_get_structure_returns_404_when_session_has_none(session):
    """A session with no structure yet returns 404 (frontend renders empty state)."""
    ctx = await _setup(session)

    async with make_client(session) as client:
        resp = await client.get(
            f"{BASE}/sessions/{ctx['training_session_id']}/structure"
        )
    assert resp.status_code == 404, resp.text


# ===========================================================================
# PUT /structures/{id} — full replace (happy path)
# ===========================================================================


@pytest.mark.asyncio
async def test_put_structure_replaces_band_and_blocks(session):
    """PUT fully replaces the band + block set, echoed on the response."""
    ctx = await _setup(session)
    create_payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    structure_id = create_resp.json()["id"]

    replaced_blocks = [
        {
            "position": 1,
            "block_type": "warmup",
            "duration_s": 240,
            "target_zone": "Z1",
            "target_cadence_rpm": 72,
            "repeat_group": None,
            "repeat_count": None,
        },
        {
            "position": 2,
            "block_type": "cooldown",
            "duration_s": 240,
            "target_zone": "Z1",
            "target_cadence_rpm": 68,
            "repeat_group": None,
            "repeat_count": None,
        },
    ]
    put_payload = {
        "target_age_band": "13-15",
        "age_gate_confirmed": False,
        "blocks": replaced_blocks,
    }

    async with make_client(session) as client:
        put_resp = await client.put(
            f"{BASE}/structures/{structure_id}", json=put_payload
        )
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["id"] == structure_id
    assert len(body["blocks"]) == 2
    assert body["total_planned_duration_s"] == 480
    positions = {b["position"] for b in body["blocks"]}
    assert positions == {1, 2}


@pytest.mark.asyncio
async def test_put_structure_returns_404_for_unknown_id(session):
    """PUT against a nonexistent structure id returns 404."""
    ctx = await _setup(session)
    payload = {
        "target_age_band": "13-15",
        "age_gate_confirmed": False,
        "blocks": _blocks_with_repeat_group(),
    }
    async with make_client(session) as client:
        resp = await client.put(f"{BASE}/structures/999999", json=payload)
    assert resp.status_code == 404, resp.text


# ===========================================================================
# DELETE /structures/{id} — delete (happy path)
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_structure_happy_path(session):
    """DELETE returns 204 and the structure is gone afterward (404 on GET)."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    structure_id = create_resp.json()["id"]

    async with make_client(session) as client:
        delete_resp = await client.delete(f"{BASE}/structures/{structure_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    async with make_client(session) as client:
        get_resp = await client.get(
            f"{BASE}/sessions/{ctx['training_session_id']}/structure"
        )
    assert get_resp.status_code == 404, get_resp.text


# ===========================================================================
# 409 — a session already has a structure
# ===========================================================================


@pytest.mark.asyncio
async def test_create_structure_conflicts_when_session_already_has_one(session):
    """A second POST for the same session returns 409 (use PUT instead)."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        first_resp = await client.post(f"{BASE}/structures", json=payload)
    assert first_resp.status_code == 201, first_resp.text

    async with make_client(session) as client:
        second_resp = await client.post(f"{BASE}/structures", json=payload)
    assert second_resp.status_code == 409, second_resp.text


# ===========================================================================
# Repeat-group persistence
# ===========================================================================


@pytest.mark.asyncio
async def test_repeat_group_fields_persist_across_create_and_get(session):
    """repeat_group/repeat_count round-trip exactly through create -> GET."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    async with make_client(session) as client:
        get_resp = await client.get(
            f"{BASE}/sessions/{ctx['training_session_id']}/structure"
        )
    assert get_resp.status_code == 200, get_resp.text
    blocks_by_position = {b["position"]: b for b in get_resp.json()["blocks"]}

    # Non-grouped blocks: repeat_group/repeat_count are NULL.
    assert blocks_by_position[1]["repeat_group"] is None
    assert blocks_by_position[1]["repeat_count"] is None
    assert blocks_by_position[4]["repeat_group"] is None
    assert blocks_by_position[4]["repeat_count"] is None

    # Grouped blocks: both rows share the same group + count (data-model.md §2).
    assert blocks_by_position[2]["repeat_group"] == 1
    assert blocks_by_position[2]["repeat_count"] == 2
    assert blocks_by_position[3]["repeat_group"] == 1
    assert blocks_by_position[3]["repeat_count"] == 2


# ===========================================================================
# 422 invalid_repeat_group
# ===========================================================================


@pytest.mark.asyncio
async def test_create_structure_rejects_repeat_group_without_count(session):
    """repeat_group set but repeat_count missing -> 422 invalid_repeat_group."""
    ctx = await _setup(session)
    blocks = [
        {
            "position": 1,
            "block_type": "warmup",
            "duration_s": 300,
            "target_zone": "Z1",
            "target_cadence_rpm": 70,
            "repeat_group": 1,
            "repeat_count": None,
        },
    ]
    payload = _structure_payload(
        training_session_id=ctx["training_session_id"], blocks=blocks
    )

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_repeat_group"


@pytest.mark.asyncio
async def test_create_structure_rejects_inconsistent_repeat_count_within_group(session):
    """Two rows in the same repeat_group with different repeat_count values fail."""
    ctx = await _setup(session)
    blocks = [
        {
            "position": 1,
            "block_type": "work",
            "duration_s": 120,
            "target_zone": "Z2",
            "target_cadence_rpm": 75,
            "repeat_group": 1,
            "repeat_count": 2,
        },
        {
            "position": 2,
            "block_type": "recovery",
            "duration_s": 60,
            "target_zone": "Z1",
            "target_cadence_rpm": 65,
            "repeat_group": 1,
            "repeat_count": 3,
        },
    ]
    payload = _structure_payload(
        training_session_id=ctx["training_session_id"], blocks=blocks
    )

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "invalid_repeat_group"


# ===========================================================================
# RBAC — parent 403
# ===========================================================================


@pytest.mark.asyncio
async def test_create_structure_forbidden_for_parent(session):
    """A parent-role user gets 403 on POST /structures (FR-018)."""
    ctx = await _setup(session)
    payload = _structure_payload(training_session_id=ctx["training_session_id"])

    async with make_client(session, user=parent_user_obj()) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 403, resp.text
