"""T044/T045 [US6] — CSV import (incl. CSAI-2 27-item) + export round-trip."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.user import UserRole
from tests.anxiety.conftest import (
    grant_consent,
    make_client,
    seed_athlete,
    seed_instruments,
    seed_user,
)


def _csv_csai2r(athlete_ref: int) -> str:
    header = "athlete_ref,instrument,date," + ",".join(f"i{i}" for i in range(1, 18))
    values = f"{athlete_ref},csai2r,2026-04-19," + ",".join("2" for _ in range(17))
    return header + "\n" + values + "\n"


def _csv_csai2_27(athlete_ref: int) -> str:
    header = "athlete_ref,instrument,date," + ",".join(f"i{i}" for i in range(1, 28))
    values = f"{athlete_ref},csai2,2026-04-19," + ",".join("2" for _ in range(27))
    return header + "\n" + values + "\n"


async def _setup(session) -> None:
    await seed_instruments(session)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await grant_consent(session, 100, 20)
    await session.commit()


@pytest.mark.asyncio
async def test_import_csai2r_scores_and_seeds_baseline(session):
    await _setup(session)
    csv_text = _csv_csai2r(100)
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/import",
            files={"file": ("hist.csv", csv_text, "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0

    async with make_client(session) as client:
        series = await client.get(
            "/api/anxiety/athletes/100/series?instrument_type=csai2r"
        )
    assert series.json()["baseline_cognitive"] == 20.0  # (2/n)*10


@pytest.mark.asyncio
async def test_import_csai2_27_item(session):
    await _setup(session)
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/import",
            files={"file": ("hist27.csv", _csv_csai2_27(100), "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1


@pytest.mark.asyncio
async def test_import_reports_bad_rows_without_crashing(session):
    await _setup(session)
    csv_text = _csv_csai2r(100)
    # add a row for an athlete with no consent / not existing
    bad = "999,csai2r,2026-04-19," + ",".join("2" for _ in range(17))
    csv_text = csv_text + bad + "\n"
    async with make_client(session) as client:
        resp = await client.post(
            "/api/anxiety/import",
            files={"file": ("mixed.csv", csv_text, "text/csv")},
        )
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert body["errors"]


@pytest.mark.asyncio
async def test_export_json_includes_scores_and_answers(session):
    await _setup(session)
    async with make_client(session) as client:
        await client.post(
            "/api/anxiety/import",
            files={"file": ("hist.csv", _csv_csai2r(100), "text/csv")},
        )
        resp = await client.get("/api/anxiety/export?format=json&athlete_id=100")
    assert resp.status_code == 200, resp.text
    records = resp.json()["assessments"]
    assert len(records) == 1
    rec = records[0]
    assert rec["score_cognitive"] == 20.0
    assert rec["answers"]  # item answers present


@pytest.mark.asyncio
async def test_export_csv_format(session):
    await _setup(session)
    async with make_client(session) as client:
        await client.post(
            "/api/anxiety/import",
            files={"file": ("hist.csv", _csv_csai2r(100), "text/csv")},
        )
        resp = await client.get("/api/anxiety/export?format=csv&athlete_id=100")
    assert resp.status_code == 200, resp.text
    assert "i1" in resp.text
    assert "score_cognitive" in resp.text
