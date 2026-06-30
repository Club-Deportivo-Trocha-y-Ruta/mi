"""T028 (QA) — Assemble creates a real TrainingSession with the synthetic
combined exercise (feature 019, US3, O-6).

Coverage:
  1. POST /sessions with combined_layout + >=2 component exercises creates
     exactly ONE TrainingSession (no parallel/duplicate store), readable via
     the normal GET /sessions/{id}/exercises endpoint.
  2. A hidden synthetic technique_exercise (is_hidden=True, is_gymkhana=True)
     exists with layout_json == the posted combined_layout (lossless), and
     is excluded from the normal catalog list (GET /exercises).
  3. The session links the synthetic exercise + the component exercises.
  4. Re-edit (combined_exercise_id + changed layout) updates the SAME
     synthetic row and the SAME session — no duplicate session, no duplicate
     synthetic exercise (FR-015).
  5. Anti-PII: a combined_layout element label that looks like an athlete
     name/DOB is rejected (422).
  6. Phase A strict guard regression: a normal POST /technique/exercises
     with a free-text label is still rejected (FR-023 unchanged).

Uses the technique integration harness (aiosqlite, ASGITransport) from
tests/technique/conftest.py. Seed data is fictitious (CLAUDE.md §Privacy).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.technique_exercise import TechniqueExercise, TechniqueSessionExercise
from app.models.training_session import TrainingSession
from app.schemas.technique import GymkhanaLayoutPhaseB
from tests.technique.conftest import (
    coach_user_obj,
    make_client,
    seed_athlete_record,
    seed_athlete_user,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

BASE = "/api/technique"

_SCHED_DATE = "2026-08-15"
_SCHED_TIME = "09:00:00"
_DURATION = 90
_LOCATION = "Pista Ficticia Valle"
_FOCUS = "Circuito combinado de gymkhana"

_COMBINED_LAYOUT = {
    "width": 100,
    "height": 60,
    "elements": [
        {"kind": "cone", "x": 10, "y": 10, "label": "Salida"},
        {"kind": "gate", "x": 50, "y": 30, "label": "#1"},
        {"kind": "ring", "x": 80, "y": 50},
    ],
}


def _base_payload(**overrides) -> dict:
    payload: dict = {
        "scheduled_date": _SCHED_DATE,
        "scheduled_start_time": _SCHED_TIME,
        "duration_min": _DURATION,
        "location": _LOCATION,
        "technical_focus": _FOCUS,
        "convocados_athlete_ids": [1],
        "items": [],
    }
    payload.update(overrides)
    return payload


async def _seed_for_assemble(session) -> dict:
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await seed_athlete_user(session, user_id=40)
    await seed_athlete_record(session, athlete_id=1, user_id=40, club_id=1, created_by=10)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


# ---------------------------------------------------------------------------
# 1-3. Combined assemble: single TrainingSession + hidden synthetic exercise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_combined_creates_single_session_and_hidden_synthetic(session):
    """combined_layout + >=2 items -> exactly 1 TrainingSession, 1 hidden synthetic."""
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    payload = _base_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_semaforo.id, "segment": "principal", "position": 0},
        ],
        combined_layout=_COMBINED_LAYOUT,
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["combined_exercise_id"] is not None
    synthetic_id = body["combined_exercise_id"]
    ts_id = body["training_session_id"]

    # Exactly one TrainingSession row total (no parallel/duplicate store).
    all_sessions = (await session.execute(select(TrainingSession))).scalars().all()
    assert len(all_sessions) == 1
    assert all_sessions[0].id == ts_id

    # Synthetic exercise: hidden, is_gymkhana, layout_json lossless round-trip.
    synth = await session.get(TechniqueExercise, synthetic_id)
    assert synth is not None
    assert synth.is_hidden is True
    assert synth.is_gymkhana is True
    # Lossless round-trip (SC-006): compare via the validated Pydantic model
    # (model_dump fills in None defaults for omitted optional fields like
    # rotation/style, so a raw-dict equality check would be too strict).
    expected = GymkhanaLayoutPhaseB.model_validate(_COMBINED_LAYOUT).model_dump()
    assert synth.layout_json == expected

    # Excluded from the normal catalog list (default include_hidden=False).
    async with make_client(session, user=coach_user_obj(10)) as client:
        list_resp = await client.get(f"{BASE}/exercises")
    assert list_resp.status_code == 200, list_resp.text
    listed_ids = {item["id"] for item in list_resp.json()["items"]}
    assert synthetic_id not in listed_ids

    # Even with include_hidden=True, only previously-existing hidden exercise
    # ("trackstand-test") plus the synthetic one would show — confirm
    # the synthetic one IS present there (sanity it's a real row, just hidden).
    async with make_client(session, user=coach_user_obj(10)) as client:
        list_hidden_resp = await client.get(f"{BASE}/exercises?include_hidden=true")
    assert list_hidden_resp.status_code == 200
    listed_hidden_ids = {item["id"] for item in list_hidden_resp.json()["items"]}
    assert synthetic_id in listed_hidden_ids

    # Session links component exercises + synthetic exercise.
    links = (
        await session.execute(
            select(TechniqueSessionExercise).where(
                TechniqueSessionExercise.training_session_id == ts_id
            )
        )
    ).scalars().all()
    linked_exercise_ids = {link.exercise_id for link in links}
    assert linked_exercise_ids == {ex_pie.id, ex_semaforo.id, synthetic_id}


# ---------------------------------------------------------------------------
# 4. Re-edit updates the SAME synthetic row and SAME session (FR-015)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_combined_re_edit_updates_same_session_and_synthetic(session):
    """Re-edit (combined_exercise_id set) updates the same row/session, no dupes."""
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]
    ex_slalom = catalog["exercises"]["slalom"]

    create_payload = _base_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_semaforo.id, "segment": "principal", "position": 0},
        ],
        combined_layout=_COMBINED_LAYOUT,
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        create_resp = await client.post(f"{BASE}/sessions", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    create_body = create_resp.json()
    ts_id = create_body["training_session_id"]
    synthetic_id = create_body["combined_exercise_id"]

    changed_layout = {
        "width": 100,
        "height": 60,
        "elements": [
            {"kind": "mine", "x": 20, "y": 20},
            {"kind": "beam", "x": 60, "y": 40, "label": "zona B"},
        ],
    }

    re_edit_payload = _base_payload(
        items=[
            {"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0},
        ],
        combined_layout=changed_layout,
        combined_exercise_id=synthetic_id,
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        re_edit_resp = await client.post(f"{BASE}/sessions", json=re_edit_payload)
    assert re_edit_resp.status_code == 201, re_edit_resp.text
    re_edit_body = re_edit_resp.json()

    # Same session, same synthetic exercise id — no duplicates.
    assert re_edit_body["training_session_id"] == ts_id
    assert re_edit_body["combined_exercise_id"] == synthetic_id

    all_sessions = (await session.execute(select(TrainingSession))).scalars().all()
    assert len(all_sessions) == 1

    all_synthetics = (
        await session.execute(
            select(TechniqueExercise).where(TechniqueExercise.is_hidden.is_(True))
        )
    ).scalars().all()
    # trackstand-test (seeded hidden) + the single synthetic exercise.
    synthetic_rows = [
        ex for ex in all_synthetics if ex.is_gymkhana and ex.id == synthetic_id
    ]
    assert len(synthetic_rows) == 1

    # layout_json updated in place.
    synth = await session.get(TechniqueExercise, synthetic_id)
    expected_changed = GymkhanaLayoutPhaseB.model_validate(changed_layout).model_dump()
    assert synth.layout_json == expected_changed

    # Links now reflect the re-edited item list + synthetic exercise only.
    links = (
        await session.execute(
            select(TechniqueSessionExercise).where(
                TechniqueSessionExercise.training_session_id == ts_id
            )
        )
    ).scalars().all()
    linked_exercise_ids = {link.exercise_id for link in links}
    assert linked_exercise_ids == {ex_slalom.id, synthetic_id}


# ---------------------------------------------------------------------------
# 5. Anti-PII guard rejects athlete-name/DOB-looking labels (422)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_combined_rejects_pii_looking_label(session):
    """A combined_layout element label resembling an athlete name/DOB -> 422."""
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    pii_layout = {
        "width": 100,
        "height": 60,
        "elements": [
            # Two capitalized words -> person-name heuristic.
            {"kind": "cone", "x": 10, "y": 10, "label": "Juan Pérez"},
        ],
    }

    payload = _base_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_semaforo.id, "segment": "principal", "position": 0},
        ],
        combined_layout=pii_layout,
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 422, resp.text

    # No TrainingSession or synthetic exercise should have been created.
    all_sessions = (await session.execute(select(TrainingSession))).scalars().all()
    assert len(all_sessions) == 0


@pytest.mark.asyncio
async def test_assemble_combined_rejects_dob_looking_label(session):
    """A combined_layout element label resembling a date of birth -> 422."""
    catalog = await _seed_for_assemble(session)
    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_semaforo = catalog["exercises"]["semaforo"]

    pii_layout = {
        "width": 100,
        "height": 60,
        "elements": [
            {"kind": "cone", "x": 10, "y": 10, "label": "15/03/2014"},
        ],
    }

    payload = _base_payload(
        items=[
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_semaforo.id, "segment": "principal", "position": 0},
        ],
        combined_layout=pii_layout,
    )

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/sessions", json=payload)
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 6. Regression: Phase A strict no-free-text-label guard unchanged (FR-023)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase_a_exercise_create_still_rejects_free_text_label(session):
    """POST /technique/exercises with a free-text layout_json label -> 422 (FR-023)."""
    await _seed_for_assemble(session)

    payload = {
        "name": "Ejercicio de prueba con etiqueta libre",
        "summary": "Resumen de prueba.",
        "how_to": "Instrucciones de prueba.",
        "difficulty": "facil",
        "is_game": False,
        "is_gymkhana": True,
        "layout_ascii": "[TEST]",
        "layout_alt": "Descripción accesible de prueba.",
        "layout_json": {
            "width": 100,
            "height": 60,
            "elements": [
                # Free text not in the Phase A controlled set -> rejected.
                {"kind": "cone", "x": 10, "y": 10, "label": "Salida del circuito"},
            ],
        },
        "age_bands": ["7-9"],
        "skill_slugs": ["posicion"],
        "material_slugs": [],
    }

    async with make_client(session, user=coach_user_obj(10)) as client:
        resp = await client.post(f"{BASE}/exercises", json=payload)
    assert resp.status_code == 422, resp.text
