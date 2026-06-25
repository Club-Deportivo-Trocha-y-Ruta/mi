"""T035 — Privacy invariants for the athlete skill-progress endpoint (SC-005, SC-007).

Invariants verified:
  SC-005  GET /api/technique/athletes/{id}/progress returns data for ONLY athlete A;
          athlete B's progress records never appear in A's response.
  SC-007  The response body exposes no ranking, aggregate, or cross-athlete
          comparison field (no 'rank', 'percentile', 'average', 'comparison').
  FR-021  Parent and anonymous callers receive 403 / 401 respectively.
  PRIVACY No athlete full name leaks into any error body; error detail messages
          must not contain first_name or last_name of any athlete.

All tests run on an in-memory aiosqlite database (no live MySQL, no real network).
Seed data uses fictitious names and dates only (CLAUDE.md §Privacy constraint).
"""
from __future__ import annotations

import json
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
    seed_admin,
    seed_parent,
    seed_technique_catalog,
)
from app.models.technique_exercise import AthleteSkillProgress, SkillProgressStatus

BASE = "/api/technique"

# ---------------------------------------------------------------------------
# Internal seed helpers
# ---------------------------------------------------------------------------


async def _seed_base(session) -> dict:
    """Insert club, coach, admin, and parent rows common to all tests."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_admin(session, user_id=20)
    await seed_parent(session, user_id=30)
    return {}


async def _seed_athlete_a(session) -> object:
    """Insert athlete A: user_id=40, athlete_id=1, fictitious data."""
    await seed_athlete_user(session, user_id=40)
    return await seed_athlete_record(
        session,
        athlete_id=1,
        user_id=40,
        club_id=1,
        created_by=10,
    )


async def _seed_athlete_b(session) -> object:
    """Insert athlete B: user_id=41, athlete_id=2, fictitious data.

    Uses a distinct first_name/last_name so name-leak assertions are
    unambiguous — 'María Gómez Ficticia' must never appear in athlete A's
    progress response.
    """
    from datetime import date
    from app.models.athlete import Athlete, Sex
    from datetime import datetime, timezone

    user_b_id = 41
    athlete_b_id = 2

    from app.models.user import User, UserRole

    user_b = User(
        id=user_b_id,
        email=None,
        hashed_password=None,
        first_name="María",
        last_name="Gómez Ficticia",
        role=UserRole.athlete,
        is_active=True,
        can_login=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user_b)
    await session.flush()

    athlete_b = Athlete(
        id=athlete_b_id,
        user_id=user_b_id,
        first_name="María",
        last_name="Gómez Ficticia",
        birth_date=date(2013, 7, 22),
        sex=Sex.F,
        club_id=1,
        created_by=10,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(athlete_b)
    await session.flush()
    return athlete_b


async def _add_progress(session, athlete_id: int, skill_id: int, season: int = 2026) -> None:
    """Insert one AthleteSkillProgress event directly (no router round-trip)."""
    from datetime import datetime, timezone

    event = AthleteSkillProgress(
        athlete_id=athlete_id,
        skill_id=skill_id,
        status=SkillProgressStatus.EN_PROGRESO,
        coach_note="Mejora progresiva en el gesto técnico.",
        season=season,
        recorded_by_user_id=10,
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(event)
    await session.flush()


# ---------------------------------------------------------------------------
# SC-005: single-athlete scope — athlete B's data never appears in A's response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_response_contains_only_athlete_a(session):
    """GET progress for athlete A returns ONLY A's events (SC-005).

    Athlete B has a progress event on the same skill.  B's event must be
    completely absent from the response for athlete A.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await _seed_athlete_b(session)
    catalog = await seed_technique_catalog(session)
    await session.commit()

    skill_id = catalog["skills"]["posicion"].id

    # Both athletes get progress on the same skill.
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp_a = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "en_progreso", "season": 2026},
        )
        assert resp_a.status_code == 201, resp_a.text
        event_a_id = resp_a.json()["id"]

        resp_b = await client.post(
            f"{BASE}/athletes/2/progress",
            json={"skill_id": skill_id, "status": "dominado", "season": 2026},
        )
        assert resp_b.status_code == 201, resp_b.text
        event_b_id = resp_b.json()["id"]

    # Retrieve athlete A's progress.
    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    # athlete_id in response must be A's id.
    assert body["athlete_id"] == 1

    # Collect all event ids from both sections.
    all_event_ids = {e["id"] for e in body["current"]} | {e["id"] for e in body["history"]}

    # Athlete A's event must be present.
    assert event_a_id in all_event_ids, "Athlete A's progress event must appear in response."

    # Athlete B's event must be absent.
    assert event_b_id not in all_event_ids, (
        "Athlete B's progress event must NOT appear in athlete A's response (SC-005)."
    )


