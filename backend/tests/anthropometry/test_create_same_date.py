"""Feature 048 (T028, parte POST/GET): regla de misma fecha, ratio imposible y
marcas de lectura (``can_modify`` / ``plausibility_flags``).

Research R4: dos evaluaciones del mismo atleta el mismo día nunca son
legítimas; la corrección va por PUT. ``same_values`` permite al frontend tratar
un reintento como "ya guardado".
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models.anthropometry import AnthropometricRecord
from tests.anthropometry.conftest import (
    ATHLETE_ID,
    OTHER_ATHLETE_ID,
    error_code,
    error_field,
    seed_record,
)

pytestmark = pytest.mark.asyncio

_POST = f"/api/athletes/{ATHLETE_ID}/anthropometry"


def _payload(
    *,
    evaluation_date: str = "2026-05-01",
    weight: str = "40.0",
    standing: str = "150.0",
    sitting: str = "76.0",
    arm_span: str | None = None,
) -> dict:
    body = {
        "evaluation_date": evaluation_date,
        "weight_kg": weight,
        "standing_height_cm": standing,
        "sitting_height_cm": sitting,
    }
    if arm_span is not None:
        body["arm_span_cm"] = arm_span
    return body


async def _record_count(factory, athlete_id: int = ATHLETE_ID) -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count()).select_from(AnthropometricRecord).where(
                    AnthropometricRecord.athlete_id == athlete_id
                )
            )
        ).scalar_one()


# ---------------------------------------------------------------------------
# POST misma fecha
# ---------------------------------------------------------------------------


async def test_same_date_same_values_is_409_with_same_values_true(make_client, anthro_factory):
    existing = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        # "40.00"/"150.00" == 40.0/150.0 tras la cuantización decimal
        resp = await c.post(_POST, json=_payload(weight="40.00", standing="150.00", sitting="76.00"))
    assert resp.status_code == 409
    assert error_code(resp) == "anthropometry_same_date_exists"
    assert error_field(resp, "existing_record_id") == existing
    assert error_field(resp, "same_values") is True
    assert await _record_count(anthro_factory) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"weight": "40.1"},
        {"standing": "150.1"},
        {"sitting": "76.1"},
        {"arm_span": "150.0"},  # el existente no tiene envergadura
    ],
)
async def test_same_date_different_values_is_409_with_same_values_false(make_client, anthro_factory, overrides):
    existing = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        resp = await c.post(_POST, json=_payload(**overrides))
    assert resp.status_code == 409
    assert error_code(resp) == "anthropometry_same_date_exists"
    assert error_field(resp, "existing_record_id") == existing
    assert error_field(resp, "same_values") is False
    assert await _record_count(anthro_factory) == 1


async def test_same_date_compares_arm_span_when_both_present(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1), arm_span="151.0")
    async with make_client("coach") as c:
        same = await c.post(_POST, json=_payload(arm_span="151.0"))
        other = await c.post(_POST, json=_payload(arm_span="152.0"))
    assert error_field(same, "same_values") is True
    assert error_field(other, "same_values") is False


async def test_conflict_body_does_not_echo_measurements(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        resp = await c.post(_POST, json=_payload(weight="40.0", standing="150.0", sitting="76.0"))
    assert resp.status_code == 409
    assert set(resp.json().get("detail") if isinstance(resp.json().get("detail"), dict) else resp.json()) <= {
        "detail", "code", "existing_record_id", "same_values", "message",
    }


async def test_different_date_or_different_athlete_is_created(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        other_day = await c.post(_POST, json=_payload(evaluation_date="2026-05-02"))
        other_athlete = await c.post(
            f"/api/athletes/{OTHER_ATHLETE_ID}/anthropometry", json=_payload(evaluation_date="2026-05-01")
        )
    assert other_day.status_code == 201, other_day.text
    assert other_athlete.status_code == 201, other_athlete.text
    assert await _record_count(anthro_factory) == 2


async def test_first_post_then_identical_retry_is_409_same_values(make_client, anthro_factory):
    """Escenario R4: el primer intento llegó al servidor; el reintento no duplica."""
    async with make_client("coach") as c:
        first = await c.post(_POST, json=_payload())
        retry = await c.post(_POST, json=_payload())
    assert first.status_code == 201, first.text
    assert retry.status_code == 409
    assert error_field(retry, "existing_record_id") == first.json()["id"]
    assert error_field(retry, "same_values") is True
    assert await _record_count(anthro_factory) == 1


# ---------------------------------------------------------------------------
# POST validación
# ---------------------------------------------------------------------------


async def test_post_impossible_sitting_ratio_is_422(make_client, anthro_factory):
    async with make_client("coach") as c:
        resp = await c.post(_POST, json=_payload(standing="150.0", sitting="112.5"))  # 0.75
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["type"] == "sitting_ratio_impossible"
    assert await _record_count(anthro_factory) == 0


@pytest.mark.parametrize("ratio_sitting", ["60.0", "97.5"])  # 0.40 y 0.65 (bordes inclusivos)
async def test_post_ratio_bounds_are_inclusive(make_client, ratio_sitting):
    async with make_client("coach") as c:
        resp = await c.post(_POST, json=_payload(standing="150.0", sitting=ratio_sitting))
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize(
    "overrides",
    [{"weight": "19.9"}, {"weight": "150.1"}, {"standing": "99.9"}, {"standing": "220.1"}, {"arm_span": "99.9"}],
)
async def test_post_hard_ranges_are_422(make_client, anthro_factory, overrides):
    async with make_client("coach") as c:
        resp = await c.post(_POST, json=_payload(**overrides))
    assert resp.status_code == 422
    assert await _record_count(anthro_factory) == 0


# ---------------------------------------------------------------------------
# GET lista: can_modify / plausibility_flags
# ---------------------------------------------------------------------------


async def _seed_two(factory) -> tuple[int, int]:
    clean = await seed_record(factory, evaluation_date=date(2026, 1, 1), standing="150.0", sitting="78.0")
    dropped = await seed_record(factory, evaluation_date=date(2026, 3, 1), standing="147.0", sitting="76.0")
    return clean, dropped


async def test_coach_list_has_flags_and_can_modify_for_the_evaluator(make_client, anthro_factory):
    clean, dropped = await _seed_two(anthro_factory)
    async with make_client("coach") as c:
        resp = await c.get(_POST)
    assert resp.status_code == 200, resp.text
    items = {item["id"]: item for item in resp.json()}
    assert items[clean]["plausibility_flags"] == []
    assert items[dropped]["plausibility_flags"] == ["height_decreased"]
    assert all(item["can_modify"] is True for item in items.values())


async def test_other_coach_sees_flags_but_cannot_modify(make_client, anthro_factory):
    await _seed_two(anthro_factory)
    async with make_client("coach2") as c:
        items = (await c.get(_POST)).json()
    assert len(items) == 2
    assert all(item["can_modify"] is False for item in items)
    assert any(item["plausibility_flags"] == ["height_decreased"] for item in items)


async def test_admin_can_modify_every_record(make_client, anthro_factory):
    await _seed_two(anthro_factory)
    async with make_client("admin") as c:
        items = (await c.get(_POST)).json()
    assert all(item["can_modify"] is True for item in items)


async def test_parent_list_omits_both_keys(make_client, anthro_factory):
    await _seed_two(anthro_factory)
    async with make_client("parent") as c:
        resp = await c.get(_POST)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    for item in items:
        assert "can_modify" not in item
        assert "plausibility_flags" not in item
