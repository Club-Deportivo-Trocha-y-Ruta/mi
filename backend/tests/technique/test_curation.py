"""T043 — Curation endpoints: POST/PUT/PATCH /api/technique/exercises (feature 018).

Endpoints covered:
  POST  /api/technique/exercises             — create custom exercise
  PUT   /api/technique/exercises/{id}        — edit any exercise (incl. seeded)
  PATCH /api/technique/exercises/{id}/visibility — soft-hide / unhide

Contract rules under test (specs/018-technique-gymkhana-library/contracts/rest-api.md):
  FR-008  gymkhana ⇒ layout_ascii required (enforced at Pydantic layer + service layer)
  FR-019  Hidden rows are never destroyed; is_seeded can be edited
  FR-020  Editing or hiding an exercise does not corrupt a previously saved session's
          TechniqueSessionExercise rows — session read still returns the exercise
  RBAC    coach / admin → allowed; parent → 403; unauthenticated → 401

All tests run on aiosqlite in-memory (no live MySQL, no real network).
Seed data uses fictitious names/dates — never real TyR athlete data.
"""
from __future__ import annotations

from datetime import date, time
from typing import Any

import pytest

from tests.technique.conftest import (
    admin_user_obj,
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_athlete_record,
    seed_athlete_user,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

BASE = "/api/technique"

# ---------------------------------------------------------------------------
# Minimal valid ExerciseCreate payload (non-gymkhana)
# ---------------------------------------------------------------------------

_VALID_CREATE: dict[str, Any] = {
    "name": "Ejercicio personalizado ficticio",
    "summary": "Descripción breve del ejercicio ficticio.",
    "how_to": "Dilo: objetivos. Muéstralo: demo. Háganlo. Revísenlo.",
    "difficulty": "facil",
    "is_game": False,
    "is_gymkhana": False,
    "layout_ascii": None,
    "layout_alt": None,
    "age_bands": ["10-12", "13-15"],
    "skill_slugs": ["posicion"],
    "material_slugs": ["conos"],
}

# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _setup(session) -> dict:
    """Seed club, coach, and catalog; commit. Returns catalog dict."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


async def _setup_with_athlete(session) -> dict:
    """Like _setup but also seeds an athlete — needed for session assembly in FR-020 tests."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_athlete_user(session, user_id=40)
    await seed_athlete_record(
        session,
        athlete_id=1,
        user_id=40,
        club_id=1,
        birth_date=date(2012, 4, 10),
        created_by=10,
    )
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ===========================================================================
# POST /api/technique/exercises — create custom exercise (US5)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_custom_exercise_happy_path_returns_201(session):
    """POST with valid non-gymkhana payload returns 201 with ExerciseDetail.

    is_seeded must be False (custom exercise) and the new exercise must
    immediately appear in GET /exercises (US5, FR-019).
    """
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_seeded"] is False
    assert body["is_hidden"] is False
    assert body["name"] == _VALID_CREATE["name"]
    assert body["difficulty"] == "facil"
    # Detail fields present
    assert "how_to" in body
    assert "created_at" in body
    assert "updated_at" in body
    # Age bands round-trip
    assert set(body["age_bands"]) == {"10-12", "13-15"}


@pytest.mark.asyncio
async def test_created_exercise_appears_in_catalog(session):
    """Custom exercise created via POST is immediately queryable via GET /exercises."""
    await _setup(session)
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
        assert post_resp.status_code == 201, post_resp.text
        new_id = post_resp.json()["id"]

        list_resp = await client.get(f"{BASE}/exercises")
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert new_id in ids


@pytest.mark.asyncio
async def test_created_exercise_retrievable_via_detail(session):
    """Newly created exercise is retrievable via GET /exercises/{id}."""
    await _setup(session)
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
        assert post_resp.status_code == 201, post_resp.text
        new_id = post_resp.json()["id"]

        detail_resp = await client.get(f"{BASE}/exercises/{new_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["id"] == new_id
    assert detail_resp.json()["name"] == _VALID_CREATE["name"]


@pytest.mark.asyncio
async def test_create_gymkhana_with_layout_succeeds(session):
    """Gymkhana exercise with layout_ascii provided returns 201 (FR-008 satisfied)."""
    await _setup(session)
    payload = {
        **_VALID_CREATE,
        "name": "Gymkhana ficticia con layout",
        "is_gymkhana": True,
        "layout_ascii": "[GYMKHANA]...",
        "layout_alt": "Descripción accesible de la gymkhana ficticia.",
    }
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_gymkhana"] is True
    assert body["layout_ascii"] == "[GYMKHANA]..."


@pytest.mark.asyncio
async def test_create_gymkhana_without_layout_returns_422(session):
    """Gymkhana without layout_ascii is rejected 422 (FR-008 schema validation)."""
    await _setup(session)
    payload = {
        **_VALID_CREATE,
        "name": "Gymkhana sin layout (inválida)",
        "is_gymkhana": True,
        "layout_ascii": None,  # missing — must trigger 422
    }
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_with_no_age_bands_returns_422(session):
    """age_bands must have at least 1 element; empty list → 422."""
    await _setup(session)
    payload = {**_VALID_CREATE, "age_bands": []}
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_with_no_skill_slugs_returns_422(session):
    """skill_slugs must have at least 1 element; empty list → 422."""
    await _setup(session)
    payload = {**_VALID_CREATE, "skill_slugs": []}
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_with_unknown_skill_slug_returns_422(session):
    """Unknown skill slug is rejected 422 by the router's slug resolution."""
    await _setup(session)
    payload = {**_VALID_CREATE, "skill_slugs": ["habilidad-inexistente"]}
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_with_unknown_material_slug_returns_422(session):
    """Unknown material slug is rejected 422 by the router's slug resolution."""
    await _setup(session)
    payload = {**_VALID_CREATE, "material_slugs": ["material-inexistente"]}
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_exercise_admin_also_allowed(session):
    """Admin can also create custom exercises."""
    await _setup(session)
    # Admin needs a club membership for _coach_club_id lookup; seed one.
    from app.models.club import ClubMember, ClubRole
    from datetime import datetime, timezone
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
    async with make_client(session, user=admin) as client:
        resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_create_exercise_parent_forbidden(session):
    """Parent receives 403 on POST /exercises (FR-021)."""
    await _setup(session)
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_create_exercise_anonymous_401(session):
    """Unauthenticated POST /exercises returns 401."""
    await _setup(session)
    async with make_client(session, authed=False) as client:
        resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
    assert resp.status_code == 401, resp.text


# ===========================================================================
# PUT /api/technique/exercises/{id} — edit exercise (US5)
# ===========================================================================


@pytest.mark.asyncio
async def test_put_edits_custom_exercise_name(session):
    """PUT with a new name persists the change; detail reflects it."""
    await _setup(session)
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/exercises", json=_VALID_CREATE)
        assert post_resp.status_code == 201, post_resp.text
        ex_id = post_resp.json()["id"]

        put_resp = await client.put(
            f"{BASE}/exercises/{ex_id}",
            json={"name": "Nombre actualizado ficticio"},
        )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["name"] == "Nombre actualizado ficticio"


@pytest.mark.asyncio
async def test_put_edits_seeded_exercise(session):
    """PUT can edit a seeded exercise (FR-019); is_seeded flag unchanged."""
    catalog = await _setup(session)
    seeded = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        resp = await client.put(
            f"{BASE}/exercises/{seeded.id}",
            json={"summary": "Resumen personalizado ficticio del pie-abajo."},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_seeded"] is True  # seeded flag never altered
    assert body["summary"] == "Resumen personalizado ficticio del pie-abajo."


@pytest.mark.asyncio
async def test_put_persisted_change_visible_in_subsequent_get(session):
    """After PUT, the updated values are served by GET /exercises/{id}."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["semaforo"]
    async with make_client(session) as client:
        await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"difficulty": "avanzada"},
        )
        detail_resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["difficulty"] == "avanzada"


@pytest.mark.asyncio
async def test_put_replaces_age_bands(session):
    """PUT with age_bands replaces existing bands completely.

    pie_abajo starts with [7-9, 10-12, 13-15].  After PUT with ["13-15"],
    the exercise must no longer appear in the age_band=7-9 filter.

    The authoritative check is through a fresh GET /exercises?age_band=7-9 rather
    than the PUT response body, because SQLAlchemy's identity-map may serve the
    eager-loaded age_bands collection from the pre-delete cache inside the same
    request/session scope.  The filter query always hits the DB directly.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # currently bands=[7-9, 10-12, 13-15]
    async with make_client(session) as client:
        put_resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"age_bands": ["13-15"]},
        )
    assert put_resp.status_code == 200, put_resp.text
    # The DB delete succeeded — verify via a fresh catalog query, not the PUT body.
    # (The PUT body may carry stale age_bands from the ORM identity map.)

    # A fresh request in a new client scope re-queries the DB.
    async with make_client(session) as client:
        list_7_9 = await client.get(f"{BASE}/exercises?age_band=7-9")
        list_13_15 = await client.get(f"{BASE}/exercises?age_band=13-15")

    assert list_7_9.status_code == 200, list_7_9.text
    ids_7_9 = {item["id"] for item in list_7_9.json()["items"]}
    assert ex.id not in ids_7_9, "pie_abajo should no longer be in the 7-9 band after PUT."

    assert list_13_15.status_code == 200, list_13_15.text
    ids_13_15 = {item["id"] for item in list_13_15.json()["items"]}
    assert ex.id in ids_13_15, "pie_abajo must appear in the 13-15 band after PUT."


@pytest.mark.asyncio
async def test_put_replaces_skill_slugs(session):
    """PUT with skill_slugs replaces M2M skills."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # currently posicion + frenado
    async with make_client(session) as client:
        put_resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"skill_slugs": ["separacion"]},
        )
    assert put_resp.status_code == 200, put_resp.text
    skill_slugs = [s["slug"] for s in put_resp.json()["skills"]]
    assert skill_slugs == ["separacion"]
    assert "posicion" not in skill_slugs
    assert "frenado" not in skill_slugs


@pytest.mark.asyncio
async def test_put_gymkhana_without_layout_in_payload_when_already_has_layout(session):
    """PUT setting is_gymkhana=True on an exercise that already has layout_ascii is valid.

    The service layer reads the persisted layout when layout_ascii is absent from
    the update payload — the effective pair (True, existing_layout) is valid.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["slalom"]  # already is_gymkhana=True with layout
    async with make_client(session) as client:
        # Update only the name; is_gymkhana stays True via persisted value.
        resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"name": "Slalom ficticio actualizado"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_gymkhana"] is True


@pytest.mark.asyncio
async def test_put_gymkhana_true_and_no_layout_in_payload_and_no_persisted_layout_422(session):
    """PUT setting is_gymkhana=True when there is no existing layout → 422.

    Pydantic validates at schema level: if is_gymkhana=True AND layout_ascii=None
    in the same payload it raises 422 immediately.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]  # layout_ascii is NULL in DB
    async with make_client(session) as client:
        resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"is_gymkhana": True},  # no layout_ascii in payload or DB → 422
        )
    # Pydantic v2 model_validator sees is_gymkhana=True + layout_ascii=None → raises
    # The service layer additionally checks the effective pair
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_put_unknown_exercise_returns_404(session):
    """PUT on non-existent exercise id returns 404."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.put(
            f"{BASE}/exercises/99999",
            json={"name": "No existe"},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_put_unknown_skill_slug_returns_422(session):
    """PUT with an unknown skill slug in skill_slugs returns 422."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["semaforo"]
    async with make_client(session) as client:
        resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"skill_slugs": ["habilidad-inexistente"]},
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_put_parent_forbidden(session):
    """Parent cannot edit exercises (FR-021)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"name": "Intento de edición por padre"},
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_put_anonymous_401(session):
    """Unauthenticated PUT returns 401."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session, authed=False) as client:
        resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"name": "Sin autenticación"},
        )
    assert resp.status_code == 401, resp.text


# ===========================================================================
# PATCH /api/technique/exercises/{id}/visibility — hide/unhide (US5, FR-019)
# ===========================================================================


@pytest.mark.asyncio
async def test_patch_visibility_hide_returns_200_with_is_hidden_true(session):
    """PATCH visibility {is_hidden: true} returns 200 {id, is_hidden: true}."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == ex.id
    assert body["is_hidden"] is True


