"""T030 — Interval template library (feature 026, US4).

Covers (contracts/api.md §Templates, data-model.md §3-4):
  - POST /api/intervals/templates: CRUD create with tags
    (target_age_band/mesocycle_phase/competition_proximity) and blocks.
  - GET /api/intervals/templates: club-scoped list, filterable by the three
    tag query params (age_band, mesocycle_phase, competition_proximity).
  - PUT /api/intervals/templates/{id}: full replace.
  - PATCH /api/intervals/templates/{id}/archive: soft-archive toggle;
    archived templates excluded from the default list, included with
    ?include_archived=true (mirrors strength_blocks / test_blocks.py).
  - POST /api/intervals/templates/{id}/attach: copy-on-attach — clones
    template blocks into a brand-new IntervalStructure for the target
    session. Independence is proven by mutating *both* sides afterward
    (editing the template does not touch an already-attached structure,
    and editing the attached structure does not touch the template) —
    verified via re-attach to a fresh session, since there is no
    standalone GET /templates/{id} endpoint in the contract (lap/template
    detail is only ever read via the list or via what was attached).
  - Z3+ on a `10-12`-tagged template → 422 `age_gate_z3_blocked` at *save*
    time (hard, no override — research D3/contracts §Templates).
  - Attaching a `10-12`-tagged, Z1-Z2-only template requires
    `age_gate_confirmed: true` in the attach body → 422
    `age_gate_confirmation_required` without it, 201 with it (persists
    `age_gate_confirmed_by`/`age_gate_confirmed_at` on the new structure).
  - POST /templates/{id}/attach onto a session that already has a
    structure → 409 (same 1:1 invariant as POST /structures).
  - RBAC: parent → 403 on create/list/attach.

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Will fail until T031 (templates service: CRUD + attach_template) and T032
(template router endpoints) exist.

Depends on `tests/intervals/conftest.py` (T009) for the identity/session
fixtures — mirrors the `tests/strength/conftest.py` convention exactly
(coach/admin/parent User helpers injected via `get_current_user` override,
`make_client` AsyncClient factory, `seed_club`/`seed_coach` DB helpers).

Seed data uses fictitious names/dates — never real TyR athlete data
(non-negotiable constraint, CLAUDE.md §Privacy).
"""
from __future__ import annotations

from datetime import date

import pytest

from tests.intervals.conftest import (
    coach_user_obj,
    make_client,
    parent_user_obj,
    seed_club,
    seed_coach,
    seed_training_session,
)

BASE = "/api/intervals"

# ---------------------------------------------------------------------------
# Shared setup / payload helpers
# ---------------------------------------------------------------------------


async def _seed_base(session, *, club_id: int = 1, coach_id: int = 10) -> None:
    """Seed club + coach; commit."""
    await seed_club(session, club_id=club_id)
    await seed_coach(session, user_id=coach_id, club_id=club_id)
    await session.commit()


async def _seed_training_session(
    session,
    *,
    club_id: int = 1,
    created_by_user_id: int = 10,
    scheduled_date: date = date(2026, 7, 10),
):
    """Insert a bare TrainingSession via the shared conftest helper and commit
    (conftest's ``seed_training_session`` only flushes; the extra commit here
    keeps this file's call sites identical to the pre-shared-helper version)."""
    ts = await seed_training_session(
        session,
        club_id=club_id,
        created_by_user_id=created_by_user_id,
        scheduled_date=scheduled_date,
    )
    await session.commit()
    await session.refresh(ts)
    return ts


