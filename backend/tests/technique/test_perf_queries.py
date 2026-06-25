"""T050 — No N+1 performance test for the catalog list service.

Verifies that ``catalog_svc.list_exercises`` (and the GET /api/technique/exercises
endpoint) issues a bounded, constant number of SQL SELECT statements regardless of
how many exercises are in the catalog.

Strategy
--------
1.  Attach a SQLAlchemy ``before_cursor_execute`` event listener to the engine to
    count every SELECT statement that hits the DB.
2.  Seed 12 exercises (well above the minimal 5 from conftest) so that an N+1
    regression would emit 12+ extra queries and breach the assertion.
3.  Assert the query count is ≤ a small fixed ceiling (``MAX_SELECTS = 10``).

    The documented service contract (catalog.py §Side-effects) states:
      "one primary query + three selectinload IN-queries for the relationship
       collections"  → 4 SELECTs total.
    We add a small margin (10) to tolerate any framework-level bookkeeping
    queries issued by aiosqlite / FastAPI startup, while still being tight
    enough to catch true N+1 regressions (which would emit N×3 extra SELECTs
    for N exercises).

Both layers are tested:
  * ``test_list_exercises_service_no_n1``   — direct service call, cleaner count
  * ``test_list_exercises_endpoint_no_n1``  — HTTP round-trip via AsyncClient

All data is fictitious (non-negotiable CLAUDE.md §Privacy constraint).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.technique_exercise import (
    AgeBand,
    ExerciseDifficulty,
    TechniqueExercise,
    TechniqueExerciseAgeBand,
    technique_exercise_materials,
    technique_exercise_skills,
)
from app.models.technique_material import TechniqueMaterial
from app.models.technique_skill import TechniqueSkill
from app.services.technique import catalog as catalog_svc
from tests.technique.conftest import (
    make_client,
    seed_club,
    seed_coach,
    seed_technique_catalog,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Upper bound on the number of SELECT statements for a single catalog list call.
#:
#: The service is documented to issue exactly 4 (1 primary + 3 selectinload).
#: We allow up to 10 to absorb any aiosqlite/asyncio overhead without masking
#: a real N+1 regression, which would emit O(N) additional queries.
MAX_SELECTS = 10

#: Total exercises seeded in the expanded catalog.  Must be large enough that
#: an N+1 would clearly exceed MAX_SELECTS.
EXPECTED_EXERCISE_COUNT = 12  # 5 from seed_technique_catalog + 7 extras


# ---------------------------------------------------------------------------
# Query counter context-manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def count_selects(engine: AsyncEngine):
    """Context manager that counts SQL SELECT statements issued via *engine*.

    Uses the synchronous SQLAlchemy ``before_cursor_execute`` Core event, which
    fires for every statement sent to the DBAPI driver regardless of whether it
    originates from an ORM query or a raw ``text()`` call.

    Yields:
        A one-element list ``[count]``.  Read ``counter[0]`` after the ``async
        with`` block to get the total number of SELECT statements executed
        inside the block.

    Implementation note:
        ``AsyncEngine`` wraps a synchronous ``Engine``; the Core event must be
        registered on the *sync* engine (``engine.sync_engine``).  The event
        fires on the thread that executes the DBAPI call, which is the asyncio
        event loop's executor thread — the list append is safe because aiosqlite
        serialises all calls via a background thread per connection.
    """
    counter: list[int] = [0]

    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        if statement.strip().upper().startswith("SELECT"):
            counter[0] += 1

    sync_engine = engine.sync_engine
    sa_event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        sa_event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)


# ---------------------------------------------------------------------------
# Expanded catalog seed (12 exercises total)
# ---------------------------------------------------------------------------


async def _seed_extra_exercises(
    session: AsyncSession,
    *,
    skill_posicion_id: int,
    mat_conos_id: int,
) -> None:
    """Insert 7 additional exercises to reach EXPECTED_EXERCISE_COUNT.

    These are fictitious coaching drills that do not exist in the real catalog
    (names tagged "(perf-test)" to make origin clear).  Each gets one age band
    and one skill/material to keep INSERT volume minimal while still exercising
    the selectinload paths.
    """
    now = datetime.now(timezone.utc)
    slugs = [
        "perf-drill-alpha",
        "perf-drill-beta",
        "perf-drill-gamma",
        "perf-drill-delta",
        "perf-drill-epsilon",
        "perf-drill-zeta",
        "perf-drill-eta",
    ]
    exercises: list[TechniqueExercise] = []
    for i, slug in enumerate(slugs):
        ex = TechniqueExercise(
            slug=slug,
            name=f"Ejercicio ficticio de rendimiento {i + 1} (perf-test)",
            summary="Ejercicio ficticio usado exclusivamente en pruebas de rendimiento.",
            how_to=(
                "Dilo: solo para tests.\n"
                "Muéstralo: N/A.\n"
                "Háganlo: N/A.\n"
                "Revísenlo: N/A."
            ),
            difficulty=ExerciseDifficulty.FACIL,
            is_game=False,
            is_gymkhana=False,
            layout_ascii=None,
            layout_alt=None,
            confidence=None,
            is_seeded=False,
            is_hidden=False,
            created_at=now,
            updated_at=now,
        )
        session.add(ex)
        exercises.append(ex)

    await session.flush()  # assigns PKs

    for ex in exercises:
        session.add(
            TechniqueExerciseAgeBand(exercise_id=ex.id, age_band=AgeBand.BAND_10_12)
        )

    await session.flush()

    # Skills M2M
    await session.execute(
        technique_exercise_skills.insert(),
        [{"exercise_id": ex.id, "skill_id": skill_posicion_id} for ex in exercises],
    )
    # Materials M2M
    await session.execute(
        technique_exercise_materials.insert(),
        [{"exercise_id": ex.id, "material_id": mat_conos_id} for ex in exercises],
    )
    await session.flush()


async def _setup_expanded(session: AsyncSession) -> dict:
    """Seed club, coach, full catalog (5 base + 7 extra = 12 exercises)."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_technique_catalog(session)
    skill_posicion_id = catalog["skills"]["posicion"].id
    mat_conos_id = catalog["materials"]["conos"].id
    await _seed_extra_exercises(
        session,
        skill_posicion_id=skill_posicion_id,
        mat_conos_id=mat_conos_id,
    )
    await session.commit()
    return catalog