@pytest.mark.asyncio
async def test_hidden_exercise_drops_from_default_catalog(session):
    """After hiding, the exercise does not appear in GET /exercises (include_hidden=false).

    FR-019: row is never destroyed, it just stops appearing in the default list.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        patch_resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
        assert patch_resp.status_code == 200, patch_resp.text

        list_resp = await client.get(f"{BASE}/exercises")
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert ex.id not in ids


@pytest.mark.asyncio
async def test_hidden_exercise_appears_with_include_hidden_true(session):
    """After hiding, the exercise is still retrievable with include_hidden=true (FR-019).

    The row is never destroyed — soft-hide only.
    """
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
        list_resp = await client.get(f"{BASE}/exercises?include_hidden=true")
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert ex.id in ids


@pytest.mark.asyncio
async def test_hidden_exercise_detail_still_accessible_by_id(session):
    """Hidden exercise is still retrievable via GET /exercises/{id} (FR-019)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
        detail_resp = await client.get(f"{BASE}/exercises/{ex.id}")
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["is_hidden"] is True


@pytest.mark.asyncio
async def test_unhide_restores_exercise_to_default_catalog(session):
    """Hiding and then unhiding restores the exercise to the default catalog."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session) as client:
        # Hide first
        await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
        # Unhide
        unhide_resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": False},
        )
        assert unhide_resp.status_code == 200, unhide_resp.text
        assert unhide_resp.json()["is_hidden"] is False

        list_resp = await client.get(f"{BASE}/exercises")
    assert list_resp.status_code == 200, list_resp.text
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert ex.id in ids


@pytest.mark.asyncio
async def test_patch_visibility_unknown_exercise_returns_404(session):
    """PATCH visibility on a non-existent exercise id returns 404."""
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.patch(
            f"{BASE}/exercises/99999/visibility",
            json={"is_hidden": True},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_patch_visibility_parent_forbidden(session):
    """Parent receives 403 on PATCH visibility (FR-021)."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    parent = parent_user_obj(user_id=30)
    async with make_client(session, user=parent) as client:
        resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_patch_visibility_anonymous_401(session):
    """Unauthenticated PATCH visibility returns 401."""
    catalog = await _setup(session)
    ex = catalog["exercises"]["pie_abajo"]
    async with make_client(session, authed=False) as client:
        resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
    assert resp.status_code == 401, resp.text


