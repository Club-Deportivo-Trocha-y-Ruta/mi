"""Tests del :class:`RaceAnalystAgent` (Fase 3 race-results v2).

Sin red — todos usan :class:`FakeChatLLM`. Verifican:

- Prompt renderiza correcto (variables sustituidas, pseudónimo presente,
  bloque de citas formateado).
- Output parsea a :class:`AnalysisOutput` con sections/recommendations/risks.
- Métricas computan (cost_usd > 0 cuando hay tokens).
- Fallback de tokens (sin ``usage_metadata`` → estimate por chars).
- Edge: explain_mode on/off cambia output sin romper parseo.
- Edge: output malformado (sin headings) preserva raw_markdown.
- No emite nombres reales (solo pseudónimo en input).
"""
from __future__ import annotations

import pytest

from app.services.race.agents.analyst import RaceAnalystAgent
from app.services.race.agents.pricing import PROMPT_VERSION_ANALYST
from app.services.race.schemas import (
    AnalysisInput,
    AnalysisOutput,
    LTADGroup,
    Priority,
    RecommendationCategory,
    RiskFlagType,
    Severity,
)
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage


def _markdown_sample(cite1: str = "[1]", cite2: str = "[2]") -> str:
    """Markdown con todas las secciones esperadas + recos/riesgos válidos."""
    return f"""## Evolución

El atleta muestra progresión positiva entre válidas {cite1}. Posición media subió de 8 a 5.

## Análisis Técnico

Cadencia promedio estimada por video: 78 rpm. Dentro del rango LTAD para 12 años {cite2}.

## Recomendaciones LTAD

- Trabajar cadencia 80-90 rpm en plano 2x/semana, 15 min (categoría=technique, prioridad=high) {cite1}
- Volumen semanal estable en 4 h durante 3 semanas (categoría=volume, prioridad=med) {cite2}

## Riesgos

- Tres competencias en 5 semanas; vigilar carga acumulada (flag=load_excess, severity=med) {cite1}

## Próximos Pasos

Revaluar en válida 5.
"""


def _sample_input(pseudonym="Atleta-PJUV-A-F-001", **over) -> AnalysisInput:
    base = dict(
        athlete_pseudonym=pseudonym,
        age=12,
        ltad_group=LTADGroup.BAMBINO,
        progression_df_records=[
            {"valida_num": 1, "event_date": "2026-01-31", "position": 8, "race_time_ms": 1800000, "points_awarded": 50},
            {"valida_num": 2, "event_date": "2026-02-28", "position": 5, "race_time_ms": 1700000, "points_awarded": 70},
        ],
        podium_context={
            "category_id": 9,
            "event_id": 22,
            "podium": [
                {"position": 1, "competitor_id": 100, "race_time_ms": 1600000},
                {"position": 2, "competitor_id": 101, "race_time_ms": 1620000},
                {"position": 3, "competitor_id": 102, "race_time_ms": 1650000},
            ],
            "finishers_count": 12,
        },
        memory_recent_insights=[
            "Válida 1 (2026): cadencia OK, posición 8/12",
        ],
        explain_mode=False,
        athlete_id=42,
        season=2026,
    )
    base.update(over)
    return AnalysisInput(**base)


async def test_analyst_happy_path_returns_structured_output():
    md = _markdown_sample()
    llm = FakeChatLLM([
        StubAIMessage(content=md, usage_metadata={"input_tokens": 1500, "output_tokens": 400})
    ])
    agent = RaceAnalystAgent(llm=llm)

    out, metrics = await agent.invoke(_sample_input())

    assert isinstance(out, AnalysisOutput)
    # Sections parseadas.
    assert "evolution" in out.sections
    assert "technical" in out.sections
    assert "recommendations" in out.sections
    assert "risks" in out.sections
    assert "next_steps" in out.sections
    # Recommendations extraídas con tipado correcto.
    assert len(out.recommendations) == 2
    assert out.recommendations[0].category == RecommendationCategory.TECHNIQUE
    assert out.recommendations[0].priority == Priority.HIGH
    # Risks extraídos.
    assert len(out.risk_flags) == 1
    assert out.risk_flags[0].flag == RiskFlagType.LOAD_EXCESS
    assert out.risk_flags[0].severity == Severity.MED
    # Pseudonym preservado.
    assert out.pseudonym == "Atleta-PJUV-A-F-001"
    # raw_markdown preservado.
    assert out.raw_markdown == md
    assert out.word_count > 0


