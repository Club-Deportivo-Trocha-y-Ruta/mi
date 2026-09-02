"""Tests del payload ``structured_draft`` del HITL (feature 037, T201).

``interrupt()`` solo corre dentro del runtime de LangGraph, así que el
payload se verifica sustituyendo el símbolo importado en el módulo — mismo
enfoque que ``test_hitl_gate.py`` usa para el resto del nodo.
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import hitl_gate_review as mod
from tests.services.race.ai.conftest import make_analysis_output, make_critic_feedback
from tests.services.race.test_insight_v3 import make_insight


@pytest.mark.asyncio
async def test_payload_includes_the_structured_draft(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "interrupt", lambda payload: captured.update(payload) or {"decision": "approve"}
    )

    insight = make_insight()
    await mod.hitl_gate_review(
        {
            "explain_mode": True,
            "draft_analysis": make_analysis_output(),
            "critic_feedback": make_critic_feedback(),
            "per_valida_drafts_v3": {4: insight},
        }
    )

    structured = captured["structured_draft"]
    assert structured["schema_version"] == "v3"
    assert structured["headline"] == insight.headline
    # Serializable a JSON: los enums viajan como string, no como objeto Python.
    assert structured["observations"][0]["domain"] == "training"
    assert structured["actions"][1]["catalog_ref"]["kind"] == "technique_skill"


@pytest.mark.asyncio
async def test_payload_structured_draft_is_none_for_v2_runs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "interrupt", lambda payload: captured.update(payload) or {"decision": "approve"}
    )

    await mod.hitl_gate_review(
        {
            "explain_mode": True,
            "draft_analysis": make_analysis_output(),
            "critic_feedback": make_critic_feedback(),
        }
    )

    assert captured["structured_draft"] is None
    assert captured["draft_markdown"]


def test_structured_draft_picks_the_lowest_valida():
    """Con varias válidas se envía la misma que ``draft_analysis`` (la menor)."""
    low = make_insight(headline="Hallazgo de la válida 4 con evidencia numérica")
    high = make_insight(headline="Hallazgo de la válida 5 con evidencia numérica")

    result = mod._structured_draft({"per_valida_drafts_v3": {5: high, 4: low}})

    assert result["headline"] == low.headline


def test_structured_draft_without_v3_drafts_is_none():
    assert mod._structured_draft({}) is None
    assert mod._structured_draft({"per_valida_drafts_v3": {}}) is None


def test_structured_draft_tolerates_a_non_pydantic_value():
    """Nunca rompe el gate HITL por un valor inesperado en el state."""
    assert mod._structured_draft({"per_valida_drafts_v3": {0: "no soy un modelo"}}) is None


# ---------------------------------------------------------------------------
# structured_drafts (plural) — feature 037, T405
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_payload_includes_structured_drafts_for_multi_valida_run(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "interrupt", lambda payload: captured.update(payload) or {"decision": "approve"}
    )

    low = make_insight(headline="Hallazgo de la válida 4 con evidencia numérica")
    high = make_insight(headline="Hallazgo de la válida 5 con evidencia numérica")

    await mod.hitl_gate_review(
        {
            "explain_mode": True,
            "draft_analysis": make_analysis_output(),
            "critic_feedback": make_critic_feedback(),
            "per_valida_drafts_v3": {5: high, 4: low},
        }
    )

    structured_drafts = captured["structured_drafts"]
    assert set(structured_drafts) == {4, 5}
    assert structured_drafts[4]["headline"] == low.headline
    assert structured_drafts[5]["headline"] == high.headline
    # Compat: el singular sigue siendo la de menor válida.
    assert captured["structured_draft"]["headline"] == low.headline


def test_structured_drafts_without_v3_drafts_is_empty_dict():
    assert mod._structured_drafts({}) == {}
    assert mod._structured_drafts({"per_valida_drafts_v3": {}}) == {}


def test_structured_drafts_tolerates_a_non_pydantic_value():
    """Un valor inesperado en una entrada no rompe el resto del mapeo."""
    good = make_insight()
    result = mod._structured_drafts(
        {"per_valida_drafts_v3": {0: "no soy un modelo", 1: good}}
    )
    assert list(result) == [1]
    assert result[1]["headline"] == good.headline
