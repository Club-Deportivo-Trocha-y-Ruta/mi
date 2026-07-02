"""T019 — Strength block CRUD endpoints (feature 021).

Covers (contracts/strength-api.md):
  - POST /api/strength/blocks: creates a block with entries and computes
    total_duration_min as the sum of entry duration_min (FR-009/FR-010).
  - GET /api/strength/blocks: club-scoped list, is_archived=false by default.
  - GET /api/strength/blocks/{id}: single block read, embeds ExerciseOut per
    entry, 404 for unknown/foreign-club id.
  - PUT /api/strength/blocks/{id}: full replace of entries; re-positions them
    0..n-1 in payload order regardless of the position values submitted.
  - PATCH /api/strength/blocks/{id}/archive: soft-archive toggle; archived
    blocks are excluded from the default list but included with
    ?include_archived=true.
  - Club scoping: a block created under club 1 is invisible to a coach in
    club 2 (list omits it; direct GET by id returns 404).
  - RBAC: parent → 403, admin → 200.

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Will fail until T021/T022 (block service + router endpoints) exist.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.club import Club, ClubMember, ClubRole
from tests.strength.conftest import (
    admin_user_obj,
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_strength_catalog,
)

BASE = "/api/strength"

# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club 1, its coach, and the strength catalog; commit."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_strength_catalog(session)
    await session.commit()
    return catalog


async def _seed_second_club_coach(session, *, club_id: int = 2, user_id: int = 11) -> None:
    """Seed a second club with its own coach (for cross-club scoping tests)."""
    club = Club(
        id=club_id,
        name="Club Ficticio Dos",
        code=f"TST{club_id:03d}",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club)
    await session.flush()
    coach = coach_user_obj(user_id)
    session.add(coach)
    await session.flush()
    session.add(
        ClubMember(
            club_id=club_id,
            user_id=user_id,
            role_in_club=ClubRole.coach,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()


def _block_payload(
    *,
    name: str = "Bloque de fuerza de prueba",
    target_age_band: str = "13-15",
    duration_target_min: int = 30,
    entries: list[dict],
) -> dict:
    return {
        "name": name,
        "target_age_band": target_age_band,
        "duration_target_min": duration_target_min,
        "entries": entries,
    }


# ===========================================================================
# POST /blocks — creation + total_duration_min computation
# ===========================================================================


@pytest.mark.asyncio
async def test_create_block_computes_total_duration_as_sum_of_entries(session):
    """total_duration_min echoes Σ duration_min across all submitted entries."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    ex_remo = catalog["exercises"]["remo_banda"]
    ex_sentadilla = catalog["exercises"]["sentadilla"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 8, "reps": "2x10"},
            {"exercise_id": ex_remo.id, "position": 1, "duration_min": 7, "reps": "2x12"},
            {"exercise_id": ex_sentadilla.id, "position": 2, "duration_min": 10, "reps": "3x10"},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_duration_min"] == 8 + 7 + 10
    assert body["name"] == "Bloque de fuerza de prueba"
    assert body["target_age_band"] == "13-15"
    assert body["duration_target_min"] == 30
    assert body["is_archived"] is False
    assert len(body["entries"]) == 3


@pytest.mark.asyncio
async def test_create_block_entries_embed_exercise_out(session):
    """Each EntryOut in the response embeds a full ExerciseOut for the exercise."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 6, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 201, resp.text
    entry = resp.json()["entries"][0]
    assert entry["duration_min"] == 6
    assert entry["reps"] == "2x10"
    assert entry["is_age_override"] is False
    assert entry["exercise"]["id"] == ex_flexiones.id
    assert entry["exercise"]["slug"] == "flexiones-test"
    # Embedded exercise is card-view shape, not detail.
    assert "how_to" not in entry["exercise"]


@pytest.mark.asyncio
async def test_create_block_single_entry_total_equals_that_entry(session):
    """A block with exactly one entry has total_duration_min == that entry's duration."""
    catalog = await _setup(session)
    ex_sentadilla = catalog["exercises"]["sentadilla"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_sentadilla.id, "position": 0, "duration_min": 12, "reps": "3x8"},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["total_duration_min"] == 12


# ===========================================================================
# GET /blocks — list (club-scoped, is_archived=false default)
# ===========================================================================


