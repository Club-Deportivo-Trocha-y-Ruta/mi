"""Tests de servicio para ``app.services.race.season_panorama`` (PR3 + hotfix
"identidad de válida", ``~/.claude/plans/multicopa-identidad-valida.md`` bug #8).

Llama ``fetch_season_panorama`` directamente (sin pasar por el router HTTP) —
complementa ``tests/routers/test_season_panorama.py``, que cubre RBAC y el
contrato JSON completo pero NO ejercita el desglose ``by_series`` porque el
router todavía no lo mapea al schema (ver reporte del worker W2-BE3).

Cobertura de este archivo:
- Una sola copa en la temporada → ``by_series`` tiene 1 entrada y coincide
  exactamente con los totales de nivel superior (deprecados pero, con una
  sola copa, numéricamente idénticos — la regresión que este hotfix corrige
  es la suma ENTRE copas, no el valor de una copa sola).
- Dos copas en la misma temporada para el mismo atleta → cada copa queda
  aislada en su propia entrada de ``by_series`` (nunca se suman entre sí);
  el total deprecado de arriba sigue sumando ambas (comportamiento previo,
  sin cambios, documentado como deprecado en el schema).
- Orden de ``by_series`` por fecha de la primera válida corrida de cada
  copa (no por ``series_id`` ni por orden de creación).
- Un campeonato en la misma temporada nunca aparece en ``by_series``
  (spec 023 SC-004, sin cambios de comportamiento).
"""
from __future__ import annotations

from datetime import date
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
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import UserRole
from app.services.race.season_panorama import fetch_season_panorama

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

_TABLES_NEEDED = [
    "users",
    "clubs",
    "athletes",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    *AUDIT_TABLES,
]

_SEASON = 2026


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_NEEDED]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_base(session: AsyncSession) -> None:
    """club 1 + coach 10 + athlete 144 + categoría INF_B — mínimo compartido."""
    await create_club(session, club_id=1, name="Trocha y Ruta", code="tyr")
    await create_user(session, user_id=10, role=UserRole.coach)
    await create_athlete(
        session, athlete_id=144, first_name="Juan", last_name="Garcia",
        club_id=1, user_id=10,
    )
    await create_race_category(session, category_id=100, code="INF_B")
    await create_race_competitor(
        session, competitor_id=501, normalized_name="juan garcia",
        display_name="Juan Garcia", athlete_id=144,
    )


@pytest.mark.asyncio
async def test_single_cup_by_series_matches_top_level_totals(session_factory):
    """Con una sola copa, ``by_series[0]`` coincide con los totales deprecados."""
    async with session_factory() as s:
        await _seed_base(s)
        await create_race_series(s, series_id=1, season_year=_SEASON, name="Copa Valle 2026")
        await create_race_event(
            s, event_id=5, series_id=1, sequence_number=4,
            name="Válida IV", event_date=date(2026, 5, 17), location="Cali",
        )
        await create_race_event(
            s, event_id=6, series_id=1, sequence_number=5,
            name="Válida V", event_date=date(2026, 8, 1), location="Palmira",
        )
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=40,
        )
        await create_race_result(
            s, event_id=6, category_id=100, competitor_id=501, athlete_id=144,
            position=3, points_awarded=20,
        )
        await s.commit()

    async with session_factory() as s:
        rows = await fetch_season_panorama(s, season=_SEASON, club_id=1)

    assert len(rows) == 1
    row = rows[0]
    assert len(row.by_series) == 1
    series = row.by_series[0]
    assert series.series_id == 1
    assert series.series_name == "Copa Valle 2026"
    assert series.series_short_name is None
    assert series.series_kind == "cup"
    assert series.races == row.races_count == 2
    assert series.points == row.total_points == 60
    assert series.podiums == row.podiums == 2
    assert series.wins == row.wins == 1
    assert series.best_position == row.best_position == 1


