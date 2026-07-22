"""T010 — Guardrail matrix for Structured Interval Training (feature 026, US1).

Covers (contracts/api.md, data-model.md §1 validation rule, research.md D2/D3,
services/intervals/structures.py::validate_structure_blocks):

  1. ``cadence_below_minimum`` (FR-004) — target_cadence_rpm < 60 is rejected
     with HTTP 422 in **every** age band, on both structures and templates.
     ``BlockIn.target_cadence_rpm`` carries a Pydantic ``ge=60`` constraint
     (schemas/intervals.py), so the HTTP-level create/update endpoints for
     structures and templates surface this as FastAPI's standard schema-
     validation 422 (a list-shaped ``detail``) rather than the service
     layer's machine-readable ``{"code": "cadence_below_minimum", ...}``
     envelope — Pydantic short-circuits before the request body ever reaches
     ``validate_structure_blocks``. The custom code is still real
     "defense in depth" (structures.py module docstring): it fires whenever
     a low-cadence block reaches the service layer *without* going through
     ``BlockIn`` first, which happens on template-attach (cloned ORM blocks
     built directly from ``IntervalTemplateBlock`` rows — see
     ``templates.py::_clone_blocks_to_block_in``). This suite asserts 422 in
     every band + surface (create/update/template, HTTP layer) and, on the
     attach path where a corrupted/legacy low-cadence template block is
     seeded directly at the DB layer bypassing the schema, asserts the exact
     machine-readable code.

  2. ``age_gate_z3_blocked`` (FR-006) — band ``10-12`` + any flattened block
     at Z3/Z4/Z5 is a **hard** block, no override, even when
     ``age_gate_confirmed=true`` is sent. Exercised on structure create,
     structure update, template create, template update, and — via a
     directly-seeded (schema-bypassing) 10-12 template block at Z3 — the
     template-attach path, proving the guardrail is not merely a client-side
     gate that a legacy/corrupted template row could slip past.

  3. ``age_gate_confirmation_required`` (FR-007) — band ``10-12`` with all
     blocks Z1-Z2 requires an explicit ``age_gate_confirmed=true``; the
     first attempt without it is rejected, and resubmitting with
     ``age_gate_confirmed=true`` succeeds and **persists** who confirmed
     (``age_gate_confirmed_by_user_id``) and when
     (``age_gate_confirmed_at``) — asserted both via the API response
     (``StructureOut.age_gate_confirmed_by``/``age_gate_confirmed_at``) and
     by reloading the row directly from the DB. Exercised on structure
     create, structure update, and template-attach (template *save* never
     requires confirmation — see ``templates.py`` module docstring: a
     template has no ``age_gate_confirmed`` column, the real gate is
     deferred to attach time). Band ``13-15`` never triggers the gate,
     confirmed or not — asserted as a boundary/negative control.

All tests run on aiosqlite in-memory (``tests/intervals/conftest.py``) — no
live MySQL, no real network. Seed data uses fictitious names/dates — never
real TyR athlete data (CLAUDE.md §Privacy).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models.interval_structure import (
    HRZone,
    IntervalBlockType,
    IntervalStructure,
    IntervalTemplate,
    IntervalTemplateBlock,
)
from app.models.technique_exercise import AgeBand
from tests.intervals.conftest import (
    make_client,
    seed_club,
    seed_coach,
    seed_training_session,
)

BASE = "/api/intervals"


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------


async def _setup(session) -> None:
    """Seed club 1 + its coach (user_id=10); commit."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    await session.commit()


async def _seed_training_session(session, *, scheduled_date: date = date(2026, 7, 10)):
    """Insert a bare TrainingSession and commit (thin wrapper over the shared
    ``conftest.seed_training_session``, which only flushes).

    Each guardrail scenario that creates/updates a *structure* needs its own
    session because ``interval_structures.training_session_id`` is UNIQUE
    (1:1, data-model.md §1).
    """
    ts = await seed_training_session(session, scheduled_date=scheduled_date)
    await session.commit()
    return ts


