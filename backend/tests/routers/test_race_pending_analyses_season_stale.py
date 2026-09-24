"""Feature 045 T074: a revised import makes the season summary stale.

Season summaries are stored with ``event_id=NULL`` (``valida_num=0``), so the
per-event invalidation used to miss them. After
``run_staleness.invalidate_runs_for_event(E)`` — the call made by the commit
path of a revised import — the season-S summary of every athlete with results
in E must:

- appear in ``GET /api/race-analysis/pending-analyses?state=stale`` with
  ``kind="season_summary"``;
- be counted by ``GET /api/dashboard/coach-summary`` (SC-005: count == list);
- be clearable with ``POST /api/race-analysis/runs/{run_id}/dismiss-stale``.

Summaries of another season or of an athlete without results in E stay fresh.
All names are fictitious (CLAUDE.md §Privacy).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete import Sex
from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.race.run_staleness import invalidate_runs_for_event
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.routers.test_race_pending_analyses import (
    _AGENT_RUNS_DDL,
    _seed_run,
    _summary,
    coach_user,
    make_client,
)

pytestmark = pytest.mark.asyncio

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    "athlete_ai_insights",
    "athlete_monthly_newsletters",
    "parental_consents",
    "training_sessions",
    "session_attendance",
    "race_identity_candidates",
    "race_imports",
    *AUDIT_TABLES,
)

_EVENT = 42
_SEASON = 2026


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


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _utc() -> datetime:
    return datetime.now(timezone.utc)


async def _seed(session: AsyncSession) -> None:
    """Club 1, athletes 101 (result in event 42) and 102 (no result).

    Runs (all completed, fresh):
    - 31: athlete 101, season summary 2026 → goes stale.
    - 32: athlete 101, season summary 2025 → untouched (other season).
    - 33: athlete 102, season summary 2026 → untouched (no results in E).
    """
    await create_club(session, club_id=1, name="Club Uno", code="uno")
    await create_user(session, user_id=10, role=UserRole.coach)
    await link_user_to_club(session, user_id=10, club_id=1, role_in_club=ClubRole.coach)
    for athlete_id, names in ((101, ("Zzyxaria", "Pruebalonga")), (102, ("Qwortan", "Simulacro"))):
        await create_user(session, user_id=900 + athlete_id, role=UserRole.athlete, can_login=False)
        await create_athlete(
            session, athlete_id=athlete_id, first_name=names[0], last_name=names[1],
            birth_date=date(2014, 5, 5), sex=Sex.F, club_id=1,
            user_id=900 + athlete_id, created_by=10,
        )
    await create_race_series(session, series_id=1, season_year=_SEASON)
    await create_race_category(session, category_id=100)
    await create_race_event(
        session, event_id=_EVENT, series_id=1, sequence_number=4,
        name="Copa Simulada - Válida 4", event_date=date(_SEASON, 5, 17),
    )
    await create_race_competitor(session, competitor_id=501, athlete_id=101)
    await create_race_result(
        session, event_id=_EVENT, category_id=100, competitor_id=501, athlete_id=101,
    )

    for run_id, athlete_id, season in ((31, 101, _SEASON), (32, 101, 2025), (33, 102, _SEASON)):
        await _seed_run(
            session, run_id, athlete_id=athlete_id, status=AgentRunStatus.completed,
        )
        await create_insight(
            session, athlete_id=athlete_id, agent_run_id=run_id, is_active=1,
            valida_num=0, season=season, use_case="season_summary",
            event_id=None, generated_by_user_id=10,
        )
    await session.commit()


async def test_revision_surfaces_season_summary_as_stale(session):
    await _seed(session)

    await invalidate_runs_for_event(session, _EVENT)
    await session.commit()

    async with make_client(session, user=coach_user()) as client:
        resp = await client.get(
            "/api/race-analysis/pending-analyses", params={"state": "stale"}
        )
        summary = await _summary(client)

    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [(i["run_id"], i["kind"], i["season"]) for i in items] == [
        ("run-31", "season_summary", _SEASON)
    ]
    assert items[0]["athlete_id"] == 101
    # SC-005: count == list, and it is not a vacuous 0 == 0.
    assert summary["insights_stale"] == len(items) == 1


async def test_dismiss_stale_clears_the_season_summary(session):
    await _seed(session)
    await invalidate_runs_for_event(session, _EVENT)
    await session.commit()

    async with make_client(session, user=coach_user()) as client:
        dismiss = await client.post("/api/race-analysis/runs/run-31/dismiss-stale")
        stale = await client.get(
            "/api/race-analysis/pending-analyses", params={"state": "stale"}
        )
        summary = await _summary(client)

    assert dismiss.status_code == 200, dismiss.text
    assert dismiss.json() == {"run_id": "run-31", "stale": False}
    assert stale.json() == []
    assert summary["insights_stale"] == 0
    run = await session.get(AgentRun, 31)
    assert run is not None and run.stale_since is None
