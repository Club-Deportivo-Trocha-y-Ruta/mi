"""Feature 048 (T008, research R1): pruebas del servicio de derivación extraído
de ``routers/anthropometry.py``.

BD aiosqlite en memoria solo con ``growth_reference_lms``. Las filas LMS son
sintéticas y simples (L=1, misma fila para todas las edades) para que el
z-score sea aritmética verificable a mano: ``z = (valor / M - 1) / S``.
Atletas ficticios, sin datos reales.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete, Sex
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.services.anthropometry import (
    WEIGHT_AGE_MAX_MONTHS,
    apply_derived_fields,
    derive_record_fields,
)

EVAL_DATE = date(2026, 5, 1)

# (M, S) por indicador; L = 1 en todos.
_LMS = {
    GrowthIndicator.height_for_age: (150.0, 0.05),
    GrowthIndicator.weight_for_age: (40.0, 0.10),
    GrowthIndicator.bmi_for_age: (20.0, 0.10),
}


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[Base.metadata.tables["growth_reference_lms"]]
            )
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


async def _seed_lms(session: AsyncSession, sex: str = "M") -> None:
    for indicator, (m, s) in _LMS.items():
        for age_months in (60.0, 240.0):
            session.add(
                GrowthReferenceLms(
                    source=GrowthSource.WHO,
                    indicator=indicator,
                    sex=sex,
                    age_months=age_months,
                    L=1.0,
                    M=m,
                    S=s,
                )
            )
    await session.commit()


def _athlete(birth_date: date, sex: Sex = Sex.M) -> Athlete:
    return Athlete(
        first_name="Deportista",
        last_name="Ficticio",
        birth_date=birth_date,
        sex=sex,
        club_id=1,
        created_by=1,
    )


def _status(derived) -> str:
    value = derived.maturation_status
    return str(getattr(value, "value", value))


async def _derive(session, athlete, *, weight="40.0", standing="150.0", sitting="76.0"):
    return await derive_record_fields(
        session,
        athlete,
        evaluation_date=EVAL_DATE,
        weight_kg=Decimal(weight),
        standing_height_cm=Decimal(standing),
        sitting_height_cm=Decimal(sitting),
    )


# ---------------------------------------------------------------------------
# PHV (Mirwald): pre / circa / post
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sex", "birth_date", "weight", "standing", "sitting", "expected"),
    [
        (Sex.M, date(2015, 1, 1), "40.0", "150.0", "76.0", "Pre-PHV"),  # offset -2.28
        (Sex.M, date(2012, 6, 1), "52.0", "165.0", "84.0", "Circa-PHV"),  # offset -0.11
        (Sex.M, date(2011, 1, 1), "60.0", "172.0", "88.0", "Post-PHV"),  # offset +1.16
        (Sex.F, date(2016, 1, 1), "30.0", "138.0", "72.0", "Pre-PHV"),  # offset -1.79
        (Sex.F, date(2013, 1, 1), "45.0", "158.0", "82.0", "Post-PHV"),  # offset +1.01
    ],
)
async def test_mirwald_status_pre_circa_post(
    session, sex, birth_date, weight, standing, sitting, expected
):
    derived = await _derive(
        session, _athlete(birth_date, sex), weight=weight, standing=standing, sitting=sitting
    )
    assert _status(derived) == expected
    offset = float(derived.maturity_offset)
    if expected == "Pre-PHV":
        assert offset < -1.0
    elif expected == "Post-PHV":
        assert offset > 1.0
    else:
        assert -1.0 <= offset <= 1.0
    assert derived.training_implications  # texto de implicaciones siempre presente


@pytest.mark.asyncio
async def test_leg_length_ratio_and_age_at_phv_are_derived(session):
    athlete = _athlete(date(2015, 1, 1))
    derived = await _derive(session, athlete, standing="150.0", sitting="76.0")
    assert float(derived.leg_length_cm) == pytest.approx(74.0)
    assert float(derived.leg_sitting_ratio) == pytest.approx(74.0 / 76.0, abs=1e-4)
    # age_at_phv = edad decimal a la fecha - offset
    assert float(derived.age_at_phv) == pytest.approx(11.33 - float(derived.maturity_offset), abs=0.01)


# ---------------------------------------------------------------------------
# LMS vacío -> fallback a None, pero IMC y Mirwald siguen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lms_empty_falls_back_to_none_but_keeps_bmi_and_phv(session):
    derived = await _derive(session, _athlete(date(2015, 1, 1)), weight="40.0", standing="150.0")
    assert derived.height_z_score is None
    assert derived.height_percentile is None
    assert derived.bmi_z_score is None
    assert derived.bmi_percentile is None
    assert derived.weight_z_score is None
    assert derived.weight_percentile is None
    assert derived.nutritional_status is None
    assert derived.nutritional_status_height is None
    # Desacoplado de la tabla LMS (feature 003 / FR-001a)
    assert derived.bmi == Decimal("17.78")
    assert _status(derived) == "Pre-PHV"
    assert derived.growth_source == GrowthSource.WHO


@pytest.mark.asyncio
async def test_lms_failure_is_swallowed_and_treated_as_no_data(session, monkeypatch):
    async def _boom(**_kwargs):
        raise RuntimeError("tabla LMS no disponible")

    monkeypatch.setattr("app.services.anthropometry.calculate_growth_percentiles", _boom)
    derived = await _derive(session, _athlete(date(2015, 1, 1)))
    assert derived.height_z_score is None
    assert derived.bmi == Decimal("17.78")


@pytest.mark.asyncio
async def test_lms_present_computes_z_scores_and_status(session):
    await _seed_lms(session)
    derived = await _derive(session, _athlete(date(2015, 1, 1)), weight="40.0", standing="150.0")
    assert float(derived.height_z_score) == pytest.approx(0.0, abs=1e-3)
    assert float(derived.height_percentile) == pytest.approx(50.0, abs=0.1)
    # IMC 17.78 con M=20, S=0.1 -> z = (0.889 - 1) / 0.1 = -1.11 -> delgadez
    assert float(derived.bmi_z_score) == pytest.approx(-1.111, abs=1e-3)
    assert derived.nutritional_status is not None
    assert str(getattr(derived.nutritional_status, "value", derived.nutritional_status)) == "delgadez"
    assert derived.growth_source == GrowthSource.WHO


# ---------------------------------------------------------------------------
# Peso/edad OMS: solo hasta WEIGHT_AGE_MAX_MONTHS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weight_z_and_percentile_are_none_above_who_age_range(session):
    await _seed_lms(session)
    # 2015-01-01 -> 11.33 años = 136 meses > 120.5
    derived = await _derive(session, _athlete(date(2015, 1, 1)))
    assert 11.33 * 12 > WEIGHT_AGE_MAX_MONTHS
    assert derived.weight_z_score is None
    assert derived.weight_percentile is None
    # talla e IMC sí conservan su z-score
    assert derived.height_z_score is not None
    assert derived.bmi_z_score is not None


@pytest.mark.asyncio
async def test_weight_z_and_percentile_present_within_who_age_range(session):
    await _seed_lms(session)
    # 2018-01-01 -> 8.33 años = 100 meses <= 120.5
    derived = await _derive(session, _athlete(date(2018, 1, 1)), weight="40.0", standing="150.0")
    assert float(derived.weight_z_score) == pytest.approx(0.0, abs=1e-3)
    assert float(derived.weight_percentile) == pytest.approx(50.0, abs=0.1)


@pytest.mark.asyncio
async def test_weight_range_boundary_is_inclusive_at_threshold(session):
    """age_months == 120.5 no se anula; el umbral es estricto (>)."""
    await _seed_lms(session)
    # Edad decimal 10.04 años -> 120.48 meses (<= 120.5): se conserva.
    # 10.04 * 365.25 = 3667.11 días -> 3667 días antes de EVAL_DATE.
    from datetime import timedelta

    birth = EVAL_DATE - timedelta(days=3667)
    derived = await _derive(session, _athlete(birth))
    assert derived.weight_z_score is not None
    # 10.05 años (3671 días) -> 120.6 meses > 120.5: se anula.
    birth_over = EVAL_DATE - timedelta(days=3671)
    derived_over = await _derive(session, _athlete(birth_over))
    assert derived_over.weight_z_score is None


# ---------------------------------------------------------------------------
# IMC: siempre, redondeado a 2 decimales
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("weight", "standing", "expected"),
    [
        ("41.3", "150.7", Decimal("18.19")),  # 18.1854...
        ("40.0", "150.0", Decimal("17.78")),  # 17.7777...
        ("33.0", "140.0", Decimal("16.84")),  # 16.8367...
    ],
)
async def test_bmi_is_rounded_to_two_decimals(session, weight, standing, expected):
    derived = await _derive(session, _athlete(date(2015, 1, 1)), weight=weight, standing=standing)
    assert derived.bmi == expected
    assert derived.bmi.as_tuple().exponent == -2


# ---------------------------------------------------------------------------
# apply_derived_fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_derived_fields_copies_derived_and_leaves_captured_untouched(session):
    await _seed_lms(session)
    derived = await _derive(session, _athlete(date(2018, 1, 1)))
    record = AnthropometricRecord(
        athlete_id=1,
        evaluation_date=EVAL_DATE,
        weight_kg=Decimal("40.0"),
        standing_height_cm=Decimal("150.0"),
        sitting_height_cm=Decimal("76.0"),
        evaluated_by=7,
        notes="nota original",
    )
    apply_derived_fields(record, derived)

    assert record.bmi == derived.bmi
    assert record.maturity_offset == derived.maturity_offset
    assert record.maturation_status == derived.maturation_status
    assert record.height_z_score == derived.height_z_score
    assert record.weight_percentile == derived.weight_percentile
    assert record.growth_source == GrowthSource.WHO
    # No toca lo capturado ni el autor
    assert record.weight_kg == Decimal("40.0")
    assert record.standing_height_cm == Decimal("150.0")
    assert record.evaluated_by == 7
    assert record.notes == "nota original"
    # nutritional_status_height no es columna
    assert not hasattr(record, "nutritional_status_height")
