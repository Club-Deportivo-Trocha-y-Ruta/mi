"""T036 — No N+1 performance test for the interval structure + template reads.

Verifies that the two eager-loaded read views of feature 026 issue a bounded,
constant number of SQL SELECT statements regardless of how many rows / child
blocks are involved:

  * ``structures.get_structure_by_session`` (GET /api/intervals/sessions/{id}/
    structure) — one structure with an eager ``blocks`` collection **and** an
    eager ``age_gate_confirmed_by`` relationship. An N+1 regression would emit
    O(N_blocks) extra queries.
  * ``templates.list_templates`` (GET /api/intervals/templates) — a club-scoped
    list, each row eager-loading its ``blocks`` collection. An N+1 regression
    would emit O(N_templates) extra queries.

Mirrors ``backend/tests/strength/test_perf_queries.py`` (feature 021) and
``backend/tests/technique/test_perf_queries.py`` (feature 018) in strategy:

1.  Attach a SQLAlchemy ``before_cursor_execute`` Core event listener to the
    engine to count every SELECT statement that hits the DB.
2.  Seed enough rows/blocks that an N+1 regression would clearly breach the
    ceiling (a 20-block structure / 12-template list each add O(N) selects
    under a lazy-load bug).
3.  Assert the query count is ≤ a small fixed ceiling (``MAX_SELECTS``).

The documented service contracts are:
  * ``_structure_select()`` → 1 primary + 2 selectinload IN-queries
    (``blocks`` + ``age_gate_confirmed_by``) = 3 SELECTs.
  * ``_template_select()`` → 1 primary + 1 selectinload IN-query (``blocks``)
    = 2 SELECTs.
The endpoint layer adds ``_coach_club_id`` (club-membership lookup) on top.
We allow a small margin (``MAX_SELECTS``) to absorb that bookkeeping while
still catching a true N+1 (which would emit O(N) additional queries).

Both layers are tested for each read: direct service call (cleaner count) and
the HTTP round-trip via ``make_client``.

All data is fictitious (non-negotiable CLAUDE.md §Privacy constraint).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.technique_exercise import AgeBand
from app.schemas.intervals import BlockIn
from app.services.intervals import structures as structures_svc
from app.services.intervals import templates as templates_svc
from tests.intervals.conftest import (
    make_client,
    seed_club,
    seed_coach,
    seed_training_session,
)

BASE = "/api/intervals"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Upper bound on the number of SELECT statements for a single read call.
#:
#: Structure read is documented at 3 (1 primary + 2 selectinload); template
#: list at 2 (1 primary + 1 selectinload). The endpoint path adds the
#: ``_coach_club_id`` membership lookup. We allow up to 8 to absorb that plus
#: any aiosqlite/asyncio overhead without masking a real N+1 regression, which
#: would emit O(N) additional queries for N blocks / N templates.
MAX_SELECTS = 8

#: Number of blocks packed into the single structure under test. Large enough
#: that a lazy-loaded ``blocks`` collection would blow past MAX_SELECTS.
STRUCTURE_BLOCK_COUNT = 20

#: Number of templates seeded for the list test. Large enough that a per-row
#: lazy ``blocks`` load would blow past MAX_SELECTS.
TEMPLATE_COUNT = 12


# ---------------------------------------------------------------------------
# Query counter context-manager (identical strategy to strength/technique)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def count_selects(engine: AsyncEngine):
    """Context manager that counts SQL SELECT statements issued via *engine*.

    Uses the synchronous ``before_cursor_execute`` Core event, which fires for
    every statement sent to the DBAPI driver. Registered on the *sync* engine
    (``engine.sync_engine``) since ``AsyncEngine`` wraps a synchronous ``Engine``.

    Yields:
        A one-element list ``[count]``; read ``counter[0]`` after the block.
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
# Seed helpers
# ---------------------------------------------------------------------------


def _many_blocks(count: int) -> list[BlockIn]:
    """Build ``count`` valid Z1/Z2 blocks (cadence ≥ 60, no repeat groups).

    Fictitious coaching content used only in this perf test. Kept guardrail-safe
    (Z1/Z2, cadence 70) so it passes ``validate_structure_blocks`` on any band.
    """
    blocks: list[BlockIn] = [
        BlockIn(
            position=1,
            block_type="warmup",
            duration_s=300,
            target_zone="Z1",
            target_cadence_rpm=70,
            repeat_group=None,
            repeat_count=None,
        )
    ]
    for i in range(2, count):
        blocks.append(
            BlockIn(
                position=i,
                block_type="work",
                duration_s=120,
                target_zone="Z2",
                target_cadence_rpm=80,
                repeat_group=None,
                repeat_count=None,
            )
        )
    blocks.append(
        BlockIn(
            position=count,
            block_type="cooldown",
            duration_s=300,
            target_zone="Z1",
            target_cadence_rpm=65,
            repeat_group=None,
            repeat_count=None,
        )
    )
    return blocks


