"""T010 — GET /api/strength/exercises filter matrix.

Covers every combinable filter parameter (contracts/strength-api.md):
  - no filters (baseline, hidden excluded)
  - include_hidden flag
  - equipment facet (sin_equipo / equipo_gym)
  - age_band facet (10-12 / 13-15)
  - movement_category facet
  - free-text `q` LIKE match over name + summary
  - combined filters (AND semantics)
  - no-match combos → 200 with items=[], total=0 (never 404/500)
  - response shape (ExerciseOut fields)
  - RBAC: parent → 403, admin → 200

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Seed data is inserted via ``seed_strength_catalog`` from conftest:

  Exercises (5):
    flexiones-test          sin_equipo  empuje_superior     bands=[10-12, 13-15]
    remo-banda-test         equipo_gym  traccion_superior   bands=[13-15]
    sentadilla-test         sin_equipo  inferior_bilateral  bands=[10-12, 13-15]
    plancha-test            sin_equipo  core_estabilidad    bands=[10-12]
    trackstand-oculto-test  sin_equipo  core_estabilidad    bands=[13-15]  is_hidden=True
"""
from __future__ import annotations

import pytest

from tests.strength.conftest import (
    admin_user_obj,
    make_client,
    parent_user_obj,
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
# Baseline: no filters
# ===========================================================================


@pytest.mark.asyncio
async def test_no_filters_returns_all_visible_exercises(session):
    """Without any filter, the four visible exercises are returned (hidden excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 4  # trackstand-oculto-test is_hidden=True → excluded
    slugs = {item["slug"] for item in body["items"]}
    assert "trackstand-oculto-test" not in slugs


@pytest.mark.asyncio
async def test_include_hidden_returns_all_five(session):
    """include_hidden=true surfaces the hidden trackstand exercise."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?include_hidden=true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    slugs = {item["slug"] for item in body["items"]}
    assert "trackstand-oculto-test" in slugs


# ===========================================================================
# Equipment filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_equipment_sin_equipo(session):
    """equipment=sin_equipo → flexiones, sentadilla, plancha (trackstand hidden excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?equipment=sin_equipo")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test", "sentadilla-test", "plancha-test"}


@pytest.mark.asyncio
async def test_filter_by_equipment_equipo_gym(session):
    """equipment=equipo_gym → remo-banda only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?equipment=equipo_gym")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"remo-banda-test"}


@pytest.mark.asyncio
async def test_filter_by_equipment_sin_equipo_include_hidden(session):
    """equipment=sin_equipo + include_hidden=true also surfaces the hidden exercise."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=sin_equipo&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {
        "flexiones-test",
        "sentadilla-test",
        "plancha-test",
        "trackstand-oculto-test",
    }


# ===========================================================================
# Age band filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_age_band_10_12(session):
    """age_band=10-12 → flexiones, sentadilla, plancha."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?age_band=10-12")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test", "sentadilla-test", "plancha-test"}


@pytest.mark.asyncio
async def test_filter_by_age_band_13_15(session):
    """age_band=13-15 → flexiones, remo-banda, sentadilla (trackstand hidden excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?age_band=13-15")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test", "remo-banda-test", "sentadilla-test"}


@pytest.mark.asyncio
async def test_filter_by_age_band_13_15_include_hidden(session):
    """age_band=13-15 + include_hidden=true also surfaces trackstand."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?age_band=13-15&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {
        "flexiones-test",
        "remo-banda-test",
        "sentadilla-test",
        "trackstand-oculto-test",
    }


# ===========================================================================
# Movement category filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_movement_category_empuje_superior(session):
    """movement_category=empuje_superior → flexiones only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?movement_category=empuje_superior"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test"}


@pytest.mark.asyncio
async def test_filter_by_movement_category_core_estabilidad_no_hidden(session):
    """movement_category=core_estabilidad without include_hidden → plancha only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?movement_category=core_estabilidad"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"plancha-test"}


@pytest.mark.asyncio
async def test_filter_by_movement_category_core_estabilidad_include_hidden(session):
    """movement_category=core_estabilidad + include_hidden=true → plancha + trackstand."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?movement_category=core_estabilidad&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"plancha-test", "trackstand-oculto-test"}


@pytest.mark.asyncio
async def test_filter_by_movement_category_unused_returns_empty(session):
    """movement_category=inferior_unilateral has no seeded exercise → 200 empty (FR-004)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?movement_category=inferior_unilateral"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


# ===========================================================================
# Free-text `q` filter (name + summary LIKE)
# ===========================================================================


