"""T010 — RBAC for catalog/detail read endpoints (feature 018).

Endpoints covered:
  GET /api/technique/skills
  GET /api/technique/materials
  GET /api/technique/exercises
  GET /api/technique/exercises/{id}

Rules under test (FR-021, data-model rule 8):
  - coach   → 200 on every read endpoint
  - admin   → 200 on every read endpoint
  - parent  → 403 (authenticated but forbidden role)
  - no auth → 401 (HTTPBearer raises 401 when Authorization header is absent)

No MySQL, no live JWT: aiosqlite in-memory DB + dependency_overrides pattern
from the technique conftest.
"""
from __future__ import annotations

import pytest

from tests.technique.conftest import (
    admin_user_obj,
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_admin,
    seed_parent,
    seed_technique_catalog,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/technique"


async def _seed_minimal(session, *, with_catalog: bool = False) -> dict:
    """Insert the minimal rows required for catalog read tests.

    Always seeds: club 1, coach (id=10) with club membership, admin (id=20),
    parent (id=30).  When ``with_catalog=True`` also inserts the representative
    technique catalog so that list/detail endpoints return real rows.
    """
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_admin(session, user_id=20)
    await seed_parent(session, user_id=30)
    catalog: dict = {}
    if with_catalog:
        catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ---------------------------------------------------------------------------
# GET /api/technique/skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_coach_200(session):
    """Coach can list technique skills (taxonomy list)."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # Seeded catalog has 3 skills; at minimum 1 must come back.
    assert len(body) >= 1
    # Each item must expose the contract fields.
    first = body[0]
    assert "code" in first
    assert "slug" in first
    assert "name" in first
    assert "sort_order" in first
    assert "focus" in first


@pytest.mark.asyncio
async def test_skills_admin_200(session):
    """Admin can list technique skills."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/skills")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_skills_parent_403(session):
    """Parent receives 403 on the skills taxonomy endpoint."""
    await _seed_minimal(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/skills")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_skills_anonymous_401(session):
    """Unauthenticated request receives 401 (no Authorization header)."""
    await _seed_minimal(session)
    # authed=False removes the get_current_user override so the real JWT auth
    # fires.  With no Authorization header the bearer scheme returns 401.
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/skills")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/technique/materials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_materials_coach_200(session):
    """Coach can list technique materials."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/materials")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # Seeded catalog has 4 materials.
    assert len(body) >= 1
    first = body[0]
    assert "slug" in first
    assert "name" in first
    assert "is_none" in first


@pytest.mark.asyncio
async def test_materials_admin_200(session):
    """Admin can list technique materials."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/materials")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_materials_parent_403(session):
    """Parent receives 403 on the materials endpoint."""
    await _seed_minimal(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/materials")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_materials_anonymous_401(session):
    """Unauthenticated request receives 401 on materials endpoint."""
    await _seed_minimal(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/materials")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/technique/exercises  (catalog list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exercises_coach_200_with_items(session):
    """Coach gets 200 and a populated items list when catalog is seeded."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    # 4 visible exercises (trackstand is hidden; include_hidden=False by default)
    assert body["total"] == 4
    assert len(body["items"]) == 4


@pytest.mark.asyncio
async def test_exercises_coach_200_empty_when_no_catalog(session):
    """Coach gets 200 { items: [], total: 0 } when the catalog is empty (FR-004)."""
    await _seed_minimal(session, with_catalog=False)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_exercises_admin_200(session):
    """Admin gets 200 on the exercises list."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_exercises_include_hidden_coach_200(session):
    """Coach with include_hidden=true receives hidden exercises too."""
    await _seed_minimal(session, with_catalog=True)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises?include_hidden=true")
    assert resp.status_code == 200
    body = resp.json()
    # All 5 seeded exercises including the hidden trackstand.
    assert body["total"] == 5


@pytest.mark.asyncio
async def test_exercises_parent_403(session):
    """Parent receives 403 on the exercises list endpoint."""
    await _seed_minimal(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_exercises_anonymous_401(session):
    """Unauthenticated request receives 401 on exercises list."""
    await _seed_minimal(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/exercises")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/technique/exercises/{id}  (exercise detail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exercise_detail_coach_200(session):
    """Coach gets full exercise detail including how_to and layout fields."""
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 200
    body = resp.json()
    # Detail fields beyond the list item.
    assert "how_to" in body
    assert "layout_ascii" in body
    assert "layout_alt" in body
    assert "confidence" in body
    assert "created_at" in body
    assert "updated_at" in body
    assert body["slug"] == "pie-abajo-test"


@pytest.mark.asyncio
async def test_exercise_detail_admin_200(session):
    """Admin gets 200 on exercise detail."""
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["slalom"]
    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "slalom-test"


@pytest.mark.asyncio
async def test_exercise_detail_hidden_still_returned_coach(session):
    """Hidden exercises are returned on detail (FR-019) — is_hidden=True in body."""
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["trackstand"]
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 200
    assert resp.json()["is_hidden"] is True


@pytest.mark.asyncio
async def test_exercise_detail_not_found_404(session):
    """Unknown exercise id returns 404."""
    await _seed_minimal(session)
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/exercises/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_exercise_detail_parent_403(session):
    """Parent receives 403 on exercise detail even with a valid exercise id."""
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_exercise_detail_anonymous_401(session):
    """Unauthenticated request receives 401 on exercise detail."""
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cross-role consistency: same endpoint, all roles in one sweep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_read_endpoints_role_matrix(session):
    """Sweep all 4 catalog read endpoints with coach, admin, parent.

    This is a compact matrix test that guards against future RBAC regressions
    in a single place. Individual role/endpoint tests above give clearer failure
    messages; this one catches cross-cutting omissions.
    """
    catalog = await _seed_minimal(session, with_catalog=True)
    ex = catalog["exercises"]["semaforo"]

    endpoints = [
        f"{BASE}/skills",
        f"{BASE}/materials",
        f"{BASE}/exercises",
        f"{BASE}/exercises/{ex.id}",
    ]

    # coach and admin: all 200
    for role_user in (coach_user_obj(10), admin_user_obj(20)):
        async with make_client(session, user=role_user) as client:
            for url in endpoints:
                resp = await client.get(url)
                assert resp.status_code == 200, (
                    f"Expected 200 for {role_user.role} on {url}; "
                    f"got {resp.status_code}: {resp.text[:200]}"
                )

    # parent: all 403
    async with make_client(session, user=parent_user_obj(30)) as client:
        for url in endpoints:
            resp = await client.get(url)
            assert resp.status_code == 403, (
                f"Expected 403 for parent on {url}; "
                f"got {resp.status_code}: {resp.text[:200]}"
            )