@pytest.mark.asyncio
async def test_list_blocks_returns_created_block(session):
    """GET /blocks returns the block just created, club-scoped."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    block_id = create_resp.json()["id"]

    async with make_client(session) as client:
        list_resp = await client.get(f"{BASE}/blocks")
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    assert body["total"] == 1
    ids = {item["id"] for item in body["items"]}
    assert block_id in ids


@pytest.mark.asyncio
async def test_list_blocks_excludes_archived_by_default(session):
    """Archived blocks are excluded from GET /blocks unless include_archived=true."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    block_id = create_resp.json()["id"]

    async with make_client(session) as client:
        archive_resp = await client.patch(
            f"{BASE}/blocks/{block_id}/archive", json={"is_archived": True}
        )
    assert archive_resp.status_code == 200, archive_resp.text

    async with make_client(session) as client:
        default_resp = await client.get(f"{BASE}/blocks")
    assert default_resp.status_code == 200, default_resp.text
    ids_default = {item["id"] for item in default_resp.json()["items"]}
    assert block_id not in ids_default

    async with make_client(session) as client:
        include_resp = await client.get(f"{BASE}/blocks?include_archived=true")
    assert include_resp.status_code == 200, include_resp.text
    ids_included = {item["id"] for item in include_resp.json()["items"]}
    assert block_id in ids_included


# ===========================================================================
# GET /blocks/{id} — single block read
# ===========================================================================


@pytest.mark.asyncio
async def test_get_block_by_id_returns_full_shape(session):
    """GET /blocks/{id} returns the BlockOut shape with entries in position order."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    ex_sentadilla = catalog["exercises"]["sentadilla"]

    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
            {"exercise_id": ex_sentadilla.id, "position": 1, "duration_min": 9, "reps": "3x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    block_id = create_resp.json()["id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/blocks/{block_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == block_id
    assert body["total_duration_min"] == 14
    positions = [entry["position"] for entry in body["entries"]]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_get_block_unknown_id_returns_404(session):
    """GET /blocks/{id} for a non-existent id returns 404."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/blocks/99999")
    assert resp.status_code == 404, resp.text


# ===========================================================================
# PUT /blocks/{id} — full replace, re-positions entries 0..n-1
# ===========================================================================


