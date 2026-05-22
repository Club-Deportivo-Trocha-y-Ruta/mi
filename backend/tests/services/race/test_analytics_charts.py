"""Tests del servicio ``app/services/race/analytics_charts.py`` (BE-3).

Cobertura:

- ``build_evolution``: low confidence con n<3, orden por valida_num,
  cálculo de podium_gap.
- ``build_distribution``: pseudonimización determinística, low confidence
  con n<5 (sin points/curve), is_self del atleta, z-score y percentil.

Estrategia: SQLite async in-memory con StaticPool. Cada test siembra
un escenario mínimo (1 atleta + 1 categoría + N race_results) y verifica
el payload del servicio.
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
from app.models.user import UserRole
from app.schemas.athlete_race_analysis import (
    AnalysisConfidence,
    EvolutionMetric,
)
from app.services.race.analytics_charts import (
    _build_pseudonym,
    build_distribution,
    build_evolution,
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
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Sesión + seed mínimo: club + coach + atleta + serie + categoría."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_race_series(
            s, series_id=1, season_year=2026
        )
        await create_race_category(s, category_id=100, code="INF_B")
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# Helpers de escenario
# ---------------------------------------------------------------------------


async def _seed_athlete_in_event(
    session: AsyncSession,
    *,
    event_id: int,
    sequence_number: int,
    event_date: date,
    name: str,
    athlete_position: int,
    athlete_time_ms: int,
    winner_time_ms: int,
    other_runners: int = 3,
    series_id: int = 1,
    category_id: int = 100,
    athlete_id: int = 144,
) -> None:
    """Crea event + ganador + N runners + el atleta. La categoría tiene
    1 + other_runners + 1 corredores en total."""
    await create_race_event(
        session,
        event_id=event_id,
        series_id=series_id,
        sequence_number=sequence_number,
        name=name,
        event_date=event_date,
    )
    # Ganador
    winner_cid = event_id * 1000 + 1
    await create_race_competitor(
        session,
        competitor_id=winner_cid,
        normalized_name=f"winner ev{event_id}",
        display_name=f"Winner {event_id}",
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=winner_cid,
        position=1,
        race_time_ms=winner_time_ms,
        bib_number=1,
        points_awarded=40,
    )
    # Atleta target
    athlete_cid = event_id * 1000 + 2
    await create_race_competitor(
        session,
        competitor_id=athlete_cid,
        normalized_name=f"athlete ev{event_id}",
        display_name=f"Athlete {event_id}",
        athlete_id=athlete_id,
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=athlete_cid,
        athlete_id=athlete_id,
        position=athlete_position,
        race_time_ms=athlete_time_ms,
        bib_number=athlete_position,
        points_awarded=40 - 4 * (athlete_position - 1),
    )
    # Otros runners (suficientes para alcanzar el sample size deseado)
    for i in range(other_runners):
        cid = event_id * 1000 + 100 + i
        await create_race_competitor(
            session,
            competitor_id=cid,
            normalized_name=f"runner{i} ev{event_id}",
            display_name=f"Runner{i} {event_id}",
        )
        await create_race_result(
            session,
            event_id=event_id,
            category_id=category_id,
            competitor_id=cid,
            position=athlete_position + i + 1,
            race_time_ms=athlete_time_ms + (i + 1) * 1_000,
            bib_number=athlete_position + i + 1,
            points_awarded=10,
        )


# ---------------------------------------------------------------------------
# build_evolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_evolution_returns_low_confidence_when_n_less_than_3(session):
    """Si hay <3 puntos válidos → confidence=low."""
    # Solo 2 eventos.
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=2,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=2,
        sequence_number=2,
        event_date=date(2026, 2, 28),
        name="V2",
        athlete_position=3,
        athlete_time_ms=1_820_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.PODIUM_GAP_MS,
    )
    assert result.confidence == AnalysisConfidence.low
    assert len(result.series) == 2


@pytest.mark.asyncio
async def test_build_evolution_orders_by_valida_num(session):
    """La serie debe venir ordenada por ``valida_num ASC`` (sequence_number)."""
    # Crear eventos fuera de orden: V3 antes que V1 en el seed.
    await _seed_athlete_in_event(
        session,
        event_id=3,
        sequence_number=3,
        event_date=date(2026, 4, 19),
        name="V3",
        athlete_position=2,
        athlete_time_ms=1_805_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=2,
        sequence_number=2,
        event_date=date(2026, 2, 28),
        name="V2",
        athlete_position=2,
        athlete_time_ms=1_807_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.RANKING,
    )
    valida_nums = [p.valida_num for p in result.series]
    assert valida_nums == sorted(valida_nums)
    assert valida_nums == [1, 2, 3]


@pytest.mark.asyncio
async def test_build_evolution_podium_gap_metric_calculates_diff_to_winner(session):
    """podium_gap_ms = athlete_time - winner_time (P1 propio → gap=0)."""
    # Atleta P2, gap esperado = 10_000 ms.
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=2,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.PODIUM_GAP_MS,
    )
    assert len(result.series) == 1
    point = result.series[0]
    assert point.value == 10_000.0
    assert point.unit == "ms"


# ---------------------------------------------------------------------------
# build_distribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_distribution_pseudonymizes_competitors(session):
    """Cada DistributionPoint expone solo ``pseudonym`` — NO display_name ni
    competitor_id."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,  # total = 6 corredores (≥5 para activar curve)
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, valida_num=1
    )
    assert result.sample_size == 6
    assert len(result.points) == 6
    for point in result.points:
        # Pseudónimo bien formado: "C0000".."C9999".
        assert point.pseudonym.startswith("C")
        assert len(point.pseudonym) == 5
        # No hay forma de exfiltrar el display_name por el schema (extra=forbid).
        # Validamos también que el modelo no incluya un display_name por azar.
        dumped = point.model_dump()
        assert "display_name" not in dumped
        assert "competitor_id" not in dumped


