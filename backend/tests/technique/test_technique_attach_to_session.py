"""T005 — POST /api/technique/sessions/{training_session_id}/exercises (feature 032).

Covers contracts/attach-technique-to-session.md:
  1. Happy path — 2 new items on a session with no prior technique content
     → 201, response items length 2, mixes_age_bands computed correctly for a
     mixed-band pair.
  2. Append onto existing content — 1 more item on a session that already has
     technique items → 201, response includes old + new rows, old rows'
     position unchanged.
  3. RBAC-negative — parent role → 403.
  4. Not-found-negative — training_session_id belonging to another club → 404,
     never 403 (never leaks existence of a foreign-club session).
  5. Validation-negative — empty items → 422; unknown exercise_id → 422
     listing the id.
  6. Idempotency regression (FR-009) — submit the identical items payload
     twice, assert both calls 201 and the final DB row count equals the first
     call's count (no duplicate rows on retry).
  7. Query-count guard — 1 vs 5 items does not scale linearly (no N+1,
     Constitution IV).

Uses the technique integration harness (aiosqlite, ASGITransport) from
tests/technique/conftest.py. All data is fictitious (CLAUDE.md §Privacy).
"""
from __future__ import annotations

from datetime import date, time
from typing import Any

import pytest
from sqlalchemy import select

from app.models.technique_exercise import SessionSegment, TechniqueSessionExercise
from app.models.training_session import SessionKind, SessionStatus, TrainingSession
from tests.helpers.query_counting import count_selects
from tests.technique.conftest import (
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

BASE = "/api/technique"


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _seed_base(session, *, club_id: int = 1) -> dict:
    """Seed a club, its coach, and the shared technique catalog; commit."""
    await seed_club(session, club_id=club_id)
    await seed_coach(session, user_id=10, club_id=club_id)
    catalog = await seed_technique_catalog(session)
    await session.commit()
    return catalog


async def _seed_bare_session(
    session,
    *,
    session_id: int,
    club_id: int = 1,
    created_by_user_id: int = 10,
) -> TrainingSession:
    """Insert a bare TrainingSession (no technique content) directly, bypassing
    the assemble endpoint, so tests can target a session with no prior
    technique content.
    """
    ts = TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        status=SessionStatus.PLANNED,
        session_kind=SessionKind.ENTRENAMIENTO,
        scheduled_date=date(2026, 7, 20),
        scheduled_start_time=time(9, 0),
        duration_min=60,
        location="Cancha Ficticia",
        technical_focus="Técnica base (test attach)",
    )
    session.add(ts)
    await session.commit()
    await session.refresh(ts)
    return ts


def _attach_payload(items: list[dict]) -> dict:
    return {"items": items}


async def _count_technique_rows(session, training_session_id: int) -> int:
    result = await session.execute(
        select(TechniqueSessionExercise).where(
            TechniqueSessionExercise.training_session_id == training_session_id
        )
    )
    return len(result.scalars().all())


# ---------------------------------------------------------------------------
# 1. Happy path — 2 new items, no prior technique content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_happy_path_two_new_items(session):
    catalog = await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=100)

    ex_semaforo = catalog["exercises"]["semaforo"]  # age_bands 7-9, 10-12
    ex_trackstand = catalog["exercises"]["trackstand"]  # age_bands 13-15

    payload = _attach_payload(
        [
            {"exercise_id": ex_semaforo.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_trackstand.id, "segment": "principal", "position": 0},
        ]
    )

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions/{ts.id}/exercises", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    # semaforo (7-9,10-12) + trackstand (13-15) → union spans 3 bands → mixed.
    assert body["mixes_age_bands"] is True

    returned_ids = {item["exercise_id"] for item in body["items"]}
    assert returned_ids == {ex_semaforo.id, ex_trackstand.id}


# ---------------------------------------------------------------------------
# 2. Append onto existing content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_appends_onto_existing_content_without_disturbing_it(session):
    catalog = await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=101)

    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]

    # Pre-existing content: one item already attached.
    existing = TechniqueSessionExercise(
        training_session_id=ts.id,
        exercise_id=ex_pie.id,
        segment=SessionSegment.CALENTAMIENTO,
        position=0,
    )
    session.add(existing)
    await session.commit()

    payload = _attach_payload(
        [{"exercise_id": ex_slalom.id, "segment": "calentamiento", "position": 0}]
    )

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions/{ts.id}/exercises", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["items"]) == 2

    by_exercise = {item["exercise_id"]: item for item in body["items"]}
    assert ex_pie.id in by_exercise
    assert ex_slalom.id in by_exercise
    # The old row's position must be unchanged.
    assert by_exercise[ex_pie.id]["position"] == 0
    # The new row must append after the existing max position in that segment.
    assert by_exercise[ex_slalom.id]["position"] == 1


