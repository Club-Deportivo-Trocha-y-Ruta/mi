"""T009 — GET /api/technique/exercises filter matrix.

Covers every combinable filter parameter:
  - no filters (baseline)
  - skill slug filter
  - age_band filter
  - difficulty filter
  - materials subset filter
      * sin_material exercises always match regardless of available materials
      * exercises requiring an unavailable material are excluded
      * exercises whose full material set is a subset of available are included
  - combined filters (AND semantics)
  - is_game filter
  - include_hidden flag
  - no-match combos → 200 with items=[], total=0  (never 404/500)
  - RBAC: parent → 403

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Seed data is inserted via ``seed_technique_catalog`` from conftest:

  Exercises (5):
    pie-abajo-test   facil  game    conos            bands=[7-9, 10-12, 13-15]  skills=[posicion, frenado]
    slalom-test      facil  gymk    conos            bands=[7-9, 10-12]         skills=[posicion]
    limbo-test       media  gymk    estacas+llantas  bands=[10-12, 13-15]       skills=[separacion]
    semaforo-test    facil  game    sin_material     bands=[7-9, 10-12]         skills=[frenado]
    trackstand-test  avanzada      sin_material     bands=[13-15]              skills=[posicion]  is_hidden=True
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


# ===========================================================================
# Baseline: no filters
# ===========================================================================


@pytest.mark.asyncio
async def test_no_filters_returns_all_visible_exercises(session):
    """Without any filter, the four visible exercises are returned (hidden excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 4  # trackstand-test is_hidden=True → excluded
    slugs = {item["slug"] for item in body["items"]}
    assert "trackstand-test" not in slugs


@pytest.mark.asyncio
async def test_include_hidden_returns_all_five(session):
    """include_hidden=true surfaces the hidden trackstand exercise."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?include_hidden=true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    slugs = {item["slug"] for item in body["items"]}
    assert "trackstand-test" in slugs


# ===========================================================================
# Skill filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_skill_posicion(session):
    """skill=posicion → pie-abajo, slalom (trackstand hidden → excluded by default)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?skill=posicion")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    slugs = {item["slug"] for item in body["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test"}


@pytest.mark.asyncio
async def test_filter_by_skill_frenado(session):
    """skill=frenado → pie-abajo, semaforo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?skill=frenado")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_filter_by_skill_separacion(session):
    """skill=separacion → limbo only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?skill=separacion")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"limbo-test"}


@pytest.mark.asyncio
async def test_filter_by_skill_include_hidden(session):
    """skill=posicion + include_hidden=true also surfaces trackstand."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=posicion&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert "trackstand-test" in slugs
    assert slugs == {"pie-abajo-test", "slalom-test", "trackstand-test"}


@pytest.mark.asyncio
async def test_filter_by_unknown_skill_returns_empty(session):
    """skill with no matching exercises → 200 with items=[], total=0 (FR-004)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?skill=habilidad-inexistente")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


# ===========================================================================
# Age band filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_age_band_7_9(session):
    """age_band=7-9 → pie-abajo, slalom, semaforo (all visible ones for that band)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?age_band=7-9")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_filter_by_age_band_10_12(session):
    """age_band=10-12 → pie-abajo, slalom, limbo, semaforo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?age_band=10-12")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test", "limbo-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_filter_by_age_band_13_15(session):
    """age_band=13-15 → pie-abajo, limbo (trackstand hidden → excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?age_band=13-15")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "limbo-test"}


@pytest.mark.asyncio
async def test_filter_by_age_band_13_15_include_hidden(session):
    """age_band=13-15 + include_hidden=true also surfaces trackstand."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?age_band=13-15&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert "trackstand-test" in slugs
    assert slugs == {"pie-abajo-test", "limbo-test", "trackstand-test"}


# ===========================================================================
# Difficulty filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_by_difficulty_facil(session):
    """difficulty=facil → pie-abajo, slalom, semaforo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?difficulty=facil")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_filter_by_difficulty_media(session):
    """difficulty=media → limbo only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?difficulty=media")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"limbo-test"}


@pytest.mark.asyncio
async def test_filter_by_difficulty_avanzada_no_visible(session):
    """difficulty=avanzada without include_hidden → empty (trackstand hidden)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?difficulty=avanzada")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_filter_by_difficulty_avanzada_include_hidden(session):
    """difficulty=avanzada + include_hidden=true → trackstand."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?difficulty=avanzada&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"trackstand-test"}


# ===========================================================================
# Materials subset filter
# ===========================================================================


@pytest.mark.asyncio
async def test_materials_only_conos_available(session):
    """materials=conos → pie-abajo (conos), slalom (conos), semaforo (sin_material), trackstand excluded (hidden).

    sin_material exercises always pass (research D2). conos exercises pass.
    limbo requires estacas+llantas which are not available → excluded.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?materials=conos")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test", "semaforo-test"}
    assert "limbo-test" not in slugs


@pytest.mark.asyncio
async def test_materials_estacas_and_llantas_available(session):
    """materials=estacas,llantas → limbo (requires both) + sin_material exercises.

    pie-abajo and slalom need conos which is unavailable → excluded.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?materials=estacas%2Cllantas"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert "limbo-test" in slugs
    assert "pie-abajo-test" not in slugs
    assert "slalom-test" not in slugs
    # semaforo is sin_material → always matches
    assert "semaforo-test" in slugs


@pytest.mark.asyncio
async def test_sin_material_exercise_always_matches_any_material_filter(session):
    """semaforo and trackstand use sin_material and appear even when available materials list has unrelated items."""
    await _setup(session)
    # Pass a single random available material (not what limbo, pie-abajo, slalom need)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?materials=estacas&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    # sin_material exercises always match
    assert "semaforo-test" in slugs
    assert "trackstand-test" in slugs
    # limbo requires both estacas AND llantas; llantas not available → excluded
    assert "limbo-test" not in slugs
    # pie-abajo and slalom require conos which is absent → excluded
    assert "pie-abajo-test" not in slugs
    assert "slalom-test" not in slugs


@pytest.mark.asyncio
async def test_sin_material_exercise_matches_empty_available_set(session):
    """materials=sin_material explicitly in the available set still matches sin_material exercises.

    This also verifies that passing only the sentinel slug does not crash.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?materials=sin_material")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    # Only sin_material exercises survive
    assert "semaforo-test" in slugs
    # Equipment exercises are excluded
    assert "pie-abajo-test" not in slugs
    assert "slalom-test" not in slugs
    assert "limbo-test" not in slugs


@pytest.mark.asyncio
async def test_materials_unavailable_excludes_requiring_exercise(session):
    """An exercise that requires a material NOT in available is excluded.

    limbo requires estacas AND llantas; providing only llantas → excluded.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?materials=llantas")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert "limbo-test" not in slugs  # needs estacas too
    # sin_material exercises survive
    assert "semaforo-test" in slugs


@pytest.mark.asyncio
async def test_all_materials_available_matches_everything_visible(session):
    """When every real material is available, all visible exercises are returned."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?materials=conos%2Cestacas%2Cllantas%2Csin_material"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 4  # trackstand hidden
    slugs = {item["slug"] for item in body["items"]}
    assert "pie-abajo-test" in slugs
    assert "slalom-test" in slugs
    assert "limbo-test" in slugs
    assert "semaforo-test" in slugs


# ===========================================================================
# is_game filter
# ===========================================================================


@pytest.mark.asyncio
async def test_filter_is_game_true(session):
    """is_game=true → pie-abajo, semaforo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?is_game=true")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_filter_is_game_false(session):
    """is_game=false → slalom, limbo (trackstand hidden excluded)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?is_game=false")
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"slalom-test", "limbo-test"}


# ===========================================================================
# Combined filters (AND semantics)
# ===========================================================================


@pytest.mark.asyncio
async def test_combined_skill_and_age_band(session):
    """skill=posicion + age_band=7-9 → pie-abajo, slalom (both visible, posicion + 7-9 band)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=posicion&age_band=7-9"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test"}