@pytest.mark.asyncio
async def test_put_block_full_replace_repositions_entries_0_to_n_minus_1(session):
    """PUT re-positions submitted entries 0..n-1 in payload order, regardless
    of the (arbitrary) position values sent in the request body.
    """
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    ex_remo = catalog["exercises"]["remo_banda"]
    ex_sentadilla = catalog["exercises"]["sentadilla"]

    create_payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    block_id = create_resp.json()["id"]

    # Replace with three entries submitted using deliberately out-of-order,
    # non-contiguous position values (5, 3, 10) to prove the server ignores
    # them and re-derives 0..n-1 from submission order.
    update_payload = _block_payload(
        entries=[
            {"exercise_id": ex_sentadilla.id, "position": 5, "duration_min": 9, "reps": "3x10"},
            {"exercise_id": ex_remo.id, "position": 3, "duration_min": 7, "reps": "2x12"},
            {"exercise_id": ex_flexiones.id, "position": 10, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        put_resp = await client.put(f"{BASE}/blocks/{block_id}", json=update_payload)
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert len(body["entries"]) == 3

    positions = [entry["position"] for entry in body["entries"]]
    assert positions == [0, 1, 2]

    # Order follows the submission order in the payload (sentadilla, remo, flexiones).
    exercise_ids_in_order = [entry["exercise"]["id"] for entry in body["entries"]]
    assert exercise_ids_in_order == [ex_sentadilla.id, ex_remo.id, ex_flexiones.id]

    assert body["total_duration_min"] == 9 + 7 + 5


@pytest.mark.asyncio
async def test_put_block_replaces_entry_count_shrinking(session):
    """PUT with fewer entries than before drops the removed ones entirely."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    ex_remo = catalog["exercises"]["remo_banda"]
    ex_sentadilla = catalog["exercises"]["sentadilla"]

    create_payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
            {"exercise_id": ex_remo.id, "position": 1, "duration_min": 7, "reps": "2x12"},
            {"exercise_id": ex_sentadilla.id, "position": 2, "duration_min": 9, "reps": "3x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=create_payload)
    block_id = create_resp.json()["id"]

    update_payload = _block_payload(
        entries=[
            {"exercise_id": ex_sentadilla.id, "position": 0, "duration_min": 9, "reps": "3x10"},
        ]
    )
    async with make_client(session) as client:
        put_resp = await client.put(f"{BASE}/blocks/{block_id}", json=update_payload)
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["exercise"]["id"] == ex_sentadilla.id
    assert body["total_duration_min"] == 9


@pytest.mark.asyncio
async def test_put_block_unknown_id_returns_404(session):
    """PUT /blocks/{id} for a non-existent id returns 404."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        resp = await client.put(f"{BASE}/blocks/99999", json=payload)
    assert resp.status_code == 404, resp.text


# ===========================================================================
# PATCH /blocks/{id}/archive — soft-archive toggle
# ===========================================================================


@pytest.mark.asyncio
async def test_patch_archive_sets_is_archived_true(session):
    """PATCH /blocks/{id}/archive with is_archived=true archives the block."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    block_id = create_resp.json()["id"]

    async with make_client(session) as client:
        resp = await client.patch(
            f"{BASE}/blocks/{block_id}/archive", json={"is_archived": True}
        )
    assert resp.status_code == 200, resp.text

    async with make_client(session) as client:
        get_resp = await client.get(f"{BASE}/blocks/{block_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["is_archived"] is True


@pytest.mark.asyncio
async def test_patch_archive_can_be_reverted(session):
    """PATCH /blocks/{id}/archive with is_archived=false un-archives the block."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    block_id = create_resp.json()["id"]

    async with make_client(session) as client:
        await client.patch(f"{BASE}/blocks/{block_id}/archive", json={"is_archived": True})

    async with make_client(session) as client:
        revert_resp = await client.patch(
            f"{BASE}/blocks/{block_id}/archive", json={"is_archived": False}
        )
    assert revert_resp.status_code == 200, revert_resp.text

    async with make_client(session) as client:
        list_resp = await client.get(f"{BASE}/blocks")
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert block_id in ids


@pytest.mark.asyncio
async def test_patch_archive_unknown_id_returns_404(session):
    """PATCH /blocks/{id}/archive for a non-existent id returns 404."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.patch(f"{BASE}/blocks/99999/archive", json={"is_archived": True})
    assert resp.status_code == 404, resp.text


# ===========================================================================
# Club scoping
# ===========================================================================


@pytest.mark.asyncio
async def test_list_blocks_excludes_other_clubs_blocks(session):
    """A block created under club 1 does not appear in club 2's coach list."""
    catalog = await _setup(session)
    await _seed_second_club_coach(session, club_id=2, user_id=11)
    await session.commit()

    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session, user=coach_user_obj(10)) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    block_id = create_resp.json()["id"]

    async with make_client(session, user=coach_user_obj(11)) as client:
        list_resp = await client.get(f"{BASE}/blocks")
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert block_id not in ids


@pytest.mark.asyncio
async def test_get_block_by_id_other_club_returns_404(session):
    """A coach from a different club cannot fetch another club's block by id."""
    catalog = await _setup(session)
    await _seed_second_club_coach(session, club_id=2, user_id=11)
    await session.commit()

    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session, user=coach_user_obj(10)) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    block_id = create_resp.json()["id"]

    async with make_client(session, user=coach_user_obj(11)) as client:
        resp = await client.get(f"{BASE}/blocks/{block_id}")
    assert resp.status_code == 404, resp.text


# ===========================================================================
# RBAC: parent → 403, admin → 200
# ===========================================================================


@pytest.mark.asyncio
async def test_parent_receives_403_on_create_block(session):
    """Parents cannot create strength blocks."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_parent_receives_403_on_list_blocks(session):
    """Parents cannot list strength blocks."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.get(f"{BASE}/blocks")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_create_and_read_block(session):
    """Admin role has full access to block creation and retrieval."""
    catalog = await _setup(session)
    # Admin needs a club membership for club-scoped block creation.
    admin = admin_user_obj(user_id=20)
    session.add(admin)
    await session.flush()
    session.add(
        ClubMember(
            club_id=1,
            user_id=20,
            role_in_club=ClubRole.admin,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    ex_flexiones = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[
            {"exercise_id": ex_flexiones.id, "position": 0, "duration_min": 5, "reps": "2x10"},
        ]
    )
    async with make_client(session, user=admin) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    block_id = create_resp.json()["id"]

    async with make_client(session, user=admin) as client:
        get_resp = await client.get(f"{BASE}/blocks/{block_id}")
    assert get_resp.status_code == 200, get_resp.text