def _template_blocks() -> list[BlockIn]:
    """A benign warmup/work/cooldown triple for a seeded template."""
    return [
        BlockIn(position=1, block_type="warmup", duration_s=300, target_zone="Z1",
                target_cadence_rpm=70, repeat_group=None, repeat_count=None),
        BlockIn(position=2, block_type="work", duration_s=120, target_zone="Z2",
                target_cadence_rpm=80, repeat_group=None, repeat_count=None),
        BlockIn(position=3, block_type="cooldown", duration_s=300, target_zone="Z1",
                target_cadence_rpm=65, repeat_group=None, repeat_count=None),
    ]


async def _seed_structure(session: AsyncSession) -> int:
    """Seed club + coach + one session + one 20-block structure. Returns session id."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    ts = await seed_training_session(session, club_id=1, created_by_user_id=10)
    await session.commit()
    await structures_svc.create_structure(
        session,
        training_session_id=ts.id,
        target_age_band=AgeBand.BAND_13_15,
        age_gate_confirmed=True,
        blocks=_many_blocks(STRUCTURE_BLOCK_COUNT),
        club_id=1,
        created_by_user_id=10,
    )
    return ts.id


async def _seed_templates(session: AsyncSession) -> None:
    """Seed club + coach + TEMPLATE_COUNT templates (3 blocks each)."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await session.commit()
    for i in range(TEMPLATE_COUNT):
        await templates_svc.create_template(
            session,
            name=f"Plantilla ficticia de rendimiento {i + 1} (perf-test)",
            target_age_band=AgeBand.BAND_13_15,
            mesocycle_phase="base",
            competition_proximity="general",
            blocks=_template_blocks(),
            club_id=1,
            created_by_user_id=10,
        )


# ===========================================================================
# Structure read — service layer
# ===========================================================================


@pytest.mark.asyncio
async def test_get_structure_service_no_n1(engine, session_factory):
    """get_structure_by_session issues ≤ MAX_SELECTS for a 20-block structure."""
    async with session_factory() as seed_session:
        session_id = await _seed_structure(seed_session)

    async with session_factory() as measure_session:
        async with count_selects(engine) as counter:
            structure = await structures_svc.get_structure_by_session(
                measure_session, training_session_id=session_id, club_id=1
            )

    assert structure is not None
    assert len(structure.blocks) == STRUCTURE_BLOCK_COUNT

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression: structure read issued {observed} SELECTs for "
        f"{STRUCTURE_BLOCK_COUNT} blocks (ceiling {MAX_SELECTS}). Check the "
        "selectinload options in _structure_select() in "
        "app/services/intervals/structures.py."
    )
    assert observed >= 3, (
        f"Too few SELECTs ({observed}): the read requires ≥ 3 (1 primary + 2 "
        "selectinload for blocks + age_gate_confirmed_by). Harness may be broken."
    )


# ===========================================================================
# Structure read — endpoint layer
# ===========================================================================


@pytest.mark.asyncio
async def test_get_structure_endpoint_no_n1(engine, session_factory):
    """GET /sessions/{id}/structure issues ≤ MAX_SELECTS for a 20-block structure."""
    async with session_factory() as seed_session:
        session_id = await _seed_structure(seed_session)

    async with session_factory() as http_session:
        async with count_selects(engine) as counter:
            async with make_client(http_session) as client:
                resp = await client.get(f"{BASE}/sessions/{session_id}/structure")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["blocks"]) == STRUCTURE_BLOCK_COUNT

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression via HTTP: structure endpoint issued {observed} SELECTs "
        f"for {STRUCTURE_BLOCK_COUNT} blocks (ceiling {MAX_SELECTS})."
    )


# ===========================================================================
# Template list — service layer
# ===========================================================================


@pytest.mark.asyncio
async def test_list_templates_service_no_n1(engine, session_factory):
    """list_templates issues ≤ MAX_SELECTS for TEMPLATE_COUNT templates."""
    async with session_factory() as seed_session:
        await _seed_templates(seed_session)

    async with session_factory() as measure_session:
        async with count_selects(engine) as counter:
            items, total = await templates_svc.list_templates(
                measure_session, club_id=1
            )

    assert total == TEMPLATE_COUNT, (
        f"Expected {TEMPLATE_COUNT} templates but got {total}. Seed may not "
        "have committed."
    )

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression: template list issued {observed} SELECTs for "
        f"{TEMPLATE_COUNT} templates (ceiling {MAX_SELECTS}). Check the "
        "selectinload option in _template_select() in "
        "app/services/intervals/templates.py."
    )
    assert observed >= 2, (
        f"Too few SELECTs ({observed}): the list requires ≥ 2 (1 primary + 1 "
        "selectinload for blocks). Harness may be broken."
    )


# ===========================================================================
# Template list — endpoint layer
# ===========================================================================


@pytest.mark.asyncio
async def test_list_templates_endpoint_no_n1(engine, session_factory):
    """GET /templates issues ≤ MAX_SELECTS for TEMPLATE_COUNT templates."""
    async with session_factory() as seed_session:
        await _seed_templates(seed_session)

    async with session_factory() as http_session:
        async with count_selects(engine) as counter:
            async with make_client(http_session) as client:
                resp = await client.get(f"{BASE}/templates")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == TEMPLATE_COUNT

    observed = counter[0]
    assert observed <= MAX_SELECTS, (
        f"N+1 regression via HTTP: template list endpoint issued {observed} "
        f"SELECTs for {TEMPLATE_COUNT} templates (ceiling {MAX_SELECTS})."
    )