@pytest.mark.asyncio
async def test_combined_skill_and_difficulty(session):
    """skill=posicion + difficulty=facil → pie-abajo, slalom."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=posicion&difficulty=facil"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "slalom-test"}


@pytest.mark.asyncio
async def test_combined_skill_and_materials(session):
    """skill=frenado + materials=conos → pie-abajo only (semaforo is sin_material: also matches).

    Corrected expectation: semaforo is a sin_material exercise so it always passes the
    materials filter; and semaforo has skill=frenado → both pie-abajo and semaforo qualify.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=frenado&materials=conos"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    # pie-abajo: skill=frenado ✓ + requires conos which is available ✓
    # semaforo: skill=frenado ✓ + sin_material always matches ✓
    assert slugs == {"pie-abajo-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_combined_age_band_and_difficulty(session):
    """age_band=10-12 + difficulty=media → limbo only."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?age_band=10-12&difficulty=media"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"limbo-test"}


@pytest.mark.asyncio
async def test_combined_skill_age_difficulty_materials(session):
    """Four simultaneous filters: skill=separacion + age_band=13-15 + difficulty=media + materials=estacas,llantas → limbo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises"
            "?skill=separacion&age_band=13-15&difficulty=media&materials=estacas%2Cllantas"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "limbo-test"


@pytest.mark.asyncio
async def test_combined_is_game_and_age_band(session):
    """is_game=true + age_band=7-9 → pie-abajo, semaforo."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?is_game=true&age_band=7-9"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "semaforo-test"}


@pytest.mark.asyncio
async def test_combined_is_game_and_materials_no_equipment(session):
    """is_game=true + materials=conos → pie-abajo (conos avail) + semaforo (sin_material)."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?is_game=true&materials=conos"
        )
    assert resp.status_code == 200, resp.text
    slugs = {item["slug"] for item in resp.json()["items"]}
    assert slugs == {"pie-abajo-test", "semaforo-test"}


