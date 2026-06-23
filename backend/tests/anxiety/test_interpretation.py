"""T030 [US4] — interpretation: LLM path, schema, fallback parity, alert flag."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from app.config import settings
from app.services.ai.providers.fake import FakeLLMProvider
from app.models.user import UserRole
from tests.anxiety.conftest import (
    VALID_INTERPRETATION,
    grant_consent,
    make_client,
    seed_athlete,
    seed_instruments,
    seed_user,
)

SCHEDULED = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc).isoformat()
_REQUIRED_KEYS = {
    "resumen",
    "por_dimension",
    "estrategias",
    "mensaje_para_el_atleta",
    "banderas",
}


async def _answered(session, answers: dict[str, int]) -> int:
    await seed_instruments(session)
    await seed_user(session, 20, UserRole.parent)
    await seed_athlete(session, 100, date(2012, 6, 1), user_id=901)
    await grant_consent(session, 100, 20)
    await session.commit()
    async with make_client(session) as client:
        created = await client.post(
            "/api/anxiety/assessments",
            json={"athlete_id": 100, "scheduled_at": SCHEDULED},
        )
        token = created.json()["token"]["token"]
        aid = created.json()["id"]
    async with make_client(session, authed=False) as client:
        await client.post(f"/api/anxiety/answer/{token}", json={"answers": answers})
    return aid


@pytest.fixture
def ai_on(monkeypatch):
    """Force the AI layer on for LLM-path assertions (default is off in tests)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    yield


def _assert_schema(interp: dict) -> None:
    assert _REQUIRED_KEYS <= set(interp)
    assert set(interp["por_dimension"]) == {"cognitiva", "somatica", "autoconfianza"}
    assert isinstance(interp["estrategias"], list)
    assert isinstance(interp["banderas"], list)


@pytest.mark.asyncio
async def test_llm_path_returns_schema_and_caches(session, ai_on):
    aid = await _answered(session, {str(i): 2 for i in range(1, 18)})
    async with make_client(session) as client:
        resp = await client.post(f"/api/anxiety/assessments/{aid}/interpret")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source"] == "llm"
        _assert_schema(body["interpretation"])

        # Cached on the assessment (GET returns it)
        read = await client.get(f"/api/anxiety/assessments/{aid}")
        assert read.json()["interpretation"] is not None
        assert read.json()["interpretation_source"] == "llm"


@pytest.mark.asyncio
async def test_invalid_json_falls_back_to_rule(session, ai_on):
    aid = await _answered(session, {str(i): 2 for i in range(1, 18)})
    broken = FakeLLMProvider(canned="this is not json")
    async with make_client(session, fake_provider=broken) as client:
        resp = await client.post(f"/api/anxiety/assessments/{aid}/interpret")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rule"
    _assert_schema(body["interpretation"])


@pytest.mark.asyncio
async def test_high_anxiety_low_confidence_alert_flag(session):
    # somatic items high (4), cognitive high (4), self-confidence low (1).
    key_high = {1, 4, 6, 9, 12, 15, 17, 2, 5, 8, 11, 14}  # somatic+cognitive
    answers = {}
    for i in range(1, 18):
        answers[str(i)] = 4 if i in key_high else 1
    aid = await _answered(session, answers)
    async with make_client(session) as client:
        read = await client.get(f"/api/anxiety/assessments/{aid}")
    flags = read.json()["flags"]
    assert flags, "expected an alert flag for high anxiety + low confidence"
    assert any("derivaci" in f.lower() or "conversaci" in f.lower() for f in flags)


@pytest.mark.asyncio
async def test_fallback_and_llm_produce_same_schema(session, ai_on):
    answers = {str(i): 2 for i in range(1, 18)}
    aid = await _answered(session, answers)
    good = FakeLLMProvider(canned=json.dumps(VALID_INTERPRETATION))
    bad = FakeLLMProvider(canned="nope")
    async with make_client(session, fake_provider=good) as client:
        llm = (await client.post(f"/api/anxiety/assessments/{aid}/interpret")).json()
    async with make_client(session, fake_provider=bad) as client:
        rule = (await client.post(f"/api/anxiety/assessments/{aid}/interpret")).json()
    assert set(llm["interpretation"]) == set(rule["interpretation"])