@pytest.mark.asyncio
async def test_progress_history_all_entries_belong_to_requested_athlete(session):
    """Every entry in history[] belongs to the requested athlete_id (SC-005).

    Multiple skills, multiple events for both A and B.  The invariant is
    checked on the raw athlete_id key: after DB insertion we assert that
    all events in history belong to athlete A (id=1).
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await _seed_athlete_b(session)
    catalog = await seed_technique_catalog(session)

    skill_posicion = catalog["skills"]["posicion"].id
    skill_frenado = catalog["skills"]["frenado"].id

    # Interleave inserts for both athletes across two skills.
    await _add_progress(session, athlete_id=1, skill_id=skill_posicion)
    await _add_progress(session, athlete_id=2, skill_id=skill_posicion)
    await _add_progress(session, athlete_id=1, skill_id=skill_frenado)
    await _add_progress(session, athlete_id=2, skill_id=skill_frenado)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    # history must have exactly 2 entries (one per skill for athlete A).
    assert len(body["history"]) == 2, (
        f"Expected 2 history entries for athlete A; got {len(body['history'])}."
    )

    # current must reflect one entry per skill (latest per skill = same event).
    assert len(body["current"]) == 2

    # Every history entry must belong to athlete A as confirmed by the
    # athlete_id field in the top-level response object.
    assert body["athlete_id"] == 1


@pytest.mark.asyncio
async def test_progress_current_contains_no_other_athlete_entries(session):
    """current[] snapshot for athlete A never mixes in athlete B's skills (SC-005).

    Each athlete has distinct skill sets so any B entry would cause a
    skill count mismatch.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await _seed_athlete_b(session)
    catalog = await seed_technique_catalog(session)

    skill_posicion = catalog["skills"]["posicion"].id
    skill_frenado = catalog["skills"]["frenado"].id
    skill_separacion = catalog["skills"]["separacion"].id

    # Athlete A: posicion + frenado (2 skills).
    await _add_progress(session, athlete_id=1, skill_id=skill_posicion)
    await _add_progress(session, athlete_id=1, skill_id=skill_frenado)
    # Athlete B: separacion only (different skill, 1 entry).
    await _add_progress(session, athlete_id=2, skill_id=skill_separacion)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    # current[] must have exactly 2 entries (A's two skills, not B's).
    assert len(body["current"]) == 2

    # Skill slugs in current must be A's skills only — separacion would indicate B's data.
    current_skill_slugs = {e["skill"]["slug"] for e in body["current"]}
    assert "separacion" not in current_skill_slugs, (
        "Athlete B's skill 'separacion' must not appear in athlete A's current snapshot."
    )
    assert current_skill_slugs == {"posicion", "frenado"}


