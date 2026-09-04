"""Resolución de la carrera analizada por event_id (feature 039, T030).

``_build_v3_inputs`` (v3) y el loop que arma ``records_for_vn`` dentro de
``_analyst_agent_v2`` deben preferir el ancla ``state["event_id"]`` sobre
``valida_num`` a secas: desde spec 014 la válida I de una copa y un
campeonato pueden compartir ``sequence_number`` (misma ``valida_num`` en
``metrics.progression``), así que resolver por número a secas puede elegir
la carrera equivocada (research.md D9, regla 2 de
``contracts/ai-context.md``):

    1. Con ``state.event_id`` seteado (lanzamiento anclado), la fila
       analizada es la de ``progression`` con ese ``event_id`` — nunca
       solo por ``valida_num``.
    2. Sin ancla, ``valida_num`` resuelve SOLO entre filas con
       ``series_kind == "cup"`` — un campeonato solo se analiza vía
       lanzamiento anclado.

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.analyst_agent import _build_v3_inputs, analyst_agent
from tests.services.race.ai.conftest import make_analysis_output, make_zero_metrics

# Válida I de copa y el campeonato departamental comparten valida_num=1
# (spec 014) — la colisión que motiva esta feature.
CUP_ROW = {
    "event_id": 11,
    "valida_num": 1,
    "series_kind": "cup",
    "series_level": "departmental",
    "position": 9,
}
CHAMPIONSHIP_ROW = {
    "event_id": 90,
    "valida_num": 1,
    "series_kind": "championship",
    "series_level": "departmental",
    "position": 2,
}


# ---------------------------------------------------------------------------
# v3 — _build_v3_inputs
# ---------------------------------------------------------------------------


def _base_v3_state(**overrides) -> dict:
    state = {
        "analysis_kind": "valida",
        "valida_nums": [1],
        "metrics": {"progression": [CUP_ROW, CHAMPIONSHIP_ROW]},
        "field_context": {},
        "season": 2026,
        "season_validas_count": 2,
    }
    state.update(overrides)
    return state


def test_build_v3_inputs_uses_anchored_event_id_over_first_match():
    """Ancla al campeonato (event_id=90) → race_row es la fila del
    campeonato, aunque la válida I de copa (misma valida_num) aparezca
    primero en metrics.progression."""
    state = _base_v3_state(event_id=90)
    inputs = _build_v3_inputs(state, "la deportista")

    assert len(inputs) == 1
    assert inputs[0].race_row is not None
    assert inputs[0].race_row["event_id"] == 90


def test_build_v3_inputs_without_anchor_resolves_only_cup_rows():
    """Sin ancla, valida_num solo resuelve entre series_kind == 'cup' — el
    campeonato con la misma valida_num nunca se elige por default aunque
    aparezca primero en la lista."""
    state = _base_v3_state(
        metrics={"progression": [CHAMPIONSHIP_ROW, CUP_ROW]},  # campeonato primero
    )
    inputs = _build_v3_inputs(state, "la deportista")

    assert len(inputs) == 1
    assert inputs[0].race_row is not None
    assert inputs[0].race_row["event_id"] == 11


# ---------------------------------------------------------------------------
# v2 — records_for_vn (dentro de _analyst_agent_v2)
# ---------------------------------------------------------------------------


class _CaptureV2Agent:
    """Agente falso v2 que solo registra los pares (valida_num, input)."""

    def __init__(self) -> None:
        self.pairs: list = []

    async def invoke_per_valida(self, pairs, **kwargs):
        self.pairs = list(pairs)
        return {
            vn: (make_analysis_output(), make_zero_metrics("race_analyst_v2"))
            for vn, _ in pairs
        }


def _base_v2_state(agent: _CaptureV2Agent, **overrides) -> dict:
    state = {
        "athlete_id": 1,
        "season": 2026,
        "athlete_age": 12,
        "ltad_group": "bambino",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {"progression": [CUP_ROW, CHAMPIONSHIP_ROW]},
        "podium_context": {},
        "principles": [],
        "memory": [],
        "valida_nums": [1],
        "prompt_version": "race_analyst_v2",
        "_analyst_agent": agent,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_v2_records_for_vn_uses_anchored_event_id():
    """Anclado al campeonato: records_for_vn (progression_df_records de la
    AnalysisInput) trae SOLO la fila del campeonato, no ambas filas
    ambiguas de valida_num=1."""
    agent = _CaptureV2Agent()
    await analyst_agent(_base_v2_state(agent, event_id=90))

    records = agent.pairs[0][1].progression_df_records
    assert [r["event_id"] for r in records] == [90]


@pytest.mark.asyncio
async def test_v2_records_for_vn_without_anchor_uses_only_cup_rows():
    """Sin ancla: records_for_vn trae solo la fila de copa, aunque el
    campeonato (misma valida_num) aparezca primero en progression_all."""
    agent = _CaptureV2Agent()
    await analyst_agent(
        _base_v2_state(
            agent,
            metrics={"progression": [CHAMPIONSHIP_ROW, CUP_ROW]},
        )
    )

    records = agent.pairs[0][1].progression_df_records
    assert [r["event_id"] for r in records] == [11]
