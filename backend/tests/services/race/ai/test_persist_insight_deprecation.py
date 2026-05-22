"""Tests del hook HITL en ``persist_insight`` (BE-3).

Verifica que el nodo ``persist_insight`` integra correctamente con
:func:`app.services.race.insights_history.deprecate_previous_active`:

- ``approve`` → deprecar la fila activa anterior + enlazar superseded_by.
- ``reject`` → NO tocar la fila previa.
- ``valida_num=None`` con use_case agregado → se mapea a 0 (sentinel).
- El puntero ``superseded_by_insight_id`` apunta al PK nuevo.

Estrategia: SQLite real (aiosqlite) + ``set_db_factory`` con factory
custom que retorna nuestra sesión. Las llamadas a LLM no ocurren acá:
el nodo solo persiste el state que ya contiene ``draft_analysis``.
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
    create_user,
)
from tests.services.race.ai.conftest import make_analysis_output


# ---------------------------------------------------------------------------
# Engine + factory
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
    """Sesión + seed: club + coach + atleta. Hace yield del factory para
    que el nodo pueda crear sesiones nuevas via get_session()."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await s.commit()
    return session_factory


@pytest.fixture(autouse=True)
def patch_db_factory(seeded_factory):
    """Cada test inyecta su factory ANTES de que persist_insight corra.

    persist_insight llama ``async with get_session() as db`` → necesitamos
    que cada llamada abra una sesión nueva del session_factory.
    """
    set_db_factory(lambda: seeded_factory())
    yield
    set_db_factory(None)


def _state(
    *,
    decision: str = "approve",
    valida_num: int | None = 1,
    use_case: str = "race_progression",
    athlete_id: int = 144,
    season: int = 2026,
    coach_id: int = 10,
) -> dict:
    """Construye un state mínimo para el nodo persist_insight."""
    return {
        "athlete_id": athlete_id,
        "season": season,
        "competitor_id": None,
        "coach_id": coach_id,
        "draft_analysis": make_analysis_output(),
        "hitl_decision": {"decision": decision},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
        "valida_num": valida_num,
        "use_case": use_case,
        "confidence": InsightConfidence.medium,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_insight_approved_marks_previous_active_as_deprecated(
    session_factory,
):
    """Cuando hay un insight activo previo para la terna, ``approve`` debe
    marcarlo como deprecado (is_active=NULL, deprecated_at SET)."""
    # Seed previo: insight activo para (athlete=144, season=2026, valida_num=1).
    async with session_factory() as s:
        previous = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()
        previous_id = previous.id

    # Disparar persist_insight con decision=approve.
    state = _state(decision="approve", valida_num=1)
    await persist_insight(state)

    # Verificar en DB que el previo quedó deprecado.
    async with session_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
        )
        reloaded = rows.scalar_one()
        assert reloaded.is_active is None
        assert reloaded.deprecated_at is not None


@pytest.mark.asyncio
async def test_persist_insight_rejected_does_not_touch_previous(
    session_factory,
):
    """Con decision=reject NO debe deprecar al previo (queda intacto)."""
    async with session_factory() as s:
        previous = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()
        previous_id = previous.id

    state = _state(decision="reject", valida_num=1)
    await persist_insight(state)

    async with session_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
        )
        reloaded = rows.scalar_one()
        # Sigue activo, sin deprecated_at.
        assert reloaded.is_active == 1
        assert reloaded.deprecated_at is None


@pytest.mark.asyncio
async def test_persist_insight_valida_num_none_maps_to_zero_for_aggregated(
    session_factory,
):
    """``valida_num=None`` + use_case agregado → la fila persiste con valida_num=0."""
    state = _state(
        decision="approve",
        valida_num=None,
        use_case="season_summary",
    )
    await persist_insight(state)

    async with session_factory() as s:
        rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.athlete_id == 144)
        )
        rows_list = list(rows.scalars().all())
        # Hay solo 1 fila nueva.
        assert len(rows_list) == 1
        assert rows_list[0].valida_num == 0
        assert rows_list[0].use_case == "season_summary"


@pytest.mark.asyncio
async def test_persist_insight_superseded_by_pointer_set_correctly(
    session_factory,
):
    """El insight previo deprecado debe apuntar via superseded_by_insight_id
    al PK del insight nuevo."""
    async with session_factory() as s:
        previous = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=1,
            coach_approved=True,
            is_active=1,
        )
        await s.commit()
        previous_id = previous.id

    state = _state(decision="approve", valida_num=1)
    await persist_insight(state)

    async with session_factory() as s:
        # Cargar el insight nuevo (el otro que existe para la misma terna).
        rows = await s.execute(
            select(AthleteAiInsight)
            .where(AthleteAiInsight.athlete_id == 144)
            .where(AthleteAiInsight.id != previous_id)
        )
        new_row = rows.scalar_one()
        # El nuevo está activo.
        assert new_row.is_active == 1
        # El previo apunta al nuevo.
        prev_rows = await s.execute(
            select(AthleteAiInsight).where(AthleteAiInsight.id == previous_id)
        )
        reloaded_prev = prev_rows.scalar_one()
        assert reloaded_prev.superseded_by_insight_id == new_row.id