def _block(
    *,
    position: int,
    block_type: str = "work",
    duration_type: str = "fixed",
    duration_s: int | None = 120,
    target_zone: str = "Z2",
    target_cadence_rpm: int = 75,
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


def _standard_blocks(*, work_duration_s: int = 120) -> list[dict]:
    """A benign, always-valid warmup/work/cooldown triple (Z1/Z2 only, cadence
    within bounds) — safe for any age band and for cadence/z3 guardrails.
    """
    return [
        _block(position=1, block_type="warmup", duration_s=300, target_zone="Z1", target_cadence_rpm=70),
        _block(position=2, block_type="work", duration_s=work_duration_s, target_zone="Z2", target_cadence_rpm=80),
        _block(position=3, block_type="cooldown", duration_s=300, target_zone="Z1", target_cadence_rpm=65),
    ]


def _template_payload(
    *,
    name: str = "Plantilla de intervalos de prueba",
    target_age_band: str = "13-15",
    mesocycle_phase: str = "base",
    competition_proximity: str = "general",
    blocks: list[dict] | None = None,
) -> dict:
    return {
        "name": name,
        "target_age_band": target_age_band,
        "mesocycle_phase": mesocycle_phase,
        "competition_proximity": competition_proximity,
        "blocks": blocks if blocks is not None else _standard_blocks(),
    }


def _sum_durations(blocks: list[dict]) -> int:
    """Sum of fixed-block durations — open_lap blocks (feature 034) carry
    ``duration_s: None`` and contribute 0, mirroring
    ``structures.total_planned_duration_s``."""
    return sum(b["duration_s"] for b in blocks if b.get("duration_s") is not None)


# ===========================================================================
# CRUD — create
# ===========================================================================


@pytest.mark.asyncio
async def test_create_template_returns_201_with_tags_and_blocks(session):
    await _seed_base(session)

    payload = _template_payload()
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/templates", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == payload["name"]
    assert body["target_age_band"] == "13-15"
    assert body["mesocycle_phase"] == "base"
    assert body["competition_proximity"] == "general"
    assert body["is_archived"] is False
    assert len(body["blocks"]) == 3
    assert body["total_planned_duration_s"] == _sum_durations(payload["blocks"])
    assert "id" in body


# ===========================================================================
# CRUD — list + tag filters
# ===========================================================================


@pytest.mark.asyncio
async def test_list_templates_returns_created_template(session):
    await _seed_base(session)
    payload = _template_payload()
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        list_resp = await client.get(f"{BASE}/templates")
    assert list_resp.status_code == 200, list_resp.text
    body = list_resp.json()
    ids = {item["id"] for item in body["items"]}
    assert template_id in ids
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_filter_templates_by_age_band(session):
    await _seed_base(session)

    async with make_client(session) as client:
        resp_10_12 = await client.post(
            f"{BASE}/templates",
            json=_template_payload(name="Plantilla 10-12", target_age_band="10-12"),
        )
        resp_13_15 = await client.post(
            f"{BASE}/templates",
            json=_template_payload(name="Plantilla 13-15", target_age_band="13-15"),
        )
    assert resp_10_12.status_code == 201, resp_10_12.text
    assert resp_13_15.status_code == 201, resp_13_15.text
    id_10_12 = resp_10_12.json()["id"]
    id_13_15 = resp_13_15.json()["id"]

    async with make_client(session) as client:
        filtered = await client.get(f"{BASE}/templates?age_band=10-12")
    assert filtered.status_code == 200, filtered.text
    ids = {item["id"] for item in filtered.json()["items"]}
    assert id_10_12 in ids
    assert id_13_15 not in ids


@pytest.mark.asyncio
async def test_filter_templates_by_mesocycle_phase(session):
    await _seed_base(session)

    async with make_client(session) as client:
        resp_base = await client.post(
            f"{BASE}/templates",
            json=_template_payload(name="Plantilla base", mesocycle_phase="base"),
        )
        resp_taper = await client.post(
            f"{BASE}/templates",
            json=_template_payload(name="Plantilla taper", mesocycle_phase="taper"),
        )
    assert resp_base.status_code == 201, resp_base.text
    assert resp_taper.status_code == 201, resp_taper.text
    id_base = resp_base.json()["id"]
    id_taper = resp_taper.json()["id"]

    async with make_client(session) as client:
        filtered = await client.get(f"{BASE}/templates?mesocycle_phase=taper")
    assert filtered.status_code == 200, filtered.text
    ids = {item["id"] for item in filtered.json()["items"]}
    assert id_taper in ids
    assert id_base not in ids


@pytest.mark.asyncio
async def test_filter_templates_by_competition_proximity(session):
    await _seed_base(session)

    async with make_client(session) as client:
        resp_general = await client.post(
            f"{BASE}/templates",
            json=_template_payload(name="Plantilla general", competition_proximity="general"),
        )
        resp_race_week = await client.post(
            f"{BASE}/templates",
            json=_template_payload(
                name="Plantilla semana de carrera", competition_proximity="semana-carrera"
            ),
        )
    assert resp_general.status_code == 201, resp_general.text
    assert resp_race_week.status_code == 201, resp_race_week.text
    id_general = resp_general.json()["id"]
    id_race_week = resp_race_week.json()["id"]

    async with make_client(session) as client:
        filtered = await client.get(f"{BASE}/templates?competition_proximity=semana-carrera")
    assert filtered.status_code == 200, filtered.text
    ids = {item["id"] for item in filtered.json()["items"]}
    assert id_race_week in ids
    assert id_general not in ids


# ===========================================================================
# CRUD — update (PUT)
# ===========================================================================


@pytest.mark.asyncio
async def test_put_template_full_replace_updates_tags_and_blocks(session):
    await _seed_base(session)
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=_template_payload())
    template_id = create_resp.json()["id"]

    update_payload = _template_payload(
        name="Plantilla actualizada",
        mesocycle_phase="especifico",
        competition_proximity="pre-competencia",
        blocks=_standard_blocks(work_duration_s=180),
    )
    async with make_client(session) as client:
        put_resp = await client.put(f"{BASE}/templates/{template_id}", json=update_payload)
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["name"] == "Plantilla actualizada"
    assert body["mesocycle_phase"] == "especifico"
    assert body["competition_proximity"] == "pre-competencia"
    assert body["total_planned_duration_s"] == _sum_durations(update_payload["blocks"])