def _block(
    *,
    position: int,
    block_type: str = "work",
    duration_type: str = "fixed",
    duration_s: int | None = 300,
    target_zone: str = "Z1",
    target_cadence_rpm: int = 70,
    repeat_group: int | None = None,
    repeat_count: int | None = None,
) -> dict:
    return {
        "position": position,
        "block_type": block_type,
        "duration_type": duration_type,
        "duration_s": duration_s,
        "target_zone": target_zone,
        "target_cadence_rpm": target_cadence_rpm,
        "repeat_group": repeat_group,
        "repeat_count": repeat_count,
    }


def _blocks_with_open_warmup(*, warmup_block_type: str = "warmup") -> list[dict]:
    """An open_lap warmup/cooldown + one fixed work block — happy path shape
    for the feature-034 duration-type guardrails (never trips cadence/age
    gate on its own — Z1/Z2, cadence 70/80)."""
    return [
        _block(
            position=1,
            block_type=warmup_block_type,
            duration_type="open_lap",
            duration_s=None,
            target_zone="Z1",
            target_cadence_rpm=70,
        ),
        _block(
            position=2,
            block_type="work",
            duration_type="fixed",
            duration_s=300,
            target_zone="Z2",
            target_cadence_rpm=80,
        ),
    ]


def _safe_blocks(*, cadence: int = 70) -> list[dict]:
    """Three well-formed Z1/Z2 blocks — never trips any guardrail on its own."""
    return [
        _block(position=1, block_type="warmup", target_zone="Z1", target_cadence_rpm=cadence),
        _block(position=2, block_type="work", target_zone="Z2", target_cadence_rpm=cadence + 5),
        _block(position=3, block_type="cooldown", target_zone="Z1", target_cadence_rpm=cadence),
    ]


def _blocks_with_zone(zone: str) -> list[dict]:
    """Three blocks where the middle ``work`` block sits at ``zone``."""
    return [
        _block(position=1, block_type="warmup", target_zone="Z1", target_cadence_rpm=70),
        _block(position=2, block_type="work", target_zone=zone, target_cadence_rpm=80),
        _block(position=3, block_type="cooldown", target_zone="Z1", target_cadence_rpm=65),
    ]


def _blocks_with_low_cadence(*, bad_cadence: int = 55) -> list[dict]:
    """Three blocks where the middle ``work`` block has cadence < 60."""
    return [
        _block(position=1, block_type="warmup", target_zone="Z1", target_cadence_rpm=70),
        _block(position=2, block_type="work", target_zone="Z2", target_cadence_rpm=bad_cadence),
        _block(position=3, block_type="cooldown", target_zone="Z1", target_cadence_rpm=65),
    ]


def _structure_payload(
    *,
    training_session_id: int,
    target_age_band: str = "13-15",
    age_gate_confirmed: bool = False,
    blocks: list[dict] | None = None,
) -> dict:
    return {
        "training_session_id": training_session_id,
        "target_age_band": target_age_band,
        "age_gate_confirmed": age_gate_confirmed,
        "blocks": blocks if blocks is not None else _safe_blocks(),
    }


def _template_payload(
    *,
    target_age_band: str = "13-15",
    blocks: list[dict] | None = None,
    name: str = "Plantilla de prueba",
    mesocycle_phase: str = "base",
    competition_proximity: str = "general",
) -> dict:
    return {
        "name": name,
        "target_age_band": target_age_band,
        "mesocycle_phase": mesocycle_phase,
        "competition_proximity": competition_proximity,
        "blocks": blocks if blocks is not None else _safe_blocks(),
    }


async def _load_structure(session, structure_id: int) -> IntervalStructure:
    """Reload a persisted ``IntervalStructure`` row directly from the DB
    (bypassing the API/response schema) to assert the raw persisted columns."""
    result = await session.execute(
        select(IntervalStructure).where(IntervalStructure.id == structure_id)
    )
    return result.scalar_one()


