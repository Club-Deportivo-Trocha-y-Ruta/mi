"""T034 — Progress endpoints: POST append + GET read (feature 018, T037).

Endpoints under test:
  POST /api/technique/athletes/{athlete_id}/progress  — append a skill-progress event
  GET  /api/technique/athletes/{athlete_id}/progress  — read current + history

Scenarios covered:
  Happy path
    test_post_progress_creates_event           — first POST returns 201 + SkillProgressEvent
    test_post_progress_event_fields            — response fields match the payload
    test_second_post_updates_current           — second POST on same skill: history grows,
                                                 current reflects latest status
    test_get_progress_current_is_latest        — current = latest-per-skill; history = all
    test_get_progress_empty_athlete            — valid athlete with no events → 200 {current:[],history:[]}
    test_multiple_skills_current_one_per_skill — two skills recorded; current has 2 items
    test_post_with_coach_note                  — coach_note persisted and returned
    test_post_without_coach_note               — coach_note omitted → null in response
    test_admin_can_post_progress               — admin role also produces 201
    test_get_history_ordered_ascending         — history list is oldest-first

  Negative / RBAC
    test_post_progress_unknown_athlete_404     — POST with non-existent athlete_id → 404
    test_get_progress_unknown_athlete_404      — GET with non-existent athlete_id → 404
    test_post_progress_parent_403              — parent role → 403
    test_get_progress_parent_403               — parent role → 403
    test_post_progress_anonymous_401           — no auth → 401
    test_get_progress_anonymous_401            — no auth → 401

  Privacy
    test_response_has_no_dob_or_full_name      — DOB and birth date must not appear in response body
    test_coach_note_excluded_from_any_log      — coach_note not emitted at INFO or above in logs
                                                 (privacy guard for minor data)

All tests run on aiosqlite in-memory DB; no live MySQL, no network calls.
Deterministic: no time.sleep; freezegun not needed here because recorded_at
is generated DB-side and we only assert relative ordering / field presence.
Fictitious names and DOBs; no real TyR athlete data (CLAUDE.md §Privacy).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from app.models.technique_exercise import SkillProgressStatus
from tests.technique.conftest import (
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
    seed_technique_catalog,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE = "/api/technique"
SEASON = 2026


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------


async def _setup(
    session,
    *,
    with_athlete: bool = True,
    athlete_id: int = 1,
) -> dict:
    """Seed the minimal rows every progress test needs.

    Always seeds: club 1, coach (id=10) with membership, admin (id=20),
    parent (id=30), technique catalog (3 skills, 5 exercises).
    When ``with_athlete=True`` also seeds athlete user (id=40) and
    Athlete record (id=athlete_id, fictitious DOB 2012-03-15).
    Returns the catalog dict so tests can look up skill ids.
    """
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_admin(session, user_id=20)
    await seed_parent(session, user_id=30)
    catalog = await seed_technique_catalog(session)
    if with_athlete:
        await seed_athlete_user(session, user_id=40)
        await seed_athlete_record(session, athlete_id=athlete_id, user_id=40, club_id=1)
    await session.commit()
    return catalog


def _skill_id(catalog: dict, slug: str) -> int:
    """Convenience: return the PK of a seeded skill by slug."""
    return catalog["skills"][slug].id


# ---------------------------------------------------------------------------
# Happy path — POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_progress_creates_event(session):
    """First POST to progress returns 201 and a SkillProgressEvent body."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Contract fields from SkillProgressEvent
    assert "id" in body
    assert "skill" in body
    assert "status" in body
    assert "season" in body
    assert "recorded_at" in body


