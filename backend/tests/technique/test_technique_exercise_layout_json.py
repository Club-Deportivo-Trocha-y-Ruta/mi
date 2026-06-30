"""T015 — GET /api/technique/exercises/{id} returns layout_json (feature 019 Phase A).

Contract assertions (contracts/rest-api.md):
  - ExerciseDetail includes layout_json: GymkhanaLayout | null
  - layout_json is non-null and structurally valid for a gymkhana exercise that
    has been seeded/backfilled with a GymkhanaLayout (round-trip via
    POST /api/technique/exercises then GET /api/technique/exercises/{id}).
  - layout_json is null for a non-gymkhana exercise.
  - ExerciseListItem (GET /api/technique/exercises) does NOT contain layout_json
    (list reads stay lean).

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Seed data via helpers from tests/technique/conftest.py (fictitious names/DOBs).
"""
from __future__ import annotations

import pytest

from tests.technique.conftest import (
    admin_user_obj,
    make_client,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

# ---------------------------------------------------------------------------
# Shared setup helper (mirrors pattern in test_exercise_detail.py)
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club, coach, and catalog; commit; return catalog dict."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ---------------------------------------------------------------------------
# A minimal valid GymkhanaLayout payload (no free-text label — FR-023).
# Uses the 'slalom-test' gymkhana exercise created by seed_technique_catalog.
# ---------------------------------------------------------------------------

_LAYOUT_PAYLOAD = {
    "width": 100.0,
    "height": 60.0,
    "elements": [
        {"kind": "cone", "x": 10.0, "y": 30.0},
        {"kind": "cone", "x": 50.0, "y": 30.0},
        {"kind": "cone", "x": 90.0, "y": 30.0},
        {"kind": "line", "x": 5.0, "y": 30.0, "style": "dashed"},
        {"kind": "arrow", "x": 5.0, "y": 30.0, "rotation": 0.0},
    ],
}


# ===========================================================================
# Round-trip: create gymkhana with layout_json → GET returns layout_json
# ===========================================================================


@pytest.mark.asyncio
async def test_gymkhana_detail_returns_layout_json_after_update(session):
    """PUT layout_json on a gymkhana exercise; GET /exercises/{id} returns it round-trip.

    This is the core T015 assertion: ExerciseDetail.layout_json is not null
    after writing a valid GymkhanaLayout to the exercise.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]  # is_gymkhana=True, seeded with ASCII layout

    admin = admin_user_obj(user_id=20)

    # Write layout_json via PUT (curation endpoint).
    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": _LAYOUT_PAYLOAD,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        put_resp = await client.put(
            f"/api/technique/exercises/{ex.id}", json=put_payload
        )
        assert put_resp.status_code == 200, put_resp.text

        # Fetch the detail.
        get_resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()

    assert "layout_json" in body, "ExerciseDetail must expose layout_json"
    lj = body["layout_json"]
    assert lj is not None, "layout_json should be non-null after backfill/update"
    assert lj["width"] == pytest.approx(100.0)
    assert lj["height"] == pytest.approx(60.0)
    assert isinstance(lj["elements"], list)
    assert len(lj["elements"]) == len(_LAYOUT_PAYLOAD["elements"])


@pytest.mark.asyncio
async def test_gymkhana_detail_layout_json_element_kinds_preserved(session):
    """Element kinds are round-tripped without alteration."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["limbo"]  # second gymkhana exercise

    admin = admin_user_obj(user_id=20)

    limbo_layout = {
        "width": 80.0,
        "height": 40.0,
        "elements": [
            {"kind": "gate", "x": 40.0, "y": 20.0},
            {"kind": "line", "x": 0.0, "y": 20.0, "style": "solid"},
        ],
    }

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": limbo_layout,
        "confidence": ex.confidence,
        "skill_slugs": ["separacion"],
        "material_slugs": ["estacas", "llantas"],
        "age_bands": ["10-12", "13-15"],
    }

    async with make_client(session, user=admin) as client:
        await client.put(f"/api/technique/exercises/{ex.id}", json=put_payload)
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    lj = resp.json()["layout_json"]
    assert lj is not None
    kinds = [el["kind"] for el in lj["elements"]]
    assert kinds == ["gate", "line"]


