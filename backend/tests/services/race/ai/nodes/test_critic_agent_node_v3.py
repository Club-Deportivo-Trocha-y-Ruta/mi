"""Tests de la rama v3 del nodo ``critic_agent`` (feature 037, T202)."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel

from app.models.athlete_ai_insight import InsightConfidence
from app.services.race.ai.nodes.critic_agent import critic_agent
from app.services.race.schemas import CriticFeedback, RunMetrics


class _Observation(BaseModel):
    claim: str
    evidence: list[str] = []


class _Draft(BaseModel):
    headline: str
    observations: list[_Observation] = []
    actions: list = []
    watch_signals: list[str] = []
    coach_question: str = "¿Cómo te sentiste?"
    field_reading: Optional[dict] = None


class _FakeCriticAgentV3:
    """Stub de ``RaceCriticAgent`` que solo implementa la rama v3."""

    def __init__(self, feedback: CriticFeedback | None = None) -> None:
        self._feedback = feedback or CriticFeedback(approved=True)
        self.invoke_v3_calls: list[tuple] = []

    @staticmethod
    def is_enabled() -> bool:
        return True

    async def invoke_v3(self, draft, ground_truth, precheck_issues):
        self.invoke_v3_calls.append((draft, ground_truth, precheck_issues))
        return self._feedback, RunMetrics(
            tokens_in=1, tokens_out=1, latency_ms=1, cost_usd=0.0,
            prompt_version="race_critic_v3",
        )


def _clean_draft(headline="Terminó 5ta con gap de 8.6% al líder") -> _Draft:
    return _Draft(
        headline=headline,
        observations=[_Observation(claim="Consistente con 8.6% previo", evidence=["8.6%"])],
    )


@pytest.mark.asyncio
async def test_v3_branch_runs_prechecks_and_merges_verdict(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    fake = _FakeCriticAgentV3()
    state = {
        "per_valida_drafts_v3": {1: _clean_draft()},
        "grounding_numbers": {1: ["8.6", "5"]},
        "training_window": {"attended": 5},
        "anthro_context": {"records_count": 1},
        "season_validas_count": 3,
        "_critic_agent": fake,
    }

    update = await critic_agent(state)

    assert fake.invoke_v3_calls  # se invocó el LLM v3
    assert update["per_valida_verdicts"][1].approved is True
    assert update["confidence"][1] == InsightConfidence.high
    assert 1 in update["precheck_issues"]
    assert update["critic_feedback"].approved is True


@pytest.mark.asyncio
async def test_v3_branch_ltad_precheck_forces_must_block_even_if_llm_approves(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    fake = _FakeCriticAgentV3(feedback=CriticFeedback(approved=True))
    draft = _Draft(
        headline="Recomendar suplementos para mejorar rendimiento",
        observations=[_Observation(claim="Necesita más energía", evidence=["1"])],
    )
    state = {
        "per_valida_drafts_v3": {1: draft},
        "_critic_agent": fake,
    }

    update = await critic_agent(state)

    assert update["per_valida_verdicts"][1].must_block is True
    assert update["confidence"][1] == InsightConfidence.low


@pytest.mark.asyncio
async def test_v3_branch_catalog_issue_sanitizes_draft_without_blocking(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    fake = _FakeCriticAgentV3()

    class _CatalogRef(BaseModel):
        kind: str
        code: str

    class _Action(BaseModel):
        text: str
        catalog_ref: Optional[_CatalogRef] = None

    class _DraftWithAction(_Draft):
        actions: list[_Action] = []

    draft = _DraftWithAction(
        headline="Terminó 5ta",
        actions=[_Action(text="Practicar habilidad", catalog_ref=_CatalogRef(kind="technique_skill", code="Z"))],
    )
    state = {
        "per_valida_drafts_v3": {1: draft},
        "catalog_context": {"technique_skills": [{"code": "A"}]},
        "_critic_agent": fake,
    }

    update = await critic_agent(state)

    assert update["per_valida_verdicts"][1].must_block is False
    sanitized = update["per_valida_drafts_v3"][1]
    assert sanitized.actions[0].catalog_ref is None


@pytest.mark.asyncio
async def test_v3_branch_skips_none_drafts(monkeypatch):
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "true")
    fake = _FakeCriticAgentV3()
    state = {
        "per_valida_drafts_v3": {1: None, 2: _clean_draft()},
        "_critic_agent": fake,
    }

    update = await critic_agent(state)

    assert 1 not in update["per_valida_verdicts"]
    assert 2 in update["per_valida_verdicts"]
