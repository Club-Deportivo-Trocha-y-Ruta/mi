"""Feature 048 (T041): ``GET /api/anthropometry/roster?date=`` (jornada de medición).

Solo lectura, coach/admin; devuelve los atletas no archivados en alcance con
``last_evaluation_date``, ``has_record_on_date`` y ``skinfolds_eligible``, en
un número acotado de consultas (Principio IV).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.athlete import Athlete, Sex
from app.models.skinfold_measurement import SkinfoldMeasurement
from tests.anthropometry.conftest import (
    ATHLETE_ID,
    COACH_ID,
    FOREIGN_ATHLETE_ID,
    HOME_CLUB_ID,
    OTHER_ATHLETE_ID,
    seed_record,
)
from tests.fixtures.race_history_fixtures import create_athlete, create_user
from app.models.user import UserRole
from tests.helpers.query_counting import count_selects

pytestmark = pytest.mark.asyncio

_URL = "/api/anthropometry/roster"
TARGET = date(2026, 5, 1)
ROW_KEYS = {
    "athlete_id",
    "full_name",
    "category",
    "sex",
    "birth_date",
    "last_evaluation_date",
    "has_record_on_date",
    "skinfolds_eligible",
}


async def _get(make_client, user: str, day: date | str | None = TARGET):
    params = {} if day is None else {"date": str(day)}
    async with make_client(user) as c:
        return await c.get(_URL, params=params)


def _by_id(resp) -> dict[int, dict]:
    return {row["athlete_id"]: row for row in resp.json()}


async def _add_athlete(factory, athlete_id: int, birth_date: date, *, club_id: int = HOME_CLUB_ID,
                       last_name: str | None = None) -> None:
    async with factory() as s:
        await create_user(s, user_id=athlete_id, role=UserRole.athlete, can_login=False)
        await create_athlete(
            s,
            athlete_id=athlete_id,
            club_id=club_id,
            user_id=athlete_id,
            first_name="Deportista",
            last_name=last_name or f"Ficticio {athlete_id}",
            birth_date=birth_date,
            sex=Sex.F,
        )
        await s.commit()


async def _add_skinfold_set(factory, record_id: int, athlete_id: int, *, counted: bool = True) -> None:
    async with factory() as s:
        sf = SkinfoldMeasurement(
            anthropometric_record_id=record_id,
            athlete_id=athlete_id,
            triceps_mm=8 if counted else None,
            triceps_declined=not counted,
            biceps_declined=not counted,
            subscapular_declined=not counted,
            medial_calf_declined=not counted,
            iliac_crest_declined=not counted,
            supraspinale_declined=not counted,
            measured_by=COACH_ID,
        )
        s.add(sf)
        await s.commit()


# ---------------------------------------------------------------------------
# Alcance
# ---------------------------------------------------------------------------


async def test_coach_sees_only_accessible_non_archived_athletes(make_client, anthro_factory):
    await _add_athlete(anthro_factory, 300, date(2013, 1, 1))
    async with anthro_factory() as s:
        archived = (await s.execute(select(Athlete).where(Athlete.id == 300))).scalar_one()
        from datetime import datetime

        archived.deleted_at = datetime(2026, 4, 1)
        await s.commit()

    resp = await _get(make_client, "coach")
    assert resp.status_code == 200, resp.text
    ids = {row["athlete_id"] for row in resp.json()}
    assert ids == {ATHLETE_ID, OTHER_ATHLETE_ID}  # ni club 2 (200) ni archivado (300)


async def test_admin_sees_every_club_but_not_archived(make_client, anthro_factory):
    resp = await _get(make_client, "admin")
    assert {row["athlete_id"] for row in resp.json()} == {ATHLETE_ID, OTHER_ATHLETE_ID, FOREIGN_ATHLETE_ID}


async def test_foreign_coach_sees_only_own_club(make_client):
    resp = await _get(make_client, "foreign_coach")
    assert {row["athlete_id"] for row in resp.json()} == {FOREIGN_ATHLETE_ID}


async def test_rows_have_exact_contract_keys_and_are_sorted_by_last_name(make_client, anthro_factory):
    await _add_athlete(anthro_factory, 301, date(2013, 1, 1), last_name="Aaa Ficticia")
    resp = await _get(make_client, "coach")
    rows = resp.json()
    assert all(set(row) == ROW_KEYS for row in rows)
    assert [r["athlete_id"] for r in rows] == [301, OTHER_ATHLETE_ID, ATHLETE_ID]  # "Aaa" < "Ficticio Dos" < "Ficticio Uno"
    assert rows[2]["birth_date"] == "2013-05-10"
    assert rows[2]["full_name"] == "Deportista Ficticio Uno"


# ---------------------------------------------------------------------------
# has_record_on_date / last_evaluation_date
# ---------------------------------------------------------------------------


async def test_has_record_on_date_and_last_evaluation_date(make_client, anthro_factory):
    await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=date(2026, 5, 1))
    await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=date(2026, 2, 1))
    await seed_record(anthro_factory, athlete_id=OTHER_ATHLETE_ID, evaluation_date=date(2026, 4, 20))

    rows = _by_id(await _get(make_client, "coach", TARGET))
    assert rows[ATHLETE_ID]["has_record_on_date"] is True
    assert rows[ATHLETE_ID]["last_evaluation_date"] == "2026-05-01"
    assert rows[OTHER_ATHLETE_ID]["has_record_on_date"] is False
    assert rows[OTHER_ATHLETE_ID]["last_evaluation_date"] == "2026-04-20"


async def test_athlete_without_records_has_null_last_evaluation(make_client):
    rows = _by_id(await _get(make_client, "coach"))
    assert rows[ATHLETE_ID]["last_evaluation_date"] is None
    assert rows[ATHLETE_ID]["has_record_on_date"] is False


async def test_has_record_on_date_follows_the_requested_date(make_client, anthro_factory):
    await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=date(2026, 5, 1))
    other_day = _by_id(await _get(make_client, "coach", date(2026, 5, 2)))
    assert other_day[ATHLETE_ID]["has_record_on_date"] is False


# ---------------------------------------------------------------------------
# skinfolds_eligible: edad >= 9 y intervalo de 90 días abierto
# ---------------------------------------------------------------------------


async def test_skinfolds_ineligible_under_nine_years(make_client, anthro_factory):
    await _add_athlete(anthro_factory, 310, date(2017, 11, 1))  # ~8,5 años a 2026-05-01
    await _add_athlete(anthro_factory, 311, date(2016, 11, 1))  # ~9,5 años
    rows = _by_id(await _get(make_client, "coach"))
    assert rows[310]["skinfolds_eligible"] is False
    assert rows[311]["skinfolds_eligible"] is True


async def test_skinfolds_ineligible_inside_90_day_interval_and_eligible_from_day_90(make_client, anthro_factory):
    for athlete_id in (320, 321):
        await _add_athlete(anthro_factory, athlete_id, date(2013, 1, 1))
    rec_89 = await seed_record(anthro_factory, athlete_id=320, evaluation_date=TARGET - timedelta(days=89))
    rec_90 = await seed_record(anthro_factory, athlete_id=321, evaluation_date=TARGET - timedelta(days=90))
    await _add_skinfold_set(anthro_factory, rec_89, 320)
    await _add_skinfold_set(anthro_factory, rec_90, 321)

    rows = _by_id(await _get(make_client, "coach"))
    assert rows[320]["skinfolds_eligible"] is False
    assert rows[321]["skinfolds_eligible"] is True


async def test_record_without_skinfold_set_does_not_close_the_interval(make_client, anthro_factory):
    await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=TARGET - timedelta(days=10))
    rows = _by_id(await _get(make_client, "coach"))
    assert rows[ATHLETE_ID]["skinfolds_eligible"] is True


async def test_fully_declined_set_does_not_count_for_the_interval(make_client, anthro_factory):
    record = await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=TARGET - timedelta(days=10))
    await _add_skinfold_set(anthro_factory, record, ATHLETE_ID, counted=False)
    rows = _by_id(await _get(make_client, "coach"))
    assert rows[ATHLETE_ID]["skinfolds_eligible"] is True


async def test_set_after_the_requested_date_is_ignored(make_client, anthro_factory):
    record = await seed_record(anthro_factory, athlete_id=ATHLETE_ID, evaluation_date=date(2026, 6, 1))
    await _add_skinfold_set(anthro_factory, record, ATHLETE_ID)
    rows = _by_id(await _get(make_client, "coach", TARGET))
    assert rows[ATHLETE_ID]["skinfolds_eligible"] is True


# ---------------------------------------------------------------------------
# Validación y RBAC
# ---------------------------------------------------------------------------


async def test_future_date_is_422(make_client):
    resp = await _get(make_client, "coach", "2999-01-01")
    assert resp.status_code == 422


async def test_today_is_accepted_and_is_the_default(make_client):
    default = await _get(make_client, "coach", None)
    today = await _get(make_client, "coach", date.today())
    assert default.status_code == 200
    assert today.status_code == 200


async def test_invalid_date_format_is_422(make_client):
    assert (await _get(make_client, "coach", "no-es-fecha")).status_code == 422


async def test_parent_is_403(make_client):
    resp = await _get(make_client, "parent")
    assert resp.status_code == 403
    assert "Ficticio" not in resp.text


# ---------------------------------------------------------------------------
# Presupuesto de consultas (≤ 4, constante respecto al tamaño del roster)
# ---------------------------------------------------------------------------


async def _seed_roster(factory, count: int, first_id: int) -> None:
    for offset in range(count):
        athlete_id = first_id + offset
        await _add_athlete(factory, athlete_id, date(2012 + offset % 4, 3, 1))
        record = await seed_record(factory, athlete_id=athlete_id, evaluation_date=TARGET - timedelta(days=100 + offset))
        if offset % 2 == 0:
            await _add_skinfold_set(factory, record, athlete_id)


async def test_query_count_is_at_most_4_for_30_athletes_and_does_not_grow(make_client, anthro_engine, anthro_factory):
    await _seed_roster(anthro_factory, 3, first_id=400)
    async with count_selects(anthro_engine) as small:
        resp_small = await _get(make_client, "coach")
    assert resp_small.status_code == 200

    await _seed_roster(anthro_factory, 30, first_id=500)
    async with count_selects(anthro_engine) as large:
        resp_large = await _get(make_client, "coach")
    assert resp_large.status_code == 200
    assert len(resp_large.json()) >= 30

    assert large[0] <= 4, f"roster ejecutó {large[0]} SELECT"
    assert large[0] == small[0], "el número de consultas no debe crecer con el roster (N+1)"