@pytest.mark.asyncio
async def test_gymkhana_detail_layout_json_label_with_number_preserved(session):
    """Element label 'cone #2' (controlled set) survives the round-trip (FR-023 allows kind#n)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]

    admin = admin_user_obj(user_id=20)

    layout_with_label = {
        "width": 60.0,
        "height": 40.0,
        "elements": [
            {"kind": "cone", "x": 10.0, "y": 20.0, "label": "cone #1"},
            {"kind": "cone", "x": 50.0, "y": 20.0, "label": "cone #2"},
        ],
    }

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": layout_with_label,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        put_resp = await client.put(
            f"/api/technique/exercises/{ex.id}", json=put_payload
        )
        assert put_resp.status_code == 200, put_resp.text

        get_resp = await client.get(f"/api/technique/exercises/{ex.id}")

    lj = get_resp.json()["layout_json"]
    assert lj is not None
    labels = [el.get("label") for el in lj["elements"]]
    assert "cone #1" in labels
    assert "cone #2" in labels


# ===========================================================================
# Non-gymkhana exercise: layout_json is null
# ===========================================================================


@pytest.mark.asyncio
async def test_non_gymkhana_detail_layout_json_is_null(session):
    """ExerciseDetail.layout_json is null for a non-gymkhana exercise (pie-abajo)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # is_gymkhana=False, no layout at all

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_gymkhana"] is False
    assert "layout_json" in body, "ExerciseDetail must always expose layout_json key"
    assert body["layout_json"] is None


