"""Router tests for ``latest_ai_analysis`` on the growth summary (feature 042 / T070).

Covers `contracts/growth-summary-latest-analysis.md` and
`specs/042-traceable-growth-ai/data-model.md` §4:

1. Null conditions: no analysis at all; legacy prose only (``schema_version``
   ``NULL``); a v2 row whose ``critic_verdict`` is not family-deliverable and
   the caller is a parent — indistinguishable from "no analysis yet" (FR-016,
   SC-004).
2. Consent denied → the field is absent, and the endpoint still returns 200
   (denied-path, not an error path).
3. Staleness, both triggers independently (data-model.md §4), plus the
   not-stale case.
4. Coach vs parent visibility split on the same rows, across all five
   ``critic_verdict`` values.
5. Non-fatal: the internal lookup raising does not turn into a 500.
6. No additional per-measurement query (SC-008).

Strategy: SQLite async in-memory with ``app.main.app`` + dependency overrides,
same pattern as ``tests/routers/test_growth_summary.py`` (feature 040). All
data is fictitious (CLAUDE.md §Privacy) — no real TyR athlete data, no minor's
name or birth date anywhere in this file.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.club import ClubRole
from app.models.growth import GrowthSource
from app.models.parental_consent import ParentalConsent
from app.models.user import UserRole
from app.services.ai.anthro.guardrails_step import FAMILY_DELIVERABLE_VERDICTS
from app.services.ai.use_cases.anthropometric_record_explainer import (
    USE_CASE_KEY as RECORD_USE_CASE,
)
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

_TODAY = date.today()
_BIRTH_DATE = date(2013, 1, 1)  # atleta ficticio, ~13 años — no es un dato real
_URL = "/api/athletes/{athlete_id}/growth-summary"

# Todos los verdicts posibles de la máquina de estados (data-model.md §3).
_ALL_VERDICTS = ("approved", "revised", "flagged", "fallback", "skipped")


# ---------------------------------------------------------------------------
# DB fixtures — mirrors tests/routers/test_growth_summary.py
# ---------------------------------------------------------------------------


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
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def ai_enabled(monkeypatch):
    """La feature está apagada por defecto (`Settings.ai_enabled = False`);
    la mayoría de estos escenarios necesitan encenderla explícitamente."""
    monkeypatch.setattr(settings, "ai_enabled", True)


# ---------------------------------------------------------------------------
# Fake users
# ---------------------------------------------------------------------------


def coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=UserRole.coach,
        club_memberships=[SimpleNamespace(club_id=club_id, role_in_club=ClubRole.coach)],
    )


def parent_user(user_id: int = 20) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.parent, club_memberships=[])


def make_client(session: AsyncSession, *, user) -> AsyncClient:
    """Bind an AsyncClient to the real ``app.main.app`` with DB/auth overrides."""

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def seed_athlete(
    session: AsyncSession,
    *,
    athlete_id: int,
    club_id: int = 1,
    sex: Sex = Sex.M,
) -> Athlete:
    """Fictitious athlete — generic first/last name, synthetic birth date."""
    a = Athlete(
        id=athlete_id,
        user_id=athlete_id,
        first_name="Atleta",
        last_name="Prueba",
        birth_date=_BIRTH_DATE,
        sex=sex,
        club_id=club_id,
        created_by=1,
    )
    session.add(a)
    await session.flush()
    return a


async def seed_record(
    session: AsyncSession,
    *,
    record_id: int,
    athlete_id: int,
    evaluation_date: date,
    standing_height_cm: float = 150.0,
    weight_kg: float = 40.0,
    updated_at: datetime | None = None,
) -> AnthropometricRecord:
    bmi = round(weight_kg / (standing_height_cm / 100) ** 2, 2)
    kwargs = dict(
        id=record_id,
        athlete_id=athlete_id,
        evaluation_date=evaluation_date,
        weight_kg=Decimal(str(weight_kg)),
        standing_height_cm=Decimal(str(standing_height_cm)),
        sitting_height_cm=Decimal("74.0"),
        leg_length_cm=Decimal("76.0"),
        leg_sitting_ratio=Decimal("1.0270"),
        maturity_offset=Decimal("0.0"),
        age_at_phv=Decimal("12.5"),
        maturation_status=MaturationStatus.pre_phv,
        evaluated_by=1,
        bmi=Decimal(str(bmi)),
        height_z_score=Decimal("-0.500"),
        height_percentile=Decimal("30.9"),
        bmi_z_score=Decimal("0.200"),
        bmi_percentile=Decimal("57.9"),
        growth_source=GrowthSource.WHO,
    )
    if updated_at is not None:
        kwargs["updated_at"] = updated_at
    r = AnthropometricRecord(**kwargs)
    session.add(r)
    await session.flush()
    return r


async def link_parent(
    session: AsyncSession, *, parent_user_id: int, athlete_id: int
) -> ParentAthlete:
    pa = ParentAthlete(
        parent_id=parent_user_id,
        athlete_id=athlete_id,
        relationship_type=FamilyRelationship.padre,
    )
    session.add(pa)
    await session.flush()
    return pa


async def grant_consent(
    session: AsyncSession,
    *,
    athlete_id: int,
    parent_user_id: int,
    third_party_sharing: bool = True,
) -> ParentalConsent:
    c = ParentalConsent(
        parent_user_id=parent_user_id,
        athlete_id=athlete_id,
        consent_version="v1",
        policy_id=None,
        consented_at=datetime.now(timezone.utc),
        third_party_sharing=third_party_sharing,
    )
    session.add(c)
    await session.flush()
    return c


async def seed_explanation(
    session: AsyncSession,
    *,
    athlete_id: int,
    record_id: int,
    generated_at: datetime,
    schema_version: str | None = "v2",
    critic_verdict: str | None = "approved",
    summary_line: str = "Cambio dentro de lo esperado para la edad.",
    has_warning_signs: bool = False,
) -> AthleteAIExplanation:
    structured_json = None
    if schema_version == "v2":
        structured_json = {
            "summary_line": summary_line,
            "warning_signs": (["señal genérica"] if has_warning_signs else []),
        }
    row = AthleteAIExplanation(
        athlete_id=athlete_id,
        anthropometric_record_id=record_id,
        use_case=RECORD_USE_CASE,
        text="Texto de análisis genérico para pruebas.",
        model="fake-model",
        provider="fake",
        generated_at=generated_at,
        age_group="10-12",
        schema_version=schema_version,
        structured_json=structured_json,
        critic_verdict=critic_verdict,
        generated_by_user_id=1,
    )
    session.add(row)
    await session.flush()
    return row


def _naive(dt: datetime) -> datetime:
    """Sqlite/aiosqlite round-trips naive datetimes; build fixtures naive too."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


