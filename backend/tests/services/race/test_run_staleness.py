"""Tests del servicio de staleness de runs IA (PR5 unificación /competitions).

Cubre:
- invalidate_runs_for_event marca stale los runs con insights del evento.
- Marca outdated los boletines `sent` del atleta+temporada afectados (D3).
- NO toca boletines en draft/approved.
- mark_run_stale es idempotente.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus
from app.models.user import UserRole
from app.services.race.run_staleness import (
    invalidate_runs_for_event,
    mark_run_stale,
)

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    "athlete_ai_insights",
    "agent_runs",
    "athlete_monthly_newsletters",
]


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
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def seeded(session_factory):
    """Evento 5 con insight ligado a run 1 (athlete 144, season 2026) + boletín sent."""
    async with session_factory() as s:
        await create_club(s, club_id=1, name="TyR", code="tyr")
        await create_user(s, user_id=10, role=UserRole.coach, email="c@test.com")
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, first_name="Juan", last_name="Garcia", club_id=1, user_id=144)
        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(s, event_id=5, series_id=1, sequence_number=4, name="V4", event_date=date(2026, 5, 17), location="Cali")
        await create_race_competitor(s, competitor_id=501, normalized_name="juan garcia", display_name="Juan Garcia", athlete_id=144)
        await create_race_result(s, event_id=5, category_id=100, competitor_id=501, athlete_id=144, position=1)

        # Run 1 (vigente)
        s.add(
            AgentRun(
                id=1,
                external_run_id="run-abc",
                graph_name="race-analyst",
                prompt_version="race_analyst_v2",
                started_at=_now(),
                status=AgentRunStatus.completed,
                requested_by_user_id=10,
                athlete_id=144,
                checkpoint_thread_id="run-abc",
                stale_since=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await s.flush()

        # Insight del evento 5 ligado al run 1
        s.add(
            AthleteAiInsight(
                id=1,
                athlete_id=144,
                event_id=5,
                agent_run_id=1,
                generated_by_user_id=10,
                season=2026,
                valida_num=4,
                use_case="race_analysis_v2",
                summary_text="resumen",
                recommendations_json=[],
                metrics_snapshot_json={},
                principles_cited_json=[],
                model="gemini",
                prompt_version="race_analyst_v2",
                coach_approved=True,
                generated_at=_now(),
                is_active=1,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        # Boletín sent de athlete 144, year 2026
        s.add(
            AthleteMonthlyNewsletter(
                id=1,
                athlete_id=144,
                year=2026,
                month=5,
                status=NewsletterStatus.sent,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        # Boletín draft de otro periodo — NO debe tocarse
        s.add(
            AthleteMonthlyNewsletter(
                id=2,
                athlete_id=144,
                year=2026,
                month=8,
                status=NewsletterStatus.draft,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await s.commit()

    return session_factory


@pytest.mark.asyncio
async def test_invalidate_marca_runs_y_boletines(seeded):
    async with seeded() as s:
        result = await invalidate_runs_for_event(s, event_id=5)
        await s.commit()

    assert result["runs_marked"] == 1
    assert result["newsletters_outdated"] == 1

    async with seeded() as s:
        run = await s.get(AgentRun, 1)
        assert run.stale_since is not None
        nl_sent = await s.get(AthleteMonthlyNewsletter, 1)
        assert nl_sent.status == NewsletterStatus.outdated
        nl_draft = await s.get(AthleteMonthlyNewsletter, 2)
        # draft de otro mes NO se toca
        assert nl_draft.status == NewsletterStatus.draft


@pytest.mark.asyncio
async def test_invalidate_idempotente(seeded):
    async with seeded() as s:
        await invalidate_runs_for_event(s, event_id=5)
        await s.commit()
    # Segunda corrida: el run ya está stale → runs_marked=0
    async with seeded() as s:
        result2 = await invalidate_runs_for_event(s, event_id=5)
        await s.commit()
    assert result2["runs_marked"] == 0


@pytest.mark.asyncio
async def test_mark_run_stale_idempotente(seeded):
    async with seeded() as s:
        ok1 = await mark_run_stale(s, 1)
        first_ts = (await s.get(AgentRun, 1)).stale_since
        ok2 = await mark_run_stale(s, 1)
        second_ts = (await s.get(AgentRun, 1)).stale_since
        await s.commit()
    assert ok1 and ok2
    # No re-marca (timestamp estable).
    assert first_ts == second_ts


@pytest.mark.asyncio
async def test_mark_run_stale_run_inexistente(seeded):
    async with seeded() as s:
        ok = await mark_run_stale(s, 999)
    assert ok is False