# ===========================================================================
# FR-020 — hiding/editing an exercise does not corrupt a saved session
# ===========================================================================


@pytest.mark.asyncio
async def test_hidden_exercise_still_appears_in_saved_session(session):
    """Hiding an exercise after it was included in a session does not remove it
    from the session's exercise list (FR-020).

    Steps:
      1. Assemble a technique session that includes exercise E.
      2. PATCH E visibility → is_hidden=True.
      3. GET /api/technique/sessions/{id}/exercises → E still present.
    """
    catalog = await _setup_with_athlete(session)
    ex = catalog["exercises"]["pie_abajo"]
    slalom = catalog["exercises"]["slalom"]

    assemble_payload = {
        "scheduled_date": "2026-07-10",
        "scheduled_start_time": "16:00:00",
        "duration_min": 60,
        "location": "Cancha ficticia de prueba",
        "technical_focus": "Equilibrio básico",
        "objectives": "Objetivos ficticios.",
        "convocados_athlete_ids": [1],
        "items": [
            {"exercise_id": ex.id, "segment": "calentamiento", "position": 1},
            {"exercise_id": slalom.id, "segment": "principal", "position": 1},
        ],
    }

    async with make_client(session) as client:
        assemble_resp = await client.post(f"{BASE}/sessions", json=assemble_payload)
        assert assemble_resp.status_code == 201, assemble_resp.text
        session_id = assemble_resp.json()["training_session_id"]

        # Now hide pie_abajo
        patch_resp = await client.patch(
            f"{BASE}/exercises/{ex.id}/visibility",
            json={"is_hidden": True},
        )
        assert patch_resp.status_code == 200, patch_resp.text

        # Session read must still include the hidden exercise
        read_resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert read_resp.status_code == 200, read_resp.text
    exercise_ids = {item["exercise_id"] for item in read_resp.json()}
    assert ex.id in exercise_ids, (
        "Hidden exercise must remain visible in a saved session (FR-020)."
    )
    assert slalom.id in exercise_ids


