"""T033 — Progress + privacy tests for the Strength Training Exercise Library
(feature 021, US4).

Mirrors ``backend/tests/technique/test_progress_privacy.py`` (feature 018),
adapted to the strength progress contract (see
``specs/021-strength-training-library/contracts/strength-api.md``):

  GET  /api/strength/athletes/{athlete_id}/progress
       -> 200 { "items": [ { exercise_id, exercise_name, status,
                              coach_note, season, recorded_at } ] }
       (latest row per exercise — NOT the full history, unlike 018's
       current/history split)
  POST /api/strength/athletes/{athlete_id}/progress
       Body { exercise_id, status, coach_note?, season } -> 201 (append-only)

Invariants verified:
  FR-020 / append-only (data-model.md "Progress notes")
      Every POST inserts a new ``strength_progress_notes`` row; a later POST
      for the same (athlete_id, exercise_id) never overwrites or deletes the
      earlier row — the underlying table is strictly append-only, and GET
      always resolves to the most-recent row per exercise.
  Latest-per-exercise read
      GET returns exactly one entry per exercise (the most recently recorded
      status), even when multiple progress notes exist for that exercise.
  PRIVACY (FR-020)
      Response bodies (GET items and POST body) expose no athlete PII beyond
      the ``athlete_id`` already present in the URL path — no first_name,
      last_name, full_name, dob/birth_date, email, or athlete_id duplicated
      inside the item payload. 404 error bodies for an unknown athlete must
      not leak any athlete's name either.
  Club scope (403)
      A coach who does not belong to the target athlete's club receives 403
      on both GET and POST, mirroring ``_require_athlete_club_scope`` from
      ``technique.py:417`` (data-model.md rule 3).
  RBAC
      Parent -> 403. Anonymous (no Authorization header) -> 401.

All tests run on an in-memory aiosqlite database (no live MySQL, no real
network). Seed data uses fictitious names and dates only (CLAUDE.md
§Privacy constraint).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.strength.conftest import (
    admin_user_obj,
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_athlete_record,
    seed_athlete_user,
    seed_club,
    seed_coach,
    seed_admin,
    seed_parent,
    seed_strength_catalog,
)
from app.models.strength import StrengthProgressNote, StrengthProgressStatus

BASE = "/api/strength"

# ---------------------------------------------------------------------------
# Internal seed helpers
# ---------------------------------------------------------------------------


async def _seed_base(session) -> None:
    """Insert club, coach, admin, and parent rows common to all tests."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_admin(session, user_id=20)
    await seed_parent(session, user_id=30)


async def _seed_athlete_a(session):
    """Insert athlete A: user_id=40, athlete_id=1, fictitious data."""
    await seed_athlete_user(session, user_id=40)
    return await seed_athlete_record(
        session,
        athlete_id=1,
        user_id=40,
        club_id=1,
        created_by=10,
    )