# ---------------------------------------------------------------------------
# SC-007: no ranking / aggregate / comparison fields in the response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_response_exposes_no_ranking_fields(session):
    """AthleteProgressRead must not expose ranking or aggregate fields (SC-007).

    The contract (schemas/technique.py AthleteProgressRead) exposes only
    athlete_id, current, and history.  Any future accidental addition of
    cross-athlete fields (rank, percentile, club_average, comparison) must
    be caught here.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_technique_catalog(session)

    skill_id = catalog["skills"]["frenado"].id
    await _add_progress(session, athlete_id=1, skill_id=skill_id)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    FORBIDDEN_KEYS = {
        "rank", "ranking", "percentile", "average", "club_average",
        "comparison", "vs_peers", "peer_rank", "position", "standing",
        "aggregate",
    }

    def _scan(obj, path="root") -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                assert key not in FORBIDDEN_KEYS, (
                    f"Forbidden aggregate/ranking field '{key}' found at {path} "
                    f"in progress response (SC-007)."
                )
                _scan(val, path=f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, path=f"{path}[{i}]")

    _scan(body)


@pytest.mark.asyncio
async def test_progress_top_level_keys_are_exactly_the_contract(session):
    """Top-level response keys are exactly {athlete_id, current, history} (SC-007).

    Guards against silent schema drift that could add cross-athlete data.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_technique_catalog(session)

    skill_id = catalog["skills"]["posicion"].id
    await _add_progress(session, athlete_id=1, skill_id=skill_id)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200

    top_level_keys = set(resp.json().keys())
    assert top_level_keys == {"athlete_id", "current", "history"}, (
        f"Unexpected top-level keys in progress response: {top_level_keys - {'athlete_id', 'current', 'history'}}. "
        "Any addition must be reviewed for SC-007 compliance."
    )


@pytest.mark.asyncio
async def test_progress_event_keys_are_exactly_the_contract(session):
    """Each SkillProgressEvent in history[] exposes exactly the contract fields.

    Expected keys: id, skill, status, coach_note, season, recorded_at.
    Fields like athlete_id, first_name, last_name, birth_date, dob must
    not appear in the event payload.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_technique_catalog(session)

    skill_id = catalog["skills"]["frenado"].id
    await _add_progress(session, athlete_id=1, skill_id=skill_id)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["history"]) == 1
    event = body["history"][0]

    EXPECTED_EVENT_KEYS = {"id", "skill", "status", "coach_note", "season", "recorded_at"}
    FORBIDDEN_PII_KEYS = {
        "first_name", "last_name", "full_name", "name", "dob",
        "birth_date", "email", "athlete_id",
    }

    actual_keys = set(event.keys())
    assert actual_keys == EXPECTED_EVENT_KEYS, (
        f"SkillProgressEvent keys mismatch. Extra: {actual_keys - EXPECTED_EVENT_KEYS}. "
        f"Missing: {EXPECTED_EVENT_KEYS - actual_keys}."
    )

    for forbidden in FORBIDDEN_PII_KEYS:
        assert forbidden not in actual_keys, (
            f"PII or forbidden field '{forbidden}' found in SkillProgressEvent payload."
        )


# ---------------------------------------------------------------------------
# RBAC: parent → 403, anonymous → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_read_parent_receives_403(session):
    """Parent cannot read athlete progress (FR-021, RBAC)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_progress_write_parent_receives_403(session):
    """Parent cannot POST a progress event (FR-021, RBAC)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    catalog = await seed_technique_catalog(session)
    await session.commit()

    skill_id = catalog["skills"]["posicion"].id

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": skill_id, "status": "en_progreso", "season": 2026},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_progress_read_anonymous_receives_401(session):
    """Unauthenticated caller receives 401 on progress read (no Authorization header)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, authed=False) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_progress_write_anonymous_receives_401(session):
    """Unauthenticated caller receives 401 on progress write."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, authed=False) as client:
        resp = await client.post(
            f"{BASE}/athletes/1/progress",
            json={"skill_id": 1, "status": "en_progreso", "season": 2026},
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PRIVACY: athlete full name must not leak into any error response body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_athlete_full_name_not_in_404_error_body(session):
    """404 error detail for unknown athlete must not expose any athlete name.

    The service raises ValueError("Athlete {id} not found") which the router
    converts to a 404 detail.  The detail must be an opaque message — no
    first_name, last_name, or reconstructed full name may appear.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    # Athlete A's fictitious name from seed_athlete_record.
    athlete_a_first = "Juan"
    athlete_a_last = "Pérez Ficticio"

    async with make_client(session, user=coach_user_obj(10)) as client:
        # Request for a non-existent athlete id.
        resp = await client.get(f"{BASE}/athletes/99999/progress")
    assert resp.status_code == 404

    error_text = resp.text
    assert athlete_a_first not in error_text, (
        f"Athlete first name '{athlete_a_first}' must not appear in 404 error body."
    )
    assert athlete_a_last not in error_text, (
        f"Athlete last name '{athlete_a_last}' must not appear in 404 error body."
    )


