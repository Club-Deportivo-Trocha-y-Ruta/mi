"""Feature 048 (T016): privacidad y auditoría de PUT / DELETE / plausibilidad / roster.

Ley 1581: ningún valor de medición ni nombre de un menor en la auditoría
(``changed_fields``/``diff``/``meta``), en cuerpos de error 4xx ni en logs.
Los valores de prueba son tokens distintivos (39.6, 43.7, ...) que no pueden
aparecer por casualidad en ids, fechas ni códigos.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.ai_explanation import AthleteAIExplanation
from app.models.audit_log import AuditLog
from tests.anthropometry.conftest import (
    ATHLETE_ID,
    COACH_ID,
    VALID_SITES,
    record_body,
    seed_record,
)

pytestmark = pytest.mark.asyncio

# Valores sembrados y valores nuevos: todos distintivos.
OLD = {"weight": "39.6", "standing": "148.2", "sitting": "76.4"}
NEW = {"weight": "43.7", "standing": "157.3", "sitting": "81.9"}
IMPOSSIBLE = {"weight": "38.4", "standing": "151.7", "sitting": "113.9"}  # ratio 0.75
SENSITIVE_TOKENS = ("39.6", "148.2", "76.4", "43.7", "157.3", "81.9", "38.4", "151.7", "113.9")
NAME_TOKENS = ("Ficticio", "Deportista")
_DRIVER_LOGGERS = ("aiosqlite", "sqlalchemy", "asyncio")
_LOG_TIMING_FIELDS = frozenset({"created", "msecs", "relativeCreated", "thread", "process", "taskName"})
EXPLANATION_TEXT = "Texto ficticio saneado sobre el estirón."


def _url(record_id: int | None = None) -> str:
    base = f"/api/athletes/{ATHLETE_ID}/anthropometry"
    return base if record_id is None else f"{base}/{record_id}"


async def _seed_with_ai_and_skinfolds(factory, make_client) -> int:
    record_id = await seed_record(factory, evaluation_date=date(2026, 5, 1), **OLD)
    async with factory() as s:
        s.add(
            AthleteAIExplanation(
                athlete_id=ATHLETE_ID,
                anthropometric_record_id=record_id,
                use_case="phv_explainer",
                text=EXPLANATION_TEXT,
                model="fake",
                provider="fake",
                generated_at=datetime.now(UTC).replace(tzinfo=None),
                age_group="12-14",
                generated_by_user_id=COACH_ID,
                maturation_status="Circa-PHV",
            )
        )
        await s.commit()
    body = {"caliper_model": "slim_guide", "sites": {k: dict(v) for k, v in VALID_SITES.items()}}
    async with make_client("coach") as c:
        assert (await c.put(f"{_url(record_id)}/skinfolds", json=body)).status_code == 200
    return record_id


async def _audit_payloads(factory) -> list[str]:
    """Todo lo que la auditoría guarda de cada fila, serializado (sin
    ``request_id`` ni ids: solo campos que podrían llevar datos)."""
    async with factory() as s:
        rows = (await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    return [
        json.dumps(
            {"changed_fields": r.changed_fields, "diff": r.diff_json, "meta": r.meta_json, "reason": r.reason_code},
            default=str,
            ensure_ascii=False,
        )
        for r in rows
    ]


async def _last_update_audit(factory) -> AuditLog:
    """Fila ``update`` de la medición cuyo ``changed_fields`` viene del PUT de
    la medición (el PUT de pliegues también audita ``update``)."""
    async with factory() as s:
        rows = (
            await s.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == "anthropometric_record", AuditLog.action == "update")
                .order_by(AuditLog.id.desc())
            )
        ).scalars().all()
    assert rows
    return rows[0]


def _assert_clean(text: str, *, tokens=SENSITIVE_TOKENS + NAME_TOKENS + (EXPLANATION_TEXT,)) -> None:
    for token in tokens:
        assert token not in text, f"'{token}' apareció donde no debe"


# ---------------------------------------------------------------------------
# Auditoría del PUT
# ---------------------------------------------------------------------------


async def test_put_audit_has_field_names_only_and_value_only_for_evaluation_date(make_client, anthro_factory):
    record_id = await _seed_with_ai_and_skinfolds(anthro_factory, make_client)

    async with make_client("coach") as c:
        resp = await c.put(
            _url(record_id),
            json=record_body(evaluation_date="2026-05-03", **{"weight": NEW["weight"], "standing": NEW["standing"], "sitting": NEW["sitting"]}),
        )
    assert resp.status_code == 200, resp.text

    row = await _last_update_audit(anthro_factory)
    assert set(row.changed_fields) == {"evaluation_date", "weight_kg", "standing_height_cm", "sitting_height_cm"}
    assert set(row.diff_json or {}) == {"evaluation_date"}  # VALUE_ALLOWLIST: solo la fecha
    assert row.actor_user_id == COACH_ID
    assert row.athlete_id == ATHLETE_ID
    _assert_clean(json.dumps([row.changed_fields, row.diff_json, row.meta_json], default=str))


async def test_put_without_date_change_has_no_value_in_diff(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, **OLD)
    async with make_client("coach") as c:
        resp = await c.put(_url(record_id), json=record_body(**{"weight": NEW["weight"], "standing": OLD["standing"], "sitting": OLD["sitting"]}))
    assert resp.status_code == 200, resp.text
    row = await _last_update_audit(anthro_factory)
    assert row.changed_fields == ["weight_kg"]
    assert not row.diff_json


async def test_no_audit_row_of_put_or_delete_carries_measurements_names_or_ai_text(make_client, anthro_factory):
    record_id = await _seed_with_ai_and_skinfolds(anthro_factory, make_client)
    async with make_client("coach") as c:
        assert (await c.put(_url(record_id), json=record_body(**NEW))).status_code == 200
        assert (await c.delete(_url(record_id))).status_code == 204

    payloads = await _audit_payloads(anthro_factory)
    assert payloads  # hubo auditoría (update + delete + borrado de la explicación)
    for payload in payloads:
        _assert_clean(payload)


async def test_delete_audit_meta_is_only_the_had_skinfolds_flag(make_client, anthro_factory):
    record_id = await _seed_with_ai_and_skinfolds(anthro_factory, make_client)
    async with make_client("coach") as c:
        assert (await c.delete(_url(record_id))).status_code == 204
    async with anthro_factory() as s:
        row = (
            await s.execute(
                select(AuditLog).where(AuditLog.entity_type == "anthropometric_record", AuditLog.action == "delete")
            )
        ).scalar_one()
    assert row.meta_json == {"had_skinfolds": True}
    assert not row.diff_json


# ---------------------------------------------------------------------------
# Cuerpos de error 4xx
# ---------------------------------------------------------------------------


async def test_4xx_bodies_never_echo_measurements_or_names(make_client, anthro_factory):
    record_id = await seed_record(anthro_factory, evaluation_date=date(2026, 5, 1), **OLD)
    other_day = await seed_record(anthro_factory, evaluation_date=date(2026, 4, 1), **OLD)
    responses = []

    async with make_client("coach") as c:
        # 422 ratio imposible: PUT, plausibilidad y POST
        responses.append(await c.put(_url(record_id), json=record_body(**IMPOSSIBLE)))
        responses.append(
            await c.post(
                f"{_url()}/plausibility",
                json={
                    "evaluation_date": "2026-05-10",
                    "weight_kg": IMPOSSIBLE["weight"],
                    "standing_height_cm": IMPOSSIBLE["standing"],
                    "sitting_height_cm": IMPOSSIBLE["sitting"],
                },
            )
        )
        responses.append(await c.post(_url(), json=record_body(evaluation_date="2026-06-01", **IMPOSSIBLE)))
        # 409 misma fecha (PUT hacia la fecha del otro registro y POST duplicado)
        responses.append(await c.put(_url(other_day), json=record_body(evaluation_date="2026-05-01", **NEW)))
        responses.append(
            await c.post(
                _url(),
                json={
                    "evaluation_date": "2026-05-01",
                    "weight_kg": OLD["weight"],
                    "standing_height_cm": OLD["standing"],
                    "sitting_height_cm": OLD["sitting"],
                },
            )
        )
        # roster con fecha futura
        responses.append(await c.get("/api/anthropometry/roster", params={"date": "2999-01-01"}))
    async with make_client("coach2") as c:
        # 403 no es el autor
        responses.append(await c.put(_url(record_id), json=record_body(**NEW)))
        responses.append(await c.delete(_url(record_id)))
    async with make_client("parent") as c:
        responses.append(await c.put(_url(record_id), json=record_body(**NEW)))
        responses.append(await c.get("/api/anthropometry/roster"))

    statuses = [r.status_code for r in responses]
    assert statuses == [422, 422, 422, 409, 409, 422, 403, 403, 403, 403], statuses
    for resp in responses:
        _assert_clean(resp.text)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


async def test_logs_never_contain_measurements_or_names(make_client, anthro_factory, caplog):
    caplog.set_level(logging.DEBUG)
    record_id = await _seed_with_ai_and_skinfolds(anthro_factory, make_client)
    other = await seed_record(anthro_factory, evaluation_date=date(2026, 2, 1), **OLD)

    async with make_client("coach") as c:
        await c.put(_url(record_id), json=record_body(**NEW))  # 200
        await c.put(_url(record_id), json=record_body(**IMPOSSIBLE))  # 422
        await c.put(_url(other), json=record_body(evaluation_date="2026-05-01", **NEW))  # 409
        await c.post(
            f"{_url()}/plausibility",
            json={
                "evaluation_date": "2026-06-01",
                "weight_kg": NEW["weight"],
                "standing_height_cm": NEW["standing"],
                "sitting_height_cm": NEW["sitting"],
            },
        )
        await c.get("/api/anthropometry/roster", params={"date": "2026-05-01"})
        await c.get("/api/anthropometry/roster", params={"date": "2999-01-01"})  # 422
        await c.delete(_url(record_id))  # 204
    async with make_client("coach2") as c:
        await c.put(_url(other), json=record_body(**NEW))  # 403
        await c.delete(_url(other))  # 403

    # Se excluyen los loggers de drivers (aiosqlite/sqlalchemy a DEBUG imprimen
    # los parámetros SQL del propio arnés de prueba; en producción no se emiten).
    records = [r for r in caplog.records if not r.name.startswith(_DRIVER_LOGGERS)]
    assert records, "caplog no capturó nada: la prueba sería vacua"
    for record in records:
        _assert_clean(record.getMessage())
        # y tampoco en los argumentos estructurados (`extra=`)
        # Los campos de tiempo (created/msecs/relativeCreated) son floats cuyos
        # dígitos pueden contener un token por azar (p. ej. «81.9»): falso positivo.
        payload = {k: v for k, v in record.__dict__.items() if k not in _LOG_TIMING_FIELDS}
        _assert_clean(json.dumps(payload, default=str))


# ---------------------------------------------------------------------------
# Lectura para familias
# ---------------------------------------------------------------------------


async def test_parent_get_omits_can_modify_and_plausibility_flags_keys(make_client, anthro_factory):
    await seed_record(anthro_factory, evaluation_date=date(2026, 1, 1), **OLD)
    await seed_record(anthro_factory, evaluation_date=date(2026, 3, 1), weight="39.6", standing="140.0", sitting="72.8")
    async with make_client("parent") as c:
        resp = await c.get(_url())
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2
    assert "can_modify" not in resp.text
    assert "plausibility_flags" not in resp.text
    async with make_client("coach") as c:
        coach_resp = await c.get(_url())
    assert "plausibility_flags" in coach_resp.text  # control: sí existen para el coach
