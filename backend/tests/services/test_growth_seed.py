"""Tests del seed offline de datos de referencia CDC LMS (app.seed_growth_data).

Cubre el contrato C4 (LMS seeding) del feature 003:
  - Sembrar desde un CSV fixture pequeño puebla growth_reference_lms.
  - Las seis combinaciones (indicator, sex) quedan no vacías cubriendo 24–240.5.
  - Un lookup (age, sex) devuelve los L/M/S del CDC y un z-score esperado.
  - Reejecutar el seed es un no-op (mismo conteo de filas; upsert idempotente).

Estrategia: SQLite async in-memory (sin red, sin MySQL). El upsert del seed es
dialect-aware y usa ON CONFLICT en SQLite.
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.growth import GrowthIndicator, GrowthReferenceLms
from app.seed_growth_data import (
    _parse_csv_content,
    bulk_insert_lms,
)
from app.services.growth import calculate_z_score, get_lms_params

# Fila real del CDC: niño masculino, height_for_age, 24 meses.
# (tomada de statage.csv vendorizado)
_CDC_MALE_HEIGHT_24 = (0.941523967, 86.45220101, 0.040321528)

# CSV fixture: ambos sexos, extremos del rango (24.0 y 240.5) por indicador.
# Solo Sex/Agemos/L/M/S se consumen; columnas extra se ignoran.
_FIXTURE_HEIGHT = (
    "Sex,Agemos,L,M,S,P50\n"
    "1,24,0.941523967,86.45220101,0.040321528,86.4\n"
    "1,240.5,0.9,175.0,0.045,175.0\n"
    "2,24,1.0,85.0,0.041,85.0\n"
    "2,240.5,0.8,163.0,0.043,163.0\n"
    "1,12,1.0,76.0,0.04,76.0\n"  # fuera de rango (24-240.5) → descartada
)
_FIXTURE_BMI = (
    "Sex,Agemos,L,M,S\n"
    "1,24,-2.0,16.5,0.08\n"
    "1,240.5,-1.5,21.0,0.13\n"
    "2,24,-1.9,16.2,0.08\n"
    "2,240.5,-1.4,20.5,0.14\n"
)
_FIXTURE_WEIGHT = (
    "Sex,Agemos,L,M,S\n"
    "1,24,-0.2,12.6,0.10\n"
    "1,240.5,-1.0,62.0,0.16\n"
    "2,24,-0.3,12.1,0.11\n"
    "2,240.5,-1.1,54.0,0.17\n"
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    table = Base.metadata.tables["growth_reference_lms"]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[table]))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_fixture(session: AsyncSession) -> int:
    total = 0
    for content, indicator in (
        (_FIXTURE_HEIGHT, "height_for_age"),
        (_FIXTURE_BMI, "bmi_for_age"),
        (_FIXTURE_WEIGHT, "weight_for_age"),
    ):
        rows = _parse_csv_content(content, indicator)
        total += await bulk_insert_lms(session, rows)
    await session.commit()
    return total


@pytest.mark.asyncio
async def test_seed_populates_table(session_factory) -> None:
    async with session_factory() as session:
        inserted = await _seed_fixture(session)
        # 4 filas válidas por indicador (la fila a 12 meses se descarta) × 3
        assert inserted == 12

        count = await session.scalar(
            select(func.count()).select_from(GrowthReferenceLms)
        )
        assert count == 12


@pytest.mark.asyncio
async def test_all_six_groups_non_empty_over_range(session_factory) -> None:
    async with session_factory() as session:
        await _seed_fixture(session)

        result = await session.execute(
            select(
                GrowthReferenceLms.indicator,
                GrowthReferenceLms.sex,
                func.count(),
                func.min(GrowthReferenceLms.age_months),
                func.max(GrowthReferenceLms.age_months),
            ).group_by(GrowthReferenceLms.indicator, GrowthReferenceLms.sex)
        )
        groups = result.all()

        # 3 indicadores × 2 sexos = 6 grupos, todos no vacíos
        assert len(groups) == 6
        for _indicator, _sex, cnt, age_min, age_max in groups:
            assert cnt >= 1
            assert float(age_min) >= 24.0
            assert float(age_max) <= 240.5
            # cada grupo cubre ambos extremos del rango CDC
            assert float(age_min) == 24.0
            assert float(age_max) == 240.5


@pytest.mark.asyncio
async def test_known_lookup_and_zscore(session_factory) -> None:
    async with session_factory() as session:
        await _seed_fixture(session)

        params = await get_lms_params(
            session, GrowthIndicator.height_for_age, "M", 24.0
        )
        assert params is not None
        L, M, S = params
        exp_L, exp_M, exp_S = _CDC_MALE_HEIGHT_24
        assert L == pytest.approx(exp_L)
        assert M == pytest.approx(exp_M)
        assert S == pytest.approx(exp_S)

        # Un valor igual a la mediana M debe dar z ≈ 0
        z_at_median = calculate_z_score(exp_M, L, M, S)
        assert z_at_median == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_reseed_is_noop(session_factory) -> None:
    async with session_factory() as session:
        await _seed_fixture(session)
        first = await session.scalar(
            select(func.count()).select_from(GrowthReferenceLms)
        )
        # Reejecutar: mismo conteo (upsert idempotente por constraint única)
        await _seed_fixture(session)
        second = await session.scalar(
            select(func.count()).select_from(GrowthReferenceLms)
        )
        assert first == second == 12
