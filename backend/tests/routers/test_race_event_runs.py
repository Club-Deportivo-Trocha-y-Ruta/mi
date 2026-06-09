"""Tests for POST/GET /api/race-analysis/race-events/{id}/runs (T005, T006).

Strategy:
- Real SQLite async in-memory DB (same pattern as test_race_imports.py).
  group_launch uses SQLAlchemy ORM select() queries that need a real engine;
  FakeSession cannot dispatch those joins.
- Runner stubbed via set_graph_factory (same pattern as conftest coach_client).
- Budget guard monkeypatched where needed.
- Auth via dependency override on _coach_or_admin (same as conftest fixtures).

Test coverage:
  T005 — POST /race-events/{id}/runs:
  1.  Happy path: event with 3 athletes → 200, started_count=3.
  2.  athlete_ids subset → only those athletes launched.
  3.  already_running skip: one active run pre-seeded → outcome=already_running.
  4.  Partial backpressure: one athlete raises RunBackpressureError → 200 mixed.
  5.  All-backpressure → 429.
  6.  Budget exceeded (check_budget raises) → 503.
  7.  Event without results → 422.
  8.  Unknown event → 404.
  9.  AI disabled → 503.
  10. RBAC: parent → 403; unauthenticated → 401/403.

  T006 — GET /race-events/{id}/runs:
  11. active_only=true returns only running/awaiting_hitl.
  12. active_only=false includes recent terminal runs.
  13. stale flag when stale_since IS NOT NULL.
  14. Non-stale run → stale=false.
  15. Unknown event → 404.
  16. Empty runs list when no runs exist.
  17. RBAC: parent → 403; anon → 401/403.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_db
from app.main import app
from app.models import Base
from app.models.user import UserRole
from app.routers.race_analysis import _admin_only, _coach_or_admin

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Single in-memory engine covering all needed tables
# ---------------------------------------------------------------------------


_AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id TEXT NOT NULL UNIQUE,
    graph_name      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    input_json      TEXT,
    final_output_json TEXT,
    error_message   TEXT,
    requested_by_user_id INTEGER,
    athlete_id      INTEGER,
    checkpoint_thread_id TEXT NOT NULL,
    explain_mode    INTEGER NOT NULL DEFAULT 0,
    stale_since     TEXT,
    created_at      TEXT,
    updated_at      TEXT
)
"""


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    """SQLite StaticPool engine with all tables needed for group-launch tests.

    The AgentRun ORM model only maps a subset of columns (no input_json,
    explain_mode, etc.).  We create agent_runs with a hand-written DDL that
    includes ALL columns queried by the group_launch service's text() queries.
    """
    # Import models to register them on Base.metadata before create_all.
    from app.models.user import User as _U  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    table_names = [
        "users",
        "clubs",
        "club_members",
        "athletes",
        "race_series",
        "race_events",
        "race_categories",
        "race_competitors",
        "race_results",
    ]
    tables = [Base.metadata.tables[t] for t in table_names]

    async with engine.begin() as conn:
        # Create ORM-managed tables.
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        # Create agent_runs with full column set (ORM model is a subset).
        from sqlalchemy import text as _text

        await conn.execute(_text(_AGENT_RUNS_DDL))

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_base(
    session_factory: async_sessionmaker[AsyncSession],
    n_athletes: int = 3,
    event_id: int = 42,
    series_id: int = 1,
    sequence_number: int = 3,
    user_id: int = 10,
) -> dict[str, Any]:
    """Seed a race event with n_athletes linked via race_results.

    Each athlete gets its own User (unique user_id constraint).
    All results use status=dns (no race_time_ms required) to avoid
    the check constraint that ties time to finished status.
    Returns {event_id, series_id, athlete_ids}.
    """
    from app.models.user import User
    from app.models.club import Club
    from app.models.athlete import Athlete, Sex
    from app.models.race_series import RaceSeries
    from app.models.race_event import RaceEvent, RaceEventStatus
    from app.models.race_category import RaceCategory, CategoryGender
    from app.models.race_competitor import RaceCompetitor
    from app.models.race_result import RaceResult, ResultStatus

    # Use a high base to avoid PK collisions between seed calls.
    # user_id * 1000 gives unique space per test group.
    base = user_id * 1000

    async with session_factory() as session:
        # Coach user (the event creator).
        coach = User(
            id=user_id,
            email=f"coach{user_id}@test.local",
            hashed_password="x",
            first_name="Coach",
            last_name="Test",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=_utc_now(),
        )
        session.add(coach)
        await session.flush()

        # Club (required by Athlete.club_id).
        club = Club(
            id=base + 1,
            name=f"Club Test {user_id}",
            code=f"CLT{user_id}",
            created_at=_utc_now(),
            is_active=True,
        )
        session.add(club)
        await session.flush()

        # One User per athlete (user_id UNIQUE constraint on athletes table).
        athlete_ids = []
        for i in range(n_athletes):
            athlete_user = User(
                id=base + i + 100,
                email=f"atleta{base + i}@test.local",
                hashed_password="x",
                first_name=f"Atleta{i}",
                last_name=f"Ape{i}",
                role=UserRole.coach,  # role doesn't matter for athlete user
                is_active=True,
                can_login=False,
                created_at=_utc_now(),
            )
            session.add(athlete_user)
            await session.flush()

            athlete = Athlete(
                id=base + i,
                user_id=base + i + 100,
                first_name=f"Atleta{i}",
                last_name=f"Ape{i}",
                birth_date=date(2012, 1, 1),
                sex=Sex.M,
                club_id=base + 1,
                created_by=user_id,
            )
            session.add(athlete)
            athlete_ids.append(base + i)

        await session.flush()

        series = RaceSeries(
            id=series_id,
            name=f"Serie {series_id}",
            season_year=2026,
            organizer="Liga Test",
            points_scheme_code="copa_valle_2026",
        )
        session.add(series)
        await session.flush()

        event = RaceEvent(
            id=event_id,
            series_id=series_id,
            sequence_number=sequence_number,
            name=f"Válida {sequence_number}",
            event_date=date(2026, 4, 19),
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=user_id,
        )
        session.add(event)
        await session.flush()

        cat = RaceCategory(
            id=series_id * 100,  # unique per series
            code=f"TET_{series_id}",
            label="Tetero",
            sex=CategoryGender.M,
            sort_order=0,
            is_active=True,
        )
        session.add(cat)
        await session.flush()

        for i in range(n_athletes):
            comp = RaceCompetitor(
                id=base + 500 + i,
                normalized_name=f"atleta{i} ape{i}",
                display_name=f"Atleta{i} Ape{i}",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
            session.add(comp)
            await session.flush()

            result = RaceResult(
                event_id=event_id,
                category_id=series_id * 100,
                competitor_id=base + 500 + i,
                athlete_id=base + i,
                status=ResultStatus.DNS,
                points_awarded=0,
                created_by_user_id=user_id,
            )
            session.add(result)

        await session.commit()

    return {"event_id": event_id, "series_id": series_id, "athlete_ids": athlete_ids}


async def _seed_agent_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    external_run_id: str,
    athlete_id: int,
    season: int = 2026,
    valida_num: int = 3,
    db_status: str = "running",
    stale_since: datetime | None = None,
    started_at: datetime | None = None,
) -> None:
    """Insert an agent_runs row for test setup."""
    from sqlalchemy import text

    input_json = json.dumps(
        {
            "athlete_id": athlete_id,
            "season": season,
            "valida_nums": [valida_num],
            "explain_mode": False,
        }
    )
    async with session_factory() as session:
        await session.execute(
            text(
                """
                INSERT INTO agent_runs (
                    external_run_id, graph_name, prompt_version, started_at,
                    status, input_json, requested_by_user_id,
                    checkpoint_thread_id, explain_mode
                ) VALUES (
                    :rid, :gn, :pv, :sa, :st, :inp, :uid, :tid, :em
                )
                """
            ),
            {
                "rid": external_run_id,
                "gn": "race-analyst",
                "pv": "race_analyst_v2",
                "sa": started_at or _utc_now(),
                "st": db_status,
                "inp": input_json,
                "uid": 10,
                "tid": external_run_id,
                "em": 0,
            },
        )
        if stale_since is not None:
            await session.execute(
                text(
                    "UPDATE agent_runs SET stale_since = :ss WHERE external_run_id = :rid"
                ),
                {"ss": stale_since, "rid": external_run_id},
            )
        await session.commit()


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def http_client(session_factory):
    """Coach-authenticated AsyncClient backed by real SQLite."""
    from app.services.race.ai import runner as runner_mod

    class _NopGraph:
        async def ainvoke(self, value: Any, config: Any = None) -> dict:
            return {}

    runner_mod.set_graph_factory(lambda: _NopGraph())
    await runner_mod._reset_for_tests()

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[_coach_or_admin] = lambda: _make_user(UserRole.coach, 10)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def admin_http_client(session_factory):
    """Admin-authenticated AsyncClient."""
    from app.services.race.ai import runner as runner_mod

    class _NopGraph:
        async def ainvoke(self, value: Any, config: Any = None) -> dict:
            return {}

    runner_mod.set_graph_factory(lambda: _NopGraph())
    await runner_mod._reset_for_tests()

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[_coach_or_admin] = lambda: _make_user(UserRole.admin, 1)
    app.dependency_overrides[_admin_only] = lambda: _make_user(UserRole.admin, 1)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
    runner_mod.set_graph_factory(None)
    await runner_mod._reset_for_tests()


