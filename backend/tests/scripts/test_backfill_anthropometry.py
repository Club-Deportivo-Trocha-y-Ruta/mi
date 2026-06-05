"""Tests del backfill idempotente de derivados antropométricos (feature 003 / T011).

Cubre ``app.scripts.backfill_anthropometry``:
  - Un registro con derivados (bmi/percentiles) en NULL pero medidas crudas
    presentes se rellena para coincidir con ``services/growth.py`` y con
    bmi = peso / talla_m**2. Las medidas crudas NO se tocan.
  - Reejecutar el backfill es un no-op (summary.updated == 0 en la 2ª corrida).
  - Privacidad: el resumen impreso por ``run()`` jamás emite nombre ni fecha de
    nacimiento del menor (solo conteos agregados).

Estrategia: SQLite async in-memory (StaticPool), sin red ni MySQL. La LMS se
siembra con el mismo helper offline del seed real.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import patch

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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.scripts.backfill_anthropometry import backfill_anthropometry, run
from app.seed_growth_data import _parse_csv_content, bulk_insert_lms
from app.services.growth import calculate_growth_percentiles
from app.models.growth import GrowthSource
from app.services.category import compute_age_decimal

# Identificadores ficticios del menor — nunca datos reales de atletas TyR.
_ATHLETE_FIRST = "Juan"
_ATHLETE_LAST = "Pérez Ficticio"
_ATHLETE_DOB = date(2015, 1, 1)
_EVAL_DATE = date(2026, 5, 1)

# CSV LMS mínimo cubriendo edad/sexo del atleta de prueba (varón ~11 años).
_LMS_HEIGHT = "Sex,Agemos,L,M,S\n1,24,1.0,86.0,0.04\n1,240.5,0.9,175.0,0.045\n"
_LMS_BMI = "Sex,Agemos,L,M,S\n1,24,-2.0,16.5,0.08\n1,240.5,-1.5,21.0,0.13\n"
_LMS_WEIGHT = "Sex,Agemos,L,M,S\n1,24,-0.2,12.6,0.10\n1,240.5,-1.0,62.0,0.16\n"


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
        for t in ("athletes", "anthropometric_records", "growth_reference_lms")
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_lms(session: AsyncSession) -> None:
    for content, indicator in (
        (_LMS_HEIGHT, "height_for_age"),
        (_LMS_BMI, "bmi_for_age"),
        (_LMS_WEIGHT, "weight_for_age"),
    ):
        await bulk_insert_lms(session, _parse_csv_content(content, indicator))
    await session.commit()


# Medidas crudas del registro a rellenar (derivados inicialmente en NULL).
_RAW_WEIGHT = Decimal("38.00")
_RAW_HEIGHT = Decimal("145.0")
_RAW_SITTING = Decimal("74.0")


async def _seed_athlete_and_record(session: AsyncSession) -> tuple[int, int]:
    """Crea un atleta ficticio + un registro antropométrico sin derivados."""
    athlete = Athlete(
        user_id=1,
        first_name=_ATHLETE_FIRST,
        last_name=_ATHLETE_LAST,
        birth_date=_ATHLETE_DOB,
        sex=Sex.M,
        club_id=1,
        created_by=1,
    )
    session.add(athlete)
    await session.flush()

    record = AnthropometricRecord(
        athlete_id=athlete.id,
        evaluation_date=_EVAL_DATE,
        weight_kg=_RAW_WEIGHT,
        standing_height_cm=_RAW_HEIGHT,
        sitting_height_cm=_RAW_SITTING,
        leg_length_cm=Decimal("71.0"),
        leg_sitting_ratio=Decimal("0.9595"),
        maturity_offset=Decimal("-1.50"),
        age_at_phv=Decimal("13.50"),
        maturation_status=MaturationStatus.pre_phv,
        evaluated_by=1,
        # Derivados deliberadamente en NULL → candidatos a backfill
        bmi=None,
        bmi_percentile=None,
        height_percentile=None,
        weight_percentile=None,
    )
    session.add(record)
    await session.commit()
    return athlete.id, record.id


@pytest.mark.asyncio
async def test_backfill_fills_derived_and_preserves_raw(session_factory) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        athlete_id, record_id = await _seed_athlete_and_record(session)

    async with session_factory() as session:
        summary = await backfill_anthropometry(session)

    assert summary.scanned == 1
    assert summary.updated == 1

    # Valor esperado de growth (misma matemática que el servicio).
    async with session_factory() as session:
        athlete = await session.get(Athlete, athlete_id)
        age_months = (
            compute_age_decimal(athlete.birth_date, _EVAL_DATE) * 12
        )
        expected = await calculate_growth_percentiles(
            db=session,
            weight_kg=float(_RAW_WEIGHT),
            standing_height_cm=float(_RAW_HEIGHT),
            sex="M",
            age_months=age_months,
            source=GrowthSource.CDC,
        )

    async with session_factory() as session:
        record = await session.get(AnthropometricRecord, record_id)

        # BMI = peso / talla_m**2
        expected_bmi = float(_RAW_WEIGHT) / (float(_RAW_HEIGHT) / 100) ** 2
        assert record.bmi is not None
        assert float(record.bmi) == pytest.approx(round(expected_bmi, 2), abs=0.01)

        # Percentiles/z-scores coinciden con services/growth.py
        assert record.bmi_percentile == expected.bmi_percentile
        assert record.height_percentile == expected.height_percentile
        assert record.weight_percentile == expected.weight_percentile
        assert record.bmi_z_score == expected.bmi_z_score
        assert record.height_z_score == expected.height_z_score
        assert record.weight_z_score == expected.weight_z_score

        # Medidas crudas INTACTAS
        assert record.weight_kg == _RAW_WEIGHT
        assert record.standing_height_cm == _RAW_HEIGHT
        assert record.sitting_height_cm == _RAW_SITTING


@pytest.mark.asyncio
async def test_backfill_is_idempotent(session_factory) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        await _seed_athlete_and_record(session)

    async with session_factory() as session:
        first = await backfill_anthropometry(session)
    assert first.updated == 1

    # Segunda corrida: nada cambia (no-op)
    async with session_factory() as session:
        second = await backfill_anthropometry(session)
    assert second.updated == 0
    assert second.scanned == 0  # ya no quedan registros con derivados NULL


@pytest.mark.asyncio
async def test_run_summary_emits_no_pii(session_factory) -> None:
    async with session_factory() as session:
        await _seed_lms(session)
        await _seed_athlete_and_record(session)

    # run() construye su propio engine; lo apuntamos al engine in-memory de test.
    buffer = io.StringIO()
    with patch(
        "app.scripts.backfill_anthropometry.create_async_engine",
        return_value=session_factory.kw["bind"],
    ):
        with redirect_stdout(buffer):
            summary = await run()

    assert summary.updated == 1
    output = buffer.getvalue()
    assert output  # se imprimió el resumen agregado

    # Privacidad: ni nombre ni fecha de nacimiento del menor en el log.
    assert _ATHLETE_FIRST not in output
    assert _ATHLETE_LAST not in output
    assert "Ficticio" not in output
    assert "2015" not in output
    assert _ATHLETE_DOB.isoformat() not in output
