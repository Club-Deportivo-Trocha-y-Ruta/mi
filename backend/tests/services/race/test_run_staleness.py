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
from tests.helpers.audit_tables import AUDIT_TABLES

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
    *AUDIT_TABLES,
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


# ---------------------------------------------------------------------------
# Feature 045 T074: season summaries (event_id=NULL) go stale on a revision
# ---------------------------------------------------------------------------


def _run(run_id: int, athlete_id: int) -> AgentRun:
    return AgentRun(
        id=run_id,
        external_run_id=f"run-{run_id}",
        graph_name="race-analyst",
        prompt_version="race_analyst_v3",
        started_at=_now(),
        status=AgentRunStatus.completed,
        requested_by_user_id=10,
        athlete_id=athlete_id,
        checkpoint_thread_id=f"run-{run_id}",
        stale_since=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _season_insight(
    insight_id: int,
    *,
    athlete_id: int,
    run_id: int,
    season: int,
    is_active: int | None = 1,
    use_case: str = "season_summary",
    valida_num: int | None = 0,
) -> AthleteAiInsight:
    return AthleteAiInsight(
        id=insight_id,
        athlete_id=athlete_id,
        event_id=None,
        agent_run_id=run_id,
        generated_by_user_id=10,
        season=season,
        valida_num=valida_num,
        use_case=use_case,
        summary_text="resumen de temporada",
        recommendations_json=[],
        metrics_snapshot_json={},
        principles_cited_json=[],
        model="gemini",
        prompt_version="race_analyst_v3",
        coach_approved=True,
        generated_at=_now(),
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )


@pytest_asyncio.fixture
async def seeded_seasons(seeded):
    """On top of ``seeded`` (event 5, season 2026, athlete 144 with a result):

    - run 20: athlete 144, active season summary 2026 → must go stale.
    - run 21: athlete 144, active season summary 2025 → other season, untouched.
    - run 22: athlete 145 (no result in event 5), season summary 2026 → untouched.
    - run 23: athlete 146, result in event 5 soft-deleted by the revision,
      season summary 2026 → stale (the revision changed their results too).
    - run 24: athlete 144, INACTIVE (superseded) season summary 2026 → untouched.
    - run 25: athlete 144, active per-válida insight of ANOTHER event of 2026
      → untouched (only E's own válida analyses go stale, as before).
    """
    async with seeded() as s:
        for uid in (145, 146):
            await create_user(s, user_id=uid, role=UserRole.athlete, can_login=False)
            await create_athlete(
                s, athlete_id=uid, first_name="Ficticio", last_name=f"N{uid}",
                club_id=1, user_id=uid,
            )
        await create_race_series(s, series_id=2, season_year=2025)
        await create_race_event(
            s, event_id=6, series_id=1, sequence_number=5, name="V5",
            event_date=date(2026, 6, 14), location="Palmira",
        )
        await create_race_competitor(
            s, competitor_id=502, normalized_name="ficticio n146",
            display_name="Ficticio N146", athlete_id=146,
        )
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=502, athlete_id=146,
            position=2, deleted_at=_now(),
        )
        for rid, aid in ((20, 144), (21, 144), (22, 145), (23, 146), (24, 144), (25, 144)):
            s.add(_run(rid, aid))
        await s.flush()
        s.add(_season_insight(20, athlete_id=144, run_id=20, season=2026))
        s.add(_season_insight(21, athlete_id=144, run_id=21, season=2025))
        s.add(_season_insight(22, athlete_id=145, run_id=22, season=2026))
        s.add(_season_insight(23, athlete_id=146, run_id=23, season=2026,
                              use_case="season_summary_v3", valida_num=0))
        s.add(_season_insight(24, athlete_id=144, run_id=24, season=2026, is_active=None))
        per_valida = _season_insight(
            25, athlete_id=144, run_id=25, season=2026,
            use_case="race_analysis_v3", valida_num=5,
        )
        per_valida.event_id = 6
        s.add(per_valida)
        await s.commit()
    return seeded


@pytest.mark.asyncio
async def test_invalidate_marks_season_summary_of_affected_athletes(seeded_seasons):
    async with seeded_seasons() as s:
        result = await invalidate_runs_for_event(s, event_id=5)
        await s.commit()

    async with seeded_seasons() as s:
        stale = {
            rid: (await s.get(AgentRun, rid)).stale_since is not None
            for rid in (1, 20, 21, 22, 23, 24, 25)
        }
    assert stale == {
        1: True,    # per-válida run of event 5 (pre-existing behaviour)
        20: True,   # season-2026 summary of an athlete with results in event 5
        21: False,  # another season
        22: False,  # another athlete (no results in event 5)
        23: True,   # athlete whose result in event 5 the revision removed
        24: False,  # inactive (superseded) summary
        25: False,  # válida analysis of another event
    }
    assert result["runs_marked"] == 3
    assert result["season_summaries_marked"] == 2


@pytest.mark.asyncio
async def test_invalidate_season_summary_idempotent(seeded_seasons):
    async with seeded_seasons() as s:
        await invalidate_runs_for_event(s, event_id=5)
        await s.commit()
    async with seeded_seasons() as s:
        first_ts = (await s.get(AgentRun, 20)).stale_since
        result2 = await invalidate_runs_for_event(s, event_id=5)
        await s.commit()
    async with seeded_seasons() as s:
        assert (await s.get(AgentRun, 20)).stale_since == first_ts
    assert result2["runs_marked"] == 0
    assert result2["season_summaries_marked"] == 0
