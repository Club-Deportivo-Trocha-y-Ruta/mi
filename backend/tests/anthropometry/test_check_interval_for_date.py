"""Feature 048 (T017): ``check_interval_for_date`` — la regla de 90 días de
pliegues evaluada en la fecha NUEVA de un registro que ya tiene set, sin
contar su propio set (``check_interval`` es un no-op en ese caso).

Datos ficticios; sesiones sobre el SQLite en memoria del conftest del paquete.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.anthropometry import AnthropometricRecord
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.services.body_composition import (
    SkinfoldIntervalTooShortError,
    check_interval_for_date,
)
from tests.anthropometry.conftest import ATHLETE_ID, COACH_ID, seed_record

pytestmark = pytest.mark.asyncio

SETTINGS = SimpleNamespace(body_comp_min_interval_days=90, body_comp_min_age_years=9)


async def _attach_set(factory, record_id: int, *, counted: bool = True) -> None:
    """Set mínimo: con ``counted=False`` todos los sitios quedan declinados
    (un intento rechazado, que la regla ignora)."""
    async with factory() as s:
        s.add(
            SkinfoldMeasurement(
                anthropometric_record_id=record_id,
                athlete_id=ATHLETE_ID,
                protocol_version="v1",
                caliper_model="slim_guide",
                measured_by=COACH_ID,
                triceps_mm=Decimal("9.0") if counted else None,
                triceps_declined=not counted,
            )
        )
        await s.commit()


async def _load(session, record_id: int) -> AnthropometricRecord:
    result = await session.execute(
        select(AnthropometricRecord)
        .options(selectinload(AnthropometricRecord.skinfolds))
        .where(AnthropometricRecord.id == record_id)
    )
    return result.scalar_one()


async def test_no_other_set_never_raises(anthro_factory):
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    await _attach_set(anthro_factory, rid)
    async with anthro_factory() as s:
        record = await _load(s, rid)
        # Su propio set no cuenta, aunque la fecha se mueva unos días.
        await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 5, 11), SETTINGS)


async def test_previous_counted_set_too_close_raises_with_wizard_dates(anthro_factory):
    prev = await seed_record(anthro_factory, evaluation_date=date(2026, 1, 10))
    await _attach_set(anthro_factory, prev)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        with pytest.raises(SkinfoldIntervalTooShortError) as exc_info:
            await check_interval_for_date(
                s, ATHLETE_ID, record, date(2026, 2, 1), SETTINGS
            )
    assert exc_info.value.previous_set_date == date(2026, 1, 10)
    assert exc_info.value.next_allowed_date == date(2026, 1, 10) + timedelta(days=90)


async def test_exactly_min_interval_is_allowed(anthro_factory):
    prev = await seed_record(anthro_factory, evaluation_date=date(2026, 1, 10))
    await _attach_set(anthro_factory, prev)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 6, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        await check_interval_for_date(
            s, ATHLETE_ID, record, date(2026, 1, 10) + timedelta(days=90), SETTINGS
        )
        with pytest.raises(SkinfoldIntervalTooShortError):
            await check_interval_for_date(
                s, ATHLETE_ID, record, date(2026, 1, 10) + timedelta(days=89), SETTINGS
            )


async def test_fully_declined_previous_attempt_is_ignored(anthro_factory):
    prev = await seed_record(anthro_factory, evaluation_date=date(2026, 4, 20))
    await _attach_set(anthro_factory, prev, counted=False)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 5, 2), SETTINGS)


async def test_previous_is_evaluated_at_new_date_not_old_one(anthro_factory):
    """A set dated after the NEW date is not "previous": the backward rule
    looks at the closest earlier set only (the forward rule is separate)."""
    later = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 20))
    await _attach_set(anthro_factory, later)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 6, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        # Con la fecha vieja (01-jun) el set del 20-may estaría a 12 días.
        with pytest.raises(SkinfoldIntervalTooShortError):
            await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 6, 1), SETTINGS)
        # Movido a >= 90 días ANTES del set del 20-may: no choca en ningún sentido.
        await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 2, 19), SETTINGS)


async def test_later_counted_set_within_interval_raises(anthro_factory):
    later = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 20))
    await _attach_set(anthro_factory, later)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 10, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        with pytest.raises(SkinfoldIntervalTooShortError) as exc_info:
            await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 5, 1), SETTINGS)
    # Forward conflict: previous_set_date carries the later set's date.
    assert exc_info.value.previous_set_date == date(2026, 5, 20)
    assert exc_info.value.next_allowed_date == date(2026, 5, 20) + timedelta(days=90)


async def test_later_set_exactly_min_interval_away_is_allowed(anthro_factory):
    later = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 20))
    await _attach_set(anthro_factory, later)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 10, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        await check_interval_for_date(
            s, ATHLETE_ID, record, date(2026, 5, 20) - timedelta(days=90), SETTINGS
        )
        with pytest.raises(SkinfoldIntervalTooShortError):
            await check_interval_for_date(
                s, ATHLETE_ID, record, date(2026, 5, 20) - timedelta(days=89), SETTINGS
            )


async def test_fully_declined_later_attempt_is_ignored(anthro_factory):
    later = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 20))
    await _attach_set(anthro_factory, later, counted=False)
    rid = await seed_record(anthro_factory, evaluation_date=date(2026, 10, 1))
    await _attach_set(anthro_factory, rid)

    async with anthro_factory() as s:
        record = await _load(s, rid)
        await check_interval_for_date(s, ATHLETE_ID, record, date(2026, 5, 1), SETTINGS)