_GEN_AT = _naive(datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# 1. Null conditions
# ---------------------------------------------------------------------------


async def test_null_when_no_analysis_at_all(session: AsyncSession, ai_enabled) -> None:
    athlete = await seed_athlete(session, athlete_id=301)
    await seed_record(session, record_id=1, athlete_id=athlete.id, evaluation_date=_TODAY)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["latest_ai_analysis"] is None


async def test_null_when_only_legacy_prose_row(session: AsyncSession, ai_enabled) -> None:
    """A `schema_version IS NULL` row (feature 033, pre-042) never surfaces here."""
    athlete = await seed_athlete(session, athlete_id=302)
    await seed_record(session, record_id=2, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session,
        athlete_id=athlete.id,
        record_id=2,
        generated_at=_GEN_AT,
        schema_version=None,
        critic_verdict=None,
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["latest_ai_analysis"] is None


async def test_flagged_only_row_indistinguishable_from_none_for_parent(
    session: AsyncSession, ai_enabled
) -> None:
    """A parent facing a `flagged`-only row must see EXACTLY the same payload
    as a parent facing an athlete with no analysis at all (FR-016, SC-004) —
    nothing in the response may reveal that a blocked analysis exists."""
    # Athlete with a blocked (flagged) v2 row.
    blocked = await seed_athlete(session, athlete_id=303)
    await seed_record(session, record_id=3, athlete_id=blocked.id, evaluation_date=_TODAY)
    await seed_explanation(
        session,
        athlete_id=blocked.id,
        record_id=3,
        generated_at=_GEN_AT,
        critic_verdict="flagged",
    )
    await link_parent(session, parent_user_id=40, athlete_id=blocked.id)
    await grant_consent(session, athlete_id=blocked.id, parent_user_id=40)

    # Athlete with no analysis at all — otherwise identical fixture.
    clean = await seed_athlete(session, athlete_id=304)
    await seed_record(session, record_id=4, athlete_id=clean.id, evaluation_date=_TODAY)
    await link_parent(session, parent_user_id=41, athlete_id=clean.id)
    await grant_consent(session, athlete_id=clean.id, parent_user_id=41)

    await session.commit()

    async with make_client(session, user=parent_user(user_id=40)) as client:
        resp_blocked = await client.get(_URL.format(athlete_id=blocked.id))
    async with make_client(session, user=parent_user(user_id=41)) as client:
        resp_clean = await client.get(_URL.format(athlete_id=clean.id))

    assert resp_blocked.status_code == 200, resp_blocked.text
    assert resp_clean.status_code == 200, resp_clean.text

    data_blocked = resp_blocked.json()
    data_clean = resp_clean.json()
    assert data_blocked["latest_ai_analysis"] is None
    assert data_clean["latest_ai_analysis"] is None
    # Every other field of the payload is fixture-identical too (same
    # records_count/stage/etc.) — nothing besides the (already-equal) null
    # field distinguishes the two responses.
    for key in data_clean:
        if key in {"athlete_id", "latest"}:
            continue
        assert data_blocked[key] == data_clean[key], key


async def test_null_when_ai_disabled(session: AsyncSession) -> None:
    """`settings.ai_enabled = False` (the default) nulls the field even when
    an approved v2 row exists."""
    athlete = await seed_athlete(session, athlete_id=305)
    await seed_record(session, record_id=5, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=5, generated_at=_GEN_AT
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["latest_ai_analysis"] is None


# ---------------------------------------------------------------------------
# 2. Consent denied — denied path, NOT an error path
# ---------------------------------------------------------------------------


async def test_consent_denied_yields_no_field_but_200(
    session: AsyncSession, ai_enabled
) -> None:
    athlete = await seed_athlete(session, athlete_id=306)
    await seed_record(session, record_id=6, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=6, generated_at=_GEN_AT
    )
    # Parent linked but with NO ParentalConsent row at all → denied by
    # `athlete_has_ai_processing_consent` (degenerate "no consent" case).
    await link_parent(session, parent_user_id=50, athlete_id=athlete.id)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["latest_ai_analysis"] is None
    # Denied-path assertion: this is not an error response.
    assert "detail" not in data


async def test_consent_withdrawn_yields_no_field_but_200(
    session: AsyncSession, ai_enabled
) -> None:
    """Same as above but via an explicit `third_party_sharing=False` consent
    row, rather than the degenerate "no row at all" case."""
    athlete = await seed_athlete(session, athlete_id=307)
    await seed_record(session, record_id=7, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=7, generated_at=_GEN_AT
    )
    await link_parent(session, parent_user_id=51, athlete_id=athlete.id)
    await grant_consent(
        session, athlete_id=athlete.id, parent_user_id=51, third_party_sharing=False
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    assert resp.json()["latest_ai_analysis"] is None


# ---------------------------------------------------------------------------
# 3. Staleness — both triggers independently, plus the not-stale case
# ---------------------------------------------------------------------------


async def test_is_stale_true_on_newer_record(session: AsyncSession, ai_enabled) -> None:
    """A newer measurement exists than the one the cached analysis covers."""
    athlete = await seed_athlete(session, athlete_id=308)
    older = await seed_record(
        session,
        record_id=8,
        athlete_id=athlete.id,
        evaluation_date=_TODAY - timedelta(days=90),
    )
    await seed_record(session, record_id=9, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session,
        athlete_id=athlete.id,
        record_id=older.id,
        generated_at=_GEN_AT,
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    analysis = resp.json()["latest_ai_analysis"]
    assert analysis is not None
    assert analysis["record_id"] == older.id
    assert analysis["is_stale"] is True


async def test_is_stale_true_on_corrected_record(session: AsyncSession, ai_enabled) -> None:
    """The analysed record itself was corrected (edited) after generation —
    `AnthropometricRecord.updated_at > AthleteAIExplanation.generated_at`."""
    athlete = await seed_athlete(session, athlete_id=309)
    corrected_at = _naive(_GEN_AT) + timedelta(days=1)
    record = await seed_record(
        session,
        record_id=10,
        athlete_id=athlete.id,
        evaluation_date=_TODAY,
        updated_at=corrected_at,
    )
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=record.id, generated_at=_GEN_AT
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    analysis = resp.json()["latest_ai_analysis"]
    assert analysis is not None
    assert analysis["record_id"] == record.id
    assert analysis["is_stale"] is True


async def test_is_stale_false_when_current(session: AsyncSession, ai_enabled) -> None:
    """Neither trigger fires: same record, not edited since generation —
    written so the test can fail in both directions."""
    athlete = await seed_athlete(session, athlete_id=310)
    not_corrected_at = _GEN_AT - timedelta(days=1)
    record = await seed_record(
        session,
        record_id=11,
        athlete_id=athlete.id,
        evaluation_date=_TODAY,
        updated_at=not_corrected_at,
    )
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=record.id, generated_at=_GEN_AT
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    analysis = resp.json()["latest_ai_analysis"]
    assert analysis is not None
    assert analysis["record_id"] == record.id
    assert analysis["is_stale"] is False


# ---------------------------------------------------------------------------
# 4. Coach vs parent visibility split — all five critic_verdict values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", _ALL_VERDICTS)
async def test_coach_vs_parent_visibility_by_verdict(
    session: AsyncSession, ai_enabled, verdict: str
) -> None:
    athlete = await seed_athlete(session, athlete_id=400 + _ALL_VERDICTS.index(verdict))
    record_id = 500 + _ALL_VERDICTS.index(verdict)
    await seed_record(
        session, record_id=record_id, athlete_id=athlete.id, evaluation_date=_TODAY
    )
    await seed_explanation(
        session,
        athlete_id=athlete.id,
        record_id=record_id,
        generated_at=_GEN_AT,
        critic_verdict=verdict,
    )
    parent_user_id = 600 + _ALL_VERDICTS.index(verdict)
    await link_parent(session, parent_user_id=parent_user_id, athlete_id=athlete.id)
    await grant_consent(session, athlete_id=athlete.id, parent_user_id=parent_user_id)
    await session.commit()

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        coach_resp = await client.get(_URL.format(athlete_id=athlete.id))
    async with make_client(session, user=parent_user(user_id=parent_user_id)) as client:
        parent_resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert coach_resp.status_code == 200, coach_resp.text
    assert parent_resp.status_code == 200, parent_resp.text

    coach_analysis = coach_resp.json()["latest_ai_analysis"]
    parent_analysis = parent_resp.json()["latest_ai_analysis"]

    # Coach always sees the row, with the real verdict attached — the coach
    # is the human-in-the-loop and must be able to tell the states apart.
    assert coach_analysis is not None
    assert coach_analysis["critic_verdict"] == verdict

    if verdict in FAMILY_DELIVERABLE_VERDICTS:
        assert parent_analysis is not None
        assert parent_analysis.get("critic_verdict") is None
    else:
        assert parent_analysis is None


# ---------------------------------------------------------------------------
# 5. Non-fatal computation
# ---------------------------------------------------------------------------


async def test_survives_internal_lookup_exception(
    session: AsyncSession, ai_enabled, monkeypatch
) -> None:
    athlete = await seed_athlete(session, athlete_id=311)
    await seed_record(session, record_id=12, athlete_id=athlete.id, evaluation_date=_TODAY)
    await seed_explanation(
        session, athlete_id=athlete.id, record_id=12, generated_at=_GEN_AT
    )
    await session.commit()

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure — no identifying data here")

    monkeypatch.setattr("app.routers.growth._compute_latest_ai_analysis", _boom)

    async with make_client(session, user=coach_user(club_id=athlete.club_id)) as client:
        resp = await client.get(_URL.format(athlete_id=athlete.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["latest_ai_analysis"] is None
    # The rest of the payload is untouched by the failure.
    assert data["records_count"] == 1
    assert data["latest"] is not None


# ---------------------------------------------------------------------------
# 6. No additional per-measurement query (SC-008)
# ---------------------------------------------------------------------------


async def test_no_extra_query_per_measurement(
    session: AsyncSession, engine: AsyncEngine, ai_enabled
) -> None:
    """The AI-analysis lookup must be a fixed number of extra queries, not
    one that scales with how many measurements the athlete has (no N+1)."""
    few = await seed_athlete(session, athlete_id=312)
    await seed_record(session, record_id=13, athlete_id=few.id, evaluation_date=_TODAY)
    await seed_explanation(
        session, athlete_id=few.id, record_id=13, generated_at=_GEN_AT
    )

    many = await seed_athlete(session, athlete_id=313)
    base_date = _TODAY - timedelta(days=300)
    last_record_id = None
    for i in range(8):
        rec = await seed_record(
            session,
            record_id=100 + i,
            athlete_id=many.id,
            evaluation_date=base_date + timedelta(days=30 * i),
        )
        last_record_id = rec.id
    await seed_explanation(
        session, athlete_id=many.id, record_id=last_record_id, generated_at=_GEN_AT
    )
    await session.commit()

    async with make_client(session, user=coach_user(club_id=few.club_id)) as client:
        async with count_selects(engine) as counter_few:
            resp_few = await client.get(_URL.format(athlete_id=few.id))
        few_count = counter_few[0]

    async with make_client(session, user=coach_user(club_id=many.club_id)) as client:
        async with count_selects(engine) as counter_many:
            resp_many = await client.get(_URL.format(athlete_id=many.id))
        many_count = counter_many[0]

    assert resp_few.status_code == 200, resp_few.text
    assert resp_many.status_code == 200, resp_many.text
    assert resp_few.json()["latest_ai_analysis"] is not None
    assert resp_many.json()["latest_ai_analysis"] is not None

    # 8 measurements vs 1 measurement must issue the exact same number of
    # SELECTs — the AI-analysis lookup (and every other query on this path)
    # is bounded by `.limit(...)`, never by `records_count`.
    assert many_count == few_count, (few_count, many_count)


# ---------------------------------------------------------------------------
# 7. Feature 046 (US2 gate, T041): the body-composition block adds at most
#    ONE query to the growth summary, and it does not scale with set count.
# ---------------------------------------------------------------------------


async def _seed_skinfold_set(
    session: AsyncSession,
    *,
    record_id: int,
    athlete_id: int,
    declined: bool = False,
    sum4: str = "30.0",
) -> None:
    from app.models.skinfold_measurement import SkinfoldMeasurement

    value = None if declined else Decimal("7.5")
    row = SkinfoldMeasurement(
        anthropometric_record_id=record_id,
        athlete_id=athlete_id,
        triceps_mm=value,
        biceps_mm=value,
        subscapular_mm=value,
        medial_calf_mm=value,
        iliac_crest_mm=value,
        supraspinale_mm=value,
        triceps_declined=declined,
        biceps_declined=declined,
        subscapular_declined=declined,
        medial_calf_declined=declined,
        iliac_crest_declined=declined,
        supraspinale_declined=declined,
        sum4_mm=None if declined else Decimal(sum4),
        sum6_mm=None if declined else Decimal("45.0"),
        measured_by=1,
        created_at=_GEN_AT,
    )
    session.add(row)
    await session.flush()


async def test_body_composition_adds_at_most_one_query(
    session: AsyncSession, engine: AsyncEngine
) -> None:
    """SC-008 extended to feature 046 (T041, re-checked by T080).

    Since T080 the growth summary loads every record WITH its skinfold set in
    ONE SELECT (`body_composition.load_athlete_records`, LEFT JOIN +
    `contains_eager`) that replaces the pre-046 `LIMIT 2` records query, and
    the shared `load_reading` adds only the FUPRECOL reference lookup (one
    SELECT for both sites). So: an athlete without skinfolds costs exactly
    the pre-046 path; with a counted set the summary costs at most ONE SELECT
    more; and 1 set vs 3 sets (one fully declined) costs the same."""
    one = await seed_athlete(session, athlete_id=412)
    await seed_record(
        session, record_id=40, athlete_id=one.id, evaluation_date=_TODAY - timedelta(days=10)
    )
    await _seed_skinfold_set(session, record_id=40, athlete_id=one.id)

    three = await seed_athlete(session, athlete_id=413)
    base_date = _TODAY - timedelta(days=400)
    for i in range(3):
        await seed_record(
            session,
            record_id=50 + i,
            athlete_id=three.id,
            evaluation_date=base_date + timedelta(days=120 * i),
        )
        await _seed_skinfold_set(
            session,
            record_id=50 + i,
            athlete_id=three.id,
            declined=(i == 2),
            sum4=str(30 + i),
        )

    # Same record history, no skinfold sets: the pre-046 cost.
    none = await seed_athlete(session, athlete_id=414)
    for i in range(3):
        await seed_record(
            session,
            record_id=60 + i,
            athlete_id=none.id,
            evaluation_date=base_date + timedelta(days=120 * i),
        )
    await session.commit()
    # Empty identity map so relationship loaders really hit the DB (otherwise
    # a many-to-one `selectinload` is served from memory and a regression to
    # two SELECTs would go unnoticed).
    session.expunge_all()

    async def _count(athlete_id: int, club_id: int) -> tuple[int, dict]:
        async with make_client(session, user=coach_user(club_id=club_id)) as client:
            async with count_selects(engine) as counter:
                resp = await client.get(_URL.format(athlete_id=athlete_id))
        assert resp.status_code == 200, resp.text
        return counter[0], resp.json()

    one_count, one_body = await _count(one.id, one.club_id)
    three_count, three_body = await _count(three.id, three.club_id)
    baseline_count, baseline_body = await _count(none.id, none.club_id)
    assert one_body["body_composition"]["has_data"] is True
    assert three_body["body_composition"]["has_data"] is True
    assert three_body["body_composition"]["latest_attempt_declined"] is not None
    assert baseline_body["body_composition"]["has_data"] is False
    assert one_count == three_count, (one_count, three_count)
    assert three_count - baseline_count <= 1, (baseline_count, three_count)
