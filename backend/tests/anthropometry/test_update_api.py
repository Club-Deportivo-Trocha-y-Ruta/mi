"""Feature 048 (T014): ``PUT /api/athletes/{id}/anthropometry/{record_id}``.

Contrato: ``specs/048-anthropometry-capture-ux/contracts/api.md`` y research
R2/R3/R6. Solo el evaluador del registro o un admin pueden editarlo; el PUT
recalcula derivados, borra las explicaciones de IA del registro, re-aplica las
reglas de pliegues y no notifica nunca.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.ai_explanation import AthleteAIExplanation
from app.models.anthropometry import AnthropometricRecord
from app.models.audit_log import AuditLog
from app.models.skinfold_measurement import SkinfoldMeasurement
from app.services.category import compute_age_decimal
from app.services.phv import calculate_mirwald_offset
from tests.anthropometry.conftest import (
    ATHLETE_BIRTH_DATE,
    ATHLETE_ID,
    COACH_ID,
    OTHER_ATHLETE_ID,
    VALID_SITES,
    error_code,
    error_field,
    record_body,
    seed_record,
)

pytestmark = pytest.mark.asyncio


def _url(athlete_id: int, record_id: int) -> str:
    return f"/api/athletes/{athlete_id}/anthropometry/{record_id}"


def _skinfold_url(athlete_id: int, record_id: int) -> str:
    return f"{_url(athlete_id, record_id)}/skinfolds"


def _skinfold_body() -> dict:
    return {"caliper_model": "slim_guide", "sites": {k: dict(v) for k, v in VALID_SITES.items()}}


async def _add_skinfold_set(make_client, record_id: int, athlete_id: int = ATHLETE_ID) -> None:
    async with make_client("coach") as c:
        resp = await c.put(_skinfold_url(athlete_id, record_id), json=_skinfold_body())
    assert resp.status_code == 200, resp.text


async def _add_explanation(factory, athlete_id: int, record_id: int, use_case: str) -> None:
    async with factory() as s:
        s.add(
            AthleteAIExplanation(
                athlete_id=athlete_id,
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


async def _explanations(factory, record_id: int) -> list[AthleteAIExplanation]:
    async with factory() as s:
        result = await s.execute(
            select(AthleteAIExplanation).where(AthleteAIExplanation.anthropometric_record_id == record_id)
        )
        return list(result.scalars())


async def _load_record(factory, record_id: int) -> AnthropometricRecord:
    async with factory() as s:
        return (
            await s.execute(select(AnthropometricRecord).where(AnthropometricRecord.id == record_id))
        ).scalar_one()


# ---------------------------------------------------------------------------
# Happy path: recálculo de derivados
# ---------------------------------------------------------------------------


async def test_evaluator_put_recomputes_derived_fields(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)  # derivados obsoletos a propósito
    async with make_client("coach") as c:
        resp = await c.put(
            _url(ATHLETE_ID, record_id),
            json=record_body(weight="42.0", standing="156.0", sitting="80.0"),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    age = compute_age_decimal(ATHLETE_BIRTH_DATE, date(2026, 5, 1))
    phv = calculate_mirwald_offset(sex="M", age=age, weight=42.0, standing_height=156.0, sitting_height=80.0)
    assert float(body["maturity_offset"]) == pytest.approx(phv["maturity_offset"], abs=0.005)
    assert body["maturation_status"] == phv["maturation_status"]
    assert float(body["leg_length_cm"]) == pytest.approx(76.0)
    assert float(body["bmi"]) == pytest.approx(17.26, abs=0.005)  # 42 / 1.56^2

    # Percentiles OMS recalculados: z = (156/150 - 1) / 0.05 = 0.8
    stored = await _load_record(anthro_factory, record_id)
    assert float(stored.height_z_score) == pytest.approx(0.8, abs=1e-3)
    assert float(stored.bmi) == pytest.approx(17.26, abs=0.005)
    assert float(stored.weight_kg) == pytest.approx(42.0)
    assert float(stored.standing_height_cm) == pytest.approx(156.0)
    assert stored.evaluated_by == COACH_ID  # el autor no cambia


async def test_admin_can_edit_a_record_of_another_evaluator_keeping_author(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("admin") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(notes="corrección"))
    assert resp.status_code == 200, resp.text
    stored = await _load_record(anthro_factory, record_id)
    assert stored.notes == "corrección"
    assert stored.evaluated_by == COACH_ID


async def test_put_is_full_replacement_of_optional_fields(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, arm_span="150.0")
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body())  # sin arm_span
    assert resp.status_code == 200, resp.text
    assert (await _load_record(anthro_factory, record_id)).arm_span_cm is None


# ---------------------------------------------------------------------------
# Efectos secundarios: pliegues, IA, notificaciones
# ---------------------------------------------------------------------------


async def test_put_with_weight_change_recomputes_skinfold_estimates(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, weight="40.0")
    await _add_skinfold_set(make_client, record_id)
    async with anthro_factory() as s:
        before = (
            await s.execute(select(SkinfoldMeasurement).where(SkinfoldMeasurement.anthropometric_record_id == record_id))
        ).scalar_one()
    assert before.fat_mass_kg is not None
    assert before.fat_mass_kg + before.fat_free_mass_kg == Decimal("40.00")

    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(weight="46.0"))
    assert resp.status_code == 200, resp.text

    async with anthro_factory() as s:
        after = (
            await s.execute(select(SkinfoldMeasurement).where(SkinfoldMeasurement.anthropometric_record_id == record_id))
        ).scalar_one()
    assert after.body_fat_pct == before.body_fat_pct  # % de grasa depende de pliegues, no del peso
    assert after.fat_mass_kg != before.fat_mass_kg
    assert after.fat_mass_kg > before.fat_mass_kg
    assert after.fat_mass_kg + after.fat_free_mass_kg == Decimal("46.00")


async def test_put_deletes_ai_explanations_of_that_record_only(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    other_id = await seed_record(anthro_factory, evaluation_date=date(2026, 2, 1))
    await _add_explanation(anthro_factory, ATHLETE_ID, record_id, "phv_explainer")
    await _add_explanation(anthro_factory, ATHLETE_ID, record_id, "record_analysis")
    await _add_explanation(anthro_factory, ATHLETE_ID, other_id, "phv_explainer")

    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body())
    assert resp.status_code == 200, resp.text

    assert await _explanations(anthro_factory, record_id) == []
    assert len(await _explanations(anthro_factory, other_id)) == 1

    # Una fila de auditoría por explicación borrada (la tabla está en AUDIT_STRICT).
    async with anthro_factory() as s:
        deleted = (
            await s.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "athlete_ai_explanation", AuditLog.action == "delete"
                )
            )
        ).scalars().all()
    assert len(deleted) == 2


async def test_put_never_notifies_parents_even_when_crossing_circa_threshold(
    make_client, anthro_factory, anthro_notifier, monkeypatch
):
    record_id = await seed_record(anthro_factory)
    detect = MagicMock(return_value=None)
    monkeypatch.setattr("app.routers.anthropometry.detect_approaching_circa", detect)

    # Valores que llevan el offset a la zona circa (~ -0.1) para un atleta de 13 años.
    async with make_client("coach") as c:
        resp = await c.put(
            _url(ATHLETE_ID, record_id),
            json=record_body(weight="52.0", standing="165.0", sitting="84.0"),
        )
    assert resp.status_code == 200, resp.text

    detect.assert_not_called()
    anthro_notifier.service.send.assert_not_called()
    assert anthro_notifier.dispatcher.mock_calls == []


# ---------------------------------------------------------------------------
# Conflictos de fecha (409)
# ---------------------------------------------------------------------------


async def test_put_date_change_colliding_with_another_record_is_409(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    editable = await seed_record(anthro_factory, evaluation_date=date(2026, 4, 1))
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, editable), json=record_body(evaluation_date="2026-05-01"))
    assert resp.status_code == 409
    assert error_code(resp) == "anthropometry_same_date_exists"
    # el registro con el que colisiona nunca es el propio
    assert error_field(resp, "existing_record_id") != editable


async def test_put_keeping_own_date_is_not_a_collision(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(evaluation_date="2026-05-01"))
    assert resp.status_code == 200, resp.text


async def test_put_same_date_of_another_athletes_record_is_allowed(make_client, anthro_factory):
    await seed_record(anthro_factory, athlete_id=OTHER_ATHLETE_ID, evaluation_date=date(2026, 5, 1))
    record_id = await seed_record(anthro_factory, evaluation_date=date(2026, 4, 1))
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(evaluation_date="2026-05-01"))
    assert resp.status_code == 200, resp.text


async def test_put_date_change_that_makes_athlete_too_young_with_skinfolds_is_409(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    await _add_skinfold_set(make_client, record_id)
    # Nace 2013-05-10: el 2021-01-01 tiene ~7,6 años (< 9).
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(evaluation_date="2021-01-01"))
    assert resp.status_code == 409
    assert error_code(resp) == "athlete_too_young"
    assert (await _load_record(anthro_factory, record_id)).evaluation_date == date(2026, 5, 1)


async def test_put_date_change_breaking_skinfold_interval_is_409_with_next_allowed_date(
    make_client, anthro_factory
):
    first = await seed_record(anthro_factory, evaluation_date=date(2026, 1, 1))
    second = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    await _add_skinfold_set(make_client, first)
    await _add_skinfold_set(make_client, second)

    # 45 días después de la toma anterior (< 90).
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, second), json=record_body(evaluation_date="2026-02-15"))
    assert resp.status_code == 409
    assert error_code(resp) == "skinfold_interval_too_short"
    assert error_field(resp, "next_allowed_date") == "2026-04-01"  # 2026-01-01 + 90 días
    assert (await _load_record(anthro_factory, second)).evaluation_date == date(2026, 5, 1)

    # Control positivo: 104 días después sí cumple el intervalo.
    async with make_client("coach") as c:
        ok = await c.put(_url(ATHLETE_ID, second), json=record_body(evaluation_date="2026-04-15"))
    assert ok.status_code == 200, ok.text


async def test_put_date_change_before_a_later_skinfold_set_is_409(make_client, anthro_factory):
    later = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 20))
    moving = await seed_record(anthro_factory, evaluation_date=date(2026, 10, 1))
    await _add_skinfold_set(make_client, later)
    await _add_skinfold_set(make_client, moving)

    # 19 días ANTES del set posterior (< 90).
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, moving), json=record_body(evaluation_date="2026-05-01"))
    assert resp.status_code == 409
    assert error_code(resp) == "skinfold_interval_too_short"
    assert error_field(resp, "next_allowed_date") == "2026-08-18"  # 2026-05-20 + 90 días
    assert (await _load_record(anthro_factory, moving)).evaluation_date == date(2026, 10, 1)

    # Control positivo: 90 días antes del set posterior sí cumple.
    async with make_client("coach") as c:
        ok = await c.put(_url(ATHLETE_ID, moving), json=record_body(evaluation_date="2026-02-19"))
    assert ok.status_code == 200, ok.text


async def test_put_date_change_without_skinfold_set_skips_skinfold_rules(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1))
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(evaluation_date="2021-01-01"))
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Validación (mismas reglas que POST)
# ---------------------------------------------------------------------------


async def test_put_impossible_sitting_ratio_is_422_and_writes_nothing(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(standing="150.0", sitting="112.5"))
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["type"] == "sitting_ratio_impossible"
    assert float((await _load_record(anthro_factory, record_id)).weight_kg) == pytest.approx(40.0)


async def test_put_out_of_range_weight_is_422(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(weight="19.9"))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rutas denegadas
# ---------------------------------------------------------------------------


async def test_other_coach_of_same_club_gets_403_not_record_author(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("coach2") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body(weight="45.0"))
    assert resp.status_code == 403
    assert error_code(resp) == "not_record_author"
    assert float((await _load_record(anthro_factory, record_id)).weight_kg) == pytest.approx(40.0)


async def test_parent_put_is_403(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory)
    async with make_client("parent") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body())
    assert resp.status_code == 403
    assert float((await _load_record(anthro_factory, record_id)).weight_kg) == pytest.approx(40.0)


async def test_coach_of_another_club_is_refused(make_client, anthro_factory):
    """``verify_athlete_access`` (feature 041) responde 403 al coach de otro club
    (404 queda para atletas archivados o inexistentes)."""
    record_id = await seed_record(anthro_factory)
    async with make_client("foreign_coach") as c:
        resp = await c.put(_url(ATHLETE_ID, record_id), json=record_body())
    assert resp.status_code == 403
    assert error_code(resp) != "not_record_author"  # se corta antes, por club
    assert float((await _load_record(anthro_factory, record_id)).weight_kg) == pytest.approx(40.0)


async def test_record_of_another_athlete_is_404(make_client, anthro_factory):
    foreign_record = await seed_record(anthro_factory, athlete_id=OTHER_ATHLETE_ID)
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, foreign_record), json=record_body())
    assert resp.status_code == 404


async def test_missing_record_is_404(make_client):
    async with make_client("coach") as c:
        resp = await c.put(_url(ATHLETE_ID, 99999), json=record_body())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT sin cambios reales: sin escritura, sin auditoría, sin invalidar la IA
# ---------------------------------------------------------------------------


async def test_put_with_identical_values_is_a_noop(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, weight="40.0", standing="150.0", sitting="76.0")
    await _add_explanation(anthro_factory, ATHLETE_ID, record_id, "phv_explainer")

    async with make_client("coach") as c:
        resp = await c.put(
            _url(ATHLETE_ID, record_id),
            json=record_body(weight="40.0", standing="150.0", sitting="76.0"),
        )
    assert resp.status_code == 200, resp.text
    assert len(await _explanations(anthro_factory, record_id)) == 1
    async with anthro_factory() as s:
        audits = (await s.execute(select(AuditLog).where(AuditLog.entity_type == "anthropometric_record"))).scalars().all()
    assert audits == []