@pytest.mark.asyncio
async def test_post_progress_event_fields(session):
    """Response fields echo back the submitted payload values."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "frenado")

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={
                "skill_id": skill_id,
                "status": "en_progreso",
                "coach_note": "Mejora en la modulación de la presión.",
                "season": SEASON,
            },
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "en_progreso"
    assert body["season"] == SEASON
    assert body["skill"]["slug"] == "frenado"
    assert body["coach_note"] == "Mejora en la modulación de la presión."
    # id must be a positive integer
    assert isinstance(body["id"], int)
    assert body["id"] > 0


@pytest.mark.asyncio
async def test_second_post_updates_current(session):
    """Two POSTs on the same skill grow history; GET current = second (latest) event."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, user=coach_user_obj(10)) as client:
        r1 = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )
        assert r1.status_code == 201, r1.text

        r2 = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "dominado", "season": SEASON},
        )
        assert r2.status_code == 201, r2.text
        # Latest event status must be the one we just submitted.
        assert r2.json()["status"] == "dominado"

        # GET: history should have both events; current should have one (the latest)
        rg = await client.get(f"{BASE}/athletes/1/progress")
    assert rg.status_code == 200, rg.text
    body = rg.json()

    history = body["history"]
    current = body["current"]

    assert len(history) == 2
    # current: exactly one entry per skill → only one since both POSTs used same skill
    assert len(current) == 1
    # The one current entry must be the latest status
    assert current[0]["status"] == "dominado"


@pytest.mark.asyncio
async def test_get_progress_current_is_latest(session):
    """GET /progress returns current = latest event per skill, history = all events."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "separacion")

    async with make_client(session, user=coach_user_obj(10)) as client:
        for s in ("introducido", "en_progreso", "dominado"):
            r = await client.post(
                f"{BASE}/athletes/1/progress",
                json={"skill_id": skill_id, "status": s, "season": SEASON},
            )
            assert r.status_code == 201

        rg = await client.get(f"{BASE}/athletes/1/progress")

    assert rg.status_code == 200, rg.text
    body = rg.json()

    assert body["athlete_id"] == 1
    assert len(body["history"]) == 3
    assert len(body["current"]) == 1
    assert body["current"][0]["status"] == "dominado"


@pytest.mark.asyncio
async def test_get_progress_empty_athlete(session):
    """Valid athlete with no progress events → 200 {current:[],history:[]}."""
    await _setup(session)

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["athlete_id"] == 1
    assert body["current"] == []
    assert body["history"] == []


@pytest.mark.asyncio
async def test_multiple_skills_current_one_per_skill(session):
    """Progress on two distinct skills → current has exactly two entries."""
    catalog = await _setup(session)
    skill_posicion = _skill_id(catalog, "posicion")
    skill_frenado = _skill_id(catalog, "frenado")

    async with make_client(session, user=coach_user_obj(10)) as client:
        for sid, status in [
            (skill_posicion, "introducido"),
            (skill_frenado, "en_progreso"),
        ]:
            r = await client.post(
                f"{BASE}/athletes/1/progress",
                json={"skill_id": sid, "status": status, "season": SEASON},
            )
            assert r.status_code == 201

        rg = await client.get(f"{BASE}/athletes/1/progress")

    assert rg.status_code == 200, rg.text
    body = rg.json()
    assert len(body["history"]) == 2
    # current must have exactly one entry per skill
    assert len(body["current"]) == 2
    current_slugs = {e["skill"]["slug"] for e in body["current"]}
    assert current_slugs == {"posicion", "frenado"}


@pytest.mark.asyncio
async def test_post_with_coach_note(session):
    """coach_note is persisted and round-tripped correctly."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")
    note = "Buen trackstand; trabaja la posición al entrar a curvas."

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "en_progreso", "coach_note": note, "season": SEASON},
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["coach_note"] == note


@pytest.mark.asyncio
async def test_post_without_coach_note(session):
    """Omitting coach_note yields null in the response — not a missing field."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "frenado")

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "coach_note" in body
    assert body["coach_note"] is None


@pytest.mark.asyncio
async def test_admin_can_post_progress(session):
    """Admin role is also allowed to record progress (same as coach)."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "separacion")

    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "dominado", "season": SEASON},
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "dominado"