async def _seed_raw_template(
    session,
    *,
    target_age_band: AgeBand,
    block_kwargs: dict,
    club_id: int = 1,
    created_by_user_id: int = 10,
) -> IntervalTemplate:
    """Insert an ``IntervalTemplate`` + one ``IntervalTemplateBlock`` directly
    via the ORM, **bypassing** ``services/intervals/templates.py::create_template``
    (and therefore its ``validate_structure_blocks`` call and the
    ``BlockIn`` Pydantic schema).

    Used only to exercise the service-layer "defense in depth" checks that
    the docstrings in ``structures.py``/``templates.py`` call out explicitly:
    ``attach_template`` clones ORM blocks straight from
    ``IntervalTemplateBlock`` rows, so a template saved before a rule
    existed (or corrupted by any non-API write path) must still be caught
    at attach time — the guardrail cannot rely on the client-facing schema
    alone. Never reachable via ``POST /api/intervals/templates`` itself
    (that path enforces the same rules at save time).
    """
    template = IntervalTemplate(
        name="Plantilla legado de prueba",
        target_age_band=target_age_band,
        mesocycle_phase="base",
        competition_proximity="general",
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        is_archived=False,
    )
    session.add(template)
    await session.flush()

    session.add(
        IntervalTemplateBlock(
            template_id=template.id,
            position=1,
            block_type=IntervalBlockType(block_kwargs.get("block_type", "work")),
            duration_s=block_kwargs.get("duration_s", 120),
            target_zone=HRZone(block_kwargs["target_zone"]),
            target_cadence_rpm=block_kwargs["target_cadence_rpm"],
            repeat_group=None,
            repeat_count=None,
        )
    )
    await session.commit()
    await session.refresh(template)
    return template


# ===========================================================================
# 1. cadence_below_minimum (FR-004) — every band, structures + templates
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("band", ["10-12", "13-15"])
async def test_cadence_below_minimum_on_structure_create_returns_422(session, band):
    """A block with target_cadence_rpm < 60 is rejected with 422, any band."""
    await _setup(session)
    ts = await _seed_training_session(session)

    payload = _structure_payload(
        training_session_id=ts.id,
        target_age_band=band,
        blocks=_blocks_with_low_cadence(),
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("band", ["10-12", "13-15"])
async def test_cadence_below_minimum_on_structure_update_returns_422(session, band):
    """PUT enforces the same cadence floor as POST, any band."""
    await _setup(session)
    ts = await _seed_training_session(session)

    create_payload = _structure_payload(training_session_id=ts.id, target_age_band=band)
    # Band 10-12 with Z1-Z2 blocks requires an explicit confirmation to save;
    # this test's subject is the UPDATE cadence floor, so pre-confirm the arrange.
    create_payload["age_gate_confirmed"] = True
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=create_payload)
        assert create_resp.status_code == 201, create_resp.text
        structure_id = create_resp.json()["id"]

        update_payload = {
            "target_age_band": band,
            "age_gate_confirmed": False,
            "blocks": _blocks_with_low_cadence(),
        }
        update_resp = await client.put(
            f"{BASE}/structures/{structure_id}", json=update_payload
        )

    assert update_resp.status_code == 422, update_resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("band", ["10-12", "13-15"])
