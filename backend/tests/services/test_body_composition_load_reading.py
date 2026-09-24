"""Shared body-composition loader (feature 046, T080 — privacy-audit F6).

`services.body_composition.load_reading` is the one DB-backed assembler of
`build_reading`'s inputs. These tests prove that the coach detail
(`GET …/body-composition`), the growth-summary card (coach and the parent's
5-key projection) and the Bitácora annex (`_build_body_composition_block`)
now agree on the same athlete, in the two edge cases F6 described:

1. A later anthropometric record WITHOUT skinfolds: the growth summary used
   to compute velocity from the two most recent records (not from the set's
   record), so a girl with an expected pubertal gain read ámbar on the card
   (`sum_up_velocity_low`) while the coach detail read verde.
2. A single set with a population-reference extreme: the growth summary had
   no FUPRECOL lookup, so the coach card read verde `first_set` while the
   coach detail read ámbar `reference_extreme` (family stays verde).

Plus unit checks of the loader's scoping parameters (`until`/`since`/
`at_record_id`). All data is synthetic (CLAUDE.md privacy rule): generic
names, synthetic birth dates, hand-made LMS rows.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.club import ClubRole
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.models.user import UserRole
from app.services.body_composition import (
    COACH_REASON_COPY,
    FAMILY_COPY,
    load_athlete_records,
    load_reading,
)
from app.services.training.newsletter_builder import _build_body_composition_block
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.query_counting import count_selects

pytestmark = pytest.mark.asyncio

_TABLES = (
    "athletes",
    "anthropometric_records",
    "skinfold_measurements",
    "growth_reference_lms",
    "parent_athlete",
    "parental_consents",
    "athlete_ai_explanations",
    *AUDIT_TABLES,
)

_CLUB_ID = 1
_PARENT_USER_ID = 900
_ATHLETE_LATER_RECORD = 801  # edge case 1
_ATHLETE_REFERENCE = 802  # edge case 2


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
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
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers (synthetic only)
# ---------------------------------------------------------------------------


def _athlete(athlete_id: int) -> Athlete:
    return Athlete(
        id=athlete_id,
        user_id=athlete_id,
        first_name="Deportista",
        last_name="Sintética",
        birth_date=date(2013, 6, 1),  # synthetic — ~12.6 years in 2026
        sex=Sex.F,
        club_id=_CLUB_ID,
        created_by=1,
    )


def _record(
    athlete_id: int,
    record_id: int,
    evaluation_date: date,
    *,
    weight: float,
    height: float,
    stage: MaturationStatus,
) -> AnthropometricRecord:
    return AnthropometricRecord(
        id=record_id,
        athlete_id=athlete_id,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight)),
        standing_height_cm=Decimal(str(height)),
        sitting_height_cm=Decimal("78.0"),
        leg_length_cm=Decimal("72.0"),
        leg_sitting_ratio=Decimal("0.9231"),
        maturity_offset=Decimal("0.5"),
        age_at_phv=Decimal("12.1"),
        maturation_status=stage,
        evaluated_by=1,
    )


def _set(athlete_id: int, *, sum4: float, triceps: float = 9.0, declined: bool = False) -> SkinfoldMeasurement:
    def value(v: float) -> Decimal | None:
        return None if declined else Decimal(str(v))

    return SkinfoldMeasurement(
        athlete_id=athlete_id,
        triceps_mm=value(triceps),
        biceps_mm=value(5.0),
        subscapular_mm=value(8.0),
        medial_calf_mm=value(10.0),
        iliac_crest_mm=value(12.0),
        supraspinale_mm=value(6.0),
        triceps_declined=declined,
        biceps_declined=declined,
        subscapular_declined=declined,
        medial_calf_declined=declined,
        iliac_crest_declined=declined,
        supraspinale_declined=declined,
        sum4_mm=None if declined else Decimal(str(sum4)),
        measured_by=1,
    )


def _lms_rows() -> list[GrowthReferenceLms]:
    """Hand-made FUPRECOL-like LMS rows (girls): triceps median 9 mm,
    subscapular median 8 mm, S = 0.2 → 9/8 mm read P50 ("normal") and a
    14 mm triceps reads ≥ P95 ("high_extreme")."""
    rows = []
    for indicator, median in (
        (GrowthIndicator.triceps_skinfold_for_age, "9.0"),
        (GrowthIndicator.subscapular_skinfold_for_age, "8.0"),
    ):
        for age_months in ("120.0", "200.0"):
            rows.append(
                GrowthReferenceLms(
                    source=GrowthSource.FUPRECOL,
                    indicator=indicator,
                    sex="F",
                    age_months=Decimal(age_months),
                    L=Decimal("1.0"),
                    M=Decimal(median),
                    S=Decimal("0.2"),
                )
            )
    return rows


async def _seed(session: AsyncSession) -> None:
    session.add_all(_lms_rows())

    # Edge case 1 — contract §5 scenario A (girl, circa → post PHV, Σ4 32 → 39,
    # weight 38 → 42.5, height 148 → 152.5) followed by a record WITHOUT
    # skinfolds whose height barely moved (velocity vs the set's record would
    # read "below" if taken from the two most recent records).
    a = _ATHLETE_LATER_RECORD
    session.add(_athlete(a))
    r1 = _record(a, 8011, date(2026, 1, 10), weight=38.0, height=148.0, stage=MaturationStatus.circa_phv)
    r1.skinfolds = _set(a, sum4=32.0)
    r2 = _record(a, 8012, date(2026, 6, 10), weight=42.5, height=152.5, stage=MaturationStatus.post_phv)
    r2.skinfolds = _set(a, sum4=39.0)
    r3 = _record(a, 8013, date(2026, 7, 15), weight=42.6, height=152.55, stage=MaturationStatus.post_phv)
    session.add_all([r1, r2, r3])

    # Edge case 2 — one set, triceps at the population extreme.
    b = _ATHLETE_REFERENCE
    session.add(_athlete(b))
    rb = _record(b, 8021, date(2026, 6, 12), weight=40.0, height=150.0, stage=MaturationStatus.circa_phv)
    rb.skinfolds = _set(b, sum4=35.0, triceps=14.0)
    session.add(rb)

    for athlete_id in (a, b):
        session.add(
            ParentAthlete(
                parent_id=_PARENT_USER_ID,
                athlete_id=athlete_id,
                relationship_type=FamilyRelationship.padre,
            )
        )
    await session.commit()
    session.expunge_all()


def _coach() -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=_CLUB_ID, role_in_club=ClubRole.coach)],
    )


def _parent() -> SimpleNamespace:
    return SimpleNamespace(id=_PARENT_USER_ID, role=UserRole.parent, club_memberships=[])


async def _get(session: AsyncSession, user: SimpleNamespace, url: str) -> dict:
    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _surfaces(session: AsyncSession, athlete_id: int, year: int, month: int) -> dict:
    coach_detail = await _get(session, _coach(), f"/api/athletes/{athlete_id}/body-composition")
    coach_card = await _get(session, _coach(), f"/api/athletes/{athlete_id}/growth-summary")
    family_card = await _get(session, _parent(), f"/api/athletes/{athlete_id}/growth-summary")
    newsletter = await _build_body_composition_block(session, athlete_id, year, month)
    return {
        "coach_detail": coach_detail["reading"],
        "coach_card": coach_card["body_composition"],
        "family_card": family_card["body_composition"],
        "newsletter": newsletter,
    }


def _assert_agree(surfaces: dict, *, band: str, reason: str, family_band: str) -> None:
    detail = surfaces["coach_detail"]
    coach_card = surfaces["coach_card"]
    family_card = surfaces["family_card"]
    newsletter = surfaces["newsletter"]

    # Coach detail and coach card: same band, same reason.
    assert (detail["band"], detail["band_reason_code"]) == (band, reason)
    assert coach_card["band"] == band
    assert coach_card["coach_reason"] == COACH_REASON_COPY[reason]
    assert detail["family_band"] == coach_card["family_band"] == family_band

    # Family card (parent projection) and Bitácora annex: same family copy.
    copy = FAMILY_COPY[family_band]
    assert family_card["family_band"] == family_band
    assert family_card["family_label"] == copy["family_label"]
    assert family_card["family_sentence"] == copy["family_sentence"]
    assert "band" not in family_card
    assert newsletter is not None
    assert newsletter["family_label"] == copy["family_label"]
    assert newsletter["family_sentence"] == copy["family_sentence"]


# ---------------------------------------------------------------------------
# Agreement across surfaces
# ---------------------------------------------------------------------------


async def test_later_record_without_skinfolds_does_not_change_the_reading(
    session: AsyncSession,
) -> None:
    """F6 edge case 1: every surface reads verde `expected_pubertal_gain`."""
    await _seed(session)
    surfaces = await _surfaces(session, _ATHLETE_LATER_RECORD, 2026, 6)
    _assert_agree(surfaces, band="verde", reason="expected_pubertal_gain", family_band="verde")
    assert surfaces["coach_detail"]["velocity_code"] == "within_or_above"


async def test_reference_only_ambar_agrees_between_detail_and_card(session: AsyncSession) -> None:
    """F6 edge case 2: coach sees ámbar `reference_extreme` on both the detail
    and the card; families see verde everywhere (spec clarification Q4)."""
    await _seed(session)
    surfaces = await _surfaces(session, _ATHLETE_REFERENCE, 2026, 6)
    _assert_agree(surfaces, band="ambar", reason="reference_extreme", family_band="verde")
    assert surfaces["coach_detail"]["reference_triceps"]["code"] == "high_extreme"


# ---------------------------------------------------------------------------
# Loader scoping and query cost
# ---------------------------------------------------------------------------


async def test_load_athlete_records_is_one_select(session: AsyncSession, engine: AsyncEngine) -> None:
    await _seed(session)
    async with count_selects(engine) as counter:
        records = await load_athlete_records(session, _ATHLETE_LATER_RECORD)
        # `.skinfolds` is populated by the same SELECT (no lazy load).
        flags = [r.skinfolds is not None for r in records]
    assert counter[0] == 1
    assert flags == [True, True, False]


async def test_at_record_id_never_looks_at_later_measurements(session: AsyncSession) -> None:
    """AI leaf scoping: analysing the first record yields a `first_set` reading
    (sets_count 1) even though a later set exists; analysing a record without
    a set yields no reading."""
    await _seed(session)
    athlete = await session.get(Athlete, _ATHLETE_LATER_RECORD)

    first = await load_reading(session, athlete, at_record_id=8011)
    assert first.reading is not None
    assert first.reading.sets_count == 1
    assert first.reading.band_reason_code == "first_set"
    assert first.previous_set_record is None

    second = await load_reading(session, athlete, at_record_id=8012)
    assert second.reading is not None
    assert second.reading.sets_count == 2
    assert second.previous_set_record is not None and second.previous_set_record.id == 8011

    no_set = await load_reading(session, athlete, at_record_id=8013)
    assert no_set.reading is None


async def test_since_until_scope_the_newsletter_month(session: AsyncSession) -> None:
    await _seed(session)
    athlete = await session.get(Athlete, _ATHLETE_LATER_RECORD)

    june = await load_reading(session, athlete, until=date(2026, 6, 30), since=date(2026, 6, 1))
    assert june.reading is not None and june.latest_set_record.id == 8012

    july = await load_reading(session, athlete, until=date(2026, 7, 31), since=date(2026, 7, 1))
    assert july.reading is None  # the July record has no skinfold set


async def test_latest_attempt_declined_comes_from_the_shared_reading(session: AsyncSession) -> None:
    """Contract §3b: a fully declined attempt after the latest counted set is
    reported by the reading itself (the growth router no longer overlays it)."""
    await _seed(session)
    b = _ATHLETE_REFERENCE
    declined = _record(b, 8022, date(2026, 9, 20), weight=40.2, height=150.8, stage=MaturationStatus.circa_phv)
    declined.skinfolds = _set(b, sum4=0.0, declined=True)
    session.add(declined)
    await session.commit()
    session.expunge_all()

    card = await _get(session, _coach(), f"/api/athletes/{b}/growth-summary")
    detail = await _get(session, _coach(), f"/api/athletes/{b}/body-composition")
    assert card["body_composition"]["latest_attempt_declined"] == "2026-09-20"
    assert detail["reading"]["latest_attempt_declined"] == "2026-09-20"
    assert card["body_composition"]["latest_set_date"] == "2026-06-12"