# ===========================================================================
# T050-A — Service layer: direct call to catalog_svc.list_exercises
# ===========================================================================


@pytest.mark.asyncio
async def test_list_exercises_service_no_n1(engine, session_factory):
    """Service list_exercises issues ≤ MAX_SELECTS SELECTs for 12 exercises.

    This verifies the selectinload strategy at the service layer in isolation,
    without HTTP overhead.  The session is opened fresh after the seed commit so
    the identity map is empty and no cached objects can mask missing queries.
    """
    # Seed using a dedicated session so we start the measurement with a clean slate.
    async with session_factory() as seed_session:
        await _setup_expanded(seed_session)

    # Measure: open a new session (cold identity map) and call the service.
    async with session_factory() as measure_session:
        async with count_selects(engine) as counter:
            exercises = await catalog_svc.list_exercises(
                measure_session, include_hidden=True
            )

    # Correctness: all 12 exercises returned.
    assert len(exercises) == EXPECTED_EXERCISE_COUNT, (
        f"Expected {EXPECTED_EXERCISE_COUNT} exercises but got {len(exercises)}. "
        "Check that the expanded seed inserted 7 extra exercises."
    )

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression detected: catalog list issued {observed} SELECT statements "
        f"for {EXPECTED_EXERCISE_COUNT} exercises (ceiling is {MAX_SELECTS}). "
        "An N+1 bug would emit O(N) queries; check that selectinload options are "
        "present in _exercise_select() in app/services/technique/catalog.py."
    )

    # Sanity-check: at least the 4 documented queries actually fired.
    assert observed >= 4, (
        f"Too few SELECTs ({observed}): the selectinload strategy requires at least "
        "4 statements (1 primary + 3 collection loads). "
        "The measurement harness may be broken."
    )


# ===========================================================================
# T050-B — Endpoint layer: HTTP round-trip via AsyncClient
# ===========================================================================


@pytest.mark.asyncio
async def test_list_exercises_endpoint_no_n1(engine, session_factory):
    """GET /api/technique/exercises issues ≤ MAX_SELECTS SELECTs for 12 exercises.

    Tests the full HTTP stack: router → service → DB.  Uses the same make_client
    pattern as other router tests; the session factory override ensures all DB
    traffic flows through our instrumented engine.
    """
    # Seed in an isolated session.
    async with session_factory() as seed_session:
        await _setup_expanded(seed_session)

    # The HTTP test needs a live session that is passed to make_client.
    # We open it manually so we can wrap the HTTP call in count_selects.
    async with session_factory() as http_session:
        async with count_selects(engine) as counter:
            async with make_client(http_session) as client:
                resp = await client.get(
                    "/api/technique/exercises",
                    params={"include_hidden": "true"},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == EXPECTED_EXERCISE_COUNT, (
        f"Expected {EXPECTED_EXERCISE_COUNT} items but endpoint returned "
        f"{body['total']}. Seed may not have committed before the HTTP call."
    )

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression detected via HTTP: endpoint issued {observed} SELECT "
        f"statements for {body['total']} exercises (ceiling is {MAX_SELECTS}). "
        "Check that the router passes the selectinload-equipped statement from "
        "_exercise_select() in catalog.py."
    )

    assert observed >= 4, (
        f"Too few SELECTs ({observed}) via HTTP path: expected ≥ 4 (1 primary + "
        "3 selectinload). The measurement harness or router may be skipping eager loads."
    )
