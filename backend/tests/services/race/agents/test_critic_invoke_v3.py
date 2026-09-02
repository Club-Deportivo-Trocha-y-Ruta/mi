"""Tests de ``RaceCriticAgent.invoke_v3`` (feature 037, T202)."""

from __future__ import annotations

import json

import pytest

from app.services.race.agents.critic import PROMPT_VERSION_CRITIC_V3, RaceCriticAgent
from app.services.race.ai.prechecks import PrecheckCategory, PrecheckIssue
from app.services.race.schemas import CriticIssue


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = text
        self.usage_metadata = {"input_tokens": 42, "output_tokens": 7}


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[str] = []

    async def ainvoke(self, messages):
        self.calls.append(messages[0].content)
        return _FakeResponse(self._text)


def _clean_json() -> str:
    return json.dumps({"approved": True, "severity": "low", "issues": [], "must_block": False})


@pytest.mark.asyncio
async def test_invoke_v3_happy_path(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    llm = _FakeLLM(_clean_json())
    agent = RaceCriticAgent(llm=llm)

    feedback, metrics = await agent.invoke_v3({"headline": "x"}, "ground truth block", [])

    assert feedback.approved is True
    assert feedback.must_block is False
    assert metrics.prompt_version == PROMPT_VERSION_CRITIC_V3
    assert metrics.tokens_in == 42


@pytest.mark.asyncio
async def test_invoke_v3_disabled_bypasses_llm(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "false")
    llm = _FakeLLM(_clean_json())
    agent = RaceCriticAgent(llm=llm)

    feedback, _metrics = await agent.invoke_v3({"headline": "x"}, "ground truth", [])

    assert feedback.approved is True
    assert llm.calls == []


@pytest.mark.asyncio
async def test_invoke_v3_includes_precheck_summary_in_prompt(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    llm = _FakeLLM(_clean_json())
    agent = RaceCriticAgent(llm=llm)

    precheck_issues = [
        PrecheckIssue(
            category=PrecheckCategory.CATALOG,
            issue=CriticIssue(
                section="catalog_ref", problem="código inexistente", suggested_fix="quitar ref"
            ),
        )
    ]
    await agent.invoke_v3({"headline": "x"}, "ground truth", precheck_issues)

    assert len(llm.calls) == 1
    assert "código inexistente" in llm.calls[0]
    assert "catalog" in llm.calls[0]


@pytest.mark.asyncio
async def test_invoke_v3_malformed_json_forces_block(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    llm = _FakeLLM("no es json")
    agent = RaceCriticAgent(llm=llm)

    feedback, _metrics = await agent.invoke_v3({"headline": "x"}, "ground truth", [])

    assert feedback.must_block is True
    assert feedback.approved is False


def test_draft_to_json_handles_pydantic_model():
    from pydantic import BaseModel

    class _Draft(BaseModel):
        headline: str

    text = RaceCriticAgent._draft_to_json(_Draft(headline="hola"))
    assert json.loads(text) == {"headline": "hola"}


def test_draft_to_json_handles_plain_dict():
    text = RaceCriticAgent._draft_to_json({"headline": "hola"})
    assert json.loads(text) == {"headline": "hola"}