async def _add_progress_note(
    session,
    *,
    athlete_id: int,
    exercise_id: int,
    status: StrengthProgressStatus,
    season: int = 2026,
    coach_note: str | None = "Buen avance en control postural.",
) -> StrengthProgressNote:
    """Insert one StrengthProgressNote row directly (no router round-trip)."""
    note = StrengthProgressNote(
        athlete_id=athlete_id,
        exercise_id=exercise_id,
        status=status,
        coach_note=coach_note,
        season=season,
        recorded_by_user_id=10,
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(note)
    await session.flush()
    return note


# ---------------------------------------------------------------------------
# Append-only: a later POST never overwrites an earlier note
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_progress_appends_does_not_overwrite_prior_note(session):
    """A second POST for the same athlete+exercise adds a new row, keeping
    the first one intact in the database (append-only, data-model.md
    "Progress notes")."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp1 = await client.post(
            f"{BASE}/athletes/1/progress",
            json={
                "exercise_id": exercise_id,
                "status": "introducido",
                "coach_note": "Primera observación.",
                "season": 2026,
            },
        )
        assert resp1.status_code == 201, resp1.text

        resp2 = await client.post(
            f"{BASE}/athletes/1/progress",
            json={
                "exercise_id": exercise_id,
                "status": "en_progreso",
                "coach_note": "Segunda observación.",
                "season": 2026,
            },
        )
        assert resp2.status_code == 201, resp2.text

    # Both rows must exist in the underlying table — the first was never
    # overwritten or deleted.
    from sqlalchemy import select

    result = await session.execute(
        select(StrengthProgressNote).where(
            StrengthProgressNote.athlete_id == 1,
            StrengthProgressNote.exercise_id == exercise_id,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 2, (
        f"Expected 2 append-only rows after 2 POSTs; found {len(rows)}."
    )
    statuses = {r.status for r in rows}
    assert statuses == {
        StrengthProgressStatus.INTRODUCIDO,
        StrengthProgressStatus.EN_PROGRESO,
    }


@pytest.mark.asyncio
async def test_post_progress_multiple_notes_all_persist_in_history(session):
    """Three consecutive POSTs for the same exercise leave three rows in the
    database — none are overwritten (append-only invariant, repeated)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["sentadilla"].id
    statuses = ["introducido", "en_progreso", "dominado"]

    async with make_client(session, user=coach_user_obj(10)) as client:
        for st in statuses:
            resp = await client.post(
                f"{BASE}/athletes/1/progress",
                json={"exercise_id": exercise_id, "status": st, "season": 2026},
            )
            assert resp.status_code == 201, resp.text

    from sqlalchemy import select

    result = await session.execute(
        select(StrengthProgressNote).where(
            StrengthProgressNote.athlete_id == 1,
            StrengthProgressNote.exercise_id == exercise_id,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 3, (
        f"Expected 3 append-only rows after 3 POSTs; found {len(rows)}."
    )


# ---------------------------------------------------------------------------
# GET returns the latest status per exercise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_progress_returns_latest_status_per_exercise(session):
    """GET returns exactly one item per exercise, reflecting the most
    recently recorded status (contract: "latest row per exercise")."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id

    await _add_progress_note(
        session,
        athlete_id=1,
        exercise_id=exercise_id,
        status=StrengthProgressStatus.INTRODUCIDO,
    )
    # Second, later note for the SAME exercise — this is the one GET must
    # surface.
    await _add_progress_note(
        session,
        athlete_id=1,
        exercise_id=exercise_id,
        status=StrengthProgressStatus.DOMINADO,
        coach_note="Domina el gesto de forma consistente.",
    )
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    items = [i for i in body["items"] if i["exercise_id"] == exercise_id]
    assert len(items) == 1, (
        f"Expected exactly 1 item for exercise {exercise_id} (latest-wins); "
        f"got {len(items)}."
    )
    assert items[0]["status"] == "dominado"
    assert items[0]["coach_note"] == "Domina el gesto de forma consistente."


@pytest.mark.asyncio
async def test_get_progress_one_item_per_exercise_with_multiple_exercises(session):
    """When progress exists for two exercises, GET returns one item per
    exercise, each showing its own latest status."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_flexiones = catalog["exercises"]["flexiones"].id
    exercise_plancha = catalog["exercises"]["plancha"].id

    await _add_progress_note(
        session,
        athlete_id=1,
        exercise_id=exercise_flexiones,
        status=StrengthProgressStatus.INTRODUCIDO,
    )
    await _add_progress_note(
        session,
        athlete_id=1,
        exercise_id=exercise_flexiones,
        status=StrengthProgressStatus.EN_PROGRESO,
    )
    await _add_progress_note(
        session,
        athlete_id=1,
        exercise_id=exercise_plancha,
        status=StrengthProgressStatus.DOMINADO,
    )
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["items"]) == 2, (
        f"Expected 1 item per distinct exercise (2 exercises); got "
        f"{len(body['items'])}."
    )

    by_exercise = {i["exercise_id"]: i for i in body["items"]}
    assert by_exercise[exercise_flexiones]["status"] == "en_progreso"
    assert by_exercise[exercise_plancha]["status"] == "dominado"


@pytest.mark.asyncio
async def test_get_progress_empty_for_valid_athlete_with_no_notes(session):
    """GET for a valid athlete with no progress notes returns 200 with an
    empty items list — not a 404 (graceful empty response)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# PRIVACY: no athlete PII beyond the athlete_id already in the URL path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_progress_response_top_level_keys_are_exactly_items(session):
    """Top-level response is exactly {"items": [...]} — no athlete_id, name,
    or other PII field is echoed back at the top level (FR-020)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id
    await _add_progress_note(
        session, athlete_id=1, exercise_id=exercise_id,
        status=StrengthProgressStatus.INTRODUCIDO,
    )
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    top_level_keys = set(resp.json().keys())
    assert top_level_keys == {"items"}, (
        f"Unexpected top-level keys in progress response: "
        f"{top_level_keys - {'items'}}."
    )


@pytest.mark.asyncio
async def test_get_progress_item_keys_contain_no_athlete_pii(session):
    """Each item exposes only exercise_id, exercise_name, status, coach_note,
    season, recorded_at — no athlete_id, first_name, last_name, full_name,
    dob/birth_date, or email (FR-020)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id
    await _add_progress_note(
        session, athlete_id=1, exercise_id=exercise_id,
        status=StrengthProgressStatus.INTRODUCIDO,
    )
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]

    EXPECTED_KEYS = {
        "exercise_id", "exercise_name", "status", "coach_note", "season",
        "recorded_at",
    }
    FORBIDDEN_PII_KEYS = {
        "athlete_id", "first_name", "last_name", "full_name", "name",
        "dob", "birth_date", "email",
    }

    actual_keys = set(item.keys())
    assert actual_keys == EXPECTED_KEYS, (
        f"Progress item keys mismatch. Extra: {actual_keys - EXPECTED_KEYS}. "
        f"Missing: {EXPECTED_KEYS - actual_keys}."
    )
    for forbidden in FORBIDDEN_PII_KEYS:
        assert forbidden not in actual_keys, (
            f"PII or forbidden field '{forbidden}' found in progress item payload."
        )


@pytest.mark.asyncio
async def test_athlete_full_name_not_in_404_error_body(session):
    """404 error detail for an unknown athlete must not expose any athlete
    name — the detail must be an opaque message (FR-020, mirrors
    technique.py:417 behaviour)."""
    await _seed_base(session)
    athlete_a = await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/99999/progress")
    assert resp.status_code == 404

    error_text = resp.text
    assert athlete_a.first_name not in error_text
    assert athlete_a.last_name not in error_text


@pytest.mark.asyncio
async def test_athlete_full_name_not_in_write_404_error_body(session):
    """POST for an unknown athlete_id returns 404 with no athlete name in
    the error detail."""
    await _seed_base(session)
    athlete_a = await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/99999/progress",
            json={"exercise_id": exercise_id, "status": "introducido", "season": 2026},
        )
    assert resp.status_code == 404

    error_text = resp.text
    assert athlete_a.first_name not in error_text
    assert athlete_a.last_name not in error_text


# ---------------------------------------------------------------------------
# Club scope: coach outside the athlete's club -> 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_progress_cross_club_coach_receives_403(session):
    """A coach who belongs only to club 2 receives 403 when reading the
    progress of an athlete who belongs to club 1 (data-model.md rule 3)."""
    from app.models.club import Club, ClubMember, ClubRole

    await _seed_base(session)
    await _seed_athlete_a(session)

    club2 = Club(
        id=2,
        name="Club Ficticio 2 — datos de prueba",
        code="TST002",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club2)
    await session.flush()

    coach2 = coach_user_obj(user_id=50)
    session.add(coach2)
    await session.flush()

    session.add(
        ClubMember(
            club_id=2,
            user_id=50,
            role_in_club=ClubRole.coach,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()
    await session.commit()

    async with make_client(session, user=coach_user_obj(user_id=50)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 403, (
        f"Cross-club coach must receive 403; got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_post_progress_cross_club_coach_receives_403(session):
    """A coach who belongs only to club 2 receives 403 when writing progress
    for an athlete who belongs to club 1."""
    from app.models.club import Club, ClubMember, ClubRole

    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)

    club2 = Club(
        id=2,
        name="Club Ficticio 2 — datos de prueba",
        code="TST002",
        location="Valle del Cauca — datos ficticios",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(club2)
    await session.flush()

    coach2 = coach_user_obj(user_id=50)
    session.add(coach2)
    await session.flush()

    session.add(
        ClubMember(
            club_id=2,
            user_id=50,
            role_in_club=ClubRole.coach,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id

    async with make_client(session, user=coach_user_obj(user_id=50)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"exercise_id": exercise_id, "status": "introducido", "season": 2026},
        )
    assert resp.status_code == 403, (
        f"Cross-club coach must receive 403 on write; got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_admin_bypasses_club_scope_on_progress(session):
    """Admin users are not restricted by club scope (data-model.md rule 3
    exempts admin) — GET returns 200 even without a club membership."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# RBAC: parent -> 403, anonymous -> 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_progress_parent_receives_403(session):
    """Parent cannot read athlete progress — all strength endpoints require
    coach/admin (contract: "No athlete/parent access")."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_progress_parent_receives_403(session):
    """Parent cannot POST a progress note."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_strength_catalog(session)
    await session.commit()

    exercise_id = catalog["exercises"]["flexiones"].id

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"exercise_id": exercise_id, "status": "introducido", "season": 2026},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_progress_anonymous_receives_401(session):
    """Unauthenticated caller receives 401 on progress read."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_progress_anonymous_receives_401(session):
    """Unauthenticated caller receives 401 on progress write."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"exercise_id": 1, "status": "introducido", "season": 2026},
        )
    assert resp.status_code == 401
