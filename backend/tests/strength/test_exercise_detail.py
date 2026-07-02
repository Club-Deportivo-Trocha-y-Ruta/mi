"""T011 — GET /api/strength/exercises/{id} detail endpoint.

Covers:
  - Happy path: ExerciseDetailOut shape (how_to, common_errors,
    illustration_ascii, illustration_alt) for a seeded exercise
  - 404 for an unknown id
  - 404 for a hidden exercise when requested by a non-admin coach

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Will fail until T014 (GET /exercises/{id} route) exists.
"""
from __future__ import annotations

import pytest

from tests.strength.conftest import (
    admin_user_obj,
    make_client,
    seed_club,
    seed_coach,
    seed_strength_catalog,
)

# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club, coach, and catalog; commit; return catalog dict."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_strength_catalog(session)
    await session.commit()
    return catalog


# ===========================================================================
# Happy path — full ExerciseDetailOut shape
# ===========================================================================


@pytest.mark.asyncio
async def test_get_exercise_detail_returns_200_and_full_shape(session):
    """GET /exercises/{id} returns 200 with how_to, common_errors, illustration_ascii, illustration_alt."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["flexiones"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/strength/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == ex.id
    assert body["slug"] == "flexiones-test"
    assert body["how_to"] == ex.how_to
    assert isinstance(body["how_to"], str) and len(body["how_to"]) > 0
    assert body["common_errors"] == ex.common_errors
    assert isinstance(body["common_errors"], str) and len(body["common_errors"]) > 0
    assert body["illustration_ascii"] == ex.illustration_ascii
    assert isinstance(body["illustration_ascii"], str) and len(body["illustration_ascii"]) > 0
    assert body["illustration_alt"] == ex.illustration_alt
    assert isinstance(body["illustration_alt"], str) and len(body["illustration_alt"]) > 0


@pytest.mark.asyncio
async def test_get_exercise_detail_includes_card_fields(session):
    """Detail response also carries the base ExerciseOut card fields."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["sentadilla"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/strength/exercises/{ex.id}")

    body = resp.json()
    assert body["equipment"] == "sin_equipo"
    assert body["movement_category"] == "inferior_bilateral"
    assert set(body["age_bands"]) == {"10-12", "13-15"}
    assert body["is_seeded"] is True
    assert body["is_hidden"] is False


# ===========================================================================
# 404 — unknown exercise id
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_exercise_id_returns_404(session):
    """GET /exercises/99999 for a non-existent id returns 404."""
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises/99999")

    assert resp.status_code == 404, resp.text


# ===========================================================================
# 404 — hidden exercise, non-admin coach
# ===========================================================================


@pytest.mark.asyncio
async def test_hidden_exercise_returns_404_for_coach(session):
    """A hidden exercise (is_hidden=True) returns 404 for a non-admin coach."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["trackstand_oculto"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/strength/exercises/{ex.id}")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_hidden_exercise_is_returned_for_admin(session):
    """A hidden exercise is still served to an admin (curation access)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["trackstand_oculto"]
    admin = admin_user_obj(user_id=20)

    async with make_client(session, user=admin) as client:
        resp = await client.get(f"/api/strength/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_hidden"] is True
    assert body["slug"] == "trackstand-oculto-test"
