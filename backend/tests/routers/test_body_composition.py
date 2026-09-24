"""Contract tests for the skinfold capture endpoints (feature 046, T018).

Source of truth: ``specs/046-body-composition-skinfolds/contracts/
skinfolds-api.md`` §1-§3. Strategy mirrors ``tests/routers/
test_anthropometry_bmi.py``: a minimal `FastAPI` app mounting both
`anthropometry.router` and `body_composition.router` over a real aiosqlite
in-memory engine, with `get_db`/`get_current_user` overridden per test so
`verify_athlete_access`'s real club/parent-link logic still runs (needed to
exercise the 403 paths honestly instead of stubbing them away).

Privacy: every athlete here is synthetic (`Test Atleta`), no real names.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.models import Base
from app.models.anthropometry import AnthropometricRecord, MaturationStatus
from app.models.athlete import Athlete, FamilyRelationship, ParentAthlete, Sex
from app.models.audit_log import AuditLog
from app.models.club import Club, ClubRole
from app.models.growth import GrowthIndicator, GrowthReferenceLms, GrowthSource
from app.models.user import UserRole
from app.routers import anthropometry as anthropometry_router
from app.routers import body_composition as body_composition_router
from app.routers import growth as growth_router
from app.routers import reports as reports_router
from tests.helpers.audit_tables import AUDIT_TABLES

HOME_CLUB_ID = 1
OTHER_CLUB_ID = 2

_VALID_SITES = {
    "triceps": {"readings": [8.5, 9.0]},
    "biceps": {"readings": [5.0, 5.0]},
    "subscapular": {"readings": [7.0, 7.5]},
    "medial_calf": {"readings": [10.0, 10.5]},
    "iliac_crest": {"declined": True},
    "supraspinale": {"readings": [6.0, 6.5]},
}


def _valid_body() -> dict:
    return {"caliper_model": "slim_guide", "sites": {k: dict(v) for k, v in _VALID_SITES.items()}}


def make_user(role: UserRole, user_id: int, club_ids: tuple[int, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=ClubRole.coach) for cid in club_ids
        ],
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
        Base.metadata.tables[t]
        for t in (
            "athletes",
            "anthropometric_records",
            "skinfold_measurements",
            "parent_athlete",
            "growth_reference_lms",
            # Needed by the referral-note endpoint's weekly-hours query
            # (T045) — otherwise unrelated to skinfold capture.
            "training_sessions",
            "session_attendance",
            # Needed by GET .../report/pdf (T049) — reports.router::_get_club.
            "clubs",
            *AUDIT_TABLES,
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def athlete(session_factory) -> Athlete:
    async with session_factory() as s:
        ath = Athlete(
            user_id=1,
            first_name="Test",
            last_name="Atleta",
            birth_date=date(2015, 1, 1),  # ~11.3 años en evaluation_date=2026-05-01
            sex=Sex.M,
            club_id=HOME_CLUB_ID,
            created_by=1,
        )
        s.add(ath)
        await s.commit()
        await s.refresh(ath)
        s.expunge(ath)
        return ath


async def _create_record(
    session_factory,
    athlete_id: int,
    evaluation_date: date,
    weight_kg: str = "40.0",
) -> int:
    async with session_factory() as s:
        record = AnthropometricRecord(
            athlete_id=athlete_id,
            evaluation_date=evaluation_date,
            weight_kg=Decimal(weight_kg),
            standing_height_cm=Decimal("150.0"),
            sitting_height_cm=Decimal("76.0"),
            leg_length_cm=Decimal("74.0"),
            leg_sitting_ratio=Decimal("0.9737"),
            maturity_offset=Decimal("-2.5"),
            age_at_phv=Decimal("13.8"),
            maturation_status=MaturationStatus.pre_phv,
            evaluated_by=1,
        )
        s.add(record)
        await s.commit()
        await s.refresh(record)
        return record.id


@pytest_asyncio.fixture
async def record_id(session_factory, athlete) -> int:
    return await _create_record(session_factory, athlete.id, date(2026, 5, 1))


def _build_app(session_factory, current_user) -> FastAPI:
    app = FastAPI()
    app.include_router(anthropometry_router.router, prefix="/api/athletes")
    app.include_router(body_composition_router.router, prefix="/api/athletes")
    app.include_router(body_composition_router.field_guide_router, prefix="/api/body-composition")
    app.include_router(growth_router.router, prefix="/api")
    app.include_router(reports_router.router, prefix="/api/athletes")

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


@pytest_asyncio.fixture
async def coach_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    coach = make_user(UserRole.coach, user_id=1, club_ids=(HOME_CLUB_ID,))
    app = _build_app(session_factory, coach)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def foreign_coach_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    coach = make_user(UserRole.coach, user_id=2, club_ids=(OTHER_CLUB_ID,))
    app = _build_app(session_factory, coach)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def parent_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _url(athlete_id: int, record_id: int) -> str:
    return f"/api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds"


# ---------------------------------------------------------------------------
# Happy path: create, replace, delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_happy_path_returns_sum4_and_estimates(coach_client, athlete, record_id):
    resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sum4_mm"] is not None
    assert body["sum6_mm"] is None  # iliac_crest declined -> Σ6 incompleto
    assert body["body_fat_pct"] is not None
    assert body["fat_mass_kg"] is not None
    assert body["fat_free_mass_kg"] is not None
    assert body["equation_version"] == "slaughter_tc_1988_v1"
    assert body["sites"]["iliac_crest"]["declined"] is True
    assert body["sites"]["iliac_crest"]["value_mm"] is None
    assert body["sites"]["triceps"]["value_mm"] == pytest.approx(8.8, abs=0.01)


@pytest.mark.asyncio
async def test_put_again_replaces(coach_client, athlete, record_id):
    first = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert first.status_code == 200

    replacement = _valid_body()
    replacement["sites"]["triceps"] = {"readings": [10.0, 10.0]}
    second = await coach_client.put(_url(athlete.id, record_id), json=replacement)
    assert second.status_code == 200, second.text
    assert second.json()["sites"]["triceps"]["value_mm"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_delete_then_404(coach_client, athlete, record_id):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    delete_resp = await coach_client.delete(_url(athlete.id, record_id))
    assert delete_resp.status_code == 204

    second_delete = await coach_client.delete(_url(athlete.id, record_id))
    assert second_delete.status_code == 404


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parent_put_forbidden(parent_client, athlete, record_id):
    resp = await parent_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_coach_of_another_club_forbidden(foreign_coach_client, athlete, record_id):
    resp = await foreign_coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_record_of_another_athlete_is_404(coach_client, session_factory, athlete):
    async with session_factory() as s:
        other = Athlete(
            user_id=99,
            first_name="Otro",
            last_name="Atleta",
            birth_date=date(2015, 1, 1),
            sex=Sex.M,
            club_id=HOME_CLUB_ID,
            created_by=1,
        )
        s.add(other)
        await s.commit()
        await s.refresh(other)
        other_id = other.id
    other_record_id = await _create_record(session_factory, other_id, date(2026, 5, 1))

    # record belongs to `other`, not to `athlete` -> 404 under athlete.id's path
    resp = await coach_client.put(_url(athlete.id, other_record_id), json=_valid_body())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Validation (422)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_reading_is_422(coach_client, athlete, record_id):
    body = _valid_body()
    body["sites"]["triceps"] = {"readings": [8.5]}
    resp = await coach_client.put(_url(athlete.id, record_id), json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_four_readings_is_422(coach_client, athlete, record_id):
    body = _valid_body()
    body["sites"]["triceps"] = {"readings": [8.5, 9.0, 9.5, 10.0]}
    resp = await coach_client.put(_url(athlete.id, record_id), json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reading_below_minimum_is_422(coach_client, athlete, record_id):
    body = _valid_body()
    body["sites"]["triceps"] = {"readings": [1.5, 9.0]}
    resp = await coach_client.put(_url(athlete.id, record_id), json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Domain conflicts (409)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_athlete_too_young_is_409(coach_client, session_factory):
    async with session_factory() as s:
        young = Athlete(
            user_id=42,
            first_name="Joven",
            last_name="Atleta",
            birth_date=date(2017, 6, 6),  # ~8.9 años en 2026-05-01
            sex=Sex.M,
            club_id=HOME_CLUB_ID,
            created_by=1,
        )
        s.add(young)
        await s.commit()
        await s.refresh(young)
        young_id = young.id
    young_record_id = await _create_record(session_factory, young_id, date(2026, 5, 1))

    resp = await coach_client.put(_url(young_id, young_record_id), json=_valid_body())
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "athlete_too_young"


@pytest.mark.asyncio
async def test_interval_too_short_is_409_with_next_allowed_date(
    coach_client, session_factory, athlete
):
    first_date = date(2026, 5, 1)
    first_record_id = await _create_record(session_factory, athlete.id, first_date)
    first_resp = await coach_client.put(_url(athlete.id, first_record_id), json=_valid_body())
    assert first_resp.status_code == 200

    second_date = first_date + timedelta(days=30)
    second_record_id = await _create_record(session_factory, athlete.id, second_date)
    second_resp = await coach_client.put(_url(athlete.id, second_record_id), json=_valid_body())

    assert second_resp.status_code == 409
    detail = second_resp.json()["detail"]
    assert detail["code"] == "skinfold_interval_too_short"
    assert detail["next_allowed_date"] == (first_date + timedelta(days=90)).isoformat()


# ---------------------------------------------------------------------------
# Audit log — no values, ids + site count only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_row_has_no_readings_or_values(coach_client, session_factory, athlete, record_id):
    resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert resp.status_code == 200

    async with session_factory() as s:
        result = await s.execute(select(AuditLog).order_by(AuditLog.id.desc()))
        rows = list(result.scalars().all())
    assert rows, "se esperaba al menos una fila de auditoría"
    latest = rows[0]
    meta = latest.meta_json or {}
    meta_text = str(meta)
    # Ninguna lectura cruda (mm) ni nombre debe aparecer en el meta_json.
    assert "8.5" not in meta_text and "9.0" not in meta_text
    assert "Atleta" not in meta_text and "Test" not in meta_text
    assert meta.get("site_count") == 5  # 6 sitios - 1 declinado (iliac_crest)


# ---------------------------------------------------------------------------
# GET .../anthropometry — coach sees skinfolds, parent sees null
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_anthropometry_coach_includes_skinfolds(coach_client, athlete, record_id):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    resp = await coach_client.get(f"/api/athletes/{athlete.id}/anthropometry")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["skinfolds"] is not None
    assert items[0]["skinfolds"]["sum4_mm"] is not None


@pytest.mark.asyncio
async def test_list_anthropometry_parent_sees_null_skinfolds(
    session_factory, athlete, record_id, coach_client
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    # Vincular al padre con el atleta para que verify_athlete_access lo deje pasar.
    from app.models.athlete import FamilyRelationship, ParentAthlete

    async with session_factory() as s:
        link = ParentAthlete(
            parent_id=3,
            athlete_id=athlete.id,
            relationship_type=FamilyRelationship.padre,
        )
        s.add(link)
        await s.commit()

    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/athletes/{athlete.id}/anthropometry")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["skinfolds"] is None


# ---------------------------------------------------------------------------
# GET .../body-composition (feature 046, T033/T035)
# ---------------------------------------------------------------------------


def _body_composition_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/body-composition"


def _growth_summary_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/growth-summary"


@pytest.mark.asyncio
async def test_get_body_composition_coach_happy_path(coach_client, session_factory, athlete):
    first_date = date(2026, 5, 1)
    first_record_id = await _create_record(session_factory, athlete.id, first_date)
    first_put = await coach_client.put(_url(athlete.id, first_record_id), json=_valid_body())
    assert first_put.status_code == 200

    second_date = first_date + timedelta(days=90)
    second_record_id = await _create_record(session_factory, athlete.id, second_date, weight_kg="42.0")
    second_body = _valid_body()
    second_body["sites"]["triceps"] = {"readings": [7.0, 7.0]}
    second_put = await coach_client.put(_url(athlete.id, second_record_id), json=second_body)
    assert second_put.status_code == 200

    resp = await coach_client.get(_body_composition_url(athlete.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["sets"]) == 2
    assert len(body["series"]["sum4"]) == 2  # ambos sets tienen Σ4 completo
    assert body["reading"]["sum_change_code"] in {"within_noise", "up_real", "down_real"}
    assert body["estimates_latest"]["margin_pct"] == 4
    assert body["reference"]["side"] == "izquierdo"


@pytest.mark.asyncio
async def test_get_body_composition_parent_forbidden(
    parent_client, session_factory, athlete, record_id, coach_client
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    async with session_factory() as s:
        link = ParentAthlete(
            parent_id=3,
            athlete_id=athlete.id,
            relationship_type=FamilyRelationship.padre,
        )
        s.add(link)
        await s.commit()

    resp = await parent_client.get(_body_composition_url(athlete.id))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_body_composition_no_sets_has_no_data_shape(coach_client, athlete, record_id):
    resp = await coach_client.get(_body_composition_url(athlete.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sets"] == []
    assert body["series"] is None
    assert body["reading"] is None
    assert body["next_due_date"] is None


# ---------------------------------------------------------------------------
# GET .../growth-summary — body_composition block (feature 046, T033/T036)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_growth_summary_coach_includes_body_composition_sum4(
    coach_client, athlete, record_id
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    resp = await coach_client.get(_growth_summary_url(athlete.id))
    assert resp.status_code == 200, resp.text
    body_composition = resp.json()["body_composition"]
    assert body_composition["has_data"] is True
    assert body_composition["sum4_mm"] is not None


@pytest.mark.asyncio
async def test_growth_summary_parent_body_composition_has_exactly_five_family_keys(
    session_factory, athlete, record_id, coach_client
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    async with session_factory() as s:
        link = ParentAthlete(
            parent_id=3,
            athlete_id=athlete.id,
            relationship_type=FamilyRelationship.padre,
        )
        s.add(link)
        await s.commit()

    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(_growth_summary_url(athlete.id))
    assert resp.status_code == 200, resp.text

    body_composition = resp.json()["body_composition"]
    assert set(body_composition.keys()) == {
        "has_data",
        "latest_set_date",
        "family_band",
        "family_label",
        "family_sentence",
    }
    assert "band" not in body_composition
    assert re.search(r"\d", body_composition["family_sentence"]) is None


# ---------------------------------------------------------------------------
# Band scenarios A-D (contracts/body-composition-reading.md §5) and the
# referral-note PDF (feature 046, T042/T044/T045)
# ---------------------------------------------------------------------------


async def _create_athlete_row(
    session_factory, *, sex: Sex, birth_date: date, user_id: int
) -> Athlete:
    async with session_factory() as s:
        ath = Athlete(
            user_id=user_id,
            first_name="Test",
            last_name=f"Atleta{user_id}",
            birth_date=birth_date,
            sex=sex,
            club_id=HOME_CLUB_ID,
            created_by=1,
        )
        s.add(ath)
        await s.commit()
        await s.refresh(ath)
        s.expunge(ath)
        return ath


async def _create_record_scored(
    session_factory,
    athlete_id: int,
    evaluation_date: date,
    *,
    weight_kg: str = "40.0",
    standing_height_cm: str = "150.0",
    maturation_status: MaturationStatus = MaturationStatus.pre_phv,
) -> int:
    """Same shape as `_create_record`, with weight/height/stage overridable
    for the band scenarios below (contract §5 needs a specific weight and
    height delta between the two records, not the fixture defaults)."""
    sitting_height_cm = Decimal("76.0")
    leg_length_cm = Decimal(standing_height_cm) - sitting_height_cm
    async with session_factory() as s:
        record = AnthropometricRecord(
            athlete_id=athlete_id,
            evaluation_date=evaluation_date,
            weight_kg=Decimal(weight_kg),
            standing_height_cm=Decimal(standing_height_cm),
            sitting_height_cm=sitting_height_cm,
            leg_length_cm=leg_length_cm,
            leg_sitting_ratio=leg_length_cm / sitting_height_cm,
            maturity_offset=Decimal("-2.5"),
            age_at_phv=Decimal("13.8"),
            maturation_status=maturation_status,
            evaluated_by=1,
        )
        s.add(record)
        await s.commit()
        await s.refresh(record)
        return record.id


def _sum4_body(triceps: float, biceps: float, subscapular: float, medial_calf: float) -> dict:
    return {
        "caliper_model": "slim_guide",
        "sites": {
            "triceps": {"readings": [triceps, triceps]},
            "biceps": {"readings": [biceps, biceps]},
            "subscapular": {"readings": [subscapular, subscapular]},
            "medial_calf": {"readings": [medial_calf, medial_calf]},
            "iliac_crest": {"declined": True},
            "supraspinale": {"declined": True},
        },
    }


@pytest.mark.asyncio
async def test_band_scenario_a_girl_circa_to_post_phv_is_verde(session_factory, coach_client):
    girl = await _create_athlete_row(
        session_factory, sex=Sex.F, birth_date=date(2013, 5, 1), user_id=10
    )
    d0 = date(2026, 5, 1)
    record1 = await _create_record_scored(
        session_factory, girl.id, d0, weight_kg="38.0", standing_height_cm="148.0",
        maturation_status=MaturationStatus.circa_phv,
    )
    put1 = await coach_client.put(_url(girl.id, record1), json=_sum4_body(9, 6, 9, 8))
    assert put1.status_code == 200, put1.text

    d1 = d0 + timedelta(days=90)
    record2 = await _create_record_scored(
        session_factory, girl.id, d1, weight_kg="42.5", standing_height_cm="152.5",
        maturation_status=MaturationStatus.circa_phv,
    )
    put2 = await coach_client.put(_url(girl.id, record2), json=_sum4_body(11, 7, 11, 10))
    assert put2.status_code == 200, put2.text

    resp = await coach_client.get(_body_composition_url(girl.id))
    assert resp.status_code == 200, resp.text
    reading = resp.json()["reading"]
    assert reading["band"] == "verde"
    assert reading["band_reason_code"] == "expected_pubertal_gain"
    assert reading["family_band"] == "verde"


@pytest.mark.asyncio
async def test_band_scenario_b_boy_post_phv_is_verde(session_factory, coach_client, athlete):
    d0 = date(2026, 5, 1)
    record1 = await _create_record_scored(
        session_factory, athlete.id, d0, weight_kg="45.0", standing_height_cm="158.0",
        maturation_status=MaturationStatus.post_phv,
    )
    put1 = await coach_client.put(_url(athlete.id, record1), json=_sum4_body(8, 5, 8, 7))
    assert put1.status_code == 200, put1.text

    d1 = d0 + timedelta(days=90)
    record2 = await _create_record_scored(
        session_factory, athlete.id, d1, weight_kg="49.5", standing_height_cm="161.0",
        maturation_status=MaturationStatus.post_phv,
    )
    put2 = await coach_client.put(_url(athlete.id, record2), json=_sum4_body(7.5, 5, 7.5, 7))
    assert put2.status_code == 200, put2.text

    resp = await coach_client.get(_body_composition_url(athlete.id))
    assert resp.status_code == 200, resp.text
    reading = resp.json()["reading"]
    assert reading["band"] == "verde"
    assert reading["band_reason_code"] == "post_phv_lean_gain"
    assert reading["family_band"] == "verde"


@pytest.mark.asyncio
async def test_band_scenario_c_energy_availability_is_rojo(session_factory, coach_client, athlete):
    d0 = date(2026, 5, 1)
    record1 = await _create_record_scored(
        session_factory, athlete.id, d0, weight_kg="40.0", standing_height_cm="145.0",
    )
    put1 = await coach_client.put(_url(athlete.id, record1), json=_sum4_body(9.0, 5.5, 8.5, 7.0))
    assert put1.status_code == 200, put1.text

    d1 = d0 + timedelta(days=90)
    record2 = await _create_record_scored(
        session_factory, athlete.id, d1, weight_kg="40.5", standing_height_cm="148.5",
    )
    put2 = await coach_client.put(_url(athlete.id, record2), json=_sum4_body(6.0, 4.0, 6.0, 6.0))
    assert put2.status_code == 200, put2.text

    resp = await coach_client.get(_body_composition_url(athlete.id))
    assert resp.status_code == 200, resp.text
    reading = resp.json()["reading"]
    assert reading["band"] == "rojo"
    assert reading["band_reason_code"] == "energy_availability_pattern"
    assert reading["family_band"] == "ambar"
    # T049: aunque el coach ve `band == "rojo"`, el body de la respuesta (que
    # incluye el proyectado `family_*`) nunca lleva el lenguaje de escalación
    # clínica — ese texto solo existe en `COACH_REASON_COPY`/`ESCALATION_COPY`.
    assert "Requiere acompañamiento profesional" not in resp.text
    assert "profesional de la salud" not in resp.text

    # T049: la superficie que realmente ve la familia es growth-summary como padre.
    async with session_factory() as s:
        s.add(ParentAthlete(
            parent_id=3,
            athlete_id=athlete.id,
            relationship_type=FamilyRelationship.padre,
        ))
        await s.commit()
    parent_app = _build_app(session_factory, make_user(UserRole.parent, user_id=3))
    async with AsyncClient(transport=ASGITransport(app=parent_app), base_url="http://test") as ac:
        parent_resp = await ac.get(_growth_summary_url(athlete.id))
    assert parent_resp.status_code == 200, parent_resp.text
    family_block = parent_resp.json()["body_composition"]
    assert family_block["family_band"] == "ambar"
    assert "band" not in family_block
    assert "rojo" not in parent_resp.text
    assert "Requiere acompañamiento profesional" not in parent_resp.text
    assert "profesional de la salud" not in parent_resp.text


async def _seed_triceps_reference(session_factory, *, sex: str, age_months: float) -> None:
    """Two bracketing LMS rows (same L/M/S so interpolation at `age_months`
    is exact) chosen so triceps_mm=15.0 lands above P95 (`high_extreme`)."""
    async with session_factory() as s:
        for delta in (-6.0, 6.0):
            s.add(
                GrowthReferenceLms(
                    source=GrowthSource.FUPRECOL,
                    indicator=GrowthIndicator.triceps_skinfold_for_age,
                    sex=sex,
                    age_months=age_months + delta,
                    L=0.0,
                    M=8.0,
                    S=0.3,
                )
            )
        await s.commit()


@pytest.mark.asyncio
async def test_band_scenario_d_single_set_reference_extreme_is_ambar_family_verde(
    session_factory, coach_client
):
    # Age exactly 10.0 years (120 months) at evaluation_date, matching the
    # bracketing LMS rows seeded below (108-216 month FUPRECOL range).
    boy = await _create_athlete_row(
        session_factory, sex=Sex.M, birth_date=date(2016, 5, 1), user_id=11
    )
    await _seed_triceps_reference(session_factory, sex="M", age_months=120.0)

    d0 = date(2026, 5, 1)
    record1 = await _create_record_scored(session_factory, boy.id, d0)
    # triceps=15mm -> z ~= ln(15/8)/0.3 ~= 2.1 -> percentile ~98 (>= P95).
    put1 = await coach_client.put(_url(boy.id, record1), json=_sum4_body(15.0, 6.0, 6.0, 6.0))
    assert put1.status_code == 200, put1.text

    resp = await coach_client.get(_body_composition_url(boy.id))
    assert resp.status_code == 200, resp.text
    reading = resp.json()["reading"]
    assert reading["band"] == "ambar"
    assert reading["band_reason_code"] == "reference_extreme"
    assert reading["family_band"] == "verde"


def _referral_note_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/body-composition/referral-note.pdf"


@pytest.mark.asyncio
async def test_referral_note_coach_happy_path_no_percent_no_mm(session_factory, coach_client, athlete):
    d0 = date(2026, 5, 1)
    record1 = await _create_record_scored(
        session_factory, athlete.id, d0, weight_kg="40.0", standing_height_cm="145.0",
    )
    put1 = await coach_client.put(_url(athlete.id, record1), json=_sum4_body(9.0, 5.5, 8.5, 7.0))
    assert put1.status_code == 200, put1.text

    d1 = d0 + timedelta(days=90)
    record2 = await _create_record_scored(
        session_factory, athlete.id, d1, weight_kg="40.5", standing_height_cm="148.5",
    )
    put2 = await coach_client.put(_url(athlete.id, record2), json=_sum4_body(6.0, 4.0, 6.0, 6.0))
    assert put2.status_code == 200, put2.text

    resp = await coach_client.get(_referral_note_url(athlete.id))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"

    import io
    import re

    import pdfplumber

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "no incluye un diagnóstico" in text.lower()
    # Iniciales únicamente ("T.A." para Test Atleta) — nunca el nombre completo.
    assert "T.A." in text
    assert "Test Atleta" not in text
    assert re.search(r"\d+\s*%", text) is None
    assert re.search(r"\d+(?:[.,]\d+)?\s*mm", text) is None

    async with session_factory() as s:
        rows = (await s.execute(select(AuditLog))).scalars().all()
    referral_rows = [r for r in rows if r.meta_json and r.meta_json.get("event_type") == "skinfolds.referral_note_generated"]
    assert len(referral_rows) == 1


@pytest.mark.asyncio
async def test_referral_note_parent_forbidden(session_factory, athlete, record_id, coach_client, parent_client):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    async with session_factory() as s:
        link = ParentAthlete(
            parent_id=3,
            athlete_id=athlete.id,
            relationship_type=FamilyRelationship.padre,
        )
        s.add(link)
        await s.commit()

    resp = await parent_client.get(_referral_note_url(athlete.id))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_referral_note_no_data_is_409(coach_client, athlete, record_id):
    resp = await coach_client.get(_referral_note_url(athlete.id))
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "no_skinfold_data"


# ---------------------------------------------------------------------------
# GET /api/body-composition/field-guide.pdf (feature 046, US5, T055)
# ---------------------------------------------------------------------------

_FIELD_GUIDE_URL = "/api/body-composition/field-guide.pdf"


@pytest.mark.asyncio
async def test_field_guide_coach_happy_path_lists_six_sites_no_athlete_data(coach_client):
    resp = await coach_client.get(_FIELD_GUIDE_URL)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["cache-control"] == "private, max-age=86400"

    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        # El instructivo debe caber en exactamente 2 páginas (hoja impresa
        # a doble cara en la estación de medición).
        assert len(pdf.pages) == 2
        images = [img for page in pdf.pages for img in page.images]
        d_tags = [
            w for page in pdf.pages for w in page.extract_words() if w["text"] == "D"
        ]

    for label in (
        "Tríceps",
        "Bíceps",
        "Subescapular",
        "Pantorrilla",
        "Cresta ilíaca",
        "Supraespinal",
    ):
        assert label in text
    assert "no contiene datos de ningún deportista" in text

    # El marcador «D» (lado derecho) está presente en cada sitio.
    assert len(d_tags) >= 6
    # Una ilustración PNG por sitio, cuadrada y de ~45 mm de lado.
    assert len(images) == 6
    for img in images:
        width_mm = (img["x1"] - img["x0"]) * 25.4 / 72
        height_mm = (img["bottom"] - img["top"]) * 25.4 / 72
        assert 44 <= width_mm <= 46
        assert abs(width_mm - height_mm) < 0.5


def test_field_guide_sites_context_points_to_existing_png():
    """`illustration` es una ruta relativa a `templates/` con PNG real por sitio."""
    from app.routers.body_composition import _build_field_guide_sites
    from app.services.notification.document_generator import _TEMPLATES_ROOT

    sites = _build_field_guide_sites()
    assert len(sites) == 6
    for site in sites:
        rel = site["illustration"]
        assert rel == f"documents/pdf/diagrams/img/skinfold_{site['key']}.png"
        assert (_TEMPLATES_ROOT / rel).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# T049 — parent-surface privacy regression tests (feature 046, US4 gate)
# ---------------------------------------------------------------------------


def _anthropometry_list_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/anthropometry"


async def _link_parent(session_factory, athlete_id: int, parent_id: int = 3) -> None:
    async with session_factory() as s:
        s.add(
            ParentAthlete(
                parent_id=parent_id,
                athlete_id=athlete_id,
                relationship_type=FamilyRelationship.padre,
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_parent_anthropometry_list_every_item_skinfolds_none(
    session_factory, athlete, record_id, coach_client
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    await _link_parent(session_factory, athlete.id)

    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(_anthropometry_list_url(athlete.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) >= 1
    assert all(item["skinfolds"] is None for item in body)


@pytest.mark.asyncio
async def test_parent_growth_summary_unchanged_after_newer_fully_declined_attempt(
    session_factory, athlete, coach_client
):
    """Scenario H (`contracts/body-composition-reading.md` §3b/§5): a fully
    declined attempt newer than the latest counted set never moves the
    family projection — it keeps reflecting the counted set."""
    d0 = date(2026, 5, 1)
    record1 = await _create_record(session_factory, athlete.id, d0)
    put1 = await coach_client.put(_url(athlete.id, record1), json=_valid_body())
    assert put1.status_code == 200

    await _link_parent(session_factory, athlete.id)
    parent = make_user(UserRole.parent, user_id=3)

    before_app = _build_app(session_factory, parent)
    before_transport = ASGITransport(app=before_app)
    async with AsyncClient(transport=before_transport, base_url="http://test") as before_ac:
        before = await before_ac.get(_growth_summary_url(athlete.id))
    assert before.status_code == 200, before.text

    d1 = d0 + timedelta(days=100)
    record2 = await _create_record(session_factory, athlete.id, d1)
    declined_body = {
        "caliper_model": "slim_guide",
        "sites": {
            site: {"declined": True}
            for site in (
                "triceps",
                "biceps",
                "subscapular",
                "medial_calf",
                "iliac_crest",
                "supraspinale",
            )
        },
    }
    put2 = await coach_client.put(_url(athlete.id, record2), json=declined_body)
    assert put2.status_code == 200, put2.text

    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(_growth_summary_url(athlete.id))
    assert resp.status_code == 200, resp.text

    before_block = before.json()["body_composition"]
    after_block = resp.json()["body_composition"]
    assert after_block == before_block
    assert after_block["latest_set_date"] == d0.isoformat()


@pytest.mark.asyncio
async def test_anthropometry_report_pdf_has_no_pliegue_or_mm_after_skinfold_set(
    session_factory, athlete, record_id, coach_client
):
    async with session_factory() as s:
        s.add(Club(id=HOME_CLUB_ID, name="Trocha y Ruta", code="TYR"))
        await s.commit()

    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200, put_resp.text

    resp = await coach_client.get(f"/api/athletes/{athlete.id}/report/pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"

    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "pliegue" not in text.lower()
    assert re.search(r"\d+(?:[.,]\d+)?\s*mm", text) is None


@pytest.mark.asyncio
async def test_unlinked_parent_gets_403_on_all_body_composition_surfaces(
    session_factory, athlete, record_id, coach_client
):
    put_resp = await coach_client.put(_url(athlete.id, record_id), json=_valid_body())
    assert put_resp.status_code == 200

    # No `ParentAthlete` link created for user_id=3 — unlinked parent.
    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        list_resp = await ac.get(_anthropometry_list_url(athlete.id))
        body_comp_resp = await ac.get(_body_composition_url(athlete.id))
        growth_summary_resp = await ac.get(_growth_summary_url(athlete.id))

    assert list_resp.status_code == 403
    assert body_comp_resp.status_code == 403
    assert growth_summary_resp.status_code == 403


@pytest.mark.asyncio
async def test_parent_of_nonexistent_athlete_gets_404(session_factory):
    """`GET .../body-composition` and the anthropometry list are coach/admin
    only (403 for any parent regardless of the athlete's existence); a
    nonexistent athlete surfaces as 404 on `growth-summary`, which — unlike
    those two — is open to `parent` and runs `verify_athlete_access` first."""
    parent = make_user(UserRole.parent, user_id=3)
    app = _build_app(session_factory, parent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        body_comp_resp = await ac.get(_body_composition_url(999_999))
        growth_summary_resp = await ac.get(_growth_summary_url(999_999))

    assert body_comp_resp.status_code == 403
    assert growth_summary_resp.status_code == 404
