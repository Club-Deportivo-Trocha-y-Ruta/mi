"""US5 (feature 011): chat prompt grounding rule + tool registration."""
from __future__ import annotations

from app.services.race.agents.chat import RaceChatAgent
from app.services.race.prompts import render_prompt


def test_chat_prompt_has_grounding_rule():
    out = render_prompt("race_chat_v1", {}, strict=False)
    assert "obtener_condiciones_evento" in out
    assert "no quedó registrado" in out
    assert "PROHIBIDO" in out


def test_conditions_tool_registered_in_agent():
    agent = RaceChatAgent(db_factory=lambda: object())
    names = [t.name for t in agent._tools]
    assert "obtener_condiciones_evento" in names