@pytest.mark.asyncio
async def test_q_matches_name(session):
    """q='flexiones' matches the exercise name."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?q=flexiones")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test"}


@pytest.mark.asyncio
async def test_q_matches_summary(session):
    """q='empuje' matches only flexiones' summary text (no other summary contains it)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?q=empuje")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test"}


@pytest.mark.asyncio
async def test_q_matches_name_substring_banda(session):
    """q='banda' matches remo-banda-test's name."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?q=banda")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"remo-banda-test"}


@pytest.mark.asyncio
async def test_q_no_match_returns_empty(session):
    """q with no matching exercise → 200 with items=[], total=0 (FR-004)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?q=ejercicio-inexistente-xyz")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


# ===========================================================================
# Combined filters (AND semantics)
# ===========================================================================


@pytest.mark.asyncio
async def test_combined_equipment_and_movement_category(session):
    """equipment=sin_equipo + movement_category=core_estabilidad → plancha only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=sin_equipo&movement_category=core_estabilidad"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"plancha-test"}


@pytest.mark.asyncio
async def test_combined_equipment_and_age_band(session):
    """equipment=sin_equipo + age_band=10-12 → flexiones, sentadilla, plancha."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=sin_equipo&age_band=10-12"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"flexiones-test", "sentadilla-test", "plancha-test"}


@pytest.mark.asyncio
async def test_combined_age_band_and_movement_category(session):
    """age_band=13-15 + movement_category=traccion_superior → remo-banda only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?age_band=13-15&movement_category=traccion_superior"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "remo-banda-test"


@pytest.mark.asyncio
async def test_combined_q_and_equipment(session):
    """q='core' + equipment=sin_equipo → plancha (matches summary 'Estabilidad de core')."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?q=core&equipment=sin_equipo"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"plancha-test"}


@pytest.mark.asyncio
async def test_combined_all_four_filters(session):
    """Four simultaneous filters narrow to exactly one exercise."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises"
            "?q=sentadilla&equipment=sin_equipo&age_band=10-12"
            "&movement_category=inferior_bilateral"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "sentadilla-test"


# ===========================================================================
# No-match combos → 200 with empty list (FR-004 — never 404/500)
# ===========================================================================


@pytest.mark.asyncio
async def test_impossible_combo_equipment_and_age_band_returns_200_empty(session):
    """equipment=equipo_gym + age_band=10-12: remo-banda only targets 13-15 → empty."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=equipo_gym&age_band=10-12"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_impossible_combo_equipment_and_movement_category_returns_200_empty(session):
    """equipment=equipo_gym + movement_category=core_estabilidad: no matching exercise → empty."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=equipo_gym&movement_category=core_estabilidad"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_all_filters_impossible_combo_is_200_empty(session):
    """q that only matches flexiones combined with an unrelated movement_category → empty."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?q=flexiones&movement_category=core_estabilidad"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_hidden_only_match_without_include_hidden_returns_empty(session):
    """movement_category=core_estabilidad + age_band=13-15: only trackstand (hidden) matches.

    Without include_hidden the result must be empty (plancha is 10-12 only).
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?movement_category=core_estabilidad&age_band=13-15"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


# ===========================================================================
# Response shape validation
# ===========================================================================


@pytest.mark.asyncio
async def test_exercise_list_item_shape(session):
    """Each item in the list has the expected ExerciseOut fields (card view)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/strength/exercises?q=flexiones")
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    for field in (
        "id",
        "slug",
        "name",
        "summary",
        "equipment",
        "equipment_detail",
        "movement_category",
        "age_bands",
        "suggested_duration_min",
        "suggested_reps",
        "is_seeded",
        "is_hidden",
    ):
        assert field in item, f"Missing field: {field}"
    # List/card view omits detail-only fields
    for field in ("how_to", "common_errors", "illustration_ascii", "illustration_alt"):
        assert field not in item, f"Unexpected detail field in list item: {field}"


@pytest.mark.asyncio
async def test_total_equals_len_items(session):
    """total always equals len(items) for any filter combination."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/strength/exercises?age_band=13-15&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["items"])


# ===========================================================================
# RBAC: parent → 403, admin → 200 (contract "All endpoints require coach/admin")
# ===========================================================================


@pytest.mark.asyncio
async def test_parent_receives_403_on_exercises(session):
    """Parents are blocked from the catalog endpoint."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.get("/api/strength/exercises")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_parent_receives_403_even_with_filters(session):
    """Parent with valid filter params still gets 403 — auth is checked before filter logic."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.get(
            "/api/strength/exercises?equipment=sin_equipo&age_band=10-12"
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_access_exercises(session):
    """Admin role has full access to the catalog endpoint."""
    await _setup(session)
    admin = admin_user_obj(user_id=20)
    async with make_client(session, user=admin) as client:
        resp = await client.get("/api/strength/exercises")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 0
