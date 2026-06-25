"""T019 — GET /api/technique/exercises/{id} detail endpoint.

Covers:
  - Happy path: ExerciseDetail shape for a regular (non-gymkhana) exercise
  - Gymkhana exercise: layout_ascii and layout_alt are non-null
  - No-material exercise: the sin_material sentinel appears and is_none=True
  - Hidden exercise is still served by the detail endpoint (FR-019)
  - 404 for an unknown id
  - RBAC: parent → 403

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Seed data via ``seed_technique_catalog`` from conftest:

  pie-abajo-test   facil  game    conos            bands=[7-9, 10-12, 13-15]  skills=[posicion, frenado]
  slalom-test      facil  gymk    conos            bands=[7-9, 10-12]         skills=[posicion]   layout non-null
  limbo-test       media  gymk    estacas+llantas  bands=[10-12, 13-15]       skills=[separacion] layout non-null
  semaforo-test    facil  game    sin_material     bands=[7-9, 10-12]         skills=[frenado]
  trackstand-test  avanzada      sin_material     bands=[13-15]              skills=[posicion]   is_hidden=True
"""
from __future__ import annotations

import pytest

from tests.technique.conftest import (
    admin_user_obj,
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club, coach, and catalog; commit; return catalog dict."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ---------------------------------------------------------------------------
# ExerciseDetail field contract (all fields present)
# ---------------------------------------------------------------------------

_DETAIL_FIELDS = (
    "id",
    "slug",
    "name",
    "summary",
    "difficulty",
    "is_game",
    "is_gymkhana",
    "age_bands",
    "skills",
    "materials",
    "is_seeded",
    "is_hidden",
    "how_to",
    "layout_ascii",
    "layout_alt",
    "confidence",
    "created_at",
    "updated_at",
)


# ===========================================================================
# Happy path — regular (non-gymkhana) exercise
# ===========================================================================


@pytest.mark.asyncio
async def test_get_exercise_detail_returns_200_and_full_shape(session):
    """GET /exercises/{id} for a regular exercise returns 200 with all ExerciseDetail fields."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    for field in _DETAIL_FIELDS:
        assert field in body, f"Missing ExerciseDetail field: {field}"


@pytest.mark.asyncio
async def test_get_exercise_detail_correct_scalar_values(session):
    """Scalar values on the returned ExerciseDetail match what was seeded."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    body = resp.json()
    assert body["id"] == ex.id
    assert body["slug"] == "pie-abajo-test"
    assert body["difficulty"] == "facil"
    assert body["is_game"] is True
    assert body["is_gymkhana"] is False
    assert body["is_seeded"] is True
    assert body["is_hidden"] is False


@pytest.mark.asyncio
async def test_get_exercise_detail_includes_nested_skills(session):
    """Skills collection is non-empty and each item has code/slug/name."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # skills=[posicion, frenado]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    skills = resp.json()["skills"]
    assert len(skills) == 2
    skill_slugs = {s["slug"] for s in skills}
    assert skill_slugs == {"posicion", "frenado"}
    for s in skills:
        assert "code" in s
        assert "slug" in s
        assert "name" in s


@pytest.mark.asyncio
async def test_get_exercise_detail_includes_nested_materials(session):
    """Materials collection is non-empty and each item has slug/name/is_none."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # materials=[conos]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    materials = resp.json()["materials"]
    assert len(materials) == 1
    mat = materials[0]
    assert mat["slug"] == "conos"
    assert mat["is_none"] is False
    assert "name" in mat


@pytest.mark.asyncio
async def test_get_exercise_detail_includes_age_bands(session):
    """age_bands list is populated and matches the seeded bands."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # bands=[7-9, 10-12, 13-15]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    bands = resp.json()["age_bands"]
    assert set(bands) == {"7-9", "10-12", "13-15"}


@pytest.mark.asyncio
async def test_get_exercise_detail_how_to_is_non_empty_string(session):
    """how_to field is a non-empty string (detail-only field, absent from list items)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    how_to = resp.json()["how_to"]
    assert isinstance(how_to, str)
    assert len(how_to) > 0


# ===========================================================================
# Gymkhana exercise — layout_ascii and layout_alt are non-null
# ===========================================================================


@pytest.mark.asyncio
async def test_gymkhana_exercise_has_non_null_layout_ascii(session):
    """A gymkhana exercise returns a non-null, non-empty layout_ascii (FR-008)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]  # is_gymkhana=True

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_gymkhana"] is True
    assert body["layout_ascii"] is not None
    assert isinstance(body["layout_ascii"], str)
    assert len(body["layout_ascii"]) > 0


@pytest.mark.asyncio
async def test_gymkhana_exercise_has_non_null_layout_alt(session):
    """A gymkhana exercise returns a non-null, non-empty layout_alt for screen readers."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    body = resp.json()
    assert body["layout_alt"] is not None
    assert isinstance(body["layout_alt"], str)
    assert len(body["layout_alt"]) > 0


@pytest.mark.asyncio
async def test_gymkhana_exercise_limbo_layouts_non_null(session):
    """Second gymkhana exercise (limbo) also returns non-null layout fields."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["limbo"]  # is_gymkhana=True, difficulty=media

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_gymkhana"] is True
    assert body["layout_ascii"] is not None and len(body["layout_ascii"]) > 0
    assert body["layout_alt"] is not None and len(body["layout_alt"]) > 0


@pytest.mark.asyncio
async def test_non_gymkhana_exercise_layout_fields_are_null(session):
    """A non-gymkhana exercise has null layout_ascii and layout_alt (they are optional)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # is_gymkhana=False

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    body = resp.json()
    assert body["is_gymkhana"] is False
    assert body["layout_ascii"] is None
    assert body["layout_alt"] is None


# ===========================================================================
# No-material exercise — sin_material sentinel appears with is_none=True
# ===========================================================================


@pytest.mark.asyncio
async def test_no_material_exercise_surfaces_sin_material_sentinel(session):
    """An exercise linked only to sin_material returns that sentinel in the materials list with is_none=True."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["semaforo"]  # materials=[sin_material]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    materials = resp.json()["materials"]
    assert len(materials) == 1
    mat = materials[0]
    assert mat["slug"] == "sin_material"
    assert mat["is_none"] is True


@pytest.mark.asyncio
async def test_no_material_exercise_hidden_also_returns_sin_material(session):
    """Hidden no-material exercise (trackstand) also surfaces sin_material sentinel via detail (FR-019)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["trackstand"]  # is_hidden=True, materials=[sin_material]

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    materials = resp.json()["materials"]
    assert any(m["slug"] == "sin_material" and m["is_none"] is True for m in materials)


# ===========================================================================
# Hidden exercise — still served by detail (FR-019)
# ===========================================================================


@pytest.mark.asyncio
async def test_hidden_exercise_is_returned_by_detail_endpoint(session):
    """Detail endpoint serves hidden exercises (is_hidden=True) — FR-019.

    The list endpoint excludes them by default but the detail never does.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["trackstand"]  # is_hidden=True

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_hidden"] is True
    assert body["slug"] == "trackstand-test"


# ===========================================================================
# 404 — unknown exercise id
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_exercise_id_returns_404(session):
    """GET /exercises/99999 for a non-existent id returns 404."""
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises/99999")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_zero_exercise_id_returns_404(session):
    """id=0 is not a valid PK and must return 404 (not 500 or 422)."""
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises/0")

    assert resp.status_code == 404, resp.text


# ===========================================================================
# RBAC — parent → 403 (FR-021)
# ===========================================================================


@pytest.mark.asyncio
async def test_parent_receives_403_on_detail_endpoint(session):
    """Parents are blocked from the exercise detail endpoint (FR-021)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    parent = parent_user_obj(user_id=30)

    async with make_client(session, user=parent) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_access_detail_endpoint(session):
    """Admin role has full access to the exercise detail endpoint."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    async with make_client(session, user=admin) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "slalom-test"
