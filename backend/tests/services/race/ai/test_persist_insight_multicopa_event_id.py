"""Regresión end-to-end: identidad de válida entre copas distintas (Bug #4).

Hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``): antes de este fix,
``persist_insight`` reutilizaba el ``event_id`` ancla del run para TODA fila
del fan-out y ``deprecate_previous_active`` filtraba por ``(season,
valida_num)`` crudo. Dos copas con la misma ``sequence_number`` (ej. Copa
Valle V4 y Copa Let's Go V4) colisionaban: aprobar el análisis de una copa
apagaba el insight activo de la OTRA copa del mismo atleta.

Este test reproduce exactamente el escenario del bug real: un atleta con un
insight activo de Copa A Válida 4, y un lanzamiento (simulando
``group_launch``) sobre Copa B Válida 4 — deben quedar AMBOS insights
activos, y la fila nueva debe persistir el ``event_id`` de Copa B (nunca el
de Copa A ni ``None``).

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence
from app.models.user import UserRole
from app.services.race.ai.db import set_db_factory
from app.services.race.ai.nodes.persist_insight import persist_insight

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_race_series,
    create_user,
)
from tests.services.race.ai.conftest import make_analysis_output
from tests.helpers.audit_tables import AUDIT_TABLES


# ---------------------------------------------------------------------------
# Engine + factory (necesita race_series/race_events además de las tablas
# base de test_persist_insight_deprecation.py, para resolver event_id real).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "athlete_ai_insights",
            "race_series",
            "race_events",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded_factory(
    session_factory,
) -> async_sessionmaker[AsyncSession]:
    """Club + coach + atleta + DOS copas (A y B) con Válida 4 cada una."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)

        await create_race_series(
            s, series_id=1, season_year=2026, name="Copa A Test"
        )
        await create_race_series(
            s, series_id=2, season_year=2026, name="Copa B Test"
        )
        await create_race_event(
            s, event_id=100, series_id=1, sequence_number=4, name="Copa A Válida 4"
        )
        await create_race_event(
            s, event_id=200, series_id=2, sequence_number=4, name="Copa B Válida 4"
        )
        await s.commit()
    return session_factory


@pytest.fixture(autouse=True)
def patch_db_factory(seeded_factory):
    set_db_factory(lambda: seeded_factory())
    yield
    set_db_factory(None)


def _state_for_copa_b_launch(*, event_id: int = 200, valida_num: int = 4) -> dict:
    """State que simula un lanzamiento de group_launch anclado a Copa B V4."""
    return {
        "athlete_id": 144,
        "season": 2026,
        "competitor_id": None,
        "coach_id": 10,
        "draft_analysis": make_analysis_output(),
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
        "valida_num": valida_num,
        "event_id": event_id,
        "use_case": "race_progression",
        "confidence": InsightConfidence.medium,
    }


@pytest.mark.asyncio
async def test_group_launch_on_other_cup_does_not_deprecate_first_cup_insight(
    session_factory,
):
    """Insight activo de Copa A V4 + lanzamiento sobre Copa B V4 → ambos activos."""
    async with session_factory() as s:
        copa_a_insight = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=4,
            event_id=100,  # Copa A
            coach_approved=True,
            is_active=1,
        )
        await s.commit()
        copa_a_id = copa_a_insight.id

    await persist_insight(_state_for_copa_b_launch())

    async with session_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.athlete_id == 144)
        )
        rows_list = list(rows.scalars().all())

    assert len(rows_list) == 2

    by_event = {r.event_id: r for r in rows_list}
    assert 100 in by_event and 200 in by_event

    copa_a_row = by_event[100]
    copa_b_row = by_event[200]

    # Copa A NUNCA se deprecó — sigue activa, sin superseded_by.
    assert copa_a_row.id == copa_a_id
    assert copa_a_row.is_active == 1
    assert copa_a_row.deprecated_at is None
    assert copa_a_row.superseded_by_insight_id is None

    # Copa B es la fila nueva, activa, con SU PROPIO event_id (nunca None,
    # nunca el de Copa A).
    assert copa_b_row.is_active == 1
    assert copa_b_row.valida_num == 4
    assert copa_b_row.event_id == 200


@pytest.mark.asyncio
async def test_relaunching_same_cup_valida_does_deprecate_its_own_prior_insight(
    session_factory,
):
    """Control: un relanzamiento de la MISMA copa/válida sí debe deprecar."""
    async with session_factory() as s:
        prior = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=4,
            event_id=200,  # Copa B — misma que el nuevo lanzamiento
            coach_approved=True,
            is_active=1,
        )
        await s.commit()
        prior_id = prior.id

    await persist_insight(_state_for_copa_b_launch())

    async with session_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.athlete_id == 144)
        )
        rows_list = list(rows.scalars().all())

    assert len(rows_list) == 2
    prior_reloaded = next(r for r in rows_list if r.id == prior_id)
    new_row = next(r for r in rows_list if r.id != prior_id)

    assert prior_reloaded.is_active is None
    assert prior_reloaded.deprecated_at is not None
    assert prior_reloaded.superseded_by_insight_id == new_row.id
    assert new_row.event_id == 200
    assert new_row.is_active == 1
