"""Fixtures reutilizables para tests de "grupos de comparación" (feature 039).

Construye, sobre una ``AsyncSession`` real (aiosqlite in-memory — mismo patrón
que ``tests/services/race/test_analytics_charts.py``), un único atleta
ficticio ligado a un único ``RaceCompetitor`` que participa en:

- Una copa (``kind=cup``) de 5 válidas con un P1 fijo por válida (para que el
  gap al ganador sea siempre calculable) — escenario **(a)**.
- Un campeonato departamental (``kind=championship``, ``level=departmental``,
  1 evento, ``sequence_number=1``, sede "Ginebra").
- Un campeonato nacional (``kind=championship``, ``level=national``, 1 evento,
  sede "Pereira").

Variantes:

- **(b)** ``race_groups_two_cups`` — agrega una segunda copa ("Liga
  Departamental", 3 rondas) cuya Válida I es **anterior** a la Válida I de la
  copa principal. La fecha se eligió a propósito antes de la copa principal
  para que cualquier test de "orden por válida más temprana" (T016/T042) no
  pueda aprobar por casualidad ordenando por ``series_id`` o por orden de
  inserción.
- **(c)** ``race_groups_dnf_championship`` — el resultado del atleta en el
  campeonato nacional queda en ``status=dnf`` (posición/tiempo nulos).

Todos los nombres (atleta, rivales, club) son ficticios — no corresponden a
ningún dato real del club (CLAUDE.md, Ley 1581).

Registro: ``tests/conftest.py`` declara ``pytest_plugins =
["tests.fixtures.race_groups"]`` para que las fixtures de este módulo estén
disponibles en toda la suite sin necesidad de importarlas explícitamente.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import AsyncGenerator, Optional

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_result import ResultStatus
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import UserRole

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
# IDs y datos ficticios del escenario
# ---------------------------------------------------------------------------

SEASON = 2026
CLUB_ID = 1
COACH_USER_ID = 910

ATHLETE_ID = 850
ATHLETE_USER_ID = 1850
ATHLETE_COMPETITOR_ID = 8500
ATHLETE_DISPLAY_NAME = "Camila Ficticia Salazar"

CATEGORY_ID = 850
CATEGORY_CODE = "INF_A_G039"
CATEGORY_LABEL = "Infantil A Ficticio"

# Rivales — mismos 3 competidores reutilizados en todas las válidas y
# campeonatos, así siempre hay un P1 para calcular el gap.
WINNER_COMPETITOR_ID = 8501
FILLER1_COMPETITOR_ID = 8502
FILLER2_COMPETITOR_ID = 8503

CUP_SERIES_ID = 6001
CUP_SERIES_NAME = "Copa Valle de Ciclomontañismo"
CUP_LOCATION = "Sevilla"

SECOND_CUP_SERIES_ID = 6002
SECOND_CUP_SERIES_NAME = "Liga Departamental"
SECOND_CUP_LOCATION = "Buga"

DEPARTMENTAL_SERIES_ID = 6011
DEPARTMENTAL_SERIES_NAME = "Campeonato Departamental de Ciclomontañismo"
DEPARTMENTAL_LOCATION = "Ginebra"

NATIONAL_SERIES_ID = 6012
NATIONAL_SERIES_NAME = "Campeonato Nacional de Ciclomontañismo"
NATIONAL_LOCATION = "Pereira"


# ---------------------------------------------------------------------------
# Dataclass de salida
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RaceGroupsScenario:
    """IDs (y la sesión ya sembrada) de un escenario de comparison groups.

    ``session`` queda commiteada y lista para pasar directamente a
    funciones del servicio bajo prueba (``athlete_progression``,
    ``build_evolution``, etc.).
    """

    session: AsyncSession

    athlete_id: int
    competitor_id: int
    category_id: int
    season: int

    cup_series_id: int
    cup_series_name: str
    cup_event_ids: list[int]

    departmental_series_id: int
    departmental_series_name: str
    departmental_event_id: int

    national_series_id: int
    national_series_name: str
    national_event_id: int

    second_cup_series_id: Optional[int] = None
    second_cup_series_name: Optional[str] = None
    second_cup_event_ids: Optional[list[int]] = None


# ---------------------------------------------------------------------------
# Helpers de siembra (funciones planas — sin decorar como fixtures, igual
# convención que tests/fixtures/race_history_fixtures.py)
# ---------------------------------------------------------------------------


async def _seed_actors(session: AsyncSession) -> None:
    """Club, coach, atleta ficticio, categoría y los 4 competidores base."""
    await create_club(session, club_id=CLUB_ID, name="Club Ficticio de Prueba", code="cft-039")
    await create_user(session, user_id=COACH_USER_ID, role=UserRole.coach)
    await create_athlete(
        session,
        athlete_id=ATHLETE_ID,
        first_name="Camila Ficticia",
        last_name="Salazar",
        birth_date=date(2013, 4, 12),
        club_id=CLUB_ID,
        user_id=ATHLETE_USER_ID,
        created_by=COACH_USER_ID,
    )
    await create_race_category(
        session, category_id=CATEGORY_ID, code=CATEGORY_CODE, label=CATEGORY_LABEL
    )
    await create_race_competitor(
        session,
        competitor_id=ATHLETE_COMPETITOR_ID,
        normalized_name="camila ficticia salazar",
        display_name=ATHLETE_DISPLAY_NAME,
        athlete_id=ATHLETE_ID,
    )
    await create_race_competitor(
        session,
        competitor_id=WINNER_COMPETITOR_ID,
        normalized_name="rival ficticio lider",
        display_name="Rival Ficticio Líder",
        club_text="Club Rival Ficticio",
    )
    await create_race_competitor(
        session,
        competitor_id=FILLER1_COMPETITOR_ID,
        normalized_name="rival ficticio dos",
        display_name="Rival Ficticio Dos",
        club_text="Club Rival Ficticio",
    )
    await create_race_competitor(
        session,
        competitor_id=FILLER2_COMPETITOR_ID,
        normalized_name="rival ficticio tres",
        display_name="Rival Ficticio Tres",
        club_text="Club Rival Ficticio",
    )


async def _seed_cup_series(
    session: AsyncSession,
    *,
    series_id: int,
    name: str,
    num_rounds: int,
    round_dates: list[date],
    location: str,
    athlete_position: int = 2,
) -> list[int]:
    """Crea una serie ``cup`` con ``num_rounds`` válidas.

    Cada válida tiene el mismo pelotón de 4: ``WINNER`` (P1, fijo — así el
    gap al ganador siempre es calculable), el atleta en ``athlete_position``
    y dos rellenos ocupando las posiciones restantes.
    """
    assert len(round_dates) == num_rounds
    await create_race_series(
        session, series_id=series_id, season_year=SEASON, name=name, kind=RaceSeriesKind.cup
    )
    event_ids: list[int] = []
    filler_positions = [p for p in (2, 3, 4) if p != athlete_position][:2]
    for i, event_date in enumerate(round_dates, start=1):
        event_id = series_id * 10 + i
        await create_race_event(
            session,
            event_id=event_id,
            series_id=series_id,
            sequence_number=i,
            name=f"{name} — Válida {i}",
            event_date=event_date,
            location=location,
            created_by_user_id=COACH_USER_ID,
        )
        winner_time_ms = 1_700_000 + i * 2_000
        await create_race_result(
            session,
            event_id=event_id,
            category_id=CATEGORY_ID,
            competitor_id=WINNER_COMPETITOR_ID,
            position=1,
            race_time_ms=winner_time_ms,
            bib_number=1,
            points_awarded=40,
            created_by_user_id=COACH_USER_ID,
        )
        await create_race_result(
            session,
            event_id=event_id,
            category_id=CATEGORY_ID,
            competitor_id=ATHLETE_COMPETITOR_ID,
            athlete_id=ATHLETE_ID,
            position=athlete_position,
            race_time_ms=winner_time_ms + 15_000 * athlete_position,
            bib_number=athlete_position,
            points_awarded=max(40 - 4 * (athlete_position - 1), 4),
            created_by_user_id=COACH_USER_ID,
        )
        for filler_competitor_id, position in zip(
            (FILLER1_COMPETITOR_ID, FILLER2_COMPETITOR_ID), filler_positions
        ):
            await create_race_result(
                session,
                event_id=event_id,
                category_id=CATEGORY_ID,
                competitor_id=filler_competitor_id,
                position=position,
                race_time_ms=winner_time_ms + 15_000 * position,
                bib_number=position,
                points_awarded=max(40 - 4 * (position - 1), 4),
                created_by_user_id=COACH_USER_ID,
            )
        event_ids.append(event_id)
    return event_ids


async def _seed_championship_series(
    session: AsyncSession,
    *,
    series_id: int,
    name: str,
    level: RaceSeriesLevel,
    event_date: date,
    location: str,
    athlete_position: int = 4,
    dnf: bool = False,
) -> int:
    """Crea una serie ``championship`` con un único evento (INV-2)."""
    await create_race_series(
        session,
        series_id=series_id,
        season_year=SEASON,
        name=name,
        kind=RaceSeriesKind.championship,
        level=level,
    )
    event_id = series_id * 10 + 1
    await create_race_event(
        session,
        event_id=event_id,
        series_id=series_id,
        sequence_number=1,
        name=f"{name} {SEASON}",
        event_date=event_date,
        location=location,
        created_by_user_id=COACH_USER_ID,
    )
    winner_time_ms = 1_900_000
    await create_race_result(
        session,
        event_id=event_id,
        category_id=CATEGORY_ID,
        competitor_id=WINNER_COMPETITOR_ID,
        position=1,
        race_time_ms=winner_time_ms,
        bib_number=1,
        points_awarded=0,
        created_by_user_id=COACH_USER_ID,
    )
    for filler_competitor_id, position in (
        (FILLER1_COMPETITOR_ID, 2),
        (FILLER2_COMPETITOR_ID, 3),
    ):
        await create_race_result(
            session,
            event_id=event_id,
            category_id=CATEGORY_ID,
            competitor_id=filler_competitor_id,
            position=position,
            race_time_ms=winner_time_ms + 20_000 * position,
            bib_number=position,
            points_awarded=0,
            created_by_user_id=COACH_USER_ID,
        )
    if dnf:
        await create_race_result(
            session,
            event_id=event_id,
            category_id=CATEGORY_ID,
            competitor_id=ATHLETE_COMPETITOR_ID,
            athlete_id=ATHLETE_ID,
            position=None,
            status=ResultStatus.DNF,
            race_time_ms=None,
            bib_number=athlete_position,
            points_awarded=0,
            created_by_user_id=COACH_USER_ID,
        )
    else:
        await create_race_result(
            session,
            event_id=event_id,
            category_id=CATEGORY_ID,
            competitor_id=ATHLETE_COMPETITOR_ID,
            athlete_id=ATHLETE_ID,
            position=athlete_position,
            race_time_ms=winner_time_ms + 20_000 * athlete_position,
            bib_number=athlete_position,
            points_awarded=0,
            created_by_user_id=COACH_USER_ID,
        )
    return event_id


async def seed_base_season(
    session: AsyncSession, *, dnf_championship: bool = False
) -> RaceGroupsScenario:
    """Escenario **(a)**: copa de 5 válidas + Cto. Departamental + Cto. Nacional.

    ``dnf_championship=True`` aplica el escenario **(c)** — el resultado del
    atleta en el campeonato *nacional* queda en ``dnf`` (el departamental
    siempre termina la prueba).
    """
    await _seed_actors(session)

    cup_event_ids = await _seed_cup_series(
        session,
        series_id=CUP_SERIES_ID,
        name=CUP_SERIES_NAME,
        num_rounds=5,
        round_dates=[date(SEASON, m, 15) for m in range(1, 6)],
        location=CUP_LOCATION,
    )
    departmental_event_id = await _seed_championship_series(
        session,
        series_id=DEPARTMENTAL_SERIES_ID,
        name=DEPARTMENTAL_SERIES_NAME,
        level=RaceSeriesLevel.departmental,
        event_date=date(SEASON, 6, 20),
        location=DEPARTMENTAL_LOCATION,
        dnf=False,
    )
    national_event_id = await _seed_championship_series(
        session,
        series_id=NATIONAL_SERIES_ID,
        name=NATIONAL_SERIES_NAME,
        level=RaceSeriesLevel.national,
        event_date=date(SEASON, 8, 22),
        location=NATIONAL_LOCATION,
        dnf=dnf_championship,
    )

    await session.commit()

    return RaceGroupsScenario(
        session=session,
        athlete_id=ATHLETE_ID,
        competitor_id=ATHLETE_COMPETITOR_ID,
        category_id=CATEGORY_ID,
        season=SEASON,
        cup_series_id=CUP_SERIES_ID,
        cup_series_name=CUP_SERIES_NAME,
        cup_event_ids=cup_event_ids,
        departmental_series_id=DEPARTMENTAL_SERIES_ID,
        departmental_series_name=DEPARTMENTAL_SERIES_NAME,
        departmental_event_id=departmental_event_id,
        national_series_id=NATIONAL_SERIES_ID,
        national_series_name=NATIONAL_SERIES_NAME,
        national_event_id=national_event_id,
    )


async def seed_two_cups_season(session: AsyncSession) -> RaceGroupsScenario:
    """Escenario **(b)**: agrega "Liga Departamental" (3 rondas) al (a).

    Las 3 rondas de la segunda copa corren **antes** que la Válida I de la
    copa principal (enero) — a propósito, para que un test de "orden por
    válida más temprana" no pueda aprobar solo por ordenar por ``series_id``
    o por orden de inserción.
    """
    scenario = await seed_base_season(session, dnf_championship=False)

    second_cup_event_ids = await _seed_cup_series(
        session,
        series_id=SECOND_CUP_SERIES_ID,
        name=SECOND_CUP_SERIES_NAME,
        num_rounds=3,
        round_dates=[date(SEASON, 1, 5), date(SEASON, 2, 5), date(SEASON, 3, 5)],
        location=SECOND_CUP_LOCATION,
    )
    await session.commit()

    return replace(
        scenario,
        second_cup_series_id=SECOND_CUP_SERIES_ID,
        second_cup_series_name=SECOND_CUP_SERIES_NAME,
        second_cup_event_ids=second_cup_event_ids,
    )


# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "athletes",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
)


@pytest_asyncio.fixture
async def race_groups_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Engine SQLite in-memory con solo las tablas que este módulo necesita."""
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
async def race_groups_session_factory(
    race_groups_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(race_groups_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def race_groups_base_season(
    race_groups_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[RaceGroupsScenario, None]:
    """(a) copa 5 válidas + Cto. Departamental + Cto. Nacional (ambos finished)."""
    async with race_groups_session_factory() as session:
        yield await seed_base_season(session)


@pytest_asyncio.fixture
async def race_groups_two_cups(
    race_groups_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[RaceGroupsScenario, None]:
    """(b) variante con una segunda copa ("Liga Departamental", 3 rondas)."""
    async with race_groups_session_factory() as session:
        yield await seed_two_cups_season(session)


@pytest_asyncio.fixture
async def race_groups_dnf_championship(
    race_groups_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[RaceGroupsScenario, None]:
    """(c) el campeonato nacional del atleta queda en ``status=dnf``."""
    async with race_groups_session_factory() as session:
        yield await seed_base_season(session, dnf_championship=True)


__all__ = [
    "RaceGroupsScenario",
    "seed_base_season",
    "seed_two_cups_season",
    "race_groups_engine",
    "race_groups_session_factory",
    "race_groups_base_season",
    "race_groups_two_cups",
    "race_groups_dnf_championship",
]