# ===========================================================================
# No-match combos → 200 with empty list (FR-004 — never 404/500)
# ===========================================================================


@pytest.mark.asyncio
async def test_impossible_combo_returns_200_empty(session):
    """skill=separacion + age_band=7-9: limbo targets 10-12/13-15 only → empty list."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=separacion&age_band=7-9"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_no_materials_match_returns_200_empty(session):
    """materials=conos + skill=separacion: limbo needs estacas+llantas → excluded; no sin_material exercise has separacion."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?materials=conos&skill=separacion"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_all_filters_impossible_combo_is_200_empty(session):
    """difficulty=avanzada + skill=frenado: no visible exercise matches both."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?difficulty=avanzada&skill=frenado"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_is_game_false_with_no_equipment_returns_empty_when_hidden_excluded(session):
    """is_game=false + materials=sin_material: the only non-game sin_material exercise is trackstand (hidden).

    Without include_hidden the result must be empty.
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?is_game=false&materials=sin_material"
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
    """Each item in the list has the expected ExerciseListItem fields."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get("/api/technique/exercises?skill=separacion")
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    for field in (
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
    ):
        assert field in item, f"Missing field: {field}"
    # Nested skill objects have code/slug/name
    skill = item["skills"][0]
    assert "code" in skill
    assert "slug" in skill
    assert "name" in skill
    # Nested material objects have slug/name/is_none
    mat = item["materials"][0]
    assert "slug" in mat
    assert "name" in mat
    assert "is_none" in mat


@pytest.mark.asyncio
async def test_total_equals_len_items(session):
    """total always equals len(items) for any filter combination."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.get(
            "/api/technique/exercises?age_band=10-12&include_hidden=true"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["items"])


# ===========================================================================
# RBAC: parent → 403 (FR-021)
# ===========================================================================


@pytest.mark.asyncio
async def test_parent_receives_403_on_exercises(session):
    """Parents are blocked from the catalog endpoint (FR-021)."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.get("/api/technique/exercises")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_parent_receives_403_even_with_filters(session):
    """Parent with valid filter params still gets 403 — auth is checked before filter logic."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.get(
            "/api/technique/exercises?skill=frenado&difficulty=facil"
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_can_access_exercises(session):
    """Admin role has full access to the catalog endpoint."""
    await _setup(session)
    admin = admin_user_obj(user_id=20)
    async with make_client(session, user=admin) as client:
        resp = await client.get("/api/technique/exercises")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 0