@pytest.mark.asyncio
async def test_two_cups_same_season_never_cross_sum(session_factory):
    """Copa Valle + Copa Let's Go, mismo atleta — cada copa queda aislada."""
    async with session_factory() as s:
        await _seed_base(s)

        # Copa Valle: 2 válidas en mayo/agosto.
        await create_race_series(s, series_id=1, season_year=_SEASON, name="Copa Valle 2026")
        await create_race_event(
            s, event_id=5, series_id=1, sequence_number=4,
            name="Válida IV", event_date=date(2026, 5, 17), location="Cali",
        )
        await create_race_event(
            s, event_id=6, series_id=1, sequence_number=5,
            name="Válida V", event_date=date(2026, 8, 1), location="Palmira",
        )
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=40,
        )
        await create_race_result(
            s, event_id=6, category_id=100, competitor_id=501, athlete_id=144,
            position=3, points_awarded=20,
        )

        # Copa Let's Go: 1 válida en ENERO (antes que la Copa Valle) — para
        # verificar que el orden de by_series es por fecha, no por series_id.
        await create_race_series(
            s, series_id=2, season_year=_SEASON,
            name="Copa Let's Go Interdepartamental XCO",
        )
        await create_race_event(
            s, event_id=7, series_id=2, sequence_number=1,
            name="Válida I", event_date=date(2026, 1, 10), location="Alcalá",
        )
        await create_race_result(
            s, event_id=7, category_id=100, competitor_id=501, athlete_id=144,
            position=2, points_awarded=30,
        )
        await s.commit()

    async with session_factory() as s:
        rows = await fetch_season_panorama(s, season=_SEASON, club_id=1)

    assert len(rows) == 1
    row = rows[0]

    # Total deprecado de nivel superior: SIGUE sumando ambas copas
    # (comportamiento preexistente, documentado como deprecado — no es lo
    # que este hotfix corrige).
    assert row.races_count == 3
    assert row.total_points == 90

    # by_series: 2 entradas, cada una aislada a su propia copa.
    assert len(row.by_series) == 2
    by_id = {series.series_id: series for series in row.by_series}
    assert by_id[1].points == 60
    assert by_id[1].races == 2
    assert by_id[2].points == 30
    assert by_id[2].races == 1

    # Orden por fecha de la primera válida corrida → Let's Go (enero) antes
    # que Copa Valle (mayo), pese a tener series_id mayor.
    assert [series.series_id for series in row.by_series] == [2, 1]


@pytest.mark.asyncio
async def test_championship_never_appears_in_by_series(session_factory):
    """Un campeonato en la misma temporada no aparece en ``by_series`` ni
    altera los totales de la copa (spec 023 SC-004, sin cambios)."""
    async with session_factory() as s:
        await _seed_base(s)
        await create_race_series(s, series_id=1, season_year=_SEASON, name="Copa Valle 2026")
        await create_race_event(
            s, event_id=5, series_id=1, sequence_number=4,
            name="Válida IV", event_date=date(2026, 5, 17), location="Cali",
        )
        await create_race_result(
            s, event_id=5, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=40,
        )
        await s.commit()

        baseline_rows = await fetch_season_panorama(s, season=_SEASON, club_id=1)

    async with session_factory() as s:
        await create_race_series(
            s, series_id=900, season_year=_SEASON,
            name="Campeonato Departamental Valle 2026",
            kind=RaceSeriesKind.championship, level=RaceSeriesLevel.departmental,
        )
        await create_race_event(
            s, event_id=900, series_id=900, sequence_number=1,
            name="Campeonato Departamental", event_date=date(2026, 7, 18),
            location="Sevilla",
        )
        await create_race_result(
            s, event_id=900, category_id=100, competitor_id=501, athlete_id=144,
            position=1, points_awarded=100,
        )
        await s.commit()

    async with session_factory() as s:
        rows_after = await fetch_season_panorama(s, season=_SEASON, club_id=1)

    assert len(baseline_rows) == 1
    assert len(rows_after) == 1
    assert rows_after == baseline_rows
    assert len(rows_after[0].by_series) == 1
    assert rows_after[0].by_series[0].series_id == 1