@pytest_asyncio.fixture
async def parent_http_client():
    """Client whose _coach_or_admin override raises 403."""

    def _forbid():
        raise HTTPException(status_code=403, detail="Forbidden")

    app.dependency_overrides[_coach_or_admin] = _forbid
    app.dependency_overrides[_admin_only] = _forbid

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_http_client():
    """Client with no auth overrides — real bearer check applies."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def ai_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_enabled", True)
    return settings


# ===========================================================================
# T005 — POST /api/race-analysis/race-events/{id}/runs
# ===========================================================================


class TestGroupLaunchHappyPath:
    async def test_three_athletes_all_started(
        self, http_client, session_factory, ai_on
    ):
        """Happy path: 3 athletes with results → 200, started_count=3."""
        seed = await _seed_base(session_factory, n_athletes=3)

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["race_event_id"] == seed["event_id"]
        assert body["season"] == 2026
        assert body["valida_num"] == 3
        assert body["started_count"] == 3
        assert body["skipped_count"] == 0
        assert len(body["items"]) == 3
        for item in body["items"]:
            assert item["outcome"] == "started"
            assert item["run_id"] is not None
            assert item["athlete_id"] in seed["athlete_ids"]

    async def test_athlete_ids_subset_filter(
        self, http_client, session_factory, ai_on
    ):
        """athlete_ids subset → only those two launched."""
        seed = await _seed_base(session_factory, n_athletes=3)
        subset = seed["athlete_ids"][:2]

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"athlete_ids": subset, "explain_mode": False},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started_count"] == 2
        launched_ids = [i["athlete_id"] for i in body["items"]]
        assert set(launched_ids) == set(subset)


class TestAlreadyRunningSkip:
    async def test_one_already_running_skipped(
        self, http_client, session_factory, ai_on
    ):
        """Pre-seeded active run → already_running for that athlete, others started."""
        seed = await _seed_base(session_factory, n_athletes=3)
        existing = uuid.uuid4().hex
        await _seed_agent_run(
            session_factory,
            external_run_id=existing,
            athlete_id=seed["athlete_ids"][0],
            db_status="running",
        )

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started_count"] == 2
        assert body["skipped_count"] == 1

        outcomes = {i["athlete_id"]: i["outcome"] for i in body["items"]}
        assert outcomes[seed["athlete_ids"][0]] == "already_running"
        for aid in seed["athlete_ids"][1:]:
            assert outcomes[aid] == "started"


class TestBackpressureRoutes:
    async def test_partial_backpressure_returns_200(
        self, http_client, session_factory, monkeypatch, ai_on
    ):
        """Second submit_run raises RunBackpressureError → 200, one started + one backpressure."""
        from app.services.race import group_launch as gl_mod
        from app.services.race.ai.runner import RunBackpressureError

        seed = await _seed_base(session_factory, n_athletes=2)

        call_count = 0
        _orig_submit = gl_mod.submit_run

        async def _patched(run_id: str, state: dict, *, on_complete=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RunBackpressureError()
            return await _orig_submit(run_id, state, on_complete=on_complete)

        monkeypatch.setattr(gl_mod, "submit_run", _patched)

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["started_count"] == 1
        assert body["skipped_count"] == 1
        outcomes = [i["outcome"] for i in body["items"]]
        assert "started" in outcomes
        assert "backpressure" in outcomes

    async def test_all_backpressure_returns_429(
        self, http_client, session_factory, monkeypatch, ai_on
    ):
        """All athletes backpressure → 429."""
        from app.services.race import group_launch as gl_mod
        from app.services.race.ai.runner import RunBackpressureError

        seed = await _seed_base(session_factory, n_athletes=2)

        async def _always_bp(run_id: str, state: dict, *, on_complete=None):
            raise RunBackpressureError()

        monkeypatch.setattr(gl_mod, "submit_run", _always_bp)

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 429, resp.text


class TestBudgetGuardEndpoint:
    async def test_budget_exceeded_returns_503(
        self, http_client, session_factory, monkeypatch
    ):
        """check_budget raises BudgetExceededError → 503 before any run starts."""
        from app.config import settings
        from app.services.race.ai.budget_guard import BudgetExceededError

        monkeypatch.setattr(settings, "ai_enabled", True)

        async def _raise_budget(db):
            raise BudgetExceededError(current_usd=5.0, budget_usd=0.001)

        monkeypatch.setattr("app.routers.race_analysis.check_budget", _raise_budget)

        seed = await _seed_base(session_factory, n_athletes=1)

        resp = await http_client.post(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 503, resp.text
        assert "Presupuesto" in resp.json()["detail"]


class TestGroupLaunchErrors:
    async def test_event_without_results_422(
        self, http_client, session_factory, ai_on
    ):
        """Event with sequence_number but no results → 422."""
        from app.models.user import User
        from app.models.race_series import RaceSeries
        from app.models.race_event import RaceEvent, RaceEventStatus

        async with session_factory() as session:
            user = User(
                id=20,
                email="coach20@test.local",
                hashed_password="x",
                first_name="Coach",
                last_name="Twenty",
                role=UserRole.coach,
                is_active=True,
                can_login=True,
                created_at=_utc_now(),
            )
            session.add(user)
            await session.flush()

            series = RaceSeries(
                id=10,
                name="Serie Empty",
                season_year=2026,
                organizer="Liga",
                points_scheme_code="copa_valle_2026",
            )
            session.add(series)
            await session.flush()

            event = RaceEvent(
                id=99,
                series_id=10,
                sequence_number=5,
                name="Empty Event",
                event_date=date(2026, 8, 1),
                status=RaceEventStatus.COMPLETED,
                created_by_user_id=20,
            )
            session.add(event)
            await session.commit()

        resp = await http_client.post(
            "/api/race-analysis/race-events/99/runs",
            json={"explain_mode": False},
        )

        assert resp.status_code == 422, resp.text
        assert "resultados" in resp.json()["detail"].lower()

    async def test_unknown_event_returns_404(
        self, http_client, ai_on
    ):
        """Non-existent race_event_id → 404."""
        resp = await http_client.post(
            "/api/race-analysis/race-events/99999/runs",
            json={"explain_mode": False},
        )
        assert resp.status_code == 404, resp.text

    async def test_ai_disabled_returns_503(self, http_client, monkeypatch):
        """AI_ENABLED=false → 503, no DB queries needed."""
        from app.config import settings

        monkeypatch.setattr(settings, "ai_enabled", False)

        resp = await http_client.post(
            "/api/race-analysis/race-events/42/runs",
            json={"explain_mode": False},
        )
        assert resp.status_code == 503, resp.text


class TestGroupLaunchRBAC:
    async def test_parent_returns_403(self, parent_http_client):
        resp = await parent_http_client.post(
            "/api/race-analysis/race-events/42/runs",
            json={"explain_mode": False},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401_or_403(self, anon_http_client):
        resp = await anon_http_client.post(
            "/api/race-analysis/race-events/42/runs",
            json={"explain_mode": False},
        )
        assert resp.status_code in (401, 403)


# ===========================================================================
# T006 — GET /api/race-analysis/race-events/{id}/runs
# ===========================================================================


class TestListEventRuns:
    async def test_active_only_true_excludes_terminal(
        self, http_client, session_factory
    ):
        """active_only=true → only running/awaiting_hitl returned."""
        seed = await _seed_base(session_factory, n_athletes=3)
        aid0, aid1, aid2 = seed["athlete_ids"]

        await _seed_agent_run(
            session_factory,
            external_run_id="run-active-a",
            athlete_id=aid0,
            db_status="running",
        )
        await _seed_agent_run(
            session_factory,
            external_run_id="run-hitl-a",
            athlete_id=aid1,
            db_status="awaiting_hitl",
        )
        await _seed_agent_run(
            session_factory,
            external_run_id="run-done-a",
            athlete_id=aid2,
            db_status="completed",
            started_at=_utc_now() - timedelta(hours=1),
        )

        resp = await http_client.get(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs?active_only=true"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["race_event_id"] == seed["event_id"]
        run_ids = {r["run_id"] for r in body["runs"]}
        assert "run-active-a" in run_ids
        assert "run-hitl-a" in run_ids
        assert "run-done-a" not in run_ids

    async def test_active_only_false_includes_recent_terminal(
        self, http_client, session_factory
    ):
        """active_only=false includes terminal runs from last 7 days."""
        seed = await _seed_base(
            session_factory,
            n_athletes=2,
            event_id=43,
            series_id=2,
            user_id=11,
        )
        aid0, aid1 = seed["athlete_ids"]

        await _seed_agent_run(
            session_factory,
            external_run_id="run-active-b",
            athlete_id=aid0,
            db_status="running",
        )
        await _seed_agent_run(
            session_factory,
            external_run_id="run-done-recent",
            athlete_id=aid1,
            db_status="completed",
            started_at=_utc_now() - timedelta(hours=2),
        )

        resp = await http_client.get(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs?active_only=false"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        run_ids = {r["run_id"] for r in body["runs"]}
        assert "run-active-b" in run_ids
        assert "run-done-recent" in run_ids

    async def test_stale_flag_true_when_stale_since_set(
        self, http_client, session_factory
    ):
        """Run with stale_since IS NOT NULL → stale=true, state=hitl_waiting."""
        seed = await _seed_base(
            session_factory,
            n_athletes=1,
            event_id=44,
            series_id=3,
            user_id=12,
        )
        aid = seed["athlete_ids"][0]

        await _seed_agent_run(
            session_factory,
            external_run_id="run-stale-x",
            athlete_id=aid,
            db_status="awaiting_hitl",
            stale_since=_utc_now() - timedelta(minutes=5),
        )

        resp = await http_client.get(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs?active_only=true"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["runs"]) == 1
        run_item = body["runs"][0]
        assert run_item["stale"] is True
        assert run_item["state"] == "hitl_waiting"
        assert run_item["athlete_id"] == aid

    async def test_stale_false_when_stale_since_null(
        self, http_client, session_factory
    ):
        """Run with stale_since IS NULL → stale=false."""
        seed = await _seed_base(
            session_factory,
            n_athletes=1,
            event_id=45,
            series_id=4,
            user_id=13,
        )
        aid = seed["athlete_ids"][0]

        await _seed_agent_run(
            session_factory,
            external_run_id="run-fresh-x",
            athlete_id=aid,
            db_status="running",
        )

        resp = await http_client.get(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs?active_only=true"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["runs"]) == 1
        assert body["runs"][0]["stale"] is False

    async def test_unknown_event_returns_404(self, http_client):
        resp = await http_client.get(
            "/api/race-analysis/race-events/99999/runs"
        )
        assert resp.status_code == 404, resp.text

    async def test_empty_runs_list_when_no_runs_exist(
        self, http_client, session_factory
    ):
        """Event with results but no agent_runs → 200, runs=[]."""
        seed = await _seed_base(
            session_factory,
            n_athletes=2,
            event_id=46,
            series_id=5,
            user_id=14,
        )

        resp = await http_client.get(
            f"/api/race-analysis/race-events/{seed['event_id']}/runs"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["race_event_id"] == seed["event_id"]
        assert body["runs"] == []

    async def test_rbac_parent_403(self, parent_http_client):
        resp = await parent_http_client.get(
            "/api/race-analysis/race-events/42/runs"
        )
        assert resp.status_code == 403

    async def test_rbac_anon_401_or_403(self, anon_http_client):
        resp = await anon_http_client.get(
            "/api/race-analysis/race-events/42/runs"
        )
        assert resp.status_code in (401, 403)
