"""Tests de ``app.services.reference_skinfolds.reference_context`` (feature 046, T011).

Estrategia: SQLite async in-memory. Se siembran dos bandas sintéticas de
``growth_reference_lms`` con fuente ``FUPRECOL`` (dos edades, un solo sexo)
para verificar la interpolación LMS existente y los casos ``unavailable``:
fuera de rango de edad (108–216 meses), sitio omitido (``None``) y tabla sin
filas sembradas. No hay datos de deportistas reales — todo es sintético.
"""
from __future__ import annotations

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
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.services.growth import calculate_z_score, z_to_percentile
from app.services.reference_skinfolds import reference_context

# Dos bandas sintéticas (114 y 126 meses = 9.5 y 10.5 años), sexo M, para
# tríceps y subescapular. Valores L/M/S inventados pero con forma plausible
# (S pequeño y positivo, L cerca de 0).
_BANDS: list[dict[str, object]] = [
    {"indicator": GrowthIndicator.triceps_skinfold_for_age, "sex": "M", "age_months": 114.0, "L": -0.3, "M": 10.0, "S": 0.37},
    {"indicator": GrowthIndicator.triceps_skinfold_for_age, "sex": "M", "age_months": 126.0, "L": -0.31, "M": 11.0, "S": 0.39},
    {"indicator": GrowthIndicator.subscapular_skinfold_for_age, "sex": "M", "age_months": 114.0, "L": -0.5, "M": 6.0, "S": 0.4},
    {"indicator": GrowthIndicator.subscapular_skinfold_for_age, "sex": "M", "age_months": 126.0, "L": -0.51, "M": 6.5, "S": 0.42},
]


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


async def _seed_bands(session: AsyncSession) -> None:
    for band in _BANDS:
        session.add(
            GrowthReferenceLms(
                source=GrowthSource.FUPRECOL,
                indicator=band["indicator"],
                sex=band["sex"],
                age_months=band["age_months"],
                L=band["L"],
                M=band["M"],
                S=band["S"],
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_interpolates_between_seeded_bands(session_factory) -> None:
    async with session_factory() as session:
        await _seed_bands(session)

        # Punto medio exacto (120 meses) entre las dos bandas sembradas.
        result = await reference_context(
            session, sex="M", age_months=120.0, triceps_mm=10.5, subscapular_mm=6.25
        )

        # Interpolación lineal a t=0.5.
        exp_L = (-0.3 + -0.31) / 2
        exp_M = (10.0 + 11.0) / 2
        exp_S = (0.37 + 0.39) / 2
        exp_z = calculate_z_score(10.5, exp_L, exp_M, exp_S)
        exp_pct = z_to_percentile(exp_z)

        assert result["triceps"]["percentile"] == pytest.approx(exp_pct)
        assert result["triceps"]["code"] == "normal"
        assert result["subscapular"]["code"] in {"low", "normal", "high", "low_extreme", "high_extreme"}


@pytest.mark.asyncio
async def test_classification_bands() -> None:
    # Percentil exacto vía z-score de referencia; se prueban los límites de
    # clasificación directamente contra la función pura de percentil.
    from app.services.reference_skinfolds import _classify

    assert _classify(4.9) == "low_extreme"
    assert _classify(5.0) == "low"
    assert _classify(9.9) == "low"
    assert _classify(10.0) == "normal"
    assert _classify(84.9) == "normal"
    assert _classify(85.0) == "high"
    assert _classify(94.9) == "high"
    assert _classify(95.0) == "high_extreme"


@pytest.mark.asyncio
async def test_unavailable_when_site_declined(session_factory) -> None:
    async with session_factory() as session:
        await _seed_bands(session)

        result = await reference_context(
            session, sex="M", age_months=120.0, triceps_mm=None, subscapular_mm=None
        )

        assert result["triceps"] == {"percentile": None, "code": "unavailable"}
        assert result["subscapular"] == {"percentile": None, "code": "unavailable"}


@pytest.mark.asyncio
async def test_unavailable_outside_age_range(session_factory) -> None:
    async with session_factory() as session:
        await _seed_bands(session)

        below = await reference_context(
            session, sex="M", age_months=107.9, triceps_mm=10.0, subscapular_mm=6.0
        )
        above = await reference_context(
            session, sex="M", age_months=216.1, triceps_mm=10.0, subscapular_mm=6.0
        )

        assert below["triceps"]["code"] == "unavailable"
        assert below["subscapular"]["code"] == "unavailable"
        assert above["triceps"]["code"] == "unavailable"
        assert above["subscapular"]["code"] == "unavailable"


@pytest.mark.asyncio
async def test_unavailable_when_no_rows_seeded(session_factory) -> None:
    async with session_factory() as session:
        # No se siembra nada: la tabla growth_reference_lms está vacía.
        result = await reference_context(
            session, sex="M", age_months=120.0, triceps_mm=10.0, subscapular_mm=6.0
        )

        assert result["triceps"] == {"percentile": None, "code": "unavailable"}
        assert result["subscapular"] == {"percentile": None, "code": "unavailable"}


@pytest.mark.asyncio
async def test_boundary_ages_are_available(session_factory) -> None:
    async with session_factory() as session:
        await _seed_bands(session)

        at_min = await reference_context(
            session, sex="M", age_months=108.0, triceps_mm=10.0, subscapular_mm=6.0
        )
        at_max = await reference_context(
            session, sex="M", age_months=216.0, triceps_mm=10.0, subscapular_mm=6.0
        )

        assert at_min["triceps"]["code"] != "unavailable"
        assert at_max["triceps"]["code"] != "unavailable"