@pytest.mark.asyncio
async def test_put_template_unknown_id_returns_404(session):
    await _seed_base(session)
    async with make_client(session) as client:
        resp = await client.put(f"{BASE}/templates/99999", json=_template_payload())
    assert resp.status_code == 404, resp.text


# ===========================================================================
# CRUD — archive
# ===========================================================================


@pytest.mark.asyncio
async def test_archive_excludes_template_from_default_list(session):
    await _seed_base(session)
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=_template_payload())
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        archive_resp = await client.patch(
            f"{BASE}/templates/{template_id}/archive", json={"is_archived": True}
        )
    assert archive_resp.status_code == 200, archive_resp.text
    assert archive_resp.json()["is_archived"] is True

    async with make_client(session) as client:
        default_resp = await client.get(f"{BASE}/templates")
    assert default_resp.status_code == 200, default_resp.text
    ids_default = {item["id"] for item in default_resp.json()["items"]}
    assert template_id not in ids_default

    async with make_client(session) as client:
        included_resp = await client.get(f"{BASE}/templates?include_archived=true")
    assert included_resp.status_code == 200, included_resp.text
    ids_included = {item["id"] for item in included_resp.json()["items"]}
    assert template_id in ids_included


@pytest.mark.asyncio
async def test_archive_can_be_reverted(session):
    await _seed_base(session)
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=_template_payload())
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        await client.patch(f"{BASE}/templates/{template_id}/archive", json={"is_archived": True})

    async with make_client(session) as client:
        revert_resp = await client.patch(
            f"{BASE}/templates/{template_id}/archive", json={"is_archived": False}
        )
    assert revert_resp.status_code == 200, revert_resp.text
    assert revert_resp.json()["is_archived"] is False

    async with make_client(session) as client:
        list_resp = await client.get(f"{BASE}/templates")
    ids = {item["id"] for item in list_resp.json()["items"]}
    assert template_id in ids


@pytest.mark.asyncio
async def test_archive_unknown_id_returns_404(session):
    await _seed_base(session)
    async with make_client(session) as client:
        resp = await client.patch(f"{BASE}/templates/99999/archive", json={"is_archived": True})
    assert resp.status_code == 404, resp.text


# ===========================================================================
# Attach — copy-on-attach, independent clone (mutate both sides)
# ===========================================================================


@pytest.mark.asyncio
async def test_attach_clones_blocks_into_new_structure(session):
    await _seed_base(session)
    ts = await _seed_training_session(session)

    payload = _template_payload(blocks=_standard_blocks(work_duration_s=150))
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=payload)
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert attach_resp.status_code == 201, attach_resp.text
    structure = attach_resp.json()
    assert structure["training_session_id"] == ts.id
    assert structure["target_age_band"] == "13-15"
    assert len(structure["blocks"]) == 3
    assert structure["total_planned_duration_s"] == _sum_durations(payload["blocks"])

    async with make_client(session) as client:
        get_resp = await client.get(f"{BASE}/sessions/{ts.id}/structure")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["id"] == structure["id"]