# ---------------------------------------------------------------------------
# 3. RBAC-negative — parent role → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_rbac_forbidden_for_parent(session):
    catalog = await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=102)
    ex_pie = catalog["exercises"]["pie_abajo"]

    payload = _attach_payload(
        [{"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0}]
    )

    async with make_client(session, user=parent_user_obj()) as client:
        resp = await client.post(f"{BASE}/sessions/{ts.id}/exercises", json=payload)
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 4. Not-found-negative — foreign-club session → 404, never 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_foreign_club_session_returns_404_not_403(session):
    catalog = await _seed_base(session, club_id=1)
    # A second club with its own session — the coach (club 1) has no access.
    await seed_club(session, club_id=2)
    await session.commit()
    foreign_ts = await _seed_bare_session(
        session, session_id=200, club_id=2, created_by_user_id=10
    )

    ex_pie = catalog["exercises"]["pie_abajo"]
    payload = _attach_payload(
        [{"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0}]
    )

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/sessions/{foreign_ts.id}/exercises", json=payload
        )
    assert resp.status_code == 404, resp.text
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_attach_unknown_session_id_returns_404(session):
    await _seed_base(session)
    payload = _attach_payload(
        [{"exercise_id": 1, "segment": "calentamiento", "position": 0}]
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions/99999/exercises", json=payload)
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# 5. Validation-negative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_empty_items_returns_422(session):
    await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=103)

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/sessions/{ts.id}/exercises", json={"items": []}
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_attach_unknown_exercise_id_returns_422_listing_id(session):
    await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=104)

    unknown_id = 987654
    payload = _attach_payload(
        [{"exercise_id": unknown_id, "segment": "calentamiento", "position": 0}]
    )

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/sessions/{ts.id}/exercises", json=payload)
    assert resp.status_code == 422, resp.text
    assert str(unknown_id) in resp.text


# ---------------------------------------------------------------------------
# 6. Idempotency regression (FR-009)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_retry_with_identical_payload_does_not_duplicate_rows(session):
    catalog = await _seed_base(session)
    ts = await _seed_bare_session(session, session_id=105)

    ex_pie = catalog["exercises"]["pie_abajo"]
    ex_slalom = catalog["exercises"]["slalom"]
    payload = _attach_payload(
        [
            {"exercise_id": ex_pie.id, "segment": "calentamiento", "position": 0},
            {"exercise_id": ex_slalom.id, "segment": "principal", "position": 0},
        ]
    )

    async with make_client(session) as client:
        first_resp = await client.post(
            f"{BASE}/sessions/{ts.id}/exercises", json=payload
        )
    assert first_resp.status_code == 201, first_resp.text
    first_count = await _count_technique_rows(session, ts.id)
    assert first_count == 2

    # Retry the identical payload — simulates a client retry after a
    # connection loss where the server had already committed.
    async with make_client(session) as client:
        second_resp = await client.post(
            f"{BASE}/sessions/{ts.id}/exercises", json=payload
        )
    assert second_resp.status_code == 201, second_resp.text
    second_count = await _count_technique_rows(session, ts.id)
    assert second_count == first_count, (
        f"Retry duplicated rows: {first_count} → {second_count}"
    )


# ---------------------------------------------------------------------------
# 7. Query-count guard — 1 vs 5 items must not scale linearly (no N+1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_query_count_does_not_scale_linearly_with_item_count(
    session, engine
):
    catalog = await _seed_base(session)
    exercises = list(catalog["exercises"].values())
    assert len(exercises) >= 5

    ts_one = await _seed_bare_session(session, session_id=300)
    ts_five = await _seed_bare_session(session, session_id=301)

    one_item_payload = _attach_payload(
        [{"exercise_id": exercises[0].id, "segment": "calentamiento", "position": 0}]
    )
    five_item_payload = _attach_payload(
        [
            {
                "exercise_id": ex.id,
                "segment": "calentamiento",
                "position": i,
            }
            for i, ex in enumerate(exercises[:5])
        ]
    )

    async with count_selects(engine) as counter_one:
        async with make_client(session) as client:
            resp_one = await client.post(
                f"{BASE}/sessions/{ts_one.id}/exercises", json=one_item_payload
            )
    assert resp_one.status_code == 201, resp_one.text
    observed_one = counter_one[0]

    async with count_selects(engine) as counter_five:
        async with make_client(session) as client:
            resp_five = await client.post(
                f"{BASE}/sessions/{ts_five.id}/exercises", json=five_item_payload
            )
    assert resp_five.status_code == 201, resp_five.text
    observed_five = counter_five[0]

    # A naive N+1 implementation would issue at least one extra SELECT per
    # item (5 vs 1 → +4 or more). The real implementation resolves exercises
    # and existing rows via bulk IN-queries, so the delta should be small and
    # independent of item count.
    assert observed_five - observed_one <= 2, (
        f"Query count scales with item count: 1 item={observed_one} SELECTs, "
        f"5 items={observed_five} SELECTs (delta={observed_five - observed_one}). "
        "Check for a per-item query (N+1) in attach_exercises_to_session."
    )