async def test_cadence_below_minimum_on_template_create_returns_422(session, band):
    """A template with a sub-60 cadence block never saves, any band."""
    await _setup(session)

    payload = _template_payload(target_age_band=band, blocks=_blocks_with_low_cadence())
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/templates", json=payload)

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_cadence_below_minimum_enforced_at_attach_defense_in_depth(session):
    """Service-layer cadence check fires independently of the Pydantic schema.

    A low-cadence template block seeded directly at the DB layer (bypassing
    ``BlockIn``'s ``ge=60`` and ``create_template``'s validation) is still
    caught by ``validate_structure_blocks`` when the template is attached —
    proving FR-004 has no exception, including for data that never passed
    through the HTTP-facing schema.
    """
    await _setup(session)
    template = await _seed_raw_template(
        session,
        target_age_band=AgeBand.BAND_13_15,
        block_kwargs={"target_zone": "Z2", "target_cadence_rpm": 55},
    )
    ts = await _seed_training_session(session)

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/templates/{template.id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == "cadence_below_minimum"
    assert detail.get("positions") == [1]


# ===========================================================================
# 2. age_gate_z3_blocked (FR-006) — hard, no override, band 10-12 only
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("zone", ["Z3", "Z4", "Z5"])
async def test_age_gate_z3_blocked_on_structure_create(session, zone):
    """Any Z3+ block on a 10-12 structure is a hard 422, no override CTA."""
    await _setup(session)
    ts = await _seed_training_session(session)

    payload = _structure_payload(
        training_session_id=ts.id,
        target_age_band="10-12",
        age_gate_confirmed=True,  # even confirmed=true must NOT bypass this
        blocks=_blocks_with_zone(zone),
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == "age_gate_z3_blocked"
    assert detail.get("positions") == [2]


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_not_bypassed_by_confirmed_flag(session):
    """age_gate_confirmed=true never overrides the hard Z3+ block (FR-006)."""
    await _setup(session)
    ts = await _seed_training_session(session)

    payload = _structure_payload(
        training_session_id=ts.id,
        target_age_band="10-12",
        age_gate_confirmed=True,
        blocks=_blocks_with_zone("Z4"),
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"].get("code") == "age_gate_z3_blocked"


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_persists_nothing_on_create(session):
    """A rejected create must not leave a partially-created structure behind."""
    await _setup(session)
    ts = await _seed_training_session(session)

    payload = _structure_payload(
        training_session_id=ts.id, target_age_band="10-12", blocks=_blocks_with_zone("Z3")
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)
        assert resp.status_code == 422, resp.text

        get_resp = await client.get(f"{BASE}/sessions/{ts.id}/structure")
    assert get_resp.status_code == 404, get_resp.text


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_on_structure_update(session):
    """PUT enforces the same hard Z3+ block as POST."""
    await _setup(session)
    ts = await _seed_training_session(session)

    create_payload = _structure_payload(training_session_id=ts.id, target_age_band="13-15")
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/structures", json=create_payload)
        assert create_resp.status_code == 201, create_resp.text
        structure_id = create_resp.json()["id"]

        update_payload = {
            "target_age_band": "10-12",
            "age_gate_confirmed": True,
            "blocks": _blocks_with_zone("Z3"),
        }
        update_resp = await client.put(
            f"{BASE}/structures/{structure_id}", json=update_payload
        )

    assert update_resp.status_code == 422, update_resp.text
    assert update_resp.json()["detail"].get("code") == "age_gate_z3_blocked"


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_on_template_create(session):
    """A 10-12 template can never be saved with a Z3+ block (kept clean at source)."""
    await _setup(session)

    payload = _template_payload(target_age_band="10-12", blocks=_blocks_with_zone("Z3"))
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/templates", json=payload)

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"].get("code") == "age_gate_z3_blocked"


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_on_template_update(session):
    """PUT on a template enforces the same hard Z3+ block as create."""
    await _setup(session)

    create_payload = _template_payload(target_age_band="13-15")
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=create_payload)
        assert create_resp.status_code == 201, create_resp.text
        template_id = create_resp.json()["id"]

        update_payload = _template_payload(
            target_age_band="10-12", blocks=_blocks_with_zone("Z5")
        )
        update_resp = await client.put(f"{BASE}/templates/{template_id}", json=update_payload)

    assert update_resp.status_code == 422, update_resp.text
    assert update_resp.json()["detail"].get("code") == "age_gate_z3_blocked"


@pytest.mark.asyncio
async def test_age_gate_z3_blocked_at_attach_defense_in_depth(session):
    """A legacy/corrupted 10-12 template block at Z3, seeded directly at the DB
    layer (bypassing create_template's own Z3 guard), is still hard-blocked
    at attach time — even with age_gate_confirmed=true."""
    await _setup(session)
    template = await _seed_raw_template(
        session,
        target_age_band=AgeBand.BAND_10_12,
        block_kwargs={"target_zone": "Z3", "target_cadence_rpm": 80},
    )
    ts = await _seed_training_session(session)

    async with make_client(session) as client:
        resp = await client.post(
            f"{BASE}/templates/{template.id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": True},
        )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail.get("code") == "age_gate_z3_blocked"

    # No structure was created for the session as a side effect of the
    # rejected attach.
    async with make_client(session) as client:
        get_resp = await client.get(f"{BASE}/sessions/{ts.id}/structure")
    assert get_resp.status_code == 404, get_resp.text


# ===========================================================================
# 3. age_gate_confirmation_required (FR-007) — then success, persists user+timestamp
# ===========================================================================


@pytest.mark.asyncio
async def test_age_gate_confirmation_required_on_structure_create_without_confirmed(session):
    """Band 10-12, all blocks Z1-Z2, no confirmation → 422."""
    await _setup(session)
    ts = await _seed_training_session(session)

    payload = _structure_payload(training_session_id=ts.id, target_age_band="10-12")
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("code") == "age_gate_confirmation_required"


@pytest.mark.asyncio
async def test_age_gate_confirmation_required_then_success_persists_confirmer_and_timestamp(
    session,
):
    """First attempt (unconfirmed) → 422; resubmitting with
    age_gate_confirmed=true → 201, and the response + the raw DB row both
    carry the confirming user and a confirmation timestamp (FR-007)."""
    await _setup(session)
    ts = await _seed_training_session(session)

    before = datetime.now(timezone.utc)

    async with make_client(session) as client:
        first_resp = await client.post(
            f"{BASE}/structures",
            json=_structure_payload(training_session_id=ts.id, target_age_band="10-12"),
        )
        assert first_resp.status_code == 422, first_resp.text
        assert first_resp.json()["detail"].get("code") == "age_gate_confirmation_required"

        second_resp = await client.post(
            f"{BASE}/structures",
            json=_structure_payload(
                training_session_id=ts.id,
                target_age_band="10-12",
                age_gate_confirmed=True,
            ),
        )

    assert second_resp.status_code == 201, second_resp.text
    body = second_resp.json()
    assert body["age_gate_confirmed"] is True
    assert body["age_gate_confirmed_by"] is not None
    assert "Entrenador" in body["age_gate_confirmed_by"]
    assert body["age_gate_confirmed_at"] is not None

    row = await _load_structure(session, body["id"])
    assert row.age_gate_confirmed is True
    assert row.age_gate_confirmed_by_user_id == 10  # seed_coach(user_id=10)
    assert row.age_gate_confirmed_at is not None
    confirmed_at = row.age_gate_confirmed_at
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
    assert confirmed_at >= before


@pytest.mark.asyncio
async def test_age_gate_confirmation_required_on_structure_update(session):
    """PUT enforces the same confirmation gate as POST, and resubmitting
    confirmed=true persists the confirmer + timestamp."""
    await _setup(session)
    ts = await _seed_training_session(session)

    async with make_client(session) as client:
        create_resp = await client.post(
            f"{BASE}/structures",
            json=_structure_payload(training_session_id=ts.id, target_age_band="13-15"),
        )
        assert create_resp.status_code == 201, create_resp.text
        structure_id = create_resp.json()["id"]

        unconfirmed_resp = await client.put(
            f"{BASE}/structures/{structure_id}",
            json={
                "target_age_band": "10-12",
                "age_gate_confirmed": False,
                "blocks": _safe_blocks(),
            },
        )
        assert unconfirmed_resp.status_code == 422, unconfirmed_resp.text
        assert (
            unconfirmed_resp.json()["detail"].get("code")
            == "age_gate_confirmation_required"
        )

        confirmed_resp = await client.put(
            f"{BASE}/structures/{structure_id}",
            json={
                "target_age_band": "10-12",
                "age_gate_confirmed": True,
                "blocks": _safe_blocks(),
            },
        )

    assert confirmed_resp.status_code == 200, confirmed_resp.text
    body = confirmed_resp.json()
    assert body["age_gate_confirmed"] is True
    assert body["age_gate_confirmed_by"] is not None
    assert body["age_gate_confirmed_at"] is not None

    row = await _load_structure(session, structure_id)
    assert row.age_gate_confirmed is True
    assert row.age_gate_confirmed_by_user_id is not None
    assert row.age_gate_confirmed_at is not None


@pytest.mark.asyncio
async def test_age_gate_confirmation_not_required_for_band_13_15(session):
    """Band 13-15 never triggers the age gate, confirmed or not (boundary)."""
    await _setup(session)
    ts_a = await _seed_training_session(session, scheduled_date=date(2026, 7, 10))
    ts_b = await _seed_training_session(session, scheduled_date=date(2026, 7, 17))

    async with make_client(session) as client:
        unconfirmed_resp = await client.post(
            f"{BASE}/structures",
            json=_structure_payload(
                training_session_id=ts_a.id,
                target_age_band="13-15",
                age_gate_confirmed=False,
            ),
        )
        confirmed_resp = await client.post(
            f"{BASE}/structures",
            json=_structure_payload(
                training_session_id=ts_b.id,
                target_age_band="13-15",
                age_gate_confirmed=True,
            ),
        )

    assert unconfirmed_resp.status_code == 201, unconfirmed_resp.text
    assert unconfirmed_resp.json()["age_gate_confirmed_by"] is None
    assert confirmed_resp.status_code == 201, confirmed_resp.text


@pytest.mark.asyncio
async def test_age_gate_confirmation_required_then_success_on_template_attach(session):
    """Template save never requires confirmation (no such field on Template);
    the real gate is deferred to attach time — first attach unconfirmed
    → 422, resubmitting confirmed=true → 201, persisting confirmer+timestamp
    on the resulting structure."""
    await _setup(session)

    async with make_client(session) as client:
        template_resp = await client.post(
            f"{BASE}/templates",
            json=_template_payload(target_age_band="10-12"),
        )
    assert template_resp.status_code == 201, template_resp.text
    template_id = template_resp.json()["id"]

    ts = await _seed_training_session(session)

    async with make_client(session) as client:
        unconfirmed_attach = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
        assert unconfirmed_attach.status_code == 422, unconfirmed_attach.text
        assert (
            unconfirmed_attach.json()["detail"].get("code")
            == "age_gate_confirmation_required"
        )

        confirmed_attach = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": True},
        )

    assert confirmed_attach.status_code == 201, confirmed_attach.text
    body = confirmed_attach.json()
    assert body["age_gate_confirmed"] is True
    assert body["age_gate_confirmed_by"] is not None
    assert body["age_gate_confirmed_at"] is not None

    row = await _load_structure(session, body["id"])
    assert row.age_gate_confirmed_by_user_id == 10
    assert row.age_gate_confirmed_at is not None


