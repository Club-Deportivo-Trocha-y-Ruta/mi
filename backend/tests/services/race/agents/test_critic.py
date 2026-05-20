"""Tests del :class:`RaceCriticAgent` (Fase 3 race-results v2)."""
from __future__ import annotations

import json

import pytest

from app.services.race.agents.critic import RaceCriticAgent, _critic_enabled
from app.services.race.agents.pricing import PROMPT_VERSION_CRITIC
from app.services.race.schemas import (
    AnalysisOutput,
    CriticFeedback,
    CriticIssueSeverity,
)
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage


def _draft(raw: str = "## Evolución\nbla bla.") -> AnalysisOutput:
    return AnalysisOutput(
        pseudonym="Atleta-X-001",
        sections={"evolution": "bla bla."},
        citations_used=[],
        recommendations=[],
        risk_flags=[],
        raw_markdown=raw,
        word_count=3,
    )


async def test_critic_approved_no_issues(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    payload = {"approved": True, "severity": "low", "issues": [], "must_block": False}
    llm = FakeChatLLM([StubAIMessage(content=json.dumps(payload), usage_metadata={"input_tokens": 800, "output_tokens": 50})])
    agent = RaceCriticAgent(llm=llm)

    fb, metrics = await agent.invoke(_draft())

    assert fb.approved is True
    assert fb.must_block is False
    assert fb.issues == []
    assert metrics.tokens_in == 800
    assert metrics.cost_usd > 0
    assert metrics.prompt_version == PROMPT_VERSION_CRITIC


async def test_critic_rejects_with_issues(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    payload = {
        "approved": False,
        "severity": "high",
        "must_block": True,
        "issues": [
            {
                "section": "Recomendaciones LTAD",
                "problem": "Suplemento mencionado",
                "suggested_fix": "Eliminar referencia a creatina",
            }
        ],
    }
    llm = FakeChatLLM([StubAIMessage(content=json.dumps(payload))])
    agent = RaceCriticAgent(llm=llm)

    fb, _ = await agent.invoke(_draft())
    assert fb.approved is False
    assert fb.must_block is True
    assert fb.severity == CriticIssueSeverity.HIGH
    assert len(fb.issues) == 1
    assert "creatina" in fb.issues[0].suggested_fix.lower()


async def test_critic_disabled_returns_pass_through_without_calling_llm(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "false")
    # FakeChatLLM con cero respuestas → si se llama lanza RuntimeError.
    llm = FakeChatLLM([])
    agent = RaceCriticAgent(llm=llm)

    fb, metrics = await agent.invoke(_draft())

    assert fb.approved is True
    assert fb.must_block is False
    assert metrics.tokens_in == 0
    assert metrics.cost_usd == 0.0
    assert llm.calls == []  # nunca se invocó.


async def test_critic_disabled_flag_variants(monkeypatch):
    for value in ("0", "off", "NO", "False"):
        monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", value)
        assert _critic_enabled() is False
    for value in ("true", "1", "yes", ""):
        # "" no setea — usa el default si delete.
        if value:
            monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", value)
        else:
            monkeypatch.delenv("RACE_AGENT_CRITIC_ENABLED", raising=False)
        assert _critic_enabled() is True


async def test_critic_unparseable_output_forces_block(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    llm = FakeChatLLM([StubAIMessage(content="esto no es JSON, lo siento")])
    agent = RaceCriticAgent(llm=llm)

    fb, _ = await agent.invoke(_draft())

    assert fb.must_block is True
    assert fb.approved is False
    assert fb.severity == CriticIssueSeverity.HIGH
    assert len(fb.issues) == 1
    assert "no produjo JSON" in fb.issues[0].problem


async def test_critic_handles_json_wrapped_in_code_fence(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    payload = {"approved": True, "severity": "low", "issues": [], "must_block": False}
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    llm = FakeChatLLM([StubAIMessage(content=wrapped)])
    agent = RaceCriticAgent(llm=llm)

    fb, _ = await agent.invoke(_draft())
    assert fb.approved is True
    assert fb.must_block is False


async def test_critic_handles_json_with_leading_prose(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    payload = {"approved": False, "severity": "med", "issues": [], "must_block": False}
    text = "Aquí va mi veredicto: " + json.dumps(payload) + " (fin)"
    llm = FakeChatLLM([StubAIMessage(content=text)])
    agent = RaceCriticAgent(llm=llm)

    fb, _ = await agent.invoke(_draft())
    assert fb.approved is False
    assert fb.severity == CriticIssueSeverity.MED
