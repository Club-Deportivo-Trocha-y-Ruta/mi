"""T0xx — RBAC negative-path sweep for the Strength Training Library (feature 021).

Mirrors ``backend/tests/technique/test_rbac.py`` (feature 018) exactly in
shape and intent, adapted to the strength router's endpoint list.

Endpoints covered (contracts/strength-api.md):
  GET    /api/strength/exercises
  GET    /api/strength/exercises/{id}
  POST   /api/strength/blocks
  GET    /api/strength/blocks
  GET    /api/strength/blocks/{id}
  PUT    /api/strength/blocks/{id}
  PATCH  /api/strength/blocks/{id}/archive
  POST   /api/strength/blocks/{id}/attach
  DELETE /api/strength/blocks/{id}/attach/{session_id}
  GET    /api/strength/sessions/{id}/blocks
  GET    /api/strength/athletes/{id}/progress
  POST   /api/strength/athletes/{id}/progress

Rules under test (mirrors ``_require_coach_or_admin`` in
``app/routers/strength.py``, same pattern as feature 018's
``_require_coach_or_admin`` in ``app/routers/technique.py``):
  - no auth  → 401 (HTTPBearer raises 401 when Authorization header is absent)
  - parent   → 403 (authenticated but forbidden role)

Positive-path (coach/admin → 200/201) coverage already lives in
test_catalog_filter.py, test_exercise_detail.py, test_blocks.py, test_attach.py
and test_progress_privacy.py — this file is the single place that guards
against RBAC regressions across *every* strength endpoint at once, and gives
each endpoint an explicit 401 + 403 negative-path test for clear failure
messages.

No MySQL, no live JWT: aiosqlite in-memory DB + dependency_overrides pattern
from the strength conftest.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from app.dependencies import get_current_user
from app.main import app
from app.models.technique_exercise import AgeBand
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from tests.strength.conftest import (
    make_client,
    parent_user_obj,
    seed_admin,
    seed_athlete_record,
    seed_athlete_user,
    seed_club,
    seed_coach,
    seed_parent,
    seed_strength_block,
    seed_strength_catalog,
)

BASE = "/api/strength"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_minimal(session, *, with_catalog: bool = False) -> dict:
    """Insert the minimal rows required for RBAC tests.

    Always seeds: club 1, coach (id=10) with club membership, admin (id=20),
    parent (id=30).  When ``with_catalog=True`` also inserts the
    representative strength catalog so that list/detail endpoints have real
    rows to return on the happy path (used implicitly by fixture reuse; the
    negative-path assertions in this file never depend on catalog contents).
    """
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_admin(session, user_id=20)
    await seed_parent(session, user_id=30)
    catalog: dict = {}
    if with_catalog:
        catalog = await seed_strength_catalog(session)
    await session.commit()
    return catalog


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


async def _seed_athlete(session, *, athlete_id: int = 1, user_id: int = 40) -> None:
    """Insert an athlete user + record in club 1 and commit."""
    await seed_athlete_user(session, user_id=user_id)
    await seed_athlete_record(session, athlete_id=athlete_id, user_id=user_id, club_id=1)
    await session.commit()


def _block_payload(*, entries: list[dict]) -> dict:
    return {
        "name": "Bloque de fuerza de prueba",
        "target_age_band": "13-15",
        "duration_target_min": 30,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# GET /api/strength/exercises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_exercises_parent_403(session):
    await _seed_minimal(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_exercises_anonymous_401(session):
    await _seed_minimal(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/strength/exercises/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exercise_detail_parent_403(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_exercise_detail_anonymous_401(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/strength/blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_block_parent_403(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[{"exercise_id": ex.id, "position": 0, "duration_min": 10}]
    )
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_block_anonymous_401(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    payload = _block_payload(
        entries=[{"exercise_id": ex.id, "position": 0, "duration_min": 10}]
    )
    async with make_client(session, authed=False) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/strength/blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocks_parent_403(session):
    await _seed_minimal(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/blocks")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_blocks_anonymous_401(session):
    await _seed_minimal(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/blocks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/strength/blocks/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_block_parent_403(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/blocks/{block.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_block_anonymous_401(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/blocks/{block.id}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/strength/blocks/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_block_parent_403(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    payload = _block_payload(
        entries=[{"exercise_id": ex.id, "position": 0, "duration_min": 10}]
    )
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.put(f"{BASE}/blocks/{block.id}", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_block_anonymous_401(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["flexiones"]
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    payload = _block_payload(
        entries=[{"exercise_id": ex.id, "position": 0, "duration_min": 10}]
    )
    async with make_client(session, authed=False) as client:
        resp = await client.put(f"{BASE}/blocks/{block.id}", json=payload)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/strength/blocks/{id}/archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_block_parent_403(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.patch(
            f"{BASE}/blocks/{block.id}/archive", json={"is_archived": True}
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_block_anonymous_401(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.patch(
            f"{BASE}/blocks/{block.id}/archive", json={"is_archived": True}
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/strength/blocks/{id}/attach
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_block_parent_403(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_attach_block_anonymous_401(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"{BASE}/blocks/{block.id}/attach",
            json={"training_session_id": ts.id},
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/strength/blocks/{id}/attach/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detach_block_parent_403(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.delete(f"{BASE}/blocks/{block.id}/attach/{ts.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_detach_block_anonymous_401(session):
    await _seed_minimal(session)
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.delete(f"{BASE}/blocks/{block.id}/attach/{ts.id}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/strength/sessions/{id}/blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_session_blocks_parent_403(session):
    await _seed_minimal(session)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/sessions/{ts.id}/blocks")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_session_blocks_anonymous_401(session):
    await _seed_minimal(session)
    ts = await _seed_training_session(session)
    await session.commit()
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/sessions/{ts.id}/blocks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/strength/athletes/{id}/progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_athlete_progress_parent_403(session):
    await _seed_minimal(session)
    await _seed_athlete(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_athlete_progress_anonymous_401(session):
    await _seed_minimal(session)
    await _seed_athlete(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/strength/athletes/{id}/progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_athlete_progress_parent_403(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    await _seed_athlete(session)
    ex = catalog["exercises"]["flexiones"]
    payload = {
        "exercise_id": ex.id,
        "status": "logrado",
        "coach_note": "Nota ficticia de prueba.",
        "season": 2026,
    }
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(f"{BASE}/athletes/1/progress", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_athlete_progress_anonymous_401(session):
    catalog = await _seed_minimal(session, with_catalog=True)
    await _seed_athlete(session)
    ex = catalog["exercises"]["flexiones"]
    payload = {
        "exercise_id": ex.id,
        "status": "logrado",
        "coach_note": "Nota ficticia de prueba.",
        "season": 2026,
    }
    async with make_client(session, authed=False) as client:
        resp = await client.post(f"{BASE}/athletes/1/progress", json=payload)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cross-role consistency: every endpoint in one sweep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_endpoints_role_matrix(session):
    """Sweep all 12 strength endpoints with coach/admin (200/201) vs parent
    (403) vs anonymous (401) in a single place.

    Individual endpoint tests above give clearer failure messages; this one
    catches cross-cutting RBAC omissions (e.g. a new endpoint added without
    the coach/admin gate).
    """
    catalog = await _seed_minimal(session, with_catalog=True)
    await _seed_athlete(session)
    ex = catalog["exercises"]["flexiones"]
    block = await seed_strength_block(session, target_age_band=AgeBand.BAND_13_15)
    ts = await _seed_training_session(session)
    await session.commit()

    block_payload = _block_payload(
        entries=[{"exercise_id": ex.id, "position": 0, "duration_min": 10}]
    )
    progress_payload = {
        "exercise_id": ex.id,
        "status": "logrado",
        "coach_note": "Nota ficticia de prueba.",
        "season": 2026,
    }

    # (method, url, kwargs) — GET/POST/PUT/PATCH/DELETE across every route.
    requests: list[tuple[str, str, dict]] = [
        ("get", f"{BASE}/exercises", {}),
        ("get", f"{BASE}/exercises/{ex.id}", {}),
        ("post", f"{BASE}/blocks", {"json": block_payload}),
        ("get", f"{BASE}/blocks", {}),
        ("get", f"{BASE}/blocks/{block.id}", {}),
        ("put", f"{BASE}/blocks/{block.id}", {"json": block_payload}),
        (
            "patch",
            f"{BASE}/blocks/{block.id}/archive",
            {"json": {"is_archived": True}},
        ),
        (
            "post",
            f"{BASE}/blocks/{block.id}/attach",
            {"json": {"training_session_id": ts.id}},
        ),
        ("delete", f"{BASE}/blocks/{block.id}/attach/{ts.id}", {}),
        ("get", f"{BASE}/sessions/{ts.id}/blocks", {}),
        ("get", f"{BASE}/athletes/1/progress", {}),
        ("post", f"{BASE}/athletes/1/progress", {"json": progress_payload}),
    ]

    # parent: all 403
    async with make_client(session, user=parent_user_obj(30)) as client:
        for method, url, kwargs in requests:
            resp = await getattr(client, method)(url, **kwargs)
            assert resp.status_code == 403, (
                f"Expected 403 for parent on {method.upper()} {url}; "
                f"got {resp.status_code}: {resp.text[:200]}"
            )

    # anonymous: all 401
    # ``make_client(authed=False)`` intentionally skips re-registering the
    # get_current_user override, but it does not clear a prior one either —
    # pop it explicitly here so the anonymous block isn't silently
    # authenticated as the parent user from the block above.
    app.dependency_overrides.pop(get_current_user, None)
    async with make_client(session, authed=False) as client:
        for method, url, kwargs in requests:
            resp = await getattr(client, method)(url, **kwargs)
            assert resp.status_code == 401, (
                f"Expected 401 for anonymous on {method.upper()} {url}; "
                f"got {resp.status_code}: {resp.text[:200]}"
            )
