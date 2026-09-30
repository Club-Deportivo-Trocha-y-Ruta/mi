"""T025 (specs/047-imderty-attendance-sheet/tasks.md, US2): sensitive-data
authorization and values (FR-006…FR-008, research R8).

Two layers:

- **Service tests** (``test_service_*``) call ``app.services.imderty.profile``
  directly; they pass as soon as T028 exists.
- **API tests** (``test_api_*``) exercise
  ``/api/athletes/{id}/sensitive-authorizations[/withdraw]`` and
  ``/api/athletes/{id}/sensitive-data`` (contracts/api.md); they pass once
  T029 mounts the routes.

The values set here are entries of the official lists, attached to a
fictitious athlete (CLAUDE.md, Ley 1581). The tests assert those values never
reach a log line or an ``audit_log`` row.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete
from app.models.audit_log import AuditLog
from app.models.imderty import (
    AthleteSensitiveAuthorization,
    AthleteSensitiveData,
    ImdertyDisability,
    ImdertyEthnicity,
    ImdertyYesNo,
)
from app.models.user import User
from app.schemas.imderty import SensitiveAuthorizationCreate, SensitiveDataUpdate
from app.services.imderty import profile as svc
from tests.imderty.conftest import _TABLES, ImdertyScenario

_SENSITIVE_TABLES = (
    *_TABLES,
    "imderty_barrios",
    "athlete_imderty_profiles",
    "athlete_sensitive_authorizations",
    "athlete_sensitive_data",
)

# Distinctive official values, easy to spot in logs/audit if they leaked.
_ETHNICITY = "ROM GITANO"
_DISABILITY = "VOZ Y HABLA"
_LEAK_MARKERS = (_ETHNICITY, _DISABILITY, "OLFATIVA Y TACTO", "PALENQUERO")
_AUTHORIZED_ON = "2026-09-01"


# Database-driver debug output (aiosqlite/SQLAlchemy echo bound parameters in
# the test lane only) is not an application log; everything else is scanned,
# message and ``extra`` attributes alike.
_DRIVER_LOGGERS = ("aiosqlite", "sqlalchemy")


def _app_log_text(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        f"{record.getMessage()} {record.__dict__}"
        for record in caplog.records
        if not record.name.startswith(_DRIVER_LOGGERS)
    )


@pytest_asyncio.fixture
async def imderty_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Same as conftest's engine, plus the four IMDERTY tables of US2."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _SENSITIVE_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


def _auth_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/sensitive-authorizations"


def _withdraw_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/sensitive-authorizations/withdraw"


def _data_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/sensitive-data"


async def _authorizations(
    scenario: ImdertyScenario, athlete_id: int
) -> list[AthleteSensitiveAuthorization]:
    result = await scenario.session.execute(
        select(AthleteSensitiveAuthorization)
        .where(AthleteSensitiveAuthorization.athlete_id == athlete_id)
        .order_by(AthleteSensitiveAuthorization.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _data_row(
    scenario: ImdertyScenario, athlete_id: int
) -> AthleteSensitiveData | None:
    result = await scenario.session.execute(
        select(AthleteSensitiveData)
        .where(AthleteSensitiveData.athlete_id == athlete_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _audit_dump(scenario: ImdertyScenario) -> str:
    rows = (
        (
            await scenario.session.execute(
                select(AuditLog).execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return json.dumps(
        [
            [r.entity_type, r.changed_fields, r.diff_json, r.meta_json, r.reason_code]
            for r in rows
        ],
        default=str,
        ensure_ascii=False,
    )


# ===========================================================================
# Service layer (T028) — runnable before the routes exist
# ===========================================================================


async def test_service_authorization_lifecycle(imderty_scenario, caplog):
    caplog.set_level(logging.DEBUG)
    s = imderty_scenario
    athlete = await s.session.get(Athlete, s.parent_athlete_one_id)
    actor = await s.session.get(User, s.coach_user_id)

    # Gated write before any authorization.
    with pytest.raises(svc.AuthorizationRequiredError):
        await svc.update_sensitive_data(
            s.session,
            athlete,
            SensitiveDataUpdate(ethnicity=_ETHNICITY, disability=_DISABILITY),
            actor,
        )
    with pytest.raises(svc.NoActiveAuthorizationError):
        await svc.get_sensitive_data(s.session, athlete)

    created = await svc.create_authorization(
        s.session,
        athlete,
        SensitiveAuthorizationCreate(
            guardian_user_id=s.parent_user_id, authorized_on=date(2026, 9, 1)
        ),
        actor,
    )
    assert created.active is True
    defaults = await svc.get_sensitive_data(s.session, athlete)
    assert defaults.ethnicity == ImdertyEthnicity.NO_SABE_NO_RESPONDE
    assert defaults.disability == ImdertyDisability.NA
    assert defaults.conflict_victim is None

    with pytest.raises(svc.AuthorizationAlreadyActiveError):
        await svc.create_authorization(
            s.session,
            athlete,
            SensitiveAuthorizationCreate(
                guardian_user_id=s.parent_user_id, authorized_on=date(2026, 9, 1)
            ),
            actor,
        )

    updated = await svc.update_sensitive_data(
        s.session,
        athlete,
        SensitiveDataUpdate(
            ethnicity=_ETHNICITY, disability=_DISABILITY, conflict_victim=ImdertyYesNo.no
        ),
        actor,
    )
    assert updated.ethnicity.value == _ETHNICITY

    await svc.withdraw_authorization(s.session, athlete, actor)
    await s.session.commit()

    assert await _data_row(s, athlete.id) is None
    auths = await _authorizations(s, athlete.id)
    assert len(auths) == 1
    assert auths[0].active_key is None
    assert auths[0].withdrawn_at is not None
    assert auths[0].withdrawn_by_user_id == actor.id

    with pytest.raises(svc.NoActiveAuthorizationError):
        await svc.withdraw_authorization(s.session, athlete, actor)

    # Re-authorizing creates a NEW row with the defaults again.
    await svc.create_authorization(
        s.session,
        athlete,
        SensitiveAuthorizationCreate(
            guardian_user_id=s.parent_user_id, authorized_on=date(2026, 9, 2)
        ),
        actor,
    )
    await s.session.commit()
    auths = await _authorizations(s, athlete.id)
    assert len(auths) == 2
    assert auths[1].active_key == athlete.id
    data = await _data_row(s, athlete.id)
    assert data is not None
    assert data.authorization_id == auths[1].id
    assert data.ethnicity == ImdertyEthnicity.NO_SABE_NO_RESPONDE

    dumped = await _audit_dump(s)
    for marker in _LEAK_MARKERS:
        assert marker not in _app_log_text(caplog)
        assert marker not in dumped
    assert "athlete_sensitive_data" in dumped  # the value write was audited


async def test_service_rejects_unlinked_guardian_and_future_date(imderty_scenario):
    s = imderty_scenario
    athlete = await s.session.get(Athlete, s.parent_athlete_one_id)
    actor = await s.session.get(User, s.coach_user_id)

    with pytest.raises(svc.GuardianNotLinkedError):
        await svc.create_authorization(
            s.session,
            athlete,
            SensitiveAuthorizationCreate(
                guardian_user_id=s.second_guardian_user_id, authorized_on=date(2026, 9, 1)
            ),
            actor,
        )

    # The schema already rejects a future date; the service re-checks it for
    # non-HTTP callers.
    body = SensitiveAuthorizationCreate.model_construct(
        guardian_user_id=s.parent_user_id,
        authorized_on=date.today() + timedelta(days=1),
    )
    with pytest.raises(svc.AuthorizationDateInFutureError):
        await svc.create_authorization(s.session, athlete, body, actor)

    assert await _authorizations(s, athlete.id) == []


async def test_service_profile_read_shows_authorization_but_no_values(imderty_scenario):
    s = imderty_scenario
    athlete = await s.session.get(Athlete, s.parent_athlete_one_id)
    actor = await s.session.get(User, s.coach_user_id)
    await svc.create_authorization(
        s.session,
        athlete,
        SensitiveAuthorizationCreate(
            guardian_user_id=s.parent_user_id, authorized_on=date(2026, 9, 1)
        ),
        actor,
    )
    read = await svc.get_or_empty_profile(s.session, athlete)
    assert read.sensitive.authorization is not None
    assert read.sensitive.authorization.guardian_user_id == s.parent_user_id
    assert read.sensitive.authorization.active is True
    dumped = read.model_dump_json()
    assert "NO SABE NO RESPONDE" not in dumped
    assert "ethnicity" not in dumped


# ===========================================================================
# API (T029 routes)
# ===========================================================================


async def test_api_create_returns_201_with_defaults(
    imderty_scenario, imderty_client_factory
):
    s = imderty_scenario
    async with imderty_client_factory(s.coach_user_id) as client:
        created = await client.post(
            _auth_url(s.parent_athlete_one_id),
            json={"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["guardian_user_id"] == s.parent_user_id
        assert body["authorized_on"] == _AUTHORIZED_ON
        assert body["active"] is True

        data = await client.get(_data_url(s.parent_athlete_one_id))
    assert data.status_code == 200
    assert data.json() == {
        "ethnicity": "NO SABE NO RESPONDE",
        "disability": "N/A",
        "conflict_victim": None,
    }


async def test_api_second_active_authorization_is_409(
    imderty_scenario, imderty_client_factory
):
    s = imderty_scenario
    payload = {"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON}
    async with imderty_client_factory(s.coach_user_id) as client:
        first = await client.post(_auth_url(s.parent_athlete_one_id), json=payload)
        second = await client.post(_auth_url(s.parent_athlete_one_id), json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_api_unlinked_guardian_or_future_date_is_422(
    imderty_scenario, imderty_client_factory
):
    s = imderty_scenario
    future = (date.today() + timedelta(days=1)).isoformat()
    async with imderty_client_factory(s.coach_user_id) as client:
        unlinked = await client.post(
            _auth_url(s.parent_athlete_one_id),
            json={
                "guardian_user_id": s.second_guardian_user_id,
                "authorized_on": _AUTHORIZED_ON,
            },
        )
        in_future = await client.post(
            _auth_url(s.parent_athlete_one_id),
            json={"guardian_user_id": s.parent_user_id, "authorized_on": future},
        )
    assert unlinked.status_code == 422
    assert in_future.status_code == 422
    assert await _authorizations(s, s.parent_athlete_one_id) == []


async def test_api_put_without_authorization_is_403(
    imderty_scenario, imderty_client_factory
):
    s = imderty_scenario
    async with imderty_client_factory(s.coach_user_id) as client:
        resp = await client.put(
            _data_url(s.parent_athlete_one_id),
            json={"ethnicity": _ETHNICITY, "disability": _DISABILITY, "conflict_victim": "no"},
        )
    assert resp.status_code == 403
    assert _ETHNICITY not in resp.text


async def test_api_put_invalid_value_is_422(imderty_scenario, imderty_client_factory):
    s = imderty_scenario
    async with imderty_client_factory(s.coach_user_id) as client:
        created = await client.post(
            _auth_url(s.parent_athlete_one_id),
            json={"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON},
        )
        assert created.status_code == 201
        bad_ethnicity = await client.put(
            _data_url(s.parent_athlete_one_id),
            json={"ethnicity": "VALOR INVENTADO", "disability": "N/A"},
        )
        bad_victim = await client.put(
            _data_url(s.parent_athlete_one_id),
            json={
                "ethnicity": "NO SABE NO RESPONDE",
                "disability": "N/A",
                "conflict_victim": "quizas",
            },
        )
    assert bad_ethnicity.status_code == 422
    assert bad_victim.status_code == 422
    # The 422 body never echoes the rejected value (app-wide
    # RequestValidationError handler strips ``input``/``ctx``).
    assert "VALOR INVENTADO" not in bad_ethnicity.text
    assert "quizas" not in bad_victim.text
    for body in (bad_ethnicity.json(), bad_victim.json()):
        for error in body["detail"]:
            assert "input" not in error
            assert "ctx" not in error


async def test_api_put_and_withdraw_erases_values(
    imderty_scenario, imderty_client_factory, caplog
):
    caplog.set_level(logging.DEBUG)
    s = imderty_scenario
    athlete_id = s.parent_athlete_one_id
    async with imderty_client_factory(s.coach_user_id) as client:
        created = await client.post(
            _auth_url(athlete_id),
            json={"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON},
        )
        assert created.status_code == 201

        put = await client.put(
            _data_url(athlete_id),
            json={"ethnicity": _ETHNICITY, "disability": _DISABILITY, "conflict_victim": "si"},
        )
        assert put.status_code == 200
        assert put.json() == {
            "ethnicity": _ETHNICITY,
            "disability": _DISABILITY,
            "conflict_victim": "si",
        }

        withdraw = await client.post(_withdraw_url(athlete_id))
        assert withdraw.status_code == 200

        after = await client.get(_data_url(athlete_id))
        assert after.status_code == 404

        again = await client.post(_withdraw_url(athlete_id))
        assert again.status_code == 404

        profile = await client.get(f"/api/athletes/{athlete_id}/imderty-profile")
        assert profile.status_code == 200
        assert profile.json()["sensitive"] == {"authorization": None}

    # The values are erased, not hidden.
    assert await _data_row(s, athlete_id) is None
    auths = await _authorizations(s, athlete_id)
    assert len(auths) == 1
    assert auths[0].active_key is None
    assert auths[0].withdrawn_at is not None

    # Re-authorizing creates a new row with the defaults.
    async with imderty_client_factory(s.coach_user_id) as client:
        reauth = await client.post(
            _auth_url(athlete_id),
            json={"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON},
        )
        assert reauth.status_code == 201
        assert reauth.json()["id"] != created.json()["id"]
        data = await client.get(_data_url(athlete_id))
    assert data.json() == {
        "ethnicity": "NO SABE NO RESPONDE",
        "disability": "N/A",
        "conflict_victim": None,
    }

    # Logs and audit never carry a sensitive value.
    dumped = await _audit_dump(s)
    for marker in _LEAK_MARKERS:
        assert marker not in _app_log_text(caplog)
        assert marker not in dumped
    scenario_rows = (await s.session.execute(select(AuditLog))).scalars().all()
    sensitive_rows = [
        r
        for r in scenario_rows
        if r.entity_type in {"athlete_sensitive_authorization", "athlete_sensitive_data"}
    ]
    assert sensitive_rows
    assert all(r.diff_json is None for r in sensitive_rows)

    # The withdrawal row carries the closed reason code ``withdrawn``
    # (contracts/api.md) and field names only.
    withdrawals = [
        r
        for r in sensitive_rows
        if r.entity_type == "athlete_sensitive_authorization"
        and r.action == "update"
    ]
    assert len(withdrawals) == 1
    assert withdrawals[0].reason_code == "withdrawn"
    assert withdrawals[0].meta_json in (None, {})


async def test_api_parent_gets_403_on_every_route(
    imderty_scenario, imderty_client_factory
):
    s = imderty_scenario
    athlete_id = s.parent_athlete_one_id
    async with imderty_client_factory(s.parent_user_id) as client:
        responses = [
            await client.post(
                _auth_url(athlete_id),
                json={"guardian_user_id": s.parent_user_id, "authorized_on": _AUTHORIZED_ON},
            ),
            await client.post(_withdraw_url(athlete_id)),
            await client.get(_data_url(athlete_id)),
            await client.put(
                _data_url(athlete_id),
                json={"ethnicity": _ETHNICITY, "disability": _DISABILITY},
            ),
        ]
    assert [r.status_code for r in responses] == [403, 403, 403, 403]
    assert await _authorizations(s, athlete_id) == []


async def test_api_foreign_coach_gets_403(imderty_scenario, imderty_client_factory):
    s = imderty_scenario
    async with imderty_client_factory(s.foreign_coach_user_id) as client:
        resp = await client.get(_data_url(s.parent_athlete_one_id))
    assert resp.status_code == 403
