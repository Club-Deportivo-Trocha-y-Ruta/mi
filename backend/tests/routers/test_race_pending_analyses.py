"""Feature 045 (US5, T028/T029): pending analyses list + dismiss-stale.

Covers:
- ``GET /api/race-analysis/pending-analyses?state=awaiting_approval|stale``:
  coach/admin 200 (club-scoped), parent 403, unknown/missing ``state`` 422,
  optional ``season`` filter, privacy (``athlete_ref`` never logged).
- SC-005: for each state the list is exactly what
  ``GET /api/dashboard/coach-summary`` counts (``analyses_awaiting_approval``
  and ``insights_stale``) — asserted with equality, including the case of one
  athlete with two stale analyses.
- ``POST /api/race-analysis/runs/{run_id}/dismiss-stale``: 200 (the run leaves
  the stale list and one audit row is written), 409 when not stale (and no
  audit row), 404 unknown run, parent 403, coach of another club 403.

Strategy: SQLite async in-memory, real ``app.main.app`` with ``get_db`` /
``get_current_user`` overrides. ``agent_runs`` is created from hand-written DDL
(the ORM model maps only a subset of the physical columns, and this suite needs
``input_json``/``explain_mode`` for ``_load_run``) — same approach as
``tests/routers/test_race_event_runs.py``.

All names are fictitious (CLAUDE.md §Privacy).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete import Sex
from app.models.audit_log import AuditLog
from app.models.club import ClubRole
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES


# ``privacy_policies.content_html`` is MySQL LONGTEXT; SQLite has no compiler
# for it (same escape hatch as tests/routers/test_dashboard_summary.py).
@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "TEXT"


pytestmark = pytest.mark.asyncio

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "race_events",
    "athlete_ai_insights",
    "parental_consents",
    "training_sessions",
    "session_attendance",
    "race_identity_candidates",
    "race_imports",
    *AUDIT_TABLES,
)

_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    input_json TEXT,
    final_output_json TEXT,
    error_message TEXT,
    requested_by_user_id INTEGER,
    athlete_id INTEGER,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode INTEGER NOT NULL DEFAULT 0,
    stale_since TEXT,
    decided_by_user_id INTEGER,
    decided_at TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

# Distinctive fictitious names so a leak into logs/other payloads is greppable.
_NAME_101 = ("Zzyxaria", "Pruebalonga")
_NAME_102 = ("Qwortan", "Simulacro")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.execute(text(_AGENT_RUNS_DDL))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Fake users / client
# ---------------------------------------------------------------------------


def coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        email=f"coach{user_id}@test.com",
        is_active=True,
        can_login=True,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


def admin_user(user_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id, role=UserRole.admin, email="admin@test.com",
        is_active=True, can_login=True, club_memberships=[],
    )


def parent_user(user_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id, role=UserRole.parent, email="parent@test.com",
        is_active=True, can_login=True, club_memberships=[],
    )


def make_client(session: AsyncSession, *, user) -> AsyncClient:
    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


async def _seed_run(
    session: AsyncSession,
    run_id: int,
    *,
    athlete_id: int | None,
    status: AgentRunStatus,
    stale: bool = False,
    input_json: dict[str, Any] | None = None,
    updated_at: datetime | None = None,
) -> AgentRun:
    now = updated_at or _utc()
    run = AgentRun(
        id=run_id,
        external_run_id=f"run-{run_id}",
        graph_name="race-analyst",
        prompt_version="race_analyst_v3",
        started_at=now,
        status=status,
        requested_by_user_id=10,
        athlete_id=athlete_id,
        checkpoint_thread_id=f"run-{run_id}",
        stale_since=now if stale else None,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.flush()
    if input_json is not None:
        await session.execute(
            text("UPDATE agent_runs SET input_json = :j WHERE id = :i"),
            {"j": json.dumps(input_json), "i": run_id},
        )
    return run


async def _seed_world(session: AsyncSession) -> None:
    """Two clubs; awaiting + stale analyses for club 1 and club 2.

    Club 1 (coach 10): athletes 101, 102 (+104 soft-deleted).
    Club 2 (coach 11): athlete 103.
    """
    await create_club(session, club_id=1, name="Club Uno", code="uno")
    await create_club(session, club_id=2, name="Club Dos", code="dos")
    await create_user(session, user_id=10, role=UserRole.coach)
    await create_user(session, user_id=11, role=UserRole.coach)
    await create_user(session, user_id=20, role=UserRole.parent)
    await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
    await link_user_to_club(session, user_id=11, club_id=2, role_in_club=ClubRole.coach)

    for athlete_id, club_id, names in (
        (101, 1, _NAME_101),
        (102, 1, _NAME_102),
        (103, 2, ("Otrocl", "Ubdos")),
        (104, 1, ("Borrada", "Deportista")),
    ):
        await create_user(session, user_id=900 + athlete_id, role=UserRole.athlete, can_login=False)
        athlete = await create_athlete(
            session, athlete_id=athlete_id, first_name=names[0], last_name=names[1],
            birth_date=date(2014, 5, 5), sex=Sex.F, club_id=club_id,
            user_id=900 + athlete_id, created_by=10,
        )
        if athlete_id == 104:
            athlete.deleted_at = _utc()

    await create_race_event(
        session, event_id=42, sequence_number=4, name="Copa Simulada - Válida 4"
    )

    base = _utc()

    # --- awaiting approval -------------------------------------------------
    # 1: club 1, anchored to event 42.  2: club 1, season-level (no event).
    # 3: club 2.  4: completed (not awaiting).  5: soft-deleted athlete.
    await _seed_run(
        session, 1, athlete_id=101, status=AgentRunStatus.awaiting_hitl,
        input_json={"athlete_id": 101, "season": 2026, "valida_nums": [4], "event_id": 42},
        updated_at=base - timedelta(minutes=5),
    )
    await _seed_run(
        session, 2, athlete_id=102, status=AgentRunStatus.awaiting_hitl,
        input_json={"athlete_id": 102, "season": 2026, "valida_nums": [0]},
        updated_at=base - timedelta(minutes=1),
    )
    await _seed_run(
        session, 3, athlete_id=103, status=AgentRunStatus.awaiting_hitl,
        input_json={"athlete_id": 103, "season": 2026, "valida_nums": [4]},
    )
    await _seed_run(session, 4, athlete_id=101, status=AgentRunStatus.completed)
    await _seed_run(session, 5, athlete_id=104, status=AgentRunStatus.awaiting_hitl)

    # --- stale (completed runs with an active insight) ---------------------
    # 11: athlete 101, event 42.   12: athlete 102, season summary (no event).
    # 13: athlete 101 AGAIN (another válida, season 2025) — second stale item.
    # 14: stale run whose insight is NOT active — excluded.
    # 15: club 2 — excluded for coach 10.   16: fresh run — excluded.
    await _seed_run(session, 11, athlete_id=101, status=AgentRunStatus.completed, stale=True,
                    updated_at=base - timedelta(hours=3))
    await create_insight(session, athlete_id=101, agent_run_id=11, is_active=1,
                         valida_num=4, season=2026, event_id=42, generated_by_user_id=10)
    await _seed_run(session, 12, athlete_id=102, status=AgentRunStatus.completed, stale=True,
                    updated_at=base - timedelta(hours=1))
    await create_insight(session, athlete_id=102, agent_run_id=12, is_active=1,
                         valida_num=0, season=2026, use_case="season_summary",
                         generated_by_user_id=10)
    await _seed_run(session, 13, athlete_id=101, status=AgentRunStatus.completed, stale=True,
                    updated_at=base - timedelta(hours=2))
    await create_insight(session, athlete_id=101, agent_run_id=13, is_active=1,
                         valida_num=1, season=2025, generated_by_user_id=10)
    await _seed_run(session, 14, athlete_id=101, status=AgentRunStatus.completed, stale=True)
    await create_insight(session, athlete_id=101, agent_run_id=14, is_active=None,
                         valida_num=2, season=2026, generated_by_user_id=10)
    await _seed_run(session, 15, athlete_id=103, status=AgentRunStatus.completed, stale=True)
    await create_insight(session, athlete_id=103, agent_run_id=15, is_active=1,
                         valida_num=4, season=2026, generated_by_user_id=10)
    await _seed_run(session, 16, athlete_id=102, status=AgentRunStatus.completed, stale=False)
    await create_insight(session, athlete_id=102, agent_run_id=16, is_active=1,
                         valida_num=3, season=2026, generated_by_user_id=10)

    await session.commit()


async def _summary(client: AsyncClient) -> dict[str, Any]:
    resp = await client.get("/api/dashboard/coach-summary")
    assert resp.status_code == 200, resp.text
    return resp.json()


_ITEM_KEYS = {
    "run_id", "insight_id", "athlete_id", "athlete_ref",
    "event_id", "event_label", "season", "kind", "state", "updated_at",
}


# ===========================================================================
# GET /api/race-analysis/pending-analyses
# ===========================================================================


class TestListPendingAnalyses:
    async def test_awaiting_approval_lists_club_runs_newest_first(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "awaiting_approval"}
            )

        assert resp.status_code == 200, resp.text
        items = resp.json()
        # Newest ``updated_at`` first: run-2 (1 min ago) before run-1 (5 min ago).
        assert [i["run_id"] for i in items] == ["run-2", "run-1"]
        assert all(set(i) == _ITEM_KEYS for i in items)
        assert all(i["state"] == "awaiting_approval" for i in items)
        by_run = {i["run_id"]: i for i in items}
        assert by_run["run-1"]["insight_id"] is None  # nothing persisted yet
        assert by_run["run-1"]["athlete_id"] == 101
        assert by_run["run-1"]["athlete_ref"] == f"{_NAME_101[0]} {_NAME_101[1]}"
        assert by_run["run-1"]["event_id"] == 42
        assert by_run["run-1"]["event_label"] == "Copa Simulada - Válida 4"
        assert by_run["run-1"]["season"] == 2026
        # Season-level run: no event, label falls back to the season.
        assert by_run["run-2"]["event_id"] is None
        assert by_run["run-2"]["event_label"] == "Temporada 2026"
        # ``kind`` comes from the run input: event-anchored → valida, [0] → season.
        assert by_run["run-1"]["kind"] == "valida"
        assert by_run["run-2"]["kind"] == "season_summary"

    async def test_stale_lists_one_item_per_stale_analysis(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "stale"}
            )

        assert resp.status_code == 200, resp.text
        items = resp.json()
        # run-14 (inactive insight), run-15 (other club) and run-16 (fresh) are out;
        # athlete 101 appears twice (runs 11 and 13) — one item per analysis.
        assert [i["run_id"] for i in items] == ["run-12", "run-13", "run-11"]
        assert all(set(i) == _ITEM_KEYS for i in items)
        assert all(i["state"] == "stale" for i in items)
        assert all(isinstance(i["insight_id"], int) for i in items)
        by_run = {i["run_id"]: i for i in items}
        assert by_run["run-11"]["event_id"] == 42
        assert by_run["run-11"]["event_label"] == "Copa Simulada - Válida 4"
        assert by_run["run-12"]["event_id"] is None
        assert by_run["run-12"]["event_label"] == "Temporada 2026"
        assert by_run["run-13"]["event_label"] == "Temporada 2025"
        assert by_run["run-13"]["season"] == 2025
        # ``kind`` comes from the active insight (valida_num / use_case).
        assert by_run["run-11"]["kind"] == "valida"
        assert by_run["run-12"]["kind"] == "season_summary"
        assert by_run["run-13"]["kind"] == "valida"

    async def test_kind_covers_real_launcher_shapes_and_unknowns(self, session):
        """``kind`` for the real season-summary input, unknown inputs and event-less insights."""
        await _seed_world(session)
        base = _utc()
        # Real ``create_season_summary`` input: analysis_kind=season, valida_nums=None.
        await _seed_run(
            session, 21, athlete_id=101, status=AgentRunStatus.awaiting_hitl,
            input_json={"athlete_id": 101, "season": 2026, "valida_nums": None,
                        "analysis_kind": "season"},
            updated_at=base,
        )
        # No usable signal at all → unknown, never guessed.
        await _seed_run(
            session, 22, athlete_id=102, status=AgentRunStatus.awaiting_hitl,
            input_json={"athlete_id": 102, "season": 2026, "valida_nums": None},
            updated_at=base,
        )
        # Positive valida_nums without event anchor → valida.
        await _seed_run(
            session, 23, athlete_id=102, status=AgentRunStatus.awaiting_hitl,
            input_json={"athlete_id": 102, "season": 2026, "valida_nums": [2, 3]},
            updated_at=base,
        )
        # Stale insight without valida/event (analytics) → unknown.
        await _seed_run(session, 24, athlete_id=102, status=AgentRunStatus.completed,
                        stale=True, updated_at=base)
        await create_insight(session, athlete_id=102, agent_run_id=24, is_active=1,
                             valida_num=None, season=2026, generated_by_user_id=10)
        # Stale season-summary v3 insight identified by use_case alone.
        await _seed_run(session, 25, athlete_id=101, status=AgentRunStatus.completed,
                        stale=True, updated_at=base)
        await create_insight(session, athlete_id=101, agent_run_id=25, is_active=1,
                             valida_num=None, season=2026, use_case="season_summary_v3",
                             generated_by_user_id=10)
        await session.commit()

        async with make_client(session, user=coach_user()) as client:
            awaiting = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "awaiting_approval"}
            )
            stale = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "stale"}
            )
            summary = await _summary(client)

        kinds_awaiting = {i["run_id"]: i["kind"] for i in awaiting.json()}
        assert kinds_awaiting["run-21"] == "season_summary"
        assert kinds_awaiting["run-22"] is None
        assert kinds_awaiting["run-23"] == "valida"
        kinds_stale = {i["run_id"]: i["kind"] for i in stale.json()}
        assert kinds_stale["run-24"] is None
        assert kinds_stale["run-25"] == "season_summary"
        # SC-005 still holds: ``kind`` is presentation, not membership.
        assert summary["analyses_awaiting_approval"] == len(awaiting.json())
        assert summary["insights_stale"] == len(stale.json())

    @pytest.mark.parametrize(
        "state, count_field",
        [("awaiting_approval", "analyses_awaiting_approval"), ("stale", "insights_stale")],
    )
    @pytest.mark.parametrize("who", ["coach", "coach_other_club", "admin"])
    async def test_items_equal_dashboard_counts(self, session, state, count_field, who):
        """SC-005: every «Pendientes» count equals the items its list returns."""
        await _seed_world(session)
        user = {
            "coach": coach_user(),
            "coach_other_club": coach_user(user_id=11, club_id=2),
            "admin": admin_user(),
        }[who]

        async with make_client(session, user=user) as client:
            summary = await _summary(client)
            resp = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": state}
            )

        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert summary[count_field] == len(items)
        assert len(items) > 0  # guards against a vacuous 0 == 0

    async def test_coach_of_other_club_only_sees_own_club(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user(user_id=11, club_id=2)) as client:
            awaiting = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "awaiting_approval"}
            )
            stale = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "stale"}
            )

        assert [i["run_id"] for i in awaiting.json()] == ["run-3"]
        assert [i["run_id"] for i in stale.json()] == ["run-15"]

    async def test_admin_sees_every_club(self, session):
        await _seed_world(session)

        async with make_client(session, user=admin_user()) as client:
            awaiting = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "awaiting_approval"}
            )

        assert {i["run_id"] for i in awaiting.json()} == {"run-1", "run-2", "run-3"}

    async def test_coach_without_clubs_gets_an_empty_list(self, session):
        await _seed_world(session)
        homeless = SimpleNamespace(
            id=12, role=UserRole.coach, email="c12@test.com",
            is_active=True, can_login=True, club_memberships=[],
        )

        async with make_client(session, user=homeless) as client:
            for state in ("awaiting_approval", "stale"):
                resp = await client.get(
                    "/api/race-analysis/pending-analyses", params={"state": state}
                )
                assert resp.status_code == 200, resp.text
                assert resp.json() == []

    async def test_season_filter(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            stale_2025 = await client.get(
                "/api/race-analysis/pending-analyses",
                params={"state": "stale", "season": 2025},
            )
            awaiting_2026 = await client.get(
                "/api/race-analysis/pending-analyses",
                params={"state": "awaiting_approval", "season": 2026},
            )
            awaiting_2025 = await client.get(
                "/api/race-analysis/pending-analyses",
                params={"state": "awaiting_approval", "season": 2025},
            )

        assert [i["run_id"] for i in stale_2025.json()] == ["run-13"]
        assert {i["run_id"] for i in awaiting_2026.json()} == {"run-1", "run-2"}
        assert awaiting_2025.json() == []

    async def test_parent_forbidden(self, session):
        await _seed_world(session)

        async with make_client(session, user=parent_user()) as client:
            resp = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "stale"}
            )

        assert resp.status_code == 403
        assert _NAME_101[0] not in resp.text

    async def test_unknown_state_unprocessable(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "archived"}
            )

        assert resp.status_code == 422

    async def test_missing_state_unprocessable(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.get("/api/race-analysis/pending-analyses")

        assert resp.status_code == 422

    async def test_athlete_ref_never_logged(self, session, caplog):
        await _seed_world(session)
        caplog.set_level(logging.DEBUG)

        async with make_client(session, user=coach_user()) as client:
            for state in ("awaiting_approval", "stale"):
                resp = await client.get(
                    "/api/race-analysis/pending-analyses", params={"state": state}
                )
                assert resp.status_code == 200, resp.text

        for token in (*_NAME_101, *_NAME_102):
            assert token not in caplog.text


# ===========================================================================
# POST /api/race-analysis/runs/{run_id}/dismiss-stale
# ===========================================================================


async def _audit_rows(session: AsyncSession, run_pk: int) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "agent_run", AuditLog.entity_id == run_pk
        )
    )
    return list(result.scalars().all())


class TestDismissStale:
    async def test_dismiss_stale_marks_fresh_and_leaves_the_stale_list(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")
            assert resp.status_code == 200, resp.text
            assert resp.json() == {"run_id": "run-11", "stale": False}

            stale = await client.get(
                "/api/race-analysis/pending-analyses", params={"state": "stale"}
            )
            summary = await _summary(client)

        run_ids = [i["run_id"] for i in stale.json()]
        assert "run-11" not in run_ids
        assert run_ids == ["run-12", "run-13"]
        assert summary["insights_stale"] == 2  # count and list stay in lockstep

        refreshed = await session.get(AgentRun, 11)
        assert refreshed is not None and refreshed.stale_since is None

    async def test_dismiss_stale_writes_an_audit_row(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")
        assert resp.status_code == 200, resp.text

        rows = await _audit_rows(session, 11)
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_user_id == 10
        assert row.club_id == 1
        assert row.athlete_id == 101
        assert "stale_since" in row.changed_fields
        assert row.meta_json == {"stale": False}

    async def test_dismiss_when_not_stale_conflicts_and_writes_no_audit(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.post("/api/race-analysis/runs/run-16/dismiss-stale")

        assert resp.status_code == 409, resp.text
        assert await _audit_rows(session, 16) == []

    async def test_dismiss_twice_second_call_conflicts(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            first = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")
            second = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")

        assert first.status_code == 200
        assert second.status_code == 409

    async def test_unknown_run_not_found(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user()) as client:
            resp = await client.post("/api/race-analysis/runs/run-999/dismiss-stale")

        assert resp.status_code == 404

    async def test_parent_forbidden_and_run_untouched(self, session):
        await _seed_world(session)

        async with make_client(session, user=parent_user()) as client:
            resp = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")

        assert resp.status_code == 403
        untouched = await session.get(AgentRun, 11)
        assert untouched is not None and untouched.stale_since is not None
        assert await _audit_rows(session, 11) == []

    async def test_coach_of_another_club_forbidden(self, session):
        await _seed_world(session)

        async with make_client(session, user=coach_user(user_id=11, club_id=2)) as client:
            resp = await client.post("/api/race-analysis/runs/run-11/dismiss-stale")

        assert resp.status_code == 403
        untouched = await session.get(AgentRun, 11)
        assert untouched is not None and untouched.stale_since is not None