@pytest.mark.asyncio
async def test_age_gate_confirmation_not_required_when_template_band_13_15_attach(session):
    """A 13-15 template attaches without any confirmation, regardless of the
    flag's value (boundary — the gate is 10-12-only, D3)."""
    await _setup(session)

    async with make_client(session) as client:
        template_resp = await client.post(
            f"{BASE}/templates",
            json=_template_payload(target_age_band="13-15"),
        )
    assert template_resp.status_code == 201, template_resp.text
    template_id = template_resp.json()["id"]

    ts = await _seed_training_session(session)

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )

    assert attach_resp.status_code == 201, attach_resp.text
    assert attach_resp.json()["age_gate_confirmed_by"] is None


# ===========================================================================
# 4. duration_type guardrails (feature 034) — open_lap vs fixed
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("block_type", ["warmup", "cooldown"])
async def test_open_lap_allowed_on_warmup_and_cooldown(session, block_type):
    """An open_lap block on warmup/cooldown saves fine (happy path,
    contracts/api-delta.md)."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = _blocks_with_open_warmup(warmup_block_type=block_type)
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    open_block = next(b for b in body["blocks"] if b["position"] == 1)
    assert open_block["duration_type"] == "open_lap"
    assert open_block["duration_s"] is None
    # Fixed sibling block is unaffected.
    fixed_block = next(b for b in body["blocks"] if b["position"] == 2)
    assert fixed_block["duration_type"] == "fixed"
    assert fixed_block["duration_s"] == 300


@pytest.mark.asyncio
@pytest.mark.parametrize("block_type", ["work", "recovery"])
async def test_open_lap_rejected_on_work_and_recovery(session, block_type):
    """open_lap is hard-restricted to warmup/cooldown — work/recovery reject
    with 422 open_lap_invalid_block_type."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = [
        _block(
            position=1,
            block_type=block_type,
            duration_type="open_lap",
            duration_s=None,
            target_zone="Z1",
            target_cadence_rpm=70,
        ),
    ]
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "open_lap_invalid_block_type"
    assert detail["positions"] == [1]


