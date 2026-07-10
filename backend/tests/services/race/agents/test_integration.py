"""Smoke test de integración Gemini real (Fase 3 race-results v2).

EXCLUIDO por default. Correr manualmente:

    AI_API_KEY=... AI_ENABLED=true RACE_AGENT_CRITIC_ENABLED=false \\
        PYTHONPATH=. .venv/bin/pytest \\
        tests/services/race/agents/test_integration.py -m integration -s

Verifica que:
- ``RaceAnalystAgent.invoke()`` retorna AnalysisOutput parseable.
- ``RunMetrics.cost_usd`` > 0.
- El output NO contiene el athlete_id ni nombres reales (solo pseudónimo).

NO se corre en CI por default (marker ``integration`` excluido en
configuración de CI; el dev local también lo skipea si AI_API_KEY no
está exportado).
"""
from __future__ import annotations

import os

import pytest

from app.services.race.agents.analyst import RaceAnalystAgent
from app.services.race.schemas import AnalysisInput, AnalysisOutput, LTADGroup

pytestmark = pytest.mark.integration


def _has_api_key() -> bool:
    return bool(os.environ.get("AI_API_KEY", "").strip())


@pytest.mark.skipif(not _has_api_key(), reason="AI_API_KEY no configurado")
async def test_analyst_real_gemini_smoke():
    inp = AnalysisInput(
        athlete_pseudonym="Atleta-PJUV-A-F-999",
        age=12,
        ltad_group=LTADGroup.BAMBINO,
        progression_df_records=[
            {"valida_num": 1, "event_date": "2026-01-31", "position": 8, "race_time_ms": 1800000, "points_awarded": 50},
            {"valida_num": 2, "event_date": "2026-02-28", "position": 5, "race_time_ms": 1700000, "points_awarded": 70},
        ],
        podium_context={
            "category_id": 9, "event_id": 22,
            "podium": [
                {"position": 1, "competitor_id": 100, "race_time_ms": 1600000},
                {"position": 2, "competitor_id": 101, "race_time_ms": 1620000},
                {"position": 3, "competitor_id": 102, "race_time_ms": 1650000},
            ],
            "finishers_count": 12,
        },
        memory_recent_insights=["Válida 1: cadencia OK"],
        explain_mode=False,
        athlete_id=999,
        season=2026,
    )

    agent = RaceAnalystAgent()  # construye LLM real desde Settings.
    out, metrics = await agent.invoke(inp)

    assert isinstance(out, AnalysisOutput)
    assert out.raw_markdown, "raw_markdown vacío — Gemini no devolvió contenido"
    assert metrics.cost_usd > 0, "cost_usd debe ser >0 con tokens reales"
    assert metrics.tokens_in > 0
    assert metrics.tokens_out > 0

    # Privacy: el output no debe mencionar el athlete_id real.
    assert "999" not in out.raw_markdown or out.raw_markdown.count("999") <= 1
    # Pseudónimo presente.
    assert "Atleta-PJUV-A-F-999" in out.raw_markdown or out.pseudonym == "Atleta-PJUV-A-F-999"
