"""T024 (specs/047-imderty-attendance-sheet/tasks.md, US2): IMDERTY profile
and "contacto principal".

Two layers:

- **Service tests** (``test_service_*``) call ``app.services.imderty.profile``
  directly on the seeded session; they pass as soon as T028 exists.
- **API tests** (``test_api_*``) exercise ``/api/athletes/{id}/imderty-profile``
  and ``/api/athletes/{id}/primary-contact`` (contracts/api.md); they pass once
  T029 mounts the routes, and the ``PATCH /api/athletes/{id}`` side effect
  once T031 lands.

Every name, surname and document number here is fictitious (CLAUDE.md,
Ley 1581). The engine is redefined to add the four IMDERTY tables that the
shared ``conftest._TABLES`` list does not carry.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Athlete, ParentAthlete
from app.models.audit_log import AuditLog
from app.models.imderty import AthleteImdertyProfile, ImdertyBarrio
from app.models.user import User, UserRole
from app.schemas.imderty import ImdertyProfileUpdate
from app.services.audit import AuditEntityType
from app.services.imderty import profile as svc
from tests.fixtures.race_history_fixtures import create_athlete, create_user
from tests.imderty.conftest import (
    PARENT_ATHLETE_ONE_USER_ID,
    _TABLES,
    ImdertyScenario,
)

_PROFILE_TABLES = (
    *_TABLES,
    "imderty_barrios",
    "athlete_imderty_profiles",
    "athlete_sensitive_authorizations",
    "athlete_sensitive_data",
)

# Fictitious values used across the module.
_COMPOUND_LAST_NAME = "Quintero Del Valle"
_DOC_NUMBER = "1000000047"
_BAD_DOC_NUMBER = "10A0047XYZ"
_FOREIGN_CLUB_ATHLETE_ID = 4749
_UNRELATED_USER_ID = 4760


@pytest_asyncio.fixture
async def imderty_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Same as conftest's engine, plus the four IMDERTY tables of US2."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _PROFILE_TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def seeded(imderty_scenario: ImdertyScenario) -> ImdertyScenario:
    """Scenario + a compound surname on athlete one, its login user (needed by
    ``PATCH /api/athletes/{id}``), one active barrio, one inactive barrio, an
    unrelated parent and an athlete of the other club."""
    s = imderty_scenario.session
    athlete = await s.get(Athlete, imderty_scenario.parent_athlete_one_id)
    athlete.last_name = _COMPOUND_LAST_NAME
    await create_user(
        s,
        user_id=PARENT_ATHLETE_ONE_USER_ID,
        role=UserRole.athlete,
        first_name="Atleta Ficticio Uno",
        last_name=_COMPOUND_LAST_NAME,
        can_login=False,
    )
    await create_user(
        s,
        user_id=_UNRELATED_USER_ID,
        role=UserRole.parent,
        first_name="Acudiente",
        last_name="Ajeno Ficticio",
    )
    await create_athlete(
        s,
        athlete_id=_FOREIGN_CLUB_ATHLETE_ID,
        first_name="Atleta Ficticio Externo",
        last_name="Ficticio",
        club_id=imderty_scenario.other_club_id,
        user_id=4769,
        created_by=imderty_scenario.foreign_coach_user_id,
    )
    s.add_all(
        [
            ImdertyBarrio(id=1, name="BARRIO FICTICIO UNO", zone="1", is_active=True),
            ImdertyBarrio(id=2, name="BARRIO FICTICIO DOS", zone="2", is_active=False),
        ]
    )
    await s.commit()
    return imderty_scenario


async def _actor(scenario: ImdertyScenario, user_id: int) -> User:
    return await scenario.session.get(User, user_id)


async def _athlete(scenario: ImdertyScenario, athlete_id: int) -> Athlete:
    return await scenario.session.get(Athlete, athlete_id)


async def _audit_rows(scenario: ImdertyScenario, entity_type: str) -> list[AuditLog]:
    result = await scenario.session.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type)
        .order_by(AuditLog.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def _profile_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/imderty-profile"


def _primary_url(athlete_id: int) -> str:
    return f"/api/athletes/{athlete_id}/primary-contact"


# ===========================================================================
# Service layer (T028) — runnable before the routes exist
# ===========================================================================


async def test_service_empty_profile_has_nulls_and_proposed_split(seeded):
    athlete = await _athlete(seeded, seeded.parent_athlete_one_id)
    read = await svc.get_or_empty_profile(seeded.session, athlete)

    assert read.athlete_id == athlete.id
    assert read.document_type is None and read.document_number is None
    assert read.barrio is None and read.other_municipality is False
    assert read.surname_split.confirmed is False
    assert read.surname_split.proposed_first == "Quintero"
    assert read.surname_split.proposed_second == "Del Valle"
    assert read.sensitive.authorization is None
    assert read.effective_phone_source == "none"
    assert [g.user_id for g in read.guardians] == [seeded.parent_user_id]


async def test_service_confirmed_split_must_rebuild_last_name(seeded):
    athlete = await _athlete(seeded, seeded.parent_athlete_one_id)
    actor = await _actor(seeded, seeded.coach_user_id)

    with pytest.raises(svc.ProfileValidationError):
        await svc.upsert_profile(
            seeded.session,
            athlete,
            ImdertyProfileUpdate(
                first_surname="Quintero", second_surname="Valle", confirm_surname_split=True
            ),
            actor,
        )

    result = await svc.upsert_profile(
        seeded.session,
        athlete,
        ImdertyProfileUpdate(
            first_surname="QUINTERO", second_surname="del valle", confirm_surname_split=True
        ),
        actor,
    )
    assert result.surname_split.confirmed is True
    profile = await seeded.session.get(AthleteImdertyProfile, athlete.id)
    assert profile.surname_split_confirmed_by_user_id == actor.id


async def test_service_editing_surnames_without_confirm_clears_confirmation(seeded):
    athlete = await _athlete(seeded, seeded.parent_athlete_one_id)
    actor = await _actor(seeded, seeded.coach_user_id)
    await svc.upsert_profile(
        seeded.session,
        athlete,
        ImdertyProfileUpdate(
            first_surname="Quintero", second_surname="Del Valle", confirm_surname_split=True
        ),
        actor,
    )
    result = await svc.upsert_profile(
        seeded.session,
        athlete,
        ImdertyProfileUpdate(first_surname="Quintero Del", second_surname="Valle"),
        actor,
    )
    assert result.surname_split.confirmed is False


async def test_service_digits_only_and_barrio_exclusive(seeded):
    athlete = await _athlete(seeded, seeded.parent_athlete_one_id)
    actor = await _actor(seeded, seeded.coach_user_id)

    # Merged-state check: a stored non-digit number plus a later switch to T.I.
    await svc.upsert_profile(
        seeded.session,
        athlete,
        ImdertyProfileUpdate(document_type="ppt", document_number=_BAD_DOC_NUMBER),
        actor,
    )
    with pytest.raises(svc.ProfileValidationError) as exc:
        await svc.upsert_profile(
            seeded.session, athlete, ImdertyProfileUpdate(document_type="ti"), actor
        )
    assert _BAD_DOC_NUMBER not in exc.value.detail

    # Inactive barrio cannot be newly chosen.
    with pytest.raises(svc.ProfileValidationError):
        await svc.upsert_profile(
            seeded.session, athlete, ImdertyProfileUpdate(barrio_id=2), actor
        )

    # Choosing a barrio after "otro municipio" flips the flag off.
    await svc.upsert_profile(
        seeded.session, athlete, ImdertyProfileUpdate(other_municipality=True), actor
    )
    result = await svc.upsert_profile(
        seeded.session, athlete, ImdertyProfileUpdate(barrio_id=1), actor
    )
    assert result.barrio is not None and result.barrio.zone == "1"
    assert result.other_municipality is False


async def test_service_duplicate_document_in_club_warns(seeded):
    actor = await _actor(seeded, seeded.coach_user_id)
    one = await _athlete(seeded, seeded.parent_athlete_one_id)
    two = await _athlete(seeded, seeded.parent_athlete_two_id)
    first = await svc.upsert_profile(
        seeded.session,
        one,
        ImdertyProfileUpdate(document_type="ti", document_number=_DOC_NUMBER),
        actor,
    )
    assert first.warnings == []
    second = await svc.upsert_profile(
        seeded.session,
        two,
        ImdertyProfileUpdate(document_type="ti", document_number=_DOC_NUMBER),
        actor,
    )
    assert second.warnings == [svc.DUPLICATE_DOCUMENT_WARNING]

    # Another club holding the same number is not a duplicate.
    foreign = await _athlete(seeded, _FOREIGN_CLUB_ATHLETE_ID)
    third = await svc.upsert_profile(
        seeded.session,
        foreign,
        ImdertyProfileUpdate(document_type="ti", document_number=_DOC_NUMBER),
        actor,
    )
    assert third.warnings == []


async def test_service_primary_contact_moves_and_rejects_unlinked(seeded):
    athlete = await _athlete(seeded, seeded.two_guardians_athlete_id)
    actor = await _actor(seeded, seeded.coach_user_id)

    with pytest.raises(svc.GuardianNotLinkedError):
        await svc.set_primary_contact(seeded.session, athlete, _UNRELATED_USER_ID, actor)

    guardians = await svc.set_primary_contact(
        seeded.session, athlete, seeded.second_guardian_user_id, actor
    )
    assert [g.user_id for g in guardians if g.is_primary_contact] == [
        seeded.second_guardian_user_id
    ]

    guardians = await svc.set_primary_contact(
        seeded.session, athlete, seeded.parent_user_id, actor
    )
    assert [g.user_id for g in guardians if g.is_primary_contact] == [seeded.parent_user_id]

    guardians = await svc.set_primary_contact(seeded.session, athlete, None, actor)
    assert not any(g.is_primary_contact for g in guardians)

    rows = await _audit_rows(seeded, AuditEntityType.parent_athlete.value)
    assert rows and all(r.changed_fields == ["primary_contact_key"] for r in rows)
    assert all(r.diff_json is None for r in rows)


async def test_service_profile_audit_has_field_names_only(seeded):
    athlete = await _athlete(seeded, seeded.parent_athlete_one_id)
    actor = await _actor(seeded, seeded.coach_user_id)
    await svc.upsert_profile(
        seeded.session,
        athlete,
        ImdertyProfileUpdate(
            document_type="ti",
            document_number=_DOC_NUMBER,
            address="CALLE FICTICIA 1 # 2-3",
            eps="EPS FICTICIA",
        ),
        actor,
    )
    await seeded.session.commit()

    rows = await _audit_rows(seeded, AuditEntityType.athlete_imderty_profile.value)
    assert len(rows) == 1
    row = rows[0]
    assert row.action.value == "update"
    assert set(row.changed_fields) == {"address", "document_number", "document_type", "eps"}
    assert row.diff_json is None
    dumped = json.dumps(
        [row.changed_fields, row.diff_json, row.meta_json, row.reason_code], default=str
    )
    for value in (_DOC_NUMBER, "CALLE FICTICIA", "EPS FICTICIA"):
        assert value not in dumped


# --- effective_phone (FR-022) — pure --------------------------------------


def test_effective_phone_chain():
    G = svc.GuardianPhone
    assert svc.resolve_effective_phone("3000000001", [G(1, "3000000002", True)]) == (
        "3000000001",
        "athlete",
    )
    assert svc.resolve_effective_phone(
        None, [G(1, "3000000002", False), G(2, "3000000003", True)]
    ) == ("3000000003", "primary_guardian")
    assert svc.resolve_effective_phone(
        "  ", [G(2, "3000000003", False), G(1, "3000000002", False)]
    ) == ("3000000002", "first_guardian")
    # Primary without phone → first linked guardian.
    assert svc.resolve_effective_phone(
        None, [G(1, "3000000002", False), G(2, None, True)]
    ) == ("3000000002", "first_guardian")
    assert svc.resolve_effective_phone(None, []) == (None, "none")
    assert svc.resolve_effective_phone(None, [G(1, None, False)]) == (None, "none")


# ===========================================================================
# API (T029 routes; T031 for the PATCH side effect)
# ===========================================================================


async def test_api_get_empty_profile_returns_200_with_nulls(
    seeded, imderty_client_factory
):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.get(_profile_url(seeded.parent_athlete_one_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["athlete_id"] == seeded.parent_athlete_one_id
    assert body["document_type"] is None
    assert body["document_number"] is None
    assert body["barrio"] is None
    assert body["surname_split"] == {
        "confirmed": False,
        "proposed_first": "Quintero",
        "proposed_second": "Del Valle",
    }
    assert body["sensitive"] == {"authorization": None}
    # Sensitive values never travel in the profile payload.
    for key in ("ethnicity", "disability", "conflict_victim"):
        assert key not in body


@pytest.mark.parametrize("doc_type", ["rc", "ti", "cc"])
async def test_api_put_rejects_non_digit_document_without_echo(
    seeded, imderty_client_factory, doc_type
):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.put(
            _profile_url(seeded.parent_athlete_one_id),
            json={"document_type": doc_type, "document_number": _BAD_DOC_NUMBER},
        )
    assert resp.status_code == 422
    assert _BAD_DOC_NUMBER not in resp.text


async def test_api_put_rejects_barrio_with_other_municipality(
    seeded, imderty_client_factory
):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.put(
            _profile_url(seeded.parent_athlete_one_id),
            json={"barrio_id": 1, "other_municipality": True},
        )
    assert resp.status_code == 422


async def test_api_put_rejects_split_that_does_not_rebuild(
    seeded, imderty_client_factory
):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.put(
            _profile_url(seeded.parent_athlete_one_id),
            json={
                "first_surname": "Quintero",
                "second_surname": "Zapatoca",
                "confirm_surname_split": True,
            },
        )
    assert resp.status_code == 422
    assert "Zapatoca" not in resp.text


async def test_api_put_confirms_split_and_saves_fields(seeded, imderty_client_factory):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.put(
            _profile_url(seeded.parent_athlete_one_id),
            json={
                "first_surname": "Quintero",
                "second_surname": "Del Valle",
                "confirm_surname_split": True,
                "document_type": "ti",
                "document_number": _DOC_NUMBER,
                "barrio_id": 1,
                "grade": "g5",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["surname_split"]["confirmed"] is True
    assert body["barrio"] == {"id": 1, "name": "BARRIO FICTICIO UNO", "zone": "1"}
    assert body["grade"] == "g5"
    assert body["warnings"] == []


async def test_api_duplicate_document_in_club_returns_200_with_warning(
    seeded, imderty_client_factory
):
    payload = {"document_type": "ti", "document_number": _DOC_NUMBER}
    async with imderty_client_factory(seeded.coach_user_id) as client:
        first = await client.put(_profile_url(seeded.parent_athlete_one_id), json=payload)
        second = await client.put(_profile_url(seeded.parent_athlete_two_id), json=payload)
    assert first.status_code == 200
    assert first.json()["warnings"] == []
    assert second.status_code == 200
    assert second.json()["warnings"] == ["duplicate_document_in_club"]


async def test_api_primary_contact_flow(seeded, imderty_client_factory):
    athlete_id = seeded.two_guardians_athlete_id
    async with imderty_client_factory(seeded.coach_user_id) as client:
        not_linked = await client.put(
            _primary_url(athlete_id), json={"guardian_user_id": _UNRELATED_USER_ID}
        )
        assert not_linked.status_code == 422

        first = await client.put(
            _primary_url(athlete_id),
            json={"guardian_user_id": seeded.second_guardian_user_id},
        )
        assert first.status_code == 200
        primaries = [g["user_id"] for g in first.json() if g["is_primary_contact"]]
        assert primaries == [seeded.second_guardian_user_id]

        switched = await client.put(
            _primary_url(athlete_id), json={"guardian_user_id": seeded.parent_user_id}
        )
        assert switched.status_code == 200
        primaries = [g["user_id"] for g in switched.json() if g["is_primary_contact"]]
        assert primaries == [seeded.parent_user_id]

    # Unlinking the primary guardian (existing route) drops the mark with the row.
    relation_id = (
        await seeded.session.execute(
            select(ParentAthlete.id).where(
                ParentAthlete.athlete_id == athlete_id,
                ParentAthlete.parent_id == seeded.parent_user_id,
            )
        )
    ).scalar_one()
    async with imderty_client_factory(seeded.coach_user_id) as client:
        unlink = await client.delete(f"/api/parent-athletes/{relation_id}")
        assert unlink.status_code == 204
        profile = await client.get(_profile_url(athlete_id))
    assert profile.status_code == 200
    guardians = profile.json()["guardians"]
    assert [g["user_id"] for g in guardians] == [seeded.second_guardian_user_id]
    assert not any(g["is_primary_contact"] for g in guardians)


async def test_api_patch_last_name_clears_confirmation(seeded, imderty_client_factory):
    athlete_id = seeded.parent_athlete_one_id
    async with imderty_client_factory(seeded.coach_user_id) as client:
        put = await client.put(
            _profile_url(athlete_id),
            json={
                "first_surname": "Quintero",
                "second_surname": "Del Valle",
                "confirm_surname_split": True,
            },
        )
        assert put.status_code == 200
        assert put.json()["surname_split"]["confirmed"] is True

        patch = await client.patch(
            f"/api/athletes/{athlete_id}", json={"last_name": "Quintero Del Monte"}
        )
        assert patch.status_code == 200

        after = await client.get(_profile_url(athlete_id))
    assert after.status_code == 200
    split = after.json()["surname_split"]
    assert split["confirmed"] is False
    assert split["proposed_second"] == "Del Monte"

    profile = await seeded.session.get(
        AthleteImdertyProfile, athlete_id, populate_existing=True
    )
    assert profile.surname_split_confirmed_at is None
    assert profile.surname_split_confirmed_by_user_id is None


@pytest.mark.parametrize("user_attr", ["parent_user_id", "foreign_coach_user_id"])
async def test_api_denied_for_parent_and_foreign_coach(
    seeded, imderty_client_factory, user_attr
):
    athlete_id = seeded.parent_athlete_one_id
    async with imderty_client_factory(getattr(seeded, user_attr)) as client:
        get = await client.get(_profile_url(athlete_id))
        put = await client.put(_profile_url(athlete_id), json={"eps": "EPS FICTICIA"})
        primary = await client.put(
            _primary_url(athlete_id), json={"guardian_user_id": seeded.parent_user_id}
        )
    assert get.status_code == 403
    assert put.status_code == 403
    assert primary.status_code == 403


async def test_api_admin_allowed(seeded, imderty_client_factory):
    async with imderty_client_factory(seeded.admin_user_id) as client:
        resp = await client.get(_profile_url(seeded.parent_athlete_one_id))
    assert resp.status_code == 200


async def test_api_audit_changed_fields_only(seeded, imderty_client_factory):
    async with imderty_client_factory(seeded.coach_user_id) as client:
        resp = await client.put(
            _profile_url(seeded.parent_athlete_one_id),
            json={
                "document_type": "ti",
                "document_number": _DOC_NUMBER,
                "address": "CALLE FICTICIA 1 # 2-3",
                "eps": "EPS FICTICIA",
                "phone": "3000000047",
            },
        )
    assert resp.status_code == 200

    rows = await _audit_rows(seeded, AuditEntityType.athlete_imderty_profile.value)
    assert len(rows) == 1
    assert set(rows[0].changed_fields) == {
        "address",
        "document_number",
        "document_type",
        "eps",
        "phone",
    }
    assert rows[0].diff_json is None
    dumped = json.dumps(
        [rows[0].changed_fields, rows[0].diff_json, rows[0].meta_json], default=str
    )
    for value in (_DOC_NUMBER, "CALLE FICTICIA", "EPS FICTICIA", "3000000047"):
        assert value not in dumped