@pytest.mark.asyncio
async def test_editing_template_after_attach_does_not_change_attached_structure(session):
    """Mutate side 1: editing the template after attach must leave the
    already-attached structure's blocks untouched (independent copy)."""
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 11))

    original_blocks = _standard_blocks(work_duration_s=120)
    async with make_client(session) as client:
        create_resp = await client.post(
            f"{BASE}/templates", json=_template_payload(blocks=original_blocks)
        )
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert attach_resp.status_code == 201, attach_resp.text
    attached_total = attach_resp.json()["total_planned_duration_s"]
    assert attached_total == _sum_durations(original_blocks)

    # Mutate the template — bump the work block's duration.
    mutated_blocks = _standard_blocks(work_duration_s=999)
    async with make_client(session) as client:
        put_resp = await client.put(
            f"{BASE}/templates/{template_id}",
            json=_template_payload(blocks=mutated_blocks),
        )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["total_planned_duration_s"] == _sum_durations(mutated_blocks)

    # The already-attached structure must be unaffected.
    async with make_client(session) as client:
        get_resp = await client.get(f"{BASE}/sessions/{ts.id}/structure")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["total_planned_duration_s"] == attached_total
    assert get_resp.json()["total_planned_duration_s"] != _sum_durations(mutated_blocks)


@pytest.mark.asyncio
async def test_editing_attached_structure_does_not_change_template(session):
    """Mutate side 2: editing the attached structure afterward must leave the
    source template untouched — verified via a fresh re-attach to a second
    session (there is no standalone GET /templates/{id} in the contract)."""
    await _seed_base(session)
    ts_first = await _seed_training_session(session, scheduled_date=date(2026, 7, 12))
    ts_second = await _seed_training_session(session, scheduled_date=date(2026, 7, 13))

    original_blocks = _standard_blocks(work_duration_s=100)
    async with make_client(session) as client:
        create_resp = await client.post(
            f"{BASE}/templates", json=_template_payload(blocks=original_blocks)
        )
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts_first.id, "age_gate_confirmed": False},
        )
    assert attach_resp.status_code == 201, attach_resp.text
    structure_id = attach_resp.json()["id"]

    # Mutate the *attached structure* directly (not the template).
    mutated_blocks = _standard_blocks(work_duration_s=777)
    async with make_client(session) as client:
        struct_put_resp = await client.put(
            f"{BASE}/structures/{structure_id}",
            json={"target_age_band": "13-15", "blocks": mutated_blocks},
        )
    assert struct_put_resp.status_code == 200, struct_put_resp.text
    assert struct_put_resp.json()["total_planned_duration_s"] == _sum_durations(mutated_blocks)

    # Re-attach the same (unedited) template to a second session — its
    # blocks must still reflect the *original* durations, proving the first
    # structure edit never touched the template's own rows.
    async with make_client(session) as client:
        second_attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts_second.id, "age_gate_confirmed": False},
        )
    assert second_attach_resp.status_code == 201, second_attach_resp.text
    assert second_attach_resp.json()["total_planned_duration_s"] == _sum_durations(original_blocks)
    assert second_attach_resp.json()["total_planned_duration_s"] != _sum_durations(mutated_blocks)


# ===========================================================================
# Copy-on-attach preserves duration_type (feature 034, T025/T028)
# ===========================================================================


@pytest.mark.asyncio
async def test_attach_preserves_open_lap_duration_type(session):
    """A template with an open_lap warmup keeps that type (and the nullable
    duration_s) after copy-on-attach — verbatim, not defaulted to fixed."""
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 18))

    blocks = [
        _block(
            position=1,
            block_type="warmup",
            duration_type="open_lap",
            duration_s=None,
            target_zone="Z1",
            target_cadence_rpm=70,
        ),
        _block(
            position=2,
            block_type="work",
            duration_type="fixed",
            duration_s=180,
            target_zone="Z2",
            target_cadence_rpm=80,
        ),
    ]
    payload = _template_payload(blocks=blocks)
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]
    assert create_resp.json()["total_planned_duration_s"] == 180  # open contributes 0

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert attach_resp.status_code == 201, attach_resp.text
    body = attach_resp.json()
    assert body["total_planned_duration_s"] == 180

    cloned_open = next(b for b in body["blocks"] if b["position"] == 1)
    assert cloned_open["duration_type"] == "open_lap"
    assert cloned_open["duration_s"] is None
    cloned_fixed = next(b for b in body["blocks"] if b["position"] == 2)
    assert cloned_fixed["duration_type"] == "fixed"
    assert cloned_fixed["duration_s"] == 180


