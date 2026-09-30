"""Feature 048 (T015): ``DELETE /api/athletes/{id}/anthropometry/{record_id}``.

Solo el evaluador o un admin; borra también el set de pliegues y las
explicaciones de IA; audita ``delete`` con ``meta={"had_skinfolds": bool}``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select

from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.audit_log import AuditLog
from app.models.skinfold_measurement import SkinfoldMeasurement
from tests.anthropometry.conftest import (
    ATHLETE_ID,
    COACH_ID,
    OTHER_ATHLETE_ID,
    VALID_SITES,
    error_code,
    seed_record,
)

pytestmark = pytest.mark.asyncio


def _url(athlete_id: int, record_id: int) -> str:
    return f"/api/athletes/{athlete_id}/anthropometry/{record_id}"


async def _add_skinfold_set(make_client, record_id: int) -> None:
    body = {"caliper_model": "slim_guide", "sites": {k: dict(v) for k, v in VALID_SITES.items()}}
    async with make_client("coach") as c:
        resp = await c.put(f"{_url(ATHLETE_ID, record_id)}/skinfolds", json=body)
    assert resp.status_code == 200, resp.text


async def _add_explanation(factory, record_id: int, use_case: str = "phv_explainer") -> None:
    async with factory() as s:
        s.add(
            AthleteAIExplanation(
                athlete_id=ATHLETE_ID,
                anthropometric_record_id=record_id,
                use_case=use_case,
                text="Texto ficticio saneado.",
                model="fake",
                provider="fake",
                generated_at=datetime.now(UTC).replace(tzinfo=None),
                age_group="12-14",
                generated_by_user_id=COACH_ID,
                maturation_status="Circa-PHV",
            )
        )
        await s.commit()


async def _count(factory, model, **filters) -> int:
    async with factory() as s:
        stmt = select(func.count()).select_from(model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(model, key) == value)
        return (await s.execute(stmt)).scalar_one()


async def _delete_audits(factory) -> list[AuditLog]:
    async with factory() as s:
        result = await s.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "anthropometric_record", AuditLog.action == "delete")
            .order_by(AuditLog.id)
        )
        return list(result.scalars())


# ---------------------------------------------------------------------------
# Éxito
# ---------------------------------------------------------------------------


async def test_evaluator_delete_is_204_and_removes_skinfolds_and_explanations(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    survivor = await seed_record(anthro_factory, evaluation_date=date(2026, 2, 1))
    await _add_skinfold_set(make_client, record_id)
    await _add_explanation(anthro_factory, record_id, "phv_explainer")
    await _add_explanation(anthro_factory, record_id, "record_analysis")
    await _add_explanation(anthro_factory, survivor)

    async with make_client("coach") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 204
    assert resp.content == b""

    assert await _count(anthro_factory, AnthropometricRecord, id=record_id) == 0
    assert await _count(anthro_factory, SkinfoldMeasurement, anthropometric_record_id=record_id) == 0
    assert await _count(anthro_factory, AthleteAIExplanation, anthropometric_record_id=record_id) == 0
    # lo de otro registro no se toca
    assert await _count(anthro_factory, AnthropometricRecord, id=survivor) == 1
    assert await _count(anthro_factory, AthleteAIExplanation, anthropometric_record_id=survivor) == 1


async def test_admin_can_delete_record_of_another_evaluator(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("admin") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 204
    assert await _count(anthro_factory, AnthropometricRecord, id=record_id) == 0


async def test_delete_audit_meta_had_skinfolds_true(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    await _add_skinfold_set(make_client, record_id)
    async with make_client("coach") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 204

    rows = await _delete_audits(anthro_factory)
    assert len(rows) == 1
    row = rows[0]
    assert row.meta_json == {"had_skinfolds": True}
    assert row.entity_id == record_id
    assert row.athlete_id == ATHLETE_ID
    assert row.actor_user_id == COACH_ID
    assert row.diff_json is None  # nunca valores de medición


async def test_delete_audit_meta_had_skinfolds_false(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach") as c:
        assert (await c.delete(_url(ATHLETE_ID, record_id))).status_code == 204
    rows = await _delete_audits(anthro_factory)
    assert [r.meta_json for r in rows] == [{"had_skinfolds": False}]


async def test_deleting_the_only_record_leaves_growth_summary_empty(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach") as c:
        before = await c.get(f"/api/athletes/{ATHLETE_ID}/growth-summary")
        assert before.status_code == 200
        assert before.json()["records_count"] == 1

        assert (await c.delete(_url(ATHLETE_ID, record_id))).status_code == 204

        after = await c.get(f"/api/athletes/{ATHLETE_ID}/growth-summary")
        listing = await c.get(f"/api/athletes/{ATHLETE_ID}/anthropometry")
    assert after.status_code == 200
    body = after.json()
    assert body["records_count"] == 0
    assert body["latest"] is None
    assert body["latest_ai_analysis"] is None
    assert listing.json() == []


async def test_second_delete_is_404(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach") as c:
        assert (await c.delete(_url(ATHLETE_ID, record_id))).status_code == 204
        assert (await c.delete(_url(ATHLETE_ID, record_id))).status_code == 404


# ---------------------------------------------------------------------------
# Rutas denegadas: el registro sigue intacto y no hay auditoría
# ---------------------------------------------------------------------------


async def test_other_coach_gets_403_not_record_author(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach2") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 403
    assert error_code(resp) == "not_record_author"
    assert await _count(anthro_factory, AnthropometricRecord, id=record_id) == 1
    assert await _delete_audits(anthro_factory) == []


async def test_parent_delete_is_403(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("parent") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 403
    assert await _count(anthro_factory, AnthropometricRecord, id=record_id) == 1


async def test_coach_of_another_club_is_refused(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("foreign_coach") as c:
        resp = await c.delete(_url(ATHLETE_ID, record_id))
    assert resp.status_code == 403  # verify_athlete_access (club scope, feature 041)
    assert await _count(anthro_factory, AnthropometricRecord, id=record_id) == 1


async def test_record_of_another_athlete_is_404(make_client, anthro_factory):
    foreign_record = await seed_record(anthro_factory, athlete_id=OTHER_ATHLETE_ID)
    async with make_client("coach") as c:
        resp = await c.delete(_url(ATHLETE_ID, foreign_record))
    assert resp.status_code == 404
    assert await _count(anthro_factory, AnthropometricRecord, id=foreign_record) == 1