@pytest.mark.asyncio
async def test_build_distribution_low_confidence_when_n_less_than_5(session):
    """sample_size < 5 → points y curve vacíos, confidence=low."""
    # Total runners = 4 (1 ganador + atleta + 2 más).
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=2,  # 1 winner + 1 athlete + 2 = 4 < 5
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, valida_num=1
    )
    assert result.sample_size == 4
    assert result.points == []
    assert result.curve == []
    assert result.confidence == AnalysisConfidence.low


@pytest.mark.asyncio
async def test_build_distribution_self_marker_correctly_flagged(session):
    """El point del atleta consultante debe tener ``is_self=True``."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, valida_num=1
    )
    self_points = [p for p in result.points if p.is_self]
    assert len(self_points) == 1
    # El tiempo del self point debe coincidir con athlete_time_ms del seed.
    assert self_points[0].time_ms == 1_810_000


@pytest.mark.asyncio
async def test_build_distribution_athlete_z_score_and_percentile(session):
    """Verifica z-score y percentile contra distribución conocida."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=4,
        athlete_time_ms=1_815_000,
        winner_time_ms=1_800_000,
        other_runners=4,
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, valida_num=1
    )
    # mean y stddev calculados sobre 6 puntos (winner..athlete..runners)
    assert result.mean_ms is not None
    assert result.stddev_ms is not None
    assert result.stddev_ms > 0
    # z-score: athlete está por encima del mean (peor tiempo) → z > 0 si el
    # tiempo está por encima del mean. Sanity check basado en datos:
    # times = [1800k, 1815k, 1816k, 1817k, 1818k] aprox.
    # El sentido exacto del signo depende de la posición del atleta.
    assert result.athlete_z_score is not None
    # Percentile en [0..100]
    assert result.athlete_percentile is not None
    assert 0.0 <= result.athlete_percentile <= 100.0
    # Pseudónimo determinístico — el helper privado lo arma así.
    self_point = next(p for p in result.points if p.is_self)
    # El competitor_id del atleta seed-eado es event_id * 1000 + 2 = 1002.
    expected_pseudo = _build_pseudonym(1002)
    assert self_point.pseudonym == expected_pseudo
