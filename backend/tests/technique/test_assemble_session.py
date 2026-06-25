"""T025 — POST /api/technique/sessions: session assembly (feature 018).

Coverage:
  - Happy path: creates a real TrainingSession row and TechniqueSessionExercise
    rows in the same aiosqlite in-memory DB.
  - mixes_age_bands=True when items span >1 AgeBand.
  - mixes_age_bands=False when all items share a single AgeBand.
  - 422 on empty items list (Pydantic min_length=1 guard).
  - 422 on unknown exercise_id.
  - 403 for parent role (FR-021).

All tests use the technique conftest fixtures (aiosqlite, no live MySQL, no JWT).
Seed data is fictitious (non-negotiable constraint, CLAUDE.md §Privacy).
"""
from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy import select

from app.models.technique_exercise import TechniqueSessionExercise
from app.models.training_session import TrainingSession
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
# Shared fixture payload builders
# ---------------------------------------------------------------------------

_SCHED_DATE = "2026-08-01"
_SCHED_TIME = "09:00:00"
_DURATION = 60
_LOCATION = "Pista Ficticia Valle"
_FOCUS = "Técnica de frenado y equilibrio"


def _base_payload(**overrides) -> dict:
    """Return a minimal valid AssembleSessionRequest payload."""
    payload: dict = {
        "scheduled_date": _SCHED_DATE,
        "scheduled_start_time": _SCHED_TIME,
        "duration_min": _DURATION,
        "location": _LOCATION,
        "technical_focus": _FOCUS,
        "convocados_athlete_ids": [1],
        "items": [],  # callers override this
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Seed helper: inserts everything POST /sessions needs
# ---------------------------------------------------------------------------


async def _seed_for_assemble(session) -> dict:
    """Seed club, coach, athlete user, athlete record, and technique catalog.

    Returns the catalog dict from seed_technique_catalog so callers can
    reference exercise ids by slug key.
    """
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_athlete_user(session, user_id=40)
    await seed_athlete_record(session, athlete_id=1, user_id=40, club_id=1, created_by=10)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ---------------------------------------------------------------------------
# Happy path: single age band — mixes_age_bands=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_creates_training_session_row(session):
    """POST /sessions 201 and a real TrainingSession row exists in the DB.

    Uses trackstand-test (age_bands=[13-15] only) twice with different segments
    so the union remains {13-15} → mixes_age_bands=False.
    Also verifies the TrainingSession row is present in aiosqlite after the call.
    """
    catalog = await _seed_for_assemble(session)
    ex_trackstand = catalog["exercises"]["trackstand"]  # only band: 13-15

    payload = _base_payload(items=[
        {"exercise_id": ex_trackstand.id, "segment": "calentamiento", "position": 0},
        {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Response schema: training_session_id, mixes_age_bands, items
    assert "training_session_id" in body
    assert isinstance(body["training_session_id"], int)
    # trackstand spans only 13-15 → single band → False
    assert body["mixes_age_bands"] is False
    assert len(body["items"]) == 2

    # Verify the TrainingSession row exists in the DB.
    ts_id = body["training_session_id"]
    row = await session.get(TrainingSession, ts_id)
    assert row is not None, "TrainingSession row not found after assemble"
    assert row.location == _LOCATION
    assert row.technical_focus == _FOCUS


@pytest.mark.asyncio
async def test_assemble_session_writes_technique_session_exercise_rows(session):
    """technique_session_exercises rows are written and retrievable via GET."""
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    payload = _base_payload(items=[
        {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
        {"exercise_id": ex_semaforo.id, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    ts_id = post_resp.json()["training_session_id"]

    # Query the link table directly.
    result = await session.execute(
        select(TechniqueSessionExercise).where(
            TechniqueSessionExercise.training_session_id == ts_id
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 2, f"Expected 2 TechniqueSessionExercise rows, got {len(rows)}"

    exercise_ids_in_db = {r.exercise_id for r in rows}
    assert ex_pie.id in exercise_ids_in_db
    assert ex_semaforo.id in exercise_ids_in_db


@pytest.mark.asyncio
async def test_assemble_session_get_exercises_returns_ordered_items(session):
    """GET /sessions/{id}/exercises returns items ordered by (segment, position)."""
    catalog = await _seed_for_assemble(session)
    ex_slalom = catalog["exercises"]["slalom"]
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    payload = _base_payload(items=[
        # Intentionally out of segment order to verify server-side sorting.
        {"exercise_id": ex_slalom.id, "segment": "principal", "position": 0},
        {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
        {"exercise_id": ex_semaforo.id, "segment": "vuelta_calma", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        post_resp = await client.post(f"{BASE}/sessions", json=payload)
        assert post_resp.status_code == 201, post_resp.text
        ts_id = post_resp.json()["training_session_id"]

        get_resp = await client.get(f"{BASE}/sessions/{ts_id}/exercises")

    assert get_resp.status_code == 200, get_resp.text
    items = get_resp.json()
    assert len(items) == 3

    # Validate segment ordering: calentamiento < principal < vuelta_calma
    segments = [item["segment"] for item in items]
    assert segments[0] == "calentamiento"
    assert segments[1] == "principal"
    assert segments[2] == "vuelta_calma"


# ---------------------------------------------------------------------------
# mixes_age_bands=True when items span >1 distinct AgeBand
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_mixes_age_bands_true(session):
    """mixes_age_bands=True when items include exercises from different age bands.

    trackstand-test (13-15 only) + slalom-test (7-9, 10-12) → union has
    at least two distinct bands → True.
    We use include_hidden=True implicitly — the assembler doesn't filter
    hidden exercises, only the catalog browse does.
    """
    catalog = await _seed_for_assemble(session)
    ex_trackstand = catalog["exercises"]["trackstand"]  # age_bands=[13-15]
    ex_slalom = catalog["exercises"]["slalom"]           # age_bands=[7-9, 10-12]

    payload = _base_payload(items=[
        {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
        {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    assert resp.json()["mixes_age_bands"] is True


@pytest.mark.asyncio
async def test_assemble_session_mixes_age_bands_false_single_band(session):
    """mixes_age_bands=False when all items share exactly one AgeBand.

    trackstand-test has only age_band 13-15.  A single-exercise session
    therefore has exactly one band → False.
    """
    catalog = await _seed_for_assemble(session)
    ex_trackstand = catalog["exercises"]["trackstand"]  # age_bands=[13-15] only

    payload = _base_payload(items=[
        {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    assert resp.json()["mixes_age_bands"] is False


@pytest.mark.asyncio
async def test_assemble_session_mixes_age_bands_true_three_band_exercise(session):
    """mixes_age_bands=True when a single exercise already covers all 3 bands.

    pie-abajo-test has [7-9, 10-12, 13-15] → union size=3 → True.
    """
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]  # all three bands

    payload = _base_payload(items=[
        {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    assert resp.json()["mixes_age_bands"] is True


# ---------------------------------------------------------------------------
# 422: empty items list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_empty_items_returns_422(session):
    """422 when items=[] (Pydantic min_length=1 on AssembleSessionRequest.items)."""
    await _seed_for_assemble(session)

    payload = _base_payload(items=[])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 422: unknown exercise_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_unknown_exercise_id_returns_422(session):
    """422 when any item references a non-existent exercise_id."""
    await _seed_for_assemble(session)

    payload = _base_payload(items=[
        {"exercise_id": 99999, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 422, resp.text
    # The error detail should mention the missing id.
    detail = resp.json().get("detail", "")
    assert "99999" in str(detail)


@pytest.mark.asyncio
async def test_assemble_session_partial_unknown_exercise_id_returns_422(session):
    """422 when the items list mixes valid and invalid exercise_ids."""
    catalog = await _seed_for_assemble(session)
    ex_slalom = catalog["exercises"]["slalom"]

    payload = _base_payload(items=[
        {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0},
        {"exercise_id": 88888, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail", "")
    assert "88888" in str(detail)


# ---------------------------------------------------------------------------
# 403: parent role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_parent_returns_403(session):
    """Parent receives 403 on POST /sessions (FR-021, RBAC guard)."""
    catalog = await _seed_for_assemble(session)
    ex_slalom = catalog["exercises"]["slalom"]

    # Also seed a parent user so the override resolves cleanly.
    from tests.technique.conftest import seed_parent
    await seed_parent(session, user_id=30)
    await session.commit()

    payload = _base_payload(items=[
        {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0},
    ])

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Admin can also assemble (admin must have club membership for _coach_club_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_admin_with_club_membership_201(session):
    """Admin with a club membership can assemble a technique session (201)."""
    from app.models.club import ClubMember, ClubRole
    from datetime import datetime, timezone

    catalog = await _seed_for_assemble(session)
    ex_semaforo = catalog["exercises"]["semaforo"]

    # Seed admin user and give them a club membership (required by _coach_club_id).
    from tests.technique.conftest import seed_admin
    admin = await seed_admin(session, user_id=20)
    cm = ClubMember(
        club_id=1,
        user_id=20,
        role_in_club=ClubRole.admin,
        joined_at=datetime.now(timezone.utc),
    )
    session.add(cm)
    await session.commit()

    payload = _base_payload(items=[
        {"exercise_id": ex_semaforo.id, "segment": "calentamiento", "position": 0},
    ])

    async with make_client(session, user=admin_user_obj(20)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["training_session_id"] > 0


# ---------------------------------------------------------------------------
# Response items field shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_response_items_shape(session):
    """Each item in the response carries exercise_id, name, segment, position,
    age_bands, and skills as per TechniqueSessionItem schema."""
    catalog = await _seed_for_assemble(session)
    ex_limbo = catalog["exercises"]["limbo"]  # skills=[separacion], bands=[10-12,13-15]

    payload = _base_payload(items=[
        {"exercise_id": ex_limbo.id, "segment": "principal", "position": 0},
    ])

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)

    assert resp.status_code == 201, resp.text
    items = resp.json()["items"]
    assert len(items) == 1

    item = items[0]
    assert item["exercise_id"] == ex_limbo.id
    assert item["name"] == "Limbo en bici (test)"
    assert item["segment"] == "principal"
    assert item["position"] == 0
    assert set(item["age_bands"]) == {"10-12", "13-15"}
    assert len(item["skills"]) == 1
    assert item["skills"][0]["slug"] == "separacion"


# ---------------------------------------------------------------------------
# Session is retrievable via standard training session id after creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_session_training_session_is_retrievable_by_id(session):
    """The created TrainingSession can be fetched from DB by its primary key.

    Confirms the row persists after both commits (one inside create_session,
    one after link rows), and that field values match the request payload.
    """
    catalog = await _seed_for_assemble(session)
    ex_slalom = catalog["exercises"]["slalom"]

    payload = _base_payload(
        scheduled_date="2026-09-15",
        scheduled_start_time="08:30:00",
        duration_min=90,
        location="Circuito Ficticio Norte",
        technical_focus="Slalom avanzado",
        objectives="Mejorar tiempo en slalom de 10 conos",
        items=[
            {"exercise_id": ex_slalom.id, "segment": "principal", "position": 0},
        ],
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 201, resp.text
    ts_id = resp.json()["training_session_id"]

    # expire_all() is synchronous on AsyncSession; no await needed.
    session.expire_all()
    ts = await session.get(TrainingSession, ts_id)
    assert ts is not None
    assert ts.location == "Circuito Ficticio Norte"
    assert ts.technical_focus == "Slalom avanzado"
    assert ts.objectives == "Mejorar tiempo en slalom de 10 conos"
    assert ts.duration_min == 90
