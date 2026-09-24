"""Tests for `app.services.body_composition` — pure calculations + guards.

Source of truth: `specs/046-body-composition-skinfolds/data-model.md` §1/§4
and `specs/046-body-composition-skinfolds/contracts/skinfolds-api.md` §1.
This file intentionally does not test `build_reading` (band classifier,
`contracts/body-composition-reading.md`) — that lives in
`test_body_composition_reading.py` against a later task.

Strategy: pure-function tests run with no I/O at all (synthetic values).
`check_interval` needs the database (it reads previous counted sets), so it
uses an aiosqlite in-memory engine with only the two tables it touches —
same pattern as `tests/services/test_growth_seed.py`. All data is
fictitious (CLAUDE.md §Privacy): no real name, birth date or note of a minor
appears anywhere.
"""
from __future__ import annotations

from datetime import date, timedelta
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

from app.config import Settings
from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.services.body_composition import (
    AthleteTooYoungError,
    SkinfoldIntervalTooShortError,
    check_interval,
    check_min_age,
    classify_sum_change,
    compute_sums,
    estimate_body_fat,
    fat_masses,
    needs_third_reading,
    site_value,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# site_value — mean of 2 / median of 3
# ---------------------------------------------------------------------------


def test_site_value_mean_of_two_matches_api_contract_example() -> None:
    # contracts/skinfolds-api.md §1 response example: readings [8.5, 9.0] -> 8.8
    assert site_value([8.5, 9.0]) == Decimal("8.8")


def test_site_value_median_of_three() -> None:
    # contracts/skinfolds-api.md §1 request example: subscapular [7.0, 8.0, 7.5]
    assert site_value([7.0, 8.0, 7.5]) == Decimal("7.5")


def test_site_value_rejects_wrong_reading_count() -> None:
    with pytest.raises(ValueError):
        site_value([8.0])
    with pytest.raises(ValueError):
        site_value([8.0, 8.5, 9.0, 9.5])


# ---------------------------------------------------------------------------
# needs_third_reading — max(5% of mean, 1.0 mm), edges from data-model.md §4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "r1, r2, expected",
    [
        (8.0, 9.0, False),  # diff 1.0 == floor 1.0 -> not > tolerance
        (8.0, 9.5, True),  # diff 1.5 > floor 1.0
        (20.0, 21.0, False),  # diff 1.0 < 5% of 20.5 = 1.025
        (20.0, 21.5, True),  # diff 1.5 > 1.025
    ],
)
def test_needs_third_reading_edges(r1: float, r2: float, expected: bool) -> None:
    assert needs_third_reading(r1, r2) is expected


# ---------------------------------------------------------------------------
# compute_sums — Σ4/Σ6 present iff every member site has a value
# ---------------------------------------------------------------------------


def _all_sites(**overrides: Decimal | None) -> dict[str, Decimal | None]:
    values: dict[str, Decimal | None] = {
        "triceps": Decimal("8.0"),
        "biceps": Decimal("5.0"),
        "subscapular": Decimal("7.5"),
        "medial_calf": Decimal("10.0"),
        "iliac_crest": Decimal("12.0"),
        "supraspinale": Decimal("6.0"),
    }
    values.update(overrides)
    return values


def test_compute_sums_present_when_all_sites_measured() -> None:
    sum4, sum6 = compute_sums(_all_sites())
    assert sum4 == Decimal("30.5")  # 8.0+5.0+7.5+10.0
    assert sum6 == Decimal("48.5")  # + 12.0 + 6.0


def test_compute_sums_sum4_absent_when_backbone_site_declined() -> None:
    sum4, sum6 = compute_sums(_all_sites(biceps=None))
    assert sum4 is None
    assert sum6 is None  # biceps is also part of Σ6


def test_compute_sums_sum6_absent_but_sum4_present_when_non_backbone_declined() -> None:
    sum4, sum6 = compute_sums(_all_sites(iliac_crest=None))
    assert sum4 == Decimal("30.5")
    assert sum6 is None


# ---------------------------------------------------------------------------
# estimate_body_fat — Slaughter TC (1988) by sex
# ---------------------------------------------------------------------------


def test_estimate_body_fat_male() -> None:
    pct, equation_version = estimate_body_fat("M", triceps_mm=10.0, calf_mm=12.0)
    assert pct == pytest.approx(0.735 * 22.0 + 1.0)
    assert equation_version == "slaughter_tc_1988_v1"


def test_estimate_body_fat_female() -> None:
    pct, equation_version = estimate_body_fat("F", triceps_mm=10.0, calf_mm=12.0)
    assert pct == pytest.approx(0.610 * 22.0 + 5.0)
    assert equation_version == "slaughter_tc_1988_v1"


# ---------------------------------------------------------------------------
# fat_masses — FM/FFM from weight
# ---------------------------------------------------------------------------


def test_fat_masses_from_weight() -> None:
    fat_mass_kg, fat_free_mass_kg = fat_masses(weight_kg=40.0, body_fat_pct=16.5)
    assert fat_mass_kg == pytest.approx(6.6)
    assert fat_free_mass_kg == pytest.approx(33.4)
    assert fat_mass_kg + fat_free_mass_kg == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# classify_sum_change — Σ4 delta codes, threshold edges from the contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delta, expected",
    [
        (6.9, "within_noise"),
        (7.0, "up_real"),
        (-7.0, "down_real"),
    ],
)
def test_classify_sum_change_edges(delta: float, expected: str) -> None:
    assert classify_sum_change(delta, threshold=7.0) == expected


# ---------------------------------------------------------------------------
# check_min_age — age gate at BODY_COMP_MIN_AGE_YEARS (9)
# ---------------------------------------------------------------------------


