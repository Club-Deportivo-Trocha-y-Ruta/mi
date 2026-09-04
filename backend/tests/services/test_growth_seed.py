"""Tests del seed offline de datos de referencia CDC/OMS LMS (app.seed_growth_data).

Cubre el contrato C4 (LMS seeding) del feature 003, para el CDC (histórico):
  - Sembrar desde un CSV fixture pequeño puebla growth_reference_lms.
  - Las seis combinaciones (indicator, sex) quedan no vacías cubriendo 24–240.5.
  - Un lookup (age, sex) devuelve los L/M/S del CDC y un z-score esperado.
  - Reejecutar el seed es un no-op (mismo conteo de filas; upsert idempotente).

Y el contrato ``who-lms-seed.md`` del feature 040 (T016), para la OMS —
referencia única a partir de este feature:
  - Conteo de filas por (indicator, sex): 168/168/60.
  - Paridad exacta de 6 tripletas (indicator, sex, age) L/M/S contra
    ``frontend/src/data/growth-reference-who.json`` (6 decimales).
  - Reejecutar el seed OMS es un no-op (mismo conteo de filas).

Estrategia: SQLite async in-memory (sin red, sin MySQL). El upsert del seed es
dialect-aware y usa ON CONFLICT en SQLite. Los CSV de la OMS son los archivos
reales vendorizados en ``app/data/who_lms/`` (no fixtures) — el objetivo es
verificar el contrato del seed real, no solo el parser.
"""
from __future__ import annotations

import json
from pathlib import Path
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
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.seed_growth_data import (
    WHO_DATA_DIR,
    WHO_SOURCES,
    _parse_csv_content,
    bulk_insert_lms,
    parse_who_csv_file,
)
from app.services.growth import calculate_z_score, get_lms_params

# Ruta al JSON fuente del cliente — misma tabla que consume el navegador.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_WHO_JSON_PATH = (
    _REPO_ROOT / "frontend" / "src" / "data" / "growth-reference-who.json"
)

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


# ---------------------------------------------------------------------------
# OMS 2007 — feature 040, T016. Usa los CSV reales vendorizados en
# app/data/who_lms/ (no fixtures): el contrato exige que el seed real, tal
# como corre en producción, cumpla los conteos y la paridad con el JSON.
# ---------------------------------------------------------------------------


async def _seed_who(session: AsyncSession) -> int:
    total = 0
    for source_info in WHO_SOURCES:
        csv_path = WHO_DATA_DIR / source_info["filename"]
        rows = parse_who_csv_file(csv_path, source_info["indicator"])
        total += await bulk_insert_lms(session, rows)
    await session.commit()
    return total


def _indicator_value(indicator: object) -> str:
    """Normaliza una columna Enum leída por SQLAlchemy a su valor str."""
    return indicator.value if hasattr(indicator, "value") else str(indicator)


@pytest.mark.asyncio
async def test_who_seed_row_counts_per_indicator_and_sex(session_factory) -> None:
    async with session_factory() as session:
        inserted = await _seed_who(session)
        # 168 (talla) + 168 (IMC) + 60 (peso), por cada uno de los 2 sexos.
        assert inserted == (168 + 168 + 60) * 2

        result = await session.execute(
            select(
                GrowthReferenceLms.indicator,
                GrowthReferenceLms.sex,
                func.count(),
            )
            .where(GrowthReferenceLms.source == GrowthSource.WHO)
            .group_by(GrowthReferenceLms.indicator, GrowthReferenceLms.sex)
        )
        counts = {
            (_indicator_value(indicator), sex): cnt
            for indicator, sex, cnt in result.all()
        }

        for sex in ("M", "F"):
            assert counts[("height_for_age", sex)] == 168
            assert counts[("bmi_for_age", sex)] == 168
            assert counts[("weight_for_age", sex)] == 60


@pytest.mark.asyncio
async def test_who_reseed_is_noop(session_factory) -> None:
    async with session_factory() as session:
        await _seed_who(session)
        first = await session.scalar(
            select(func.count())
            .select_from(GrowthReferenceLms)
            .where(GrowthReferenceLms.source == GrowthSource.WHO)
        )
        # Reejecutar el seed OMS: mismo conteo (upsert idempotente).
        await _seed_who(session)
        second = await session.scalar(
            select(func.count())
            .select_from(GrowthReferenceLms)
            .where(GrowthReferenceLms.source == GrowthSource.WHO)
        )
        assert first == second == (168 + 168 + 60) * 2


# 6 tripletas (indicator, sex, age_months) que cubren ambos sexos, los tres
# indicadores y ambos extremos del rango de cada uno.
_WHO_PARITY_SAMPLES: list[tuple[GrowthIndicator, str, float]] = [
    (GrowthIndicator.height_for_age, "M", 61.5),
    (GrowthIndicator.height_for_age, "F", 228.5),
    (GrowthIndicator.bmi_for_age, "M", 120.5),
    (GrowthIndicator.bmi_for_age, "F", 61.5),
    (GrowthIndicator.weight_for_age, "M", 61.5),
    (GrowthIndicator.weight_for_age, "F", 120.5),
]


def _lookup_json_lms(indicator: str, sex: str, age_months: float) -> tuple[float, float, float]:
    with _WHO_JSON_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    points = data["indicators"][indicator][sex]
    for point in points:
        if float(point["age"]) == age_months:
            return float(point["L"]), float(point["M"]), float(point["S"])
    raise AssertionError(f"No se encontró age={age_months} en {indicator}/{sex}")


@pytest.mark.asyncio
async def test_who_lms_parity_with_client_json(session_factory) -> None:
    async with session_factory() as session:
        await _seed_who(session)

        for indicator, sex, age_months in _WHO_PARITY_SAMPLES:
            params = await get_lms_params(
                session, indicator, sex, age_months, source=GrowthSource.WHO
            )
            assert params is not None
            L, M, S = params
            exp_L, exp_M, exp_S = _lookup_json_lms(indicator.value, sex, age_months)

            assert round(L, 6) == round(exp_L, 6)
            assert round(M, 6) == round(exp_M, 6)
            assert round(S, 6) == round(exp_S, 6)