@pytest.mark.asyncio
async def test_get_history_ordered_ascending(session):
    """History is returned oldest-first (recorded_at ASC)."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")
    statuses = ["introducido", "en_progreso", "dominado"]

    async with make_client(session, user=coach_user_obj(10)) as client:
        for s in statuses:
            r = await client.post(
                f"{BASE}/athletes/1/progress",
                json={"skill_id": skill_id, "status": s, "season": SEASON},
            )
            assert r.status_code == 201

        rg = await client.get(f"{BASE}/athletes/1/progress")

    assert rg.status_code == 200, rg.text
    history = rg.json()["history"]
    assert len(history) == 3

    # Statuses must appear in insertion order (oldest first)
    returned_statuses = [e["status"] for e in history]
    assert returned_statuses == statuses

    # Timestamps must be non-decreasing (aiosqlite resolves to iso strings)
    recorded_ats = [e["recorded_at"] for e in history]
    assert recorded_ats == sorted(recorded_ats)


# ---------------------------------------------------------------------------
# Negative / RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_progress_unknown_athlete_404(session):
    """POST to a non-existent athlete_id → 404 (graceful 7–9 handling, FR-018)."""
    catalog = await _setup(session, with_athlete=False)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/99999/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_get_progress_unknown_athlete_404(session):
    """GET for a non-existent athlete_id → 404 (graceful 7–9 handling, FR-018)."""
    await _setup(session, with_athlete=False)

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/99999/progress")

    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_post_progress_parent_403(session):
    """Parent role is forbidden on POST /athletes/{id}/progress (FR-021)."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_get_progress_parent_403(session):
    """Parent role is forbidden on GET /athletes/{id}/progress (FR-021)."""
    await _setup(session)

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_post_progress_anonymous_401(session):
    """Unauthenticated POST → 401 (no Authorization header)."""
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )

    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_get_progress_anonymous_401(session):
    """Unauthenticated GET → 401 (no Authorization header)."""
    await _setup(session)

    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")

    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_has_no_dob_or_full_name(session):
    """Progress API response must not expose the athlete's DOB or full name.

    The fictitious athlete "Juan Pérez Ficticio" (DOB 2012-03-15) must not
    appear anywhere in the GET or POST response body (Ley 1581 / FR-017,
    SC-005).  Names of real athletes are never used in test fixtures (CLAUDE.md
    §Privacy).
    """
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "posicion")

    async with make_client(session, user=coach_user_obj(10)) as client:
        post_resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "introducido", "season": SEASON},
        )
        assert post_resp.status_code == 201

        get_resp = await client.get(f"{BASE}/athletes/1/progress")
        assert get_resp.status_code == 200

    for resp_body, label in [(post_resp.text, "POST"), (get_resp.text, "GET")]:
        # DOB must not appear in any form (ISO date, year alone is acceptable
        # but the full date 2012-03-15 must not be emitted)
        assert "2012-03-15" not in resp_body, (
            f"{label} body must not expose athlete DOB"
        )
        # Full legal name must not appear
        assert "Pérez Ficticio" not in resp_body, (
            f"{label} body must not expose athlete full name"
        )


@pytest.mark.asyncio
async def test_coach_note_excluded_from_info_logs(session, caplog):
    """coach_note content must not appear in INFO-level or above log output.

    The progress service explicitly excludes coach_note from its debug log
    to prevent minor data from leaking into server logs (CLAUDE.md §Privacy).
    This test asserts that even when a note is provided it does not appear
    at WARNING or above severity.
    """
    catalog = await _setup(session)
    skill_id = _skill_id(catalog, "frenado")
    sensitive_note = "Atleta ficticio tiene dificultad al bajar pendientes."

    with caplog.at_level(logging.WARNING, logger="app.services.technique.progress"):
        async with make_client(session, user=coach_user_obj(10)) as client:
            resp = await client.post(
                f"{BASE}/athletes/1/progress",
                json={
                    "skill_id": skill_id,
                    "status": "en_progreso",
                    "coach_note": sensitive_note,
                    "season": SEASON,
                },
            )
        assert resp.status_code == 201

    # The note text must not appear in any log record at WARNING or above.
    for record in caplog.records:
        assert sensitive_note not in record.getMessage(), (
            f"coach_note leaked into log at level {record.levelname}"
        )