@pytest.mark.asyncio
async def test_open_lap_rejected_when_in_repeat_group(session):
    """A block cannot be both open_lap and part of a repeat group (spec edge
    case: order-independent — the server rejects the combined state
    regardless of which field the client conceptually 'set first')."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = [
        _block(
            position=1,
            block_type="warmup",
            duration_type="open_lap",
            duration_s=None,
            target_zone="Z1",
            target_cadence_rpm=70,
            repeat_group=1,
            repeat_count=2,
        ),
        _block(
            position=2,
            block_type="warmup",
            duration_type="open_lap",
            duration_s=None,
            target_zone="Z1",
            target_cadence_rpm=70,
            repeat_group=1,
            repeat_count=2,
        ),
    ]
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "open_lap_repeat_group_not_allowed"
    assert detail["positions"] == [1, 2]


@pytest.mark.asyncio
async def test_open_lap_rejected_with_duration_s_present(session):
    """An open_lap block must not carry a duration_s value."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = [
        _block(
            position=1,
            block_type="warmup",
            duration_type="open_lap",
            duration_s=120,
            target_zone="Z1",
            target_cadence_rpm=70,
        ),
    ]
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "open_lap_duration_not_allowed"
    assert detail["positions"] == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration_s", [None, 0, -5])
