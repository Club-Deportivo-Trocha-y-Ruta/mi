"""T028 — Age-band guardrail on strength block entries (feature 021, US3).

Covers (contracts/strength-api.md, data-model.md validation rule 2, FR-011):
  - POST /api/strength/blocks with an entry whose exercise's age_bands do NOT
    include the block's target_age_band, submitted WITHOUT
    is_age_override=true, returns 422 with an AGE_BAND_GUARDRAIL code/detail
    (Spanish explanation of which exercise and why).
  - The same request WITH is_age_override=true (optionally with
    override_note) returns 201 and the persisted entry has
    is_age_override=true (and the submitted override_note, when provided).
  - An exercise whose age_bands DO include the target band never triggers
    the guardrail, even when is_age_override is omitted (defaults to False)
    — the entry persists with is_age_override=false.

Uses the shared `seed_strength_catalog` fixtures (conftest.py):
  - "plancha-test"    → age_bands = {10-12}            only
  - "remo-banda-test" → age_bands = {13-15}             only
  - "flexiones-test"  → age_bands = {10-12, 13-15}      both
  - "sentadilla-test" → age_bands = {10-12, 13-15}      both

All tests run on aiosqlite in-memory — no live MySQL, no real network.
Will fail until T029 (blocks.py guardrail enforcement) is implemented.
"""
from __future__ import annotations

import pytest

from tests.strength.conftest import make_client, seed_club, seed_coach, seed_strength_catalog

BASE = "/api/strength"


async def _setup(session) -> dict:
    """Seed club 1, its coach, and the strength catalog; commit."""
    await seed_club(session, club_id=1)
    await seed_coach(session, user_id=10, club_id=1)
    catalog = await seed_strength_catalog(session)
    await session.commit()
    return catalog


def _block_payload(
    *,
    name: str = "Bloque de fuerza de prueba",
    target_age_band: str = "13-15",
    duration_target_min: int = 30,
    entries: list[dict],
) -> dict:
    return {
        "name": name,
        "target_age_band": target_age_band,
        "duration_target_min": duration_target_min,
        "entries": entries,
    }


# ===========================================================================
# Mismatch, no override → 422 AGE_BAND_GUARDRAIL
# ===========================================================================


@pytest.mark.asyncio
async def test_age_band_mismatch_without_override_returns_422_guardrail(session):
    """Entry exercise's age_bands ∌ target_age_band, no is_age_override → 422."""
    catalog = await _setup(session)
    ex_plancha = catalog["exercises"]["plancha"]  # age_bands = {10-12} only

    payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_plancha.id,
                "position": 0,
                "duration_min": 5,
                "reps": "3x15-20 seg",
            },
        ],
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)

    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail = body["detail"]
    # Structured detail: a code identifying the guardrail plus a human
    # (Spanish) explanation of which exercise/band triggered it.
    assert isinstance(detail, dict)
    assert detail.get("code") == "AGE_BAND_GUARDRAIL"
    message = detail.get("message") or detail.get("detail") or ""
    assert "plancha" in message.lower() or str(ex_plancha.id) in message


@pytest.mark.asyncio
async def test_age_band_mismatch_without_override_persists_nothing(session):
    """A rejected 422 create must not leave a partially-created block behind."""
    catalog = await _setup(session)
    ex_plancha = catalog["exercises"]["plancha"]

    payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_plancha.id,
                "position": 0,
                "duration_min": 5,
                "reps": "3x15-20 seg",
            },
        ],
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)
        assert resp.status_code == 422, resp.text

        list_resp = await client.get(f"{BASE}/blocks")
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json()["total"] == 0


# ===========================================================================
# Mismatch, WITH override → 201, is_age_override persisted true
# ===========================================================================


@pytest.mark.asyncio
async def test_age_band_mismatch_with_override_returns_201_and_persists_flag(session):
    """Same mismatched entry, is_age_override=true → 201, entry flagged true."""
    catalog = await _setup(session)
    ex_plancha = catalog["exercises"]["plancha"]  # age_bands = {10-12} only

    payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_plancha.id,
                "position": 0,
                "duration_min": 5,
                "reps": "3x15-20 seg",
                "is_age_override": True,
                "override_note": "Atleta 13-15 con base técnica sólida en plancha.",
            },
        ],
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["entries"]) == 1
    entry = body["entries"][0]
    assert entry["is_age_override"] is True
    assert entry["override_note"] == "Atleta 13-15 con base técnica sólida en plancha."
    assert entry["exercise"]["id"] == ex_plancha.id