class _FakeAthlete:
    """Minimal stand-in — `check_min_age` only reads `birth_date`."""

    def __init__(self, birth_date: date) -> None:
        self.birth_date = birth_date


def _birth_date_for_age(evaluation_date: date, age_years: float) -> date:
    return evaluation_date - timedelta(days=round(age_years * 365.25))


def test_check_min_age_blocks_below_minimum() -> None:
    evaluation_date = date(2026, 1, 1)
    athlete = _FakeAthlete(_birth_date_for_age(evaluation_date, 8.9))
    record = AnthropometricRecord(evaluation_date=evaluation_date)
    settings = _settings()

    with pytest.raises(AthleteTooYoungError) as exc_info:
        check_min_age(athlete, record, settings)  # type: ignore[arg-type]

    assert exc_info.value.min_age_years == 9


def test_check_min_age_allows_at_minimum() -> None:
    evaluation_date = date(2026, 1, 1)
    athlete = _FakeAthlete(_birth_date_for_age(evaluation_date, 9.0))
    record = AnthropometricRecord(evaluation_date=evaluation_date)
    settings = _settings()

    check_min_age(athlete, record, settings)  # type: ignore[arg-type]  # must not raise


# ---------------------------------------------------------------------------
# check_interval — BODY_COMP_MIN_INTERVAL_DAYS (90) between counted sets
# ---------------------------------------------------------------------------

_ATHLETE_ID = 1
_MEASURED_BY = 1
_EVALUATED_BY = 1


def _record_kwargs(evaluation_date: date) -> dict[str, object]:
    return dict(
        athlete_id=_ATHLETE_ID,
        evaluation_date=evaluation_date,
        weight_kg=Decimal("40.0"),
        standing_height_cm=Decimal("150.0"),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("-1.0"),
        age_at_phv=Decimal("13.5"),
        maturation_status=MaturationStatus.pre_phv,
        evaluated_by=_EVALUATED_BY,
    )


def _skinfold_kwargs(*, all_declined: bool = False) -> dict[str, object]:
    if all_declined:
        return dict(
            triceps_declined=True,
            biceps_declined=True,
            subscapular_declined=True,
            medial_calf_declined=True,
            iliac_crest_declined=True,
            supraspinale_declined=True,
            measured_by=_MEASURED_BY,
        )
    return dict(
        triceps_mm=Decimal("8.0"),
        biceps_mm=Decimal("5.0"),
        subscapular_mm=Decimal("7.5"),
        medial_calf_mm=Decimal("10.0"),
        iliac_crest_mm=Decimal("12.0"),
        supraspinale_mm=Decimal("6.0"),
        measured_by=_MEASURED_BY,
    )


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables["anthropometric_records"],
        Base.metadata.tables["skinfold_measurements"],
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _add_previous_counted_set(
    session: AsyncSession, *, evaluation_date: date
) -> AnthropometricRecord:
    record = AnthropometricRecord(**_record_kwargs(evaluation_date))
    # Assign through the relationship (not the raw FK) so `record.skinfolds`
    # is populated in-memory — a lazy load on an async session outside a
    # greenlet would otherwise blow up when `check_interval` reads it.
    record.skinfolds = SkinfoldMeasurement(athlete_id=_ATHLETE_ID, **_skinfold_kwargs())
    session.add(record)
    await session.flush()
    return record


async def _add_previous_fully_declined_set(
    session: AsyncSession, *, evaluation_date: date
) -> AnthropometricRecord:
    record = AnthropometricRecord(**_record_kwargs(evaluation_date))
    record.skinfolds = SkinfoldMeasurement(
        athlete_id=_ATHLETE_ID, **_skinfold_kwargs(all_declined=True)
    )
    session.add(record)
    await session.flush()
    return record


def _new_record_without_set(evaluation_date: date, *, record_id: int) -> AnthropometricRecord:
    """A transient (never flushed) record standing in for "the record being
    submitted" — it has no `skinfolds` set yet, only a synthetic `id` so
    `check_interval`'s `!=` filter excludes nothing real."""
    record = AnthropometricRecord(**_record_kwargs(evaluation_date))
    record.id = record_id
    return record


@pytest.mark.asyncio
async def test_check_interval_blocks_at_89_days(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _add_previous_counted_set(session, evaluation_date=date(2026, 1, 1))
        new_record = _new_record_without_set(date(2026, 3, 31), record_id=9001)  # +89 days

        with pytest.raises(SkinfoldIntervalTooShortError) as exc_info:
            await check_interval(session, _ATHLETE_ID, new_record, _settings())

        assert exc_info.value.previous_set_date == date(2026, 1, 1)
        assert exc_info.value.next_allowed_date == date(2026, 4, 1)


@pytest.mark.asyncio
async def test_check_interval_allows_at_90_days(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _add_previous_counted_set(session, evaluation_date=date(2026, 1, 1))
        new_record = _new_record_without_set(date(2026, 4, 1), record_id=9002)  # +90 days

        await check_interval(session, _ATHLETE_ID, new_record, _settings())  # must not raise


@pytest.mark.asyncio
async def test_check_interval_replacement_always_allowed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        previous = await _add_previous_counted_set(session, evaluation_date=date(2026, 1, 1))
        # `previous` already has a set attached (loaded in-memory) -> replace path.
        new_record = previous

        await check_interval(session, _ATHLETE_ID, new_record, _settings())  # must not raise


@pytest.mark.asyncio
async def test_check_interval_ignores_fully_declined_previous_attempt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        # Only a fully-declined attempt exists — must not count as "previous set".
        await _add_previous_fully_declined_set(session, evaluation_date=date(2026, 3, 20))
        new_record = _new_record_without_set(date(2026, 3, 25), record_id=9003)  # 5 days later

        await check_interval(session, _ATHLETE_ID, new_record, _settings())  # must not raise