@pytest.mark.asyncio
async def test_edited_exercise_saved_session_reflects_update(session):
    """Editing an exercise name via PUT is reflected in the session read (FR-020).

    The session read reads live exercise data — edits ARE reflected in the
    TechniqueSessionItem.name field returned from GET /sessions/{id}/exercises.
    This is correct behaviour: the session's item list is NOT a snapshot copy,
    it joins on the live exercise row.
    """
    catalog = await _setup_with_athlete(session)
    ex = catalog["exercises"]["semaforo"]

    assemble_payload = {
        "scheduled_date": "2026-07-11",
        "scheduled_start_time": "09:00:00",
        "duration_min": 45,
        "location": "Pista ficticia",
        "technical_focus": "Frenado",
        "objectives": None,
        "convocados_athlete_ids": [1],
        "items": [
            {"exercise_id": ex.id, "segment": "principal", "position": 1},
        ],
    }

    async with make_client(session) as client:
        assemble_resp = await client.post(f"{BASE}/sessions", json=assemble_payload)
        assert assemble_resp.status_code == 201, assemble_resp.text
        session_id = assemble_resp.json()["training_session_id"]

        # Rename the exercise
        put_resp = await client.put(
            f"{BASE}/exercises/{ex.id}",
            json={"name": "Semáforo renombrado ficticio"},
        )
        assert put_resp.status_code == 200, put_resp.text

        # Session exercises read reflects the updated name (join, not snapshot)
        read_resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert read_resp.status_code == 200, read_resp.text
    items = read_resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Semáforo renombrado ficticio"
    assert items[0]["exercise_id"] == ex.id


