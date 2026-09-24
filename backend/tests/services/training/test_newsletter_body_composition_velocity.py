"""Newsletter body-composition block uses the same height-velocity leg as the
coach reading (feature 046, T069 privacy/safeguard audit finding F2).

Without the velocity leg, ``growth_explanation`` can never be
``expected_pubertal_gain`` / ``pre_spurt_accumulation``, so a girl around her
growth peak with a real (expected) rise in the skinfold sum would read
``sum_up_unexplained`` -> ámbar, and her family would get "En observación" in
the Bitácora PDF while the app card says "En su curva esperada" (contract
``body-composition-reading.md`` §5 scenario A: verde -> verde).

All data is synthetic (CLAUDE.md privacy rule): no real name or birth date.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
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
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, Sex
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.services.body_composition import FAMILY_COPY
from app.services.training.newsletter_builder import _build_body_composition_block
from tests.helpers.audit_tables import AUDIT_TABLES

_ATHLETE_ID = 301


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "athletes",
            "anthropometric_records",
            "skinfold_measurements",
            "growth_reference_lms",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _record(evaluation_date: date, *, weight: float, height: float, stage: MaturationStatus) -> AnthropometricRecord:
    return AnthropometricRecord(
        athlete_id=_ATHLETE_ID,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight)),
        standing_height_cm=Decimal(str(height)),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("0.5"),
        age_at_phv=Decimal("12.5"),
        maturation_status=stage,
        evaluated_by=1,
    )


def _set(sum4: float) -> SkinfoldMeasurement:
    return SkinfoldMeasurement(
        athlete_id=_ATHLETE_ID,
        triceps_mm=Decimal("9.0"),
        biceps_mm=Decimal("5.0"),
        subscapular_mm=Decimal("8.0"),
        medial_calf_mm=Decimal("10.0"),
        iliac_crest_mm=Decimal("12.0"),
        supraspinale_mm=Decimal("6.0"),
        sum4_mm=Decimal(str(sum4)),
        measured_by=1,
    )


@pytest_asyncio.fixture
async def scenario_a(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Contract §5 scenario A: girl circa -> post PHV, Σ4 32 -> 39, weight
    38 -> 42.5, height 148 -> 152.5 (velocity within the expected range)."""
    async with session_factory() as s:
        s.add(
            Athlete(
                id=_ATHLETE_ID,
                user_id=_ATHLETE_ID,
                first_name="Deportista",
                last_name="Sintética",
                birth_date=date(2013, 6, 1),
                sex=Sex.F,
                club_id=1,
                created_by=1,
            )
        )
        first = _record(date(2026, 1, 10), weight=38.0, height=148.0, stage=MaturationStatus.circa_phv)
        first.skinfolds = _set(32.0)
        second = _record(date(2026, 6, 10), weight=42.5, height=152.5, stage=MaturationStatus.post_phv)
        second.skinfolds = _set(39.0)
        s.add_all([first, second])
        await s.commit()


@pytest.mark.asyncio
async def test_expected_pubertal_gain_reads_verde_for_the_family(
    session_factory: async_sessionmaker[AsyncSession], scenario_a: None
) -> None:
    async with session_factory() as s:
        block = await _build_body_composition_block(s, _ATHLETE_ID, 2026, 6)

    assert block is not None
    assert block["family_label"] == FAMILY_COPY["verde"]["family_label"]
    assert block["family_sentence"] == FAMILY_COPY["verde"]["family_sentence"]