@pytest.mark.asyncio
async def test_age_band_mismatch_with_override_no_note_still_succeeds(session):
    """override_note is optional — omitting it still allows the override through."""
    catalog = await _setup(session)
    ex_plancha = catalog["exercises"]["plancha"]

    payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_plancha.id,
                "position": 0,
                "duration_min": 5,
                "reps": "3x15-20 seg",
                "is_age_override": True,
            },
        ],
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)

    assert resp.status_code == 201, resp.text
    entry = resp.json()["entries"][0]
    assert entry["is_age_override"] is True
    assert entry["override_note"] is None


# ===========================================================================
# Matching band → guardrail never triggers, even without the override flag
# ===========================================================================


@pytest.mark.asyncio
async def test_matching_age_band_never_triggers_guardrail(session):
    """Exercise whose age_bands DO include the target band → 201 regardless
    of is_age_override being omitted (defaults False) and persists false."""
    catalog = await _setup(session)
    ex_remo = catalog["exercises"]["remo_banda"]  # age_bands = {13-15} only

    payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_remo.id,
                "position": 0,
                "duration_min": 7,
                "reps": "2x12",
            },
        ],
    )
    async with make_client(session) as client:
        resp = await client.post(f"{BASE}/blocks", json=payload)

    assert resp.status_code == 201, resp.text
    entry = resp.json()["entries"][0]
    assert entry["is_age_override"] is False
    assert entry["override_note"] is None


@pytest.mark.asyncio
async def test_matching_age_band_multi_band_exercise_never_triggers_guardrail(session):
    """Exercise covering both bands never triggers the guardrail for either band."""
    catalog = await _setup(session)
    ex_flexiones = catalog["exercises"]["flexiones"]  # age_bands = {10-12, 13-15}

    for target_band in ("10-12", "13-15"):
        payload = _block_payload(
            target_age_band=target_band,
            entries=[
                {
                    "exercise_id": ex_flexiones.id,
                    "position": 0,
                    "duration_min": 6,
                    "reps": "2x10",
                },
            ],
        )
        async with make_client(session) as client:
            resp = await client.post(f"{BASE}/blocks", json=payload)
        assert resp.status_code == 201, resp.text
        entry = resp.json()["entries"][0]
        assert entry["is_age_override"] is False


# ===========================================================================
# Guardrail also applies on PUT (full replace) — same semantics as POST
# ===========================================================================


@pytest.mark.asyncio
async def test_update_block_entry_age_band_mismatch_without_override_returns_422(session):
    """PUT (full replace) enforces the same guardrail as POST (contracts.md)."""
    catalog = await _setup(session)
    ex_sentadilla = catalog["exercises"]["sentadilla"]  # both bands — safe seed entry
    ex_plancha = catalog["exercises"]["plancha"]  # 10-12 only — mismatch on 13-15

    create_payload = _block_payload(
        target_age_band="13-15",
        entries=[
            {
                "exercise_id": ex_sentadilla.id,
                "position": 0,
                "duration_min": 10,
                "reps": "3x10",
            },
        ],
    )
    async with make_client(session) as client:
        create_resp = await client.post(f"{BASE}/blocks", json=create_payload)
        assert create_resp.status_code == 201, create_resp.text
        block_id = create_resp.json()["id"]

        update_payload = _block_payload(
            target_age_band="13-15",
            entries=[
                {
                    "exercise_id": ex_plancha.id,
                    "position": 0,
                    "duration_min": 5,
                    "reps": "3x15-20 seg",
                },
            ],
        )
        update_resp = await client.put(f"{BASE}/blocks/{block_id}", json=update_payload)

    assert update_resp.status_code == 422, update_resp.text
    assert update_resp.json()["detail"].get("code") == "AGE_BAND_GUARDRAIL"
