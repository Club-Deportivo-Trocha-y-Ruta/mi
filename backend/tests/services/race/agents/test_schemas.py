"""Tests Pydantic de los schemas de la capa agéntica (Fase 3 race-results v2).

Cubren:
- Defaults sensatos (listas vacías, severity=low).
- Validaciones de bounds (palabras count >=0, pseudonym min_length, etc.).
- JSON-serializable (round-trip ``.model_dump()`` → ``model_validate``).
- ``citations_used`` deduplica preservando orden.
"""
from __future__ import annotations

import json

import pytest

from app.services.race.rag.retriever import Citation
from app.services.race.schemas import (
    AnalysisInput,
    AnalysisOutput,
    ChatResponse,
    CriticFeedback,
    CriticIssue,
    CriticIssueSeverity,
    LTADGroup,
    Priority,
    Recommendation,
    RecommendationCategory,
    RiskFlag,
    RiskFlagType,
    RunMetrics,
    Severity,
)


# ---------------------------------------------------------------------------
# Recommendation / RiskFlag
# ---------------------------------------------------------------------------


def test_recommendation_minimal_defaults_priority_med():
    r = Recommendation(text="Trabajar cadencia 80-90 rpm", category=RecommendationCategory.TECHNIQUE)
    assert r.priority == Priority.MED
    assert r.category == RecommendationCategory.TECHNIQUE


def test_recommendation_rejects_short_text():
    with pytest.raises(ValueError):
        Recommendation(text="ok", category=RecommendationCategory.VOLUME)


def test_risk_flag_full_roundtrip():
    rf = RiskFlag(
        flag=RiskFlagType.LOAD_EXCESS,
        severity=Severity.HIGH,
        evidence="Tres podios en 5 semanas",
    )
    j = rf.model_dump()
    assert j["flag"] == "load_excess"
    assert RiskFlag.model_validate(j) == rf


# ---------------------------------------------------------------------------
# AnalysisInput
# ---------------------------------------------------------------------------


def _sample_input(**over) -> AnalysisInput:
    base = dict(
        athlete_pseudonym="Atleta-PJUV-A-F-001",
        age=12,
        ltad_group=LTADGroup.BAMBINO,
        progression_df_records=[],
        podium_context={},
        memory_recent_insights=[],
        principles_citations=[],
        explain_mode=False,
        athlete_id=42,
        season=2026,
    )
    base.update(over)
    return AnalysisInput(**base)


def test_analysis_input_happy_path():
    inp = _sample_input()
    assert inp.athlete_pseudonym.startswith("Atleta-")
    assert inp.ltad_group == LTADGroup.BAMBINO


def test_analysis_input_age_bounds():
    with pytest.raises(ValueError):
        _sample_input(age=5)
    with pytest.raises(ValueError):
        _sample_input(age=25)


def test_analysis_input_forbids_extra_fields():
    with pytest.raises(ValueError):
        AnalysisInput(
            athlete_pseudonym="X-Y",
            age=12,
            ltad_group=LTADGroup.BAMBINO,
            athlete_id=1,
            season=2026,
            unexpected_field="boom",
        )


def test_analysis_input_with_citations_json_serializable():
    cites = [
        Citation(chunk_id="abc123", source="docs/01.md", content="bla", score=0.9, metadata={}),
    ]
    inp = _sample_input(principles_citations=cites)
    dump = inp.model_dump(mode="json")
    # Round-trip via JSON.
    json.dumps(dump)


# ---------------------------------------------------------------------------
# AnalysisOutput
# ---------------------------------------------------------------------------


def test_analysis_output_citations_used_deduplicated():
    out = AnalysisOutput(
        pseudonym="X-Y",
        sections={"evolution": "..."},
        citations_used=["abc", "abc", "def", "abc"],
        recommendations=[],
        risk_flags=[],
        raw_markdown="hello",
        word_count=1,
    )
    assert out.citations_used == ["abc", "def"]


def test_analysis_output_requires_raw_markdown_nonempty():
    with pytest.raises(ValueError):
        AnalysisOutput(
            pseudonym="X-Y",
            sections={},
            citations_used=[],
            recommendations=[],
            risk_flags=[],
            raw_markdown="",
            word_count=0,
        )


# ---------------------------------------------------------------------------
# CriticFeedback
# ---------------------------------------------------------------------------


def test_critic_feedback_defaults_pass_through():
    fb = CriticFeedback(approved=True)
    assert fb.severity == CriticIssueSeverity.LOW
    assert fb.issues == []
    assert fb.must_block is False


def test_critic_feedback_with_issues_roundtrip():
    fb = CriticFeedback(
        approved=False,
        severity=CriticIssueSeverity.HIGH,
        issues=[
            CriticIssue(
                section="Recomendaciones",
                problem="Cita inexistente [5]",
                suggested_fix="Verificar mapeo de citas",
            )
        ],
        must_block=True,
    )
    json.dumps(fb.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# ChatResponse
# ---------------------------------------------------------------------------


def test_chat_response_defaults():
    cr = ChatResponse(answer="hola coach")
    assert cr.citations_used == []
    assert cr.tools_called == []


def test_chat_response_rejects_empty_answer():
    with pytest.raises(ValueError):
        ChatResponse(answer="")


# ---------------------------------------------------------------------------
# RunMetrics
# ---------------------------------------------------------------------------


def test_run_metrics_nonneg():
    m = RunMetrics(tokens_in=10, tokens_out=20, latency_ms=100, cost_usd=0.0001, prompt_version="v1")
    assert m.cost_usd == 0.0001


def test_run_metrics_rejects_negative():
    with pytest.raises(ValueError):
        RunMetrics(tokens_in=-1, tokens_out=0, latency_ms=0, cost_usd=0.0, prompt_version="v1")
