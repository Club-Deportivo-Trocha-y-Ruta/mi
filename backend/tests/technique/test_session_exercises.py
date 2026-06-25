"""T026 — GET /api/technique/sessions/{id}/exercises (feature 018).

Covers:
  - Happy path: items returned ordered by segment then position (FR-013).
  - Multi-segment ordering: calentamiento < principal < vuelta_calma, then by
    position within each segment.
  - Mixed position values: positions need not be contiguous; ordering is stable.
  - Session with a single exercise in a single segment.
  - Session with exercises spanning all three segments.
  - FR-020: after an exercise is hidden via PATCH /visibility, the previously
    saved session still returns its items intact (hidden row is not excluded
    from get_session_exercises).
  - Session with no technique exercises returns an empty list (200), not 404.
  - Non-existent session id returns an empty list (router delegates to
    get_session_exercises which returns [] for unknown session — no 404 is
    raised, consistent with the contract).
  - RBAC: parent receives 403; unauthenticated receives 401.
  - Response shape: each TechniqueSessionItem has the required fields.

All tests run on aiosqlite in-memory (no live MySQL, no real network).
Seed data uses fictitious names and dates — never real TyR athlete data.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from app.models.technique_exercise import SessionSegment
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
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _seed_base(session) -> dict:
    """Seed club, coach, athlete, and technique catalog; commit.

    Returns the catalog dict produced by seed_technique_catalog.
    The athlete (id=1) is linked to athlete user (id=40) at club 1.
    The coach (id=10) holds a club membership at club 1.
    """
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_athlete_user(session, user_id=40)
    await seed_athlete_record(
        session,
        athlete_id=1,
        user_id=40,
        club_id=1,
        birth_date=date(2012, 3, 15),
        created_by=10,
    )
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


def _assemble_payload(
    *,
    athlete_id: int = 1,
    items: list[dict],
) -> dict:
    """Build a minimal AssembleSessionRequest dict for POST /api/technique/sessions."""
    return {
        "scheduled_date": "2026-07-01",
        "scheduled_start_time": "09:00:00",
        "duration_min": 60,
        "location": "Cancha Ficticia",
        "technical_focus": "Técnica base (test)",
        "objectives": None,
        "convocados_athlete_ids": [athlete_id],
        "items": items,
    }


# ---------------------------------------------------------------------------
# T026-01: happy path — items ordered by segment then position
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_ordered_by_segment_then_position(session):
    """GET /sessions/{id}/exercises returns items sorted (segment, position).

    Three exercises inserted in reversed position order across two segments.
    The response must respect (segment enum order, position asc) regardless of
    insertion order.
    """
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]     # calentamiento pos=2
    ex_slalom = catalog["exercises"]["slalom"]     # calentamiento pos=1
    ex_limbo = catalog["exercises"]["limbo"]       # principal pos=0

    payload = _assemble_payload(
        items=[
            # Deliberately insert calentamiento pos=2 before pos=1.
            {"exercise_id": ex_pie.id,   "segment": "calentamiento", "position": 2},
            {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 1},
            {"exercise_id": ex_limbo.id, "segment": "principal",     "position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 3

    # calentamiento pos=1 must come before calentamiento pos=2.
    assert items[0]["segment"] == "calentamiento"
    assert items[0]["position"] == 1
    assert items[0]["exercise_id"] == ex_slalom.id

    assert items[1]["segment"] == "calentamiento"
    assert items[1]["position"] == 2
    assert items[1]["exercise_id"] == ex_pie.id

    # principal comes after calentamiento.
    assert items[2]["segment"] == "principal"
    assert items[2]["position"] == 0
    assert items[2]["exercise_id"] == ex_limbo.id


# ---------------------------------------------------------------------------
# T026-02: all three segments — full calentamiento / principal / vuelta_calma
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_spans_all_three_segments_in_order(session):
    """Exercises across all three segments are returned in canonical segment order."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    payload = _assemble_payload(
        items=[
            # Insert in reverse canonical order to ensure the server sorts.
            {"exercise_id": ex_semaforo.id, "segment": "vuelta_calma", "position": 0},
            {"exercise_id": ex_slalom.id,   "segment": "principal",    "position": 0},
            {"exercise_id": ex_pie.id,      "segment": "calentamiento","position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 3

    segments = [item["segment"] for item in items]
    assert segments == ["calentamiento", "principal", "vuelta_calma"]


# ---------------------------------------------------------------------------
# T026-03: single exercise in a single segment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_single_item(session):
    """A session assembled with one exercise returns a list with exactly one item."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["exercise_id"] == ex_pie.id
    assert items[0]["segment"] == "principal"
    assert items[0]["position"] == 0


# ---------------------------------------------------------------------------
# T026-04: non-contiguous position values are ordered correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_non_contiguous_positions_sorted(session):
    """Positions 0, 5, 10 within the same segment are returned in ascending order."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_semaforo.id, "segment": "calentamiento", "position": 10},
            {"exercise_id": ex_pie.id,      "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_slalom.id,   "segment": "calentamiento", "position": 5},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 3
    positions = [item["position"] for item in items]
    assert positions == [0, 5, 10]


# ---------------------------------------------------------------------------
# T026-05 (FR-020): hiding an exercise after session assembly does not break
#                   the session exercise list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_intact_after_exercise_hidden(session):
    """FR-020: hiding an exercise via PATCH /visibility does not remove it from
    a previously assembled session (get_session_exercises includes hidden rows).
    """
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]

    # Assemble a session with two exercises.
    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id,   "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_slalom.id, "segment": "principal",    "position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    # Hide one of the exercises after the session is assembled.
    async with make_client(session) as client:
        patch_resp = await client.patch(
            f"{BASE}/exercises/{ex_pie.id}/visibility",
            json={"is_hidden": True},
        )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["is_hidden"] is True

    # Verify that the catalog list no longer shows the hidden exercise.
    async with make_client(session) as client:
        catalog_resp = await client.get(f"{BASE}/exercises")
    catalog_slugs = {item["slug"] for item in catalog_resp.json()["items"]}
    assert "pie-abajo-test" not in catalog_slugs, (
        "Hidden exercise must not appear in default catalog list"
    )

    # The session must still return both exercises — FR-020 guarantees
    # that hiding does not corrupt previously saved sessions.
    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2, (
        f"Expected 2 items (FR-020 — hidden exercise must remain in session), "
        f"got {len(items)}: {items}"
    )
    exercise_ids = {item["exercise_id"] for item in items}
    assert ex_pie.id in exercise_ids
    assert ex_slalom.id in exercise_ids


# ---------------------------------------------------------------------------
# T026-06 (FR-020): unhiding an exercise leaves session unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_intact_after_exercise_unhidden(session):
    """FR-020: toggling is_hidden back to False also has no side-effect on the
    assembled session (items remain stable regardless of visibility state).
    """
    catalog = await _seed_base(session)
    ex_trackstand = catalog["exercises"]["trackstand"]  # starts hidden=True

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    # Unhide the exercise.
    async with make_client(session) as client:
        patch_resp = await client.patch(
            f"{BASE}/exercises/{ex_trackstand.id}/visibility",
            json={"is_hidden": False},
        )
    assert patch_resp.status_code == 200, patch_resp.text

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["exercise_id"] == ex_trackstand.id


# ---------------------------------------------------------------------------
# T026-07: session with no technique exercises returns empty list (not 404)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_empty_list_for_non_technique_session(session):
    """A session that has no TechniqueSessionExercise rows returns [].

    The endpoint does not raise 404 for a valid training session without
    technique links (regular non-technique sessions are legal callers).
    """
    from app.models.training_session import (
        SessionKind,
        SessionStatus,
        TrainingSession,
    )

    await _seed_base(session)

    # Insert a bare TrainingSession without going through the assembler.
    ts = TrainingSession(
        club_id=1,
        created_by_user_id=10,
        status=SessionStatus.PLANNED,
        session_kind=SessionKind.ENTRENAMIENTO,
        scheduled_date=date(2026, 7, 10),
        scheduled_start_time=time(10, 0),
        duration_min=45,
        location="Cancha Ficticia",
        technical_focus="Técnica base (test sin técnica)",
    )
    session.add(ts)
    await session.commit()
    await session.refresh(ts)

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{ts.id}/exercises")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ---------------------------------------------------------------------------
# T026-08: unknown session id — service returns empty list (no 404)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_unknown_session_returns_empty_list(session):
    """get_session_exercises filters by FK; unknown session simply yields [].

    The router does not validate whether the session row exists; it delegates
    to get_session_exercises which returns an empty result set.
    """
    await _seed_base(session)
    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/99999/exercises")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ---------------------------------------------------------------------------
# T026-09: response shape — TechniqueSessionItem contract fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_response_shape(session):
    """Each item in the response has the TechniqueSessionItem contract fields."""
    catalog = await _seed_base(session)
    ex_limbo = catalog["exercises"]["limbo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_limbo.id, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1

    item = items[0]
    # TechniqueSessionItem mandatory fields.
    for field in ("exercise_id", "name", "segment", "position", "age_bands", "skills"):
        assert field in item, f"Missing TechniqueSessionItem field: {field}"

    assert isinstance(item["age_bands"], list)
    assert len(item["age_bands"]) > 0

    assert isinstance(item["skills"], list)
    assert len(item["skills"]) > 0
    # Nested SkillRead shape.
    skill = item["skills"][0]
    for skill_field in ("code", "slug", "name"):
        assert skill_field in skill, f"Missing SkillRead field: {skill_field}"


# ---------------------------------------------------------------------------
# T026-10: assemble response shape matches POST contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_response_shape(session):
    """POST /api/technique/sessions 201 body matches AssembleSessionResponse contract."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert "training_session_id" in body
    assert isinstance(body["training_session_id"], int)
    assert "mixes_age_bands" in body
    assert isinstance(body["mixes_age_bands"], bool)
    assert "items" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 1


# ---------------------------------------------------------------------------
# T026-11: mixes_age_bands flag — False when all exercises share the same bands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_mixes_age_bands_false_same_band(session):
    """mixes_age_bands=False when all exercises target the same single band.

    trackstand targets 13-15 only; a session with just trackstand has a union
    of exactly one band → mixes_age_bands must be False.
    """
    catalog = await _seed_base(session)
    ex_trackstand = catalog["exercises"]["trackstand"]  # bands: 13-15 only

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["mixes_age_bands"] is False


# ---------------------------------------------------------------------------
# T026-12: mixes_age_bands flag — True when exercises span multiple bands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_mixes_age_bands_true_different_bands(session):
    """mixes_age_bands=True when exercises span more than one age band.

    slalom (7-9, 10-12) + trackstand (13-15 only) → union has all three bands.
    """
    catalog = await _seed_base(session)
    ex_slalom = catalog["exercises"]["slalom"]       # bands: 7-9, 10-12
    ex_trackstand = catalog["exercises"]["trackstand"]  # bands: 13-15

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_slalom.id,    "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_trackstand.id, "segment": "principal",    "position": 0},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["mixes_age_bands"] is True


# ---------------------------------------------------------------------------
# T026-13: 422 when exercise_id does not exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_unknown_exercise_id_returns_422(session):
    """POST /api/technique/sessions with an unknown exercise_id returns 422."""
    await _seed_base(session)

    payload = _assemble_payload(
        items=[
            {"exercise_id": 99999, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 422, resp.text
    assert "99999" in resp.text


# ---------------------------------------------------------------------------
# T026-14: RBAC — parent receives 403 on session exercises read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_parent_receives_403(session):
    """Parent cannot read session exercises — 403 (FR-021)."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "principal", "position": 0},
        ]
    )
    # Assemble with coach first.
    async with make_client(session, user=coach_user_obj(10)) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    # Parent tries to read.
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# T026-15: RBAC — parent receives 403 on session assembly (POST)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_parent_receives_403(session):
    """Parent cannot assemble a technique session — 403 (FR-021)."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "principal", "position": 0},
        ]
    )
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# T026-16: RBAC — unauthenticated request receives 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_anonymous_receives_401(session):
    """No Authorization header → 401 on the session exercises endpoint."""
    await _seed_base(session)
    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/sessions/1/exercises")
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# T026-17: RBAC — admin can read session exercises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_exercises_admin_200(session):
    """Admin role can read session exercises without error."""
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
        ]
    )
    async with make_client(session, user=coach_user_obj(10)) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    session_id = post_resp.json()["training_session_id"]

    # Admin needs a club membership for POST (assembler calls _coach_club_id);
    # for GET it only needs the RBAC gate.
    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id}/exercises")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1


# ---------------------------------------------------------------------------
# T026-18 (FR-020): visibility patch on exercise does not alter other sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hiding_exercise_does_not_affect_other_session(session):
    """FR-020: hiding an exercise does not corrupt a different session that does
    not contain that exercise.
    """
    catalog = await _seed_base(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]
    ex_limbo = catalog["exercises"]["limbo"]

    # Session A: contains pie_abajo only.
    payload_a = _assemble_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "principal", "position": 0},
        ]
    )
    # Session B: contains slalom + limbo.
    payload_b = _assemble_payload(
        items=[
            {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_limbo.id,  "segment": "principal",     "position": 0},
        ]
    )

    async with make_client(session) as client:
        resp_a = await client.post(f"{BASE}/sessions", json=payload_a)
        resp_b = await client.post(f"{BASE}/sessions", json=payload_b)
    assert resp_a.status_code == 201 and resp_b.status_code == 201
    session_id_a = resp_a.json()["training_session_id"]
    session_id_b = resp_b.json()["training_session_id"]

    # Hide pie_abajo (only in session A).
    async with make_client(session) as client:
        patch_resp = await client.patch(
            f"{BASE}/exercises/{ex_pie.id}/visibility",
            json={"is_hidden": True},
        )
    assert patch_resp.status_code == 200, patch_resp.text

    # Session A still has pie_abajo (FR-020).
    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id_a}/exercises")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["exercise_id"] == ex_pie.id

    # Session B is unaffected — slalom and limbo are still there.
    async with make_client(session) as client:
        resp = await client.get(f"{BASE}/sessions/{session_id_b}/exercises")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    ids_b = {item["exercise_id"] for item in resp.json()}
    assert ex_slalom.id in ids_b
    assert ex_limbo.id in ids_b