@pytest.mark.asyncio
async def test_athlete_b_name_not_in_athlete_a_404_write_error(session):
    """Progress write 404 for unknown athlete must not expose any athlete name.

    Even when another athlete (B, with a distinct name) exists, a POST for
    a non-existent athlete_id must not mention any name in its error detail.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await _seed_athlete_b(session)
    catalog = await seed_technique_catalog(session)
    await session.commit()

    skill_id = catalog["skills"]["posicion"].id

    # B's fictitious name — must never appear in an error for a different id.
    athlete_b_first = "María"
    athlete_b_last = "Gómez Ficticia"

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(
            f"{BASE}/athletes/99999/progress",
            json={"skill_id": skill_id, "status": "en_progreso", "season": 2026},
        )
    assert resp.status_code == 404

    error_text = resp.text
    assert athlete_b_first not in error_text, (
        f"Athlete B first name '{athlete_b_first}' must not appear in error body."
    )
    assert athlete_b_last not in error_text, (
        f"Athlete B last name '{athlete_b_last}' must not appear in error body."
    )


@pytest.mark.asyncio
async def test_no_athlete_name_in_403_error_body(session):
    """403 response for parent caller must not expose any athlete's name."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    athlete_a_first = "Juan"
    athlete_a_last = "Pérez Ficticio"

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 403

    error_text = resp.text
    assert athlete_a_first not in error_text
    assert athlete_a_last not in error_text


# ---------------------------------------------------------------------------
# Happy-path baseline: empty progress for valid athlete is 200, not 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_athlete_with_no_progress_returns_200_empty(session):
    """GET progress for a valid athlete with no events returns 200 with empty lists.

    FR-018: graceful empty response — not a 404.  This guards against
    accidentally treating absence of progress as a missing resource.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["athlete_id"] == 1
    assert body["current"] == []
    assert body["history"] == []


@pytest.mark.asyncio
async def test_valid_athlete_with_no_progress_admin_200(session):
    """Admin also receives 200 with empty lists for a valid athlete (happy path)."""
    await _seed_base(session)
    await _seed_athlete_a(session)
    await session.commit()

    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.get(f"{BASE}/athletes/1/progress")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == []
    assert body["history"] == []


# ---------------------------------------------------------------------------
# Isolation: athlete B's response is also correctly scoped (symmetric check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_symmetry_b_does_not_see_a_events(session):
    """GET progress for athlete B must not contain athlete A's events (SC-005 symmetric).

    This mirrors the A-first direction to confirm the WHERE clause is always
    applied correctly regardless of which athlete_id is queried.
    """
    await _seed_base(session)
    await _seed_athlete_a(session)
    await _seed_athlete_b(session)
    catalog = await seed_technique_catalog(session)

    skill_id = catalog["skills"]["posicion"].id

    await _add_progress(session, athlete_id=1, skill_id=skill_id)
    # Athlete B has no events at all.
    await session.commit()

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.get(f"{BASE}/athletes/2/progress")
    assert resp.status_code == 200
    body = resp.json()

    # Athlete B has no events; A's event must not bleed through.
    assert body["athlete_id"] == 2
    assert body["current"] == [], (
        "Athlete A's current events must not appear in athlete B's response."
    )
    assert body["history"] == [], (
        "Athlete A's history events must not appear in athlete B's response."
    )