async def test_analyst_citations_used_always_empty_without_rag():
    """Sin RAG, el analyst ya no mapea `[n]` a chunk_id — citations_used vacío."""
    md = _markdown_sample("[1]", "[2]")
    llm = FakeChatLLM([
        StubAIMessage(content=md, usage_metadata={"input_tokens": 1000, "output_tokens": 300})
    ])
    agent = RaceAnalystAgent(llm=llm)
    inp = _sample_input()

    out, _ = await agent.invoke(inp)

    assert out.citations_used == []


async def test_analyst_metrics_use_usage_metadata():
    llm = FakeChatLLM([
        StubAIMessage(content="## Evolución\nx", usage_metadata={"input_tokens": 2000, "output_tokens": 500})
    ])
    agent = RaceAnalystAgent(llm=llm)
    _, metrics = await agent.invoke(_sample_input())
    assert metrics.tokens_in == 2000
    assert metrics.tokens_out == 500
    assert metrics.cost_usd > 0
    assert metrics.prompt_version == PROMPT_VERSION_ANALYST
    assert metrics.latency_ms >= 0


async def test_analyst_metrics_fallback_to_char_estimate():
    """Sin usage_metadata → fallback len(text)//4."""
    llm = FakeChatLLM([
        StubAIMessage(content="hola mundo " * 20, usage_metadata=None)
    ])
    agent = RaceAnalystAgent(llm=llm)
    _, metrics = await agent.invoke(_sample_input())
    assert metrics.tokens_in > 0  # estimado del prompt renderizado
    assert metrics.tokens_out > 0  # estimado del texto de respuesta


async def test_analyst_prompt_contains_pseudonym_and_no_real_name():
    """Verifica que el prompt enviado al LLM no leakeó nombres reales."""
    llm = FakeChatLLM([StubAIMessage(content="## Evolución\nok")])
    agent = RaceAnalystAgent(llm=llm)
    inp = _sample_input(pseudonym="Atleta-PJUV-A-F-077")

    await agent.invoke(inp)

    # Inspeccionar el prompt enviado.
    assert len(llm.calls) == 1
    msgs = llm.calls[0]
    rendered = msgs[0].content
    assert "Atleta-PJUV-A-F-077" in rendered
    # Sanity: no aparece athlete_id=42 textual (no debería inyectarse).
    assert "athlete_id=42" not in rendered


async def test_analyst_explain_mode_includes_aprendizaje_marker():
    llm = FakeChatLLM([StubAIMessage(content="## Evolución\nok")])
    agent = RaceAnalystAgent(llm=llm)

    await agent.invoke(_sample_input(explain_mode=True))

    rendered = llm.calls[0][0].content
    assert "Modo aprendizaje activo" in rendered


async def test_analyst_explain_mode_off_does_not_include_marker():
    llm = FakeChatLLM([StubAIMessage(content="## Evolución\nok")])
    agent = RaceAnalystAgent(llm=llm)

    await agent.invoke(_sample_input(explain_mode=False))

    rendered = llm.calls[0][0].content
    assert "Modo aprendizaje activo" not in rendered


async def test_analyst_handles_malformed_output_without_sections():
    """Output del LLM sin headings → sections vacío pero raw_markdown se preserva."""
    llm = FakeChatLLM([
        StubAIMessage(content="Lo siento, no puedo generar análisis sin más datos.")
    ])
    agent = RaceAnalystAgent(llm=llm)
    out, _ = await agent.invoke(_sample_input())
    assert out.sections == {}
    assert "Lo siento" in out.raw_markdown
    assert out.recommendations == []
    assert out.risk_flags == []


async def test_analyst_ignores_recommendation_with_invalid_category():
    md = """## Recomendaciones LTAD

- Reco con categoría inválida (categoría=metaverse, prioridad=high) [1]
- Reco válida (categoría=recovery, prioridad=low) [1]
"""
    llm = FakeChatLLM([StubAIMessage(content=md)])
    agent = RaceAnalystAgent(llm=llm)
    out, _ = await agent.invoke(_sample_input())
    # Solo la válida.
    assert len(out.recommendations) == 1
    assert out.recommendations[0].category == RecommendationCategory.RECOVERY
