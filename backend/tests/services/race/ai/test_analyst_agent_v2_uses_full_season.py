"""Task #22 — smoke integration: ``_analyst_agent_v2`` debe consumir
``is_first_in_season`` y ``full_season_results`` del state (cargados por
``load_race_data``), NO derivarlos del tamaño del set lanzado.

Escenario crítico que motivó la decisión Task #22:

    El coach lanza un análisis aislado del set [V4] (len=1) para un atleta
    que ya tiene resultados de V1, V2, V3 en la temporada. El nodo
    ``load_race_data`` puebla ``state["is_first_in_season"] = False`` y
    ``state["season_validas_count"] = 3``. El orquestador
    ``_analyst_agent_v2`` debe propagar esos valores al ``RaceAnalystAgent``
    sin gatillar el flujo N=1 (sin fallback_n1, sin veto de tendencia).

Si el agente recibe ``is_first_in_season=True`` por error, el atleta vería
falsos vetos en frases legítimas como "mejoró respecto a la válida anterior".
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.race.ai.nodes.analyst_agent import _analyst_agent_v2
from app.services.race.schemas import AnalysisInput, AnalysisOutput, RunMetrics
from tests.services.race.ai.conftest import (
    make_analysis_output,
    make_zero_metrics,
)


class _RecordingAgent:
    """Captura los kwargs con que se invocó invoke_per_valida.

    Permite verificar que el nodo orquestador propagó correctamente los
    valores del state al agente.
    """

    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []

    async def invoke_per_valida(
        self,
        pairs: list[tuple[int, AnalysisInput]],
        *,
        forbidden_names: list[str] | None = None,
        is_first_in_season: bool = False,
        full_season_records: list[dict] | None = None,
        timeout_seconds: float | None = None,
        athlete_age: int | None = None,
    ) -> dict[int, tuple[AnalysisOutput, RunMetrics]]:
        self.invocations.append(
            {
                "pairs_len": len(pairs),
                "valida_nums": [vn for vn, _ in pairs],
                "forbidden_names": list(forbidden_names or []),
                "is_first_in_season": is_first_in_season,
                "full_season_records_len": (
                    len(full_season_records) if full_season_records else 0
                ),
                "athlete_age": athlete_age,
            }
        )
        # Devuelve un output dummy por cada par.
        return {
            vn: (
                make_analysis_output(
                    markdown=f"## Qué pasó\nDraft válida {vn}."
                ),
                make_zero_metrics("race_analyst_v2"),
            )
            for vn, _ in pairs
        }


def _base_state(
    *,
    is_first_in_season: bool,
    season_validas_count: int,
    valida_nums: list[int],
    full_season_results: list[dict] | None,
    agent: _RecordingAgent,
) -> dict:
    """Construye un state realista para _analyst_agent_v2."""
    return {
        "athlete_id": 1,
        "season": 2026,
        "athlete_age": 12,
        "ltad_group": "bambino",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {
            "progression": [
                # Solo el set lanzado (lo que el caller pidió analizar).
                {"valida_num": vn, "position": 5}
                for vn in valida_nums
            ]
        },
        "podium_context": {},
        "principles": [],
        "memory": [],
        "forbidden_names": [],
        "valida_nums": valida_nums,
        "prompt_version": "race_analyst_v2",
        # Campos clave Task #22 — los pone load_race_data en producción.
        "is_first_in_season": is_first_in_season,
        "season_validas_count": season_validas_count,
        "full_season_results": full_season_results,
        "_analyst_agent": agent,
    }


async def test_analyst_agent_v2_uses_state_is_first_in_season_not_set_size():
    """Set=[V4] (len=1) + atleta con historial (season_validas_count=3) →
    el agente recibe is_first_in_season=False, NO derivado del set.
    """
    agent = _RecordingAgent()
    full_season = [
        {"valida_num": 1, "position": 7, "race_time_ms": 1_000_000},
        {"valida_num": 2, "position": 6, "race_time_ms": 980_000},
        {"valida_num": 3, "position": 5, "race_time_ms": 970_000},
        {"valida_num": 4, "position": 4, "race_time_ms": 960_000},
    ]
    state = _base_state(
        is_first_in_season=False,
        season_validas_count=3,
        valida_nums=[4],  # ¡SET CON UNA SOLA VÁLIDA!
        full_season_results=full_season,
        agent=agent,
    )

    update = await _analyst_agent_v2(state)

    assert len(agent.invocations) == 1, (
        "El orquestador debe llamar invoke_per_valida exactamente una vez."
    )
    call = agent.invocations[0]
    assert call["is_first_in_season"] is False, (
        "Regresión Task #22: el nodo derivó N=1 del tamaño del set "
        "(valida_nums=[4]) en vez de leer is_first_in_season=False del state."
    )
    assert call["full_season_records_len"] == 4, (
        "full_season_results debe llegar al agente para alimentar la "
        "sección 'Recorrido hasta acá'."
    )
    # El draft se emite normalmente, no fallback N=1.
    assert "per_valida_drafts" in update
    assert 4 in update["per_valida_drafts"]
    aggregate = update.get("aggregate_metrics", {})
    assert aggregate.get("is_first_in_season") is False
    assert aggregate.get("season_validas_count") == 3


async def test_analyst_agent_v2_propagates_n1_when_truly_first():
    """Atleta con realmente 1 sola válida en la temporada →
    is_first_in_season=True llega al agente, full_season_records puede
    venir como None (no hay historial relevante).
    """
    agent = _RecordingAgent()
    state = _base_state(
        is_first_in_season=True,
        season_validas_count=1,
        valida_nums=[1],
        full_season_results=[],  # sola válida = sin historial previo
        agent=agent,
    )

    await _analyst_agent_v2(state)

    assert len(agent.invocations) == 1
    call = agent.invocations[0]
    assert call["is_first_in_season"] is True, (
        "Cuando el atleta tiene realmente 1 válida en toda la temporada, "
        "el orquestador debe propagar is_first_in_season=True."
    )


async def test_analyst_agent_v2_set_size_4_with_full_season_history():
    """Set=[V1..V4] (len=4) con atleta con historial: el cap=4 no se viola
    y el flujo NO es N=1 — verifica que la lógica de set-size no aplica."""
    agent = _RecordingAgent()
    full_season = [
        {"valida_num": vn, "position": 7 - vn, "race_time_ms": 1_000_000}
        for vn in (1, 2, 3, 4)
    ]
    state = _base_state(
        is_first_in_season=False,
        season_validas_count=4,
        valida_nums=[1, 2, 3, 4],
        full_season_results=full_season,
        agent=agent,
    )

    update = await _analyst_agent_v2(state)

    call = agent.invocations[0]
    assert call["pairs_len"] == 4
    assert call["is_first_in_season"] is False
    assert call["full_season_records_len"] == 4
    assert len(update["per_valida_drafts"]) == 4
