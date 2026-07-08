"""Tests — Feature 022 (Alinear el Informe Técnico Mensual al formato institucional).

Cubre ``build_competition_results`` (backend/app/services/training/competition_results.py):

(happy) los ``CompetitionResultItem`` devueltos incluyen ``event_id``,
        ``series_kind`` y ``awards_points``.
(happy) un evento de una serie ``cup`` produce ``awards_points=True``; un
        evento de una serie ``championship`` produce ``awards_points=False``
        (semántica: ``awards_points = (series_kind == "cup")`` — spec 014,
        `RaceSeries.kind` / `RaceSeriesKind`).
(edge)  un período sin competencias devuelve una lista vacía sin error.

NOTA (T015, escrito antes/junto a T017): a la fecha de este test,
``build_competition_results`` NO hace join con ``RaceSeries`` ni popula
``event_id``/``series_kind``/``awards_points`` reales (usa los defaults del
schema: ``event_id=0``, ``series_kind=None``, ``awards_points=True``). Los
tests de "happy" fallan hasta que T017 implemente el join. Se documenta
explícitamente para que el fallo inicial no se confunda con un test mal
escrito.

Estrategia: SQLite async in-memory real, reutilizando las factories de
``tests/fixtures/race_history_fixtures.py`` (mismo patrón que
``tests/routers/test_athlete_race_analysis.py``).
"""
from __future__ import annotations

from datetime import date
from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_series import RaceSeriesKind
from app.models.user import UserRole
from app.services.training.competition_results import build_competition_results

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


# ---------------------------------------------------------------------------
# Engine / sesión SQLite in-memory
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
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# (edge) Período sin competencias
# ---------------------------------------------------------------------------


class TestNoCompetitionsInPeriod:
    async def test_empty_period_returns_empty_list(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await create_club(session, club_id=1)
            await create_user(session, user_id=10, role=UserRole.coach)
            await session.commit()

            items = await build_competition_results(session, club_id=1, year=2026, month=7)

        assert items == []


# ---------------------------------------------------------------------------
# (happy) Serie cup vs championship — event_id / series_kind / awards_points
# ---------------------------------------------------------------------------


class TestCupVsChampionshipGrouping:
    async def _seed_common(self, session: AsyncSession) -> None:
        await create_club(session, club_id=1)
        await create_user(session, user_id=10, role=UserRole.coach)
        await create_athlete(session, athlete_id=144, club_id=1, user_id=10, created_by=10)
        await create_race_category(session, category_id=100, code="INF_B", label="Infantil B")

    async def test_cup_series_event_awards_points_true(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await self._seed_common(session)
            await create_race_series(
                session, series_id=1, season_year=2026, kind=RaceSeriesKind.cup
            )
            await create_race_event(
                session,
                event_id=501,
                series_id=1,
                sequence_number=1,
                name="Copa Valle I",
                event_date=date(2026, 7, 15),
                created_by_user_id=10,
            )
            await create_race_competitor(session, competitor_id=1441, athlete_id=144)
            await create_race_result(
                session,
                event_id=501,
                category_id=100,
                competitor_id=1441,
                athlete_id=144,
                position=2,
                points_awarded=36,
                created_by_user_id=10,
            )
            await session.commit()

            items = await build_competition_results(session, club_id=1, year=2026, month=7)

        assert len(items) == 1
        item = items[0]
        assert item.event_id == 501
        assert item.series_kind == "cup"
        assert item.awards_points is True

    async def test_championship_series_event_awards_points_false(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with session_factory() as session:
            await self._seed_common(session)
            await create_race_series(
                session,
                series_id=2,
                season_year=2026,
                name="Campeonato Departamental de Ciclomontanismo",
                kind=RaceSeriesKind.championship,
            )
            await create_race_event(
                session,
                event_id=502,
                series_id=2,
                sequence_number=1,
                name="Campeonato Departamental",
                event_date=date(2026, 7, 20),
                created_by_user_id=10,
            )
            await create_race_competitor(session, competitor_id=1442, athlete_id=144)
            await create_race_result(
                session,
                event_id=502,
                category_id=100,
                competitor_id=1442,
                athlete_id=144,
                position=1,
                points_awarded=0,
                created_by_user_id=10,
            )
            await session.commit()

            items = await build_competition_results(session, club_id=1, year=2026, month=7)

        assert len(items) == 1
        item = items[0]
        assert item.event_id == 502
        assert item.series_kind == "championship"
        assert item.awards_points is False

    async def test_both_series_kinds_in_same_period(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Un mismo mes puede tener resultados de una copa y de un campeonato."""
        async with session_factory() as session:
            await self._seed_common(session)
            await create_race_series(
                session, series_id=1, season_year=2026, kind=RaceSeriesKind.cup
            )
            await create_race_series(
                session,
                series_id=2,
                season_year=2026,
                name="Campeonato Departamental de Ciclomontanismo",
                kind=RaceSeriesKind.championship,
            )
            await create_race_event(
                session,
                event_id=501,
                series_id=1,
                sequence_number=1,
                name="Copa Valle I",
                event_date=date(2026, 7, 10),
                created_by_user_id=10,
            )
            await create_race_event(
                session,
                event_id=502,
                series_id=2,
                sequence_number=1,
                name="Campeonato Departamental",
                event_date=date(2026, 7, 20),
                created_by_user_id=10,
            )
            await create_race_competitor(session, competitor_id=1441, athlete_id=144)
            await create_race_result(
                session,
                event_id=501,
                category_id=100,
                competitor_id=1441,
                athlete_id=144,
                position=3,
                points_awarded=32,
                created_by_user_id=10,
            )
            await create_race_result(
                session,
                event_id=502,
                category_id=100,
                competitor_id=1441,
                athlete_id=144,
                position=1,
                points_awarded=0,
                created_by_user_id=10,
            )
            await session.commit()

            items = await build_competition_results(session, club_id=1, year=2026, month=7)

        assert len(items) == 2
        by_event = {i.event_id: i for i in items}
        assert by_event[501].series_kind == "cup"
        assert by_event[501].awards_points is True
        assert by_event[502].series_kind == "championship"
        assert by_event[502].awards_points is False
