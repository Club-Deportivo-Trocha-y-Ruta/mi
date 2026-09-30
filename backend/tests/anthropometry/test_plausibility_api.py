"""Feature 048 (T028): ``POST /api/athletes/{id}/anthropometry/plausibility``.

Dry-run: nunca escribe ni audita. ``previous`` es el último registro con fecha
ESTRICTAMENTE anterior a la solicitada, excluyendo ``record_id``.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.models.anthropometry import AnthropometricRecord
from app.models.athlete import Athlete
from app.models.audit_log import AuditLog
from tests.anthropometry.conftest import (
    ATHLETE_ID,
    OTHER_ATHLETE_ID,
    seed_record,
)

pytestmark = pytest.mark.asyncio


def _url(athlete_id: int = ATHLETE_ID) -> str:
    return f"/api/athletes/{athlete_id}/anthropometry/plausibility"


def _body(
    *,
    evaluation_date: str = "2026-05-01",
    weight: str = "42.0",
    standing: str = "152.0",
    sitting: str = "79.0",
    arm_span: str | None = None,
    record_id: int | None = None,
) -> dict:
    return {
        "evaluation_date": evaluation_date,
        "weight_kg": weight,
        "standing_height_cm": standing,
        "sitting_height_cm": sitting,
        "arm_span_cm": arm_span,
        "record_id": record_id,
    }


async def _counts(factory) -> tuple[int, int]:
    async with factory() as s:
        records = (await s.execute(select(func.count()).select_from(AnthropometricRecord))).scalar_one()
        audits = (await s.execute(select(func.count()).select_from(AuditLog))).scalar_one()
        return records, audits


def _pairs(resp) -> list[tuple[str, str]]:
    return [(w["code"], w["measure"]) for w in resp.json()["warnings"]]


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


async def test_dry_run_returns_warnings_and_previous_date_without_writing(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1), weight="40.0", standing="150.0")
    before = await _counts(anthro_factory)

    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(weight="50.0", standing="152.0", sitting="92.0"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_evaluation_date"] == "2026-03-01"
    assert _pairs(resp) == [
        ("weight_change_large", "weight"),  # +25 %
        ("sitting_ratio_atypical", "sitting_height"),  # 0.605
    ]
    assert set(body) == {"warnings", "previous_evaluation_date"}
    assert await _counts(anthro_factory) == before  # ni fila nueva ni auditoría


async def test_dry_run_with_clean_values_has_no_warnings(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1))
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(weight="41.0", standing="152.0", sitting="79.0"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"warnings": [], "previous_evaluation_date": "2026-03-01"}


async def test_first_evaluation_has_null_previous_and_only_ratio_rules(make_client, anthro_factory):
    async with make_client("coach") as c:
        resp = await c.post(
            _url(OTHER_ATHLETE_ID), json=_body(weight="99.0", standing="152.0", sitting="92.0")
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["previous_evaluation_date"] is None
    assert _pairs(resp) == [("sitting_ratio_atypical", "sitting_height")]


async def test_previous_is_strictly_earlier_than_requested_date(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1))
    await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1), weight="70.0")  # misma fecha: no cuenta
    await seed_record(anthro_factory, evaluation_date=date(2026, 6, 1), weight="80.0")  # posterior: no cuenta
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(evaluation_date="2026-05-01", weight="41.0"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["previous_evaluation_date"] == "2026-03-01"
    assert _pairs(resp) == []


async def test_record_id_excludes_the_edited_record_from_previous(make_client, anthro_factory):
    older = await seed_record(anthro_factory, evaluation_date=date(2026, 1, 1), weight="40.0")
    edited = await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1), weight="55.0")

    async with make_client("coach") as c:
        without = await c.post(_url(), json=_body(evaluation_date="2026-05-01", weight="41.0"))
        with_id = await c.post(
            _url(), json=_body(evaluation_date="2026-05-01", weight="41.0", record_id=edited)
        )
    # sin record_id: previous = el de 55 kg (-25.5 %)
    assert without.json()["previous_evaluation_date"] == "2026-03-01"
    assert ("weight_change_large", "weight") in _pairs(without)
    # con record_id: se ignora el registro que se edita; previous = el de enero (40 kg)
    assert with_id.json()["previous_evaluation_date"] == "2026-01-01"
    assert _pairs(with_id) == []
    assert older != edited


async def test_editing_the_latest_record_compares_against_its_own_predecessor(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 1, 1), standing="150.0")
    edited = await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1), standing="151.0")
    async with make_client("coach") as c:
        resp = await c.post(
            _url(),
            json=_body(evaluation_date="2026-03-01", weight="40.0", standing="140.0", sitting="72.8", record_id=edited),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["previous_evaluation_date"] == "2026-01-01"
    assert ("height_decreased", "standing_height") in _pairs(resp)


async def test_other_coach_of_same_club_can_run_dry_run(make_client, anthro_factory):
    """No hay autoría en un dry-run: cualquier coach con acceso al atleta."""
    async with make_client("coach2") as c:
        assert (await c.post(_url(), json=_body())).status_code == 200


# ---------------------------------------------------------------------------
# 422: solo rangos duros / imposibles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"weight": "19.9"},
        {"weight": "150.1"},
        {"standing": "99.9"},
        {"standing": "220.1"},
        {"sitting": "49.9", "standing": "110.0"},
        {"arm_span": "99.9"},
        {"arm_span": "220.1"},
    ],
)
async def test_hard_range_violation_is_422_and_writes_nothing(make_client, anthro_factory, overrides):
    before = await _counts(anthro_factory)
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(**overrides))
    assert resp.status_code == 422
    assert await _counts(anthro_factory) == before


async def test_impossible_sitting_ratio_is_422_not_a_warning(make_client):
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(standing="152.0", sitting="114.0"))  # 0.75
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["type"] == "sitting_ratio_impossible"


async def test_future_date_is_422(make_client):
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(evaluation_date="2999-01-01"))
    assert resp.status_code == 422


async def test_atypical_but_possible_ratio_is_a_warning_not_a_422(make_client):
    async with make_client("coach") as c:
        resp = await c.post(_url(), json=_body(standing="152.0", sitting="70.0"))  # 0.46
    assert resp.status_code == 200, resp.text
    assert _pairs(resp) == [("sitting_ratio_atypical", "sitting_height")]


# ---------------------------------------------------------------------------
# Rutas denegadas
# ---------------------------------------------------------------------------


async def test_parent_is_403(make_client):
    async with make_client("parent") as c:
        resp = await c.post(_url(), json=_body())
    assert resp.status_code == 403


async def test_coach_of_another_club_is_refused(make_client):
    """verify_athlete_access (feature 041) responde 403 a un coach de otro club."""
    async with make_client("foreign_coach") as c:
        resp = await c.post(_url(), json=_body())
    assert resp.status_code == 403


async def test_archived_athlete_is_404(make_client, anthro_factory):
    async with anthro_factory() as s:
        athlete = (await s.execute(select(Athlete).where(Athlete.id == OTHER_ATHLETE_ID))).scalar_one()
        athlete.deleted_at = datetime(2026, 4, 1)
        await s.commit()
    async with make_client("coach") as c:
        resp = await c.post(_url(OTHER_ATHLETE_ID), json=_body())
    assert resp.status_code == 404


async def test_unknown_athlete_is_404(make_client):
    async with make_client("coach") as c:
        resp = await c.post(_url(99999), json=_body())
    assert resp.status_code == 404