@pytest.mark.asyncio
async def test_gymkhana_without_layout_json_returns_null_not_absent(session):
    """A gymkhana exercise that was never backfilled returns layout_json=null (not absent)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    # slalom is seeded with ASCII but layout_json is null (no backfill in conftest).

    async with make_client(session) as client:
        resp = await client.get(f"/api/technique/exercises/{ex.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_gymkhana"] is True
    assert "layout_json" in body
    # Before any backfill, layout_json must be null (not missing from the response).
    assert body["layout_json"] is None


# ===========================================================================
# ExerciseListItem does NOT include layout_json (list reads stay lean)
# ===========================================================================


@pytest.mark.asyncio
async def test_catalog_list_item_does_not_expose_layout_json(session):
    """GET /api/technique/exercises list items must NOT include layout_json.

    ExerciseListItem is intentionally lean; layout is detail-only (contracts/rest-api.md).
    The list endpoint returns {"items": [...], "total": N} (FR-004 envelope).
    """
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    # The catalog list endpoint returns a {"items": [...], "total": N} envelope.
    assert "items" in payload, f"Expected envelope with 'items' key, got: {payload}"
    items = payload["items"]
    assert len(items) > 0, "Catalog must be non-empty after seed"

    for item in items:
        assert "layout_json" not in item, (
            f"ExerciseListItem must NOT expose layout_json (found in slug={item.get('slug')})"
        )


@pytest.mark.asyncio
async def test_catalog_list_gymkhana_items_do_not_expose_layout_json(session):
    """Gymkhana exercises in the catalog list also omit layout_json."""
    await _setup(session)

    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    gymkhana_items = [i for i in items if i.get("is_gymkhana") is True]
    assert len(gymkhana_items) > 0, "Seed must include at least one gymkhana exercise"

    for item in gymkhana_items:
        assert "layout_json" not in item, (
            f"ExerciseListItem for gymkhana slug={item.get('slug')} must NOT expose layout_json"
        )


# ===========================================================================
# Validation: malformed layout_json is rejected with 422
# ===========================================================================


@pytest.mark.asyncio
async def test_put_rejects_unknown_element_kind(session):
    """PUT with an unknown element kind returns 422 (validation guard FR-023)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    bad_layout = {
        "width": 60.0,
        "height": 40.0,
        "elements": [
            {"kind": "unknown_shape", "x": 10.0, "y": 20.0},
        ],
    }

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": bad_layout,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        resp = await client.put(f"/api/technique/exercises/{ex.id}", json=put_payload)

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_put_rejects_element_out_of_canvas_bounds(session):
    """PUT with element coordinates outside [0,width]×[0,height] returns 422."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    bad_layout = {
        "width": 60.0,
        "height": 40.0,
        "elements": [
            # x=70 > width=60 → out of bounds
            {"kind": "cone", "x": 70.0, "y": 20.0},
        ],
    }

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": bad_layout,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        resp = await client.put(f"/api/technique/exercises/{ex.id}", json=put_payload)

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_put_rejects_free_text_label_on_element(session):
    """PUT with a free-text label on an element returns 422 (Phase A guard FR-023)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    bad_layout = {
        "width": 60.0,
        "height": 40.0,
        "elements": [
            # Free-text label — not in controlled set 'kind [#n]'
            {"kind": "cone", "x": 10.0, "y": 20.0, "label": "Inicio del circuito"},
        ],
    }

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": bad_layout,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        resp = await client.put(f"/api/technique/exercises/{ex.id}", json=put_payload)

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_put_accepts_empty_elements_list(session):
    """PUT with layout_json.elements=[] is valid (empty canvas is accepted — contracts/rest-api.md)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    empty_layout = {"width": 100.0, "height": 60.0, "elements": []}

    put_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "layout_json": empty_layout,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        put_resp = await client.put(
            f"/api/technique/exercises/{ex.id}", json=put_payload
        )
        assert put_resp.status_code == 200, put_resp.text

        get_resp = await client.get(f"/api/technique/exercises/{ex.id}")

    lj = get_resp.json()["layout_json"]
    assert lj is not None
    assert lj["elements"] == []


# ===========================================================================
# PUT partial-update convention: layout_json=None means "leave unchanged"
# ===========================================================================


@pytest.mark.asyncio
async def test_put_with_null_layout_json_leaves_existing_value_unchanged(session):
    """PUT partial-update: layout_json=None leaves the previously persisted layout intact.

    ExerciseUpdate follows the project's partial-update convention — None means
    "not provided / leave unchanged", not "clear this field".  This is consistent
    with how other nullable scalar fields behave on PUT (router/technique.py line ~725).
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]
    admin = admin_user_obj(user_id=20)

    base_payload = {
        "slug": ex.slug,
        "name": ex.name,
        "summary": ex.summary,
        "how_to": ex.how_to,
        "difficulty": ex.difficulty.value,
        "is_game": ex.is_game,
        "is_gymkhana": ex.is_gymkhana,
        "layout_ascii": ex.layout_ascii,
        "layout_alt": ex.layout_alt,
        "confidence": ex.confidence,
        "skill_slugs": ["posicion"],
        "material_slugs": ["conos"],
        "age_bands": ["7-9", "10-12"],
    }

    async with make_client(session, user=admin) as client:
        # Step 1: write a layout.
        r1 = await client.put(
            f"/api/technique/exercises/{ex.id}",
            json={**base_payload, "layout_json": _LAYOUT_PAYLOAD},
        )
        assert r1.status_code == 200, r1.text

        # Step 2: PUT with layout_json=None (partial-update convention: leave unchanged).
        r2 = await client.put(
            f"/api/technique/exercises/{ex.id}",
            json={**base_payload, "layout_json": None},
        )
        assert r2.status_code == 200, r2.text

        get_resp = await client.get(f"/api/technique/exercises/{ex.id}")

    lj = get_resp.json()["layout_json"]
    # Partial-update: layout_json=None does NOT clear the persisted value.
    assert lj is not None, (
        "layout_json=None in PUT should leave the previously persisted layout intact "
        "(partial-update convention; router technique.py `if payload.layout_json is not None`)"
    )
    assert lj["width"] == pytest.approx(_LAYOUT_PAYLOAD["width"])