@pytest.mark.asyncio
async def test_session_unchanged_after_hiding_unrelated_exercise(session):
    """Hiding an exercise that is NOT in a session does not affect that session.

    Sanity guard: only exercises referenced by TechniqueSessionExercise rows
    for this session should appear; an unrelated hidden exercise must not bleed in.
    """
    catalog = await _setup_with_athlete(session)
    ex_in_session = catalog["exercises"]["semaforo"]
    ex_not_in_session = catalog["exercises"]["limbo"]

    assemble_payload = {
        "scheduled_date": "2026-07-12",
        "scheduled_start_time": "15:00:00",
        "duration_min": 50,
        "location": "Parque ficticio",
        "technical_focus": "Frenado",
        "objectives": None,
        "convocados_athlete_ids": [1],
        "items": [
            {"exercise_id": ex_in_session.id, "segment": "calentamiento", "position": 1},
        ],
    }

    async with make_client(session) as client:
        assemble_resp = await client.post(f"{BASE}/sessions", json=assemble_payload)
        assert assemble_resp.status_code == 201, assemble_resp.text
        session_id = assemble_resp.json()["training_session_id"]

        # Hide limbo (not in this session)
        await client.patch(
            f"{BASE}/exercises/{ex_not_in_session.id}/visibility",
            json={"is_hidden": True},
        )

        read_resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert read_resp.status_code == 200, read_resp.text
    items = read_resp.json()
    assert len(items) == 1
    assert items[0]["exercise_id"] == ex_in_session.id