async def test_fixed_block_requires_positive_duration(session, bad_duration_s):
    """A fixed block (the default type) with a missing/non-positive
    duration_s is rejected — the cross-field rule that used to live in the
    schema's Field(gt=0) now lives here (service layer, feature 034)."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = [
        _block(
            position=1,
            block_type="work",
            duration_type="fixed",
            duration_s=bad_duration_s,
            target_zone="Z1",
            target_cadence_rpm=70,
        ),
    ]
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "fixed_duration_required"
    assert detail["positions"] == [1]


@pytest.mark.asyncio
async def test_duration_type_defaults_to_fixed_when_omitted(session):
    """A block payload without ``duration_type`` behaves exactly as before
    (FR-011, backward compatibility) — defaults to 'fixed', still requiring
    a positive ``duration_s``, and the response echoes 'fixed' explicitly."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = [
        {
            "position": 1,
            "block_type": "work",
            "duration_s": 300,
            "target_zone": "Z1",
            "target_cadence_rpm": 70,
            "repeat_group": None,
            "repeat_count": None,
        },
    ]
    payload = _structure_payload(training_session_id=ts.id, blocks=blocks)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/structures", json=payload)

    assert resp.status_code == 201, resp.text
    assert resp.json()["blocks"][0]["duration_type"] == "fixed"


@pytest.mark.asyncio
async def test_open_lap_on_10_12_structure_still_requires_age_gate_confirmation(session):
    """duration_type and age-gate guardrails are independent: an open_lap
    warmup at Z1 on a 10-12 structure still needs explicit age-gate
    confirmation (FR-007), unrelated to its duration type."""
    await _setup(session)
    ts = await _seed_training_session(session)

    blocks = _blocks_with_open_warmup()
    payload = _structure_payload(
        training_session_id=ts.id, target_age_band="10-12", blocks=blocks
    )

    async with make_client(session) as client:
        unconfirmed = await client.post(f"{BASE}/structures", json=payload)
    assert unconfirmed.status_code == 422, unconfirmed.text
    assert unconfirmed.json()["detail"]["code"] == "age_gate_confirmation_required"

    payload["age_gate_confirmed"] = True
    async with make_client(session) as client:
        confirmed = await client.post(f"{BASE}/structures", json=payload)
    assert confirmed.status_code == 201, confirmed.text
