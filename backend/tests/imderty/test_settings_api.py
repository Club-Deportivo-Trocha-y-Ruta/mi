"""T039 (specs/047-imderty-attendance-sheet/tasks.md, US3): GET/PUT
``/api/clubs/{club_id}/imderty-settings``.

Covers: GET before any save returns nulls/``[]`` (no row created); PUT is a
get-or-create upsert; an invalid program value is rejected with 422; a
foreign coach and a parent both get 403; the audit entry records
``changed_fields``.

No name here corresponds to a real person (CLAUDE.md, Ley 1581) — this
module reuses the fictitious ``imderty_scenario`` fixture from ``conftest.py``.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from app.models import Base
from app.models.audit_log import AuditLog
from app.services.audit import AuditEntityType


@pytest_asyncio.fixture(autouse=True)
async def _ensure_settings_table(imderty_engine):
    """``club_imderty_settings`` is not in conftest's shared ``_TABLES``
    list (owned by a foundation task, not this one); create it locally on
    the same in-memory engine instead of editing ``conftest.py``."""
    async with imderty_engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.tables["club_imderty_settings"].create(
                c, checkfirst=True
            )
        )
    yield


_NULL_PAYLOAD = {
    "contractor_name": None,
    "venue": None,
    "training_days": None,
    "schedule": None,
    "programs": [],
}


async def test_get_before_save_returns_nulls_and_empty_programs(
    coach_client, imderty_scenario
):
    resp = await coach_client.get(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    )
    assert resp.status_code == 200
    assert resp.json() == _NULL_PAYLOAD


async def test_put_is_get_or_create_and_get_reflects_it(
    coach_client, imderty_scenario
):
    payload = {
        "contractor_name": "Coordinador Ficticio",
        "venue": "Polideportivo Ficticio",
        "training_days": "LUNES A VIERNES",
        "schedule": "4:00 PM A 6:00 PM",
        "programs": ["individual", "competencia"],
    }
    put_resp = await coach_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=payload,
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == payload

    get_resp = await coach_client.get(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    )
    assert get_resp.status_code == 200
    assert get_resp.json() == payload

    # A second PUT updates the same row rather than creating a new one.
    updated = {**payload, "venue": "Otro Polideportivo Ficticio"}
    second_put = await coach_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=updated,
    )
    assert second_put.status_code == 200
    assert second_put.json()["venue"] == "Otro Polideportivo Ficticio"


async def test_put_invalid_program_returns_422(coach_client, imderty_scenario):
    payload = {**_NULL_PAYLOAD, "programs": ["not_a_real_program"]}
    resp = await coach_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=payload,
    )
    assert resp.status_code == 422


async def test_foreign_coach_forbidden(foreign_coach_client, imderty_scenario):
    get_resp = await foreign_coach_client.get(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    )
    put_resp = await foreign_coach_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=_NULL_PAYLOAD,
    )
    assert get_resp.status_code == 403
    assert put_resp.status_code == 403


async def test_parent_forbidden(parent_client, imderty_scenario):
    get_resp = await parent_client.get(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings"
    )
    put_resp = await parent_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=_NULL_PAYLOAD,
    )
    assert get_resp.status_code == 403
    assert put_resp.status_code == 403


async def test_audit_entry_records_changed_fields(coach_client, imderty_scenario):
    payload = {
        "contractor_name": "Coordinador Ficticio",
        "venue": "Polideportivo Ficticio",
        "training_days": "LUNES A VIERNES",
        "schedule": "4:00 PM A 6:00 PM",
        "programs": ["individual"],
    }
    resp = await coach_client.put(
        f"/api/clubs/{imderty_scenario.club_id}/imderty-settings",
        json=payload,
    )
    assert resp.status_code == 200

    result = await imderty_scenario.session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == AuditEntityType.club_imderty_settings,
            AuditLog.entity_id == imderty_scenario.club_id,
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.changed_fields is not None
    assert set(entry.changed_fields) == {
        "contractor_name",
        "venue",
        "training_days",
        "schedule",
        "programs",
    }
    # No value of these fields ever reaches diff_json.
    assert entry.diff_json is None