# ===========================================================================
# Age gate — Z3+ on a 10-12 template rejected at save
# ===========================================================================


@pytest.mark.asyncio
async def test_save_z3_block_on_10_12_template_returns_422_hard_block(session):
    await _seed_base(session)
    blocks_with_z3 = [
        _block(position=1, block_type="warmup", duration_s=300, target_zone="Z1", target_cadence_rpm=70),
        _block(position=2, block_type="work", duration_s=120, target_zone="Z3", target_cadence_rpm=75),
        _block(position=3, block_type="cooldown", duration_s=300, target_zone="Z1", target_cadence_rpm=65),
    ]
    payload = _template_payload(target_age_band="10-12", blocks=blocks_with_z3)

    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/templates", json=payload)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "age_gate_z3_blocked"


# ===========================================================================
# Age gate — attaching a 10-12 (Z1-Z2 only) template requires confirmation
# ===========================================================================


@pytest.mark.asyncio
async def test_attach_10_12_template_without_confirmation_returns_422(session):
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 14))

    payload = _template_payload(
        target_age_band="10-12", blocks=_standard_blocks(work_duration_s=90)
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert attach_resp.status_code == 422, attach_resp.text
    assert attach_resp.json()["detail"]["code"] == "age_gate_confirmation_required"


@pytest.mark.asyncio
async def test_attach_10_12_template_with_confirmation_succeeds_and_records_it(session):
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 15))

    payload = _template_payload(
        target_age_band="10-12", blocks=_standard_blocks(work_duration_s=90)
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/templates", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    async with make_client(session) as client:
        attach_resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": True},
        )
    assert attach_resp.status_code == 201, attach_resp.text
    body = attach_resp.json()
    assert body["age_gate_confirmed"] is True
    assert body["age_gate_confirmed_by"] is not None
    assert body["age_gate_confirmed_at"] is not None


# ===========================================================================
# 409 — attaching onto a session that already has a structure
# ===========================================================================


@pytest.mark.asyncio
async def test_attach_onto_already_structured_session_returns_409(session):
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 16))

    async with make_client(session) as client:
        template_a = await client.post(f"{BASE}/templates", json=_template_payload(name="Plantilla A"))
        template_b = await client.post(f"{BASE}/templates", json=_template_payload(name="Plantilla B"))
    assert template_a.status_code == 201, template_a.text
    assert template_b.status_code == 201, template_b.text
    template_a_id = template_a.json()["id"]
    template_b_id = template_b.json()["id"]

    async with make_client(session) as client:
        first_attach = await client.post(
            f"{BASE}/templates/{template_a_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert first_attach.status_code == 201, first_attach.text

    async with make_client(session) as client:
        second_attach = await client.post(
            f"{BASE}/templates/{template_b_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert second_attach.status_code == 409, second_attach.text


# ===========================================================================
# RBAC — parent receives 403
# ===========================================================================


@pytest.mark.asyncio
async def test_parent_receives_403_on_create_template(session):
    await _seed_base(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(f"{BASE}/templates", json=_template_payload())
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_parent_receives_403_on_list_templates(session):
    await _seed_base(session)
    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.get(f"{BASE}/templates")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_parent_receives_403_on_attach_template(session):
    await _seed_base(session)
    ts = await _seed_training_session(session, scheduled_date=date(2026, 7, 17))

    async with make_client(session, user=coach_user_obj(10)) as client:
        create_resp = await client.post(f"{BASE}/templates", json=_template_payload())
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    async with make_client(session, user=parent_user_obj(30)) as client:
        resp = await client.post(
            f"{BASE}/templates/{template_id}/attach",
            json={"training_session_id": ts.id, "age_gate_confirmed": False},
        )
    assert resp.status_code == 403, resp.text
