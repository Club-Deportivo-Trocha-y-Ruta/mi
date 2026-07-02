"""T020 — POST/DELETE /api/strength/blocks/{id}/attach + GET /sessions/{id}/blocks.

Covers (contracts/strength-api.md §Session attachment):
  - POST /blocks/{block_id}/attach → 201, and the block then appears via
    GET /sessions/{training_session_id}/blocks (FR — session plan rendering).
  - Re-attaching the same (block_id, training_session_id) pair → 409
    (unique pair constraint).
  - DELETE /blocks/{block_id}/attach/{training_session_id} → 204, and the
    block no longer appears in GET /sessions/{id}/blocks afterward.
  - 404 when attaching an unknown block_id or an unknown training_session_id.
  - RBAC: parent → 403 on attach.
  - RESTRICT survives: deleting (cancelling) the training session via the
    existing training-session deletion path (DELETE /api/training-sessions/{id})
    does NOT delete the strength block — the block remains fetchable via
    GET /api/strength/blocks/{id} after the session is gone.

Will fail until T021 (blocks CRUD router: GET /blocks/{id}) and T022 (attach/
detach/session-blocks endpoints) exist.

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Seed data uses fictitious names/dates — never real TyR athlete data.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from app.models.technique_exercise import AgeBand
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from tests.strength.conftest import (
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_strength_block,
)

BASE = "/api/strength"

# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _seed_base(session) -> dict:
    """Seed club + coach; commit. Returns nothing extra (blocks/sessions are
    seeded per-test to keep fixtures explicit)."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await session.commit()


async def _seed_training_session(
    session,
    *,
    club_id: int = 1,
    created_by_user_id: int = 10,
    scheduled_date: date = date(2026, 7, 10),
) -> TrainingSession:
    """Insert a bare TrainingSession (no wizard) and commit."""
    ts = TrainingSession(
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        status=SessionStatus.PLANNED,
        session_kind=SessionKind.ENTRENAMIENTO,
        scheduled_date=scheduled_date,
        scheduled_start_time=time(10, 0),
        duration_min=45,
        location="Cancha Ficticia",
        technical_focus="Fuerza (test)",
    )
    session.add(ts)
    await session.commit()
    await session.refresh(ts)
    return ts


# ---------------------------------------------------------------------------
# Happy path: attach → 201, appears in session blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_returns_201_and_appears_in_session_blocks(session):
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["training_session_id"] == ts.id
    assert body["block_id"] == block.id
    assert "id" in body
    assert "position" in body
    assert "attached_at" in body

    async with make_client(session) as client:
        blocks_resp = await client.get(f"{BASE}/sessions/{ts.id}/blocks")
    assert blocks_resp.status_code == 200, blocks_resp.text
    items = blocks_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == block.id


# ---------------------------------------------------------------------------
# Duplicate attach → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reattach_same_pair_returns_409(session):
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session) as client:
        first = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert first.status_code == 201, first.text

    async with make_client(session) as client:
        second = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert second.status_code == 409, second.text


# ---------------------------------------------------------------------------
# 404 — unknown block_id / unknown training_session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_unknown_block_returns_404(session):
    await _seed_base(session)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/blocks/99999/attach",
            json={"training_session_id": ts.id},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_attach_unknown_training_session_returns_404(session):
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": 99999},
        )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# RBAC — parent receives 403 on attach
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_parent_receives_403(session):
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Detach → 204, removed from session blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detach_returns_204_and_removes_from_session_blocks(session):
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert attach_resp.status_code == 201, attach_resp.text

    async with make_client(session) as client:
        detach_resp = await client.delete(f"{BASE}/blocks/{block.id}/attach/{ts.id}")
    assert detach_resp.status_code == 204, detach_resp.text

    async with make_client(session) as client:
        blocks_resp = await client.get(f"{BASE}/sessions/{ts.id}/blocks")
    assert blocks_resp.status_code == 200, blocks_resp.text
    assert blocks_resp.json()["items"] == []


# ---------------------------------------------------------------------------
# RESTRICT survives: deleting the training session does NOT delete the block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleting_training_session_does_not_delete_strength_block(session):
    """Cancelling/deleting a training session (existing deletion path) must
    leave the attached strength block intact — RESTRICT semantics (data-model).

    The block must still be fetchable via GET /api/strength/blocks/{id} after
    the training session that had it attached is gone.
    """
    await _seed_base(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        attach_resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert attach_resp.status_code == 201, attach_resp.text

    # Delete the training session via the existing training-session deletion
    # path (DELETE /api/training-sessions/{id}).
    async with make_client(session, user=coach_user_obj(10)) as client:
        delete_resp = await client.delete(f"/api/training-sessions/{ts.id}")
    assert delete_resp.status_code == 204, delete_resp.text

    # The strength block must survive and still be fetchable.
    async with make_client(session, user=coach_user_obj(10)) as client:
        block_resp = await client.get(f"{BASE}/blocks/{block.id}")
    assert block_resp.status_code == 200, block_resp.text
    assert block_resp.json()["id"] == block.id
