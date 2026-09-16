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

from app.services.race.ai.nodes.analyst_agent import (
    _build_v3_inputs,
    _valida_label,
    analyst_agent,
)
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
# v3 — _build_v3_inputs, temporada: course_by_valida en lanzamiento global
# (feature 043, US4 + hotfix multicopa) — ``state["valida_nums"]`` viene
# vacío en un lanzamiento global (spec §US5); las carreras reales de la
# temporada solo están en las claves de ``state["course_context_by_event"]``
# (keyed por event_id, NUNCA por valida_num — dos copas de la misma
# temporada pueden compartir "Válida 4", spec 014, y un dict int-keyed
# perdería una de las dos entradas). Las etiquetas se resuelven desde
# ``state["field_context"]`` (también keyed por event_id).
# ---------------------------------------------------------------------------


def test_build_v3_inputs_season_course_by_valida_uses_by_event_keys_not_valida_nums():
    """En lanzamiento global (``valida_nums`` vacío), ``course_by_valida`` debe
    poblarse desde las claves de ``course_context_by_event`` — de lo
    contrario el bloque de circuito de temporada queda inerte (SIN DATO)
    aunque haya perfiles de circuito registrados."""
    state = {
        "analysis_kind": "season",
        "valida_nums": [],
        "metrics": {"progression": []},
        "field_context": {
            41: {
                "event_id": 41, "valida_num": 4, "event_date": "2026-05-10",
                "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
            },
            72: {
                "event_id": 72, "valida_num": 7, "event_date": "2026-08-02",
                "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
            },
        },
        "season": 2026,
        "season_validas_count": 2,
        "course_context_by_event": {
            41: {"terrain_type": "mixto", "technical_difficulty": 4},
            72: {"laps": 3},
        },
    }
    inputs = _build_v3_inputs(state, "la deportista")

    assert len(inputs) == 1
    assert inputs[0].course_by_valida == {
        "Copa Valle · Válida IV": "- Tipo de superficie: mixto\n- Dificultad técnica: 4/5 (técnico)",
        "Copa Valle · Válida VII": "- Vueltas de la categoría: 3",
    }


def test_build_v3_inputs_season_course_by_valida_omits_events_without_course_data():
    """Un evento presente en ``course_context_by_event`` pero con los seis
    campos en ``None``/ausentes (dict vacío) se omite del mapping — veto de
    ausencia por carrera, no un bloque vacío."""
    state = {
        "analysis_kind": "season",
        "valida_nums": [],
        "metrics": {"progression": []},
        "field_context": {
            50: {
                "event_id": 50, "valida_num": 5, "event_date": "2026-07-01",
                "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
            },
        },
        "season": 2026,
        "season_validas_count": 1,
        "course_context_by_event": {50: {}},
    }
    inputs = _build_v3_inputs(state, "la deportista")

    assert inputs[0].course_by_valida == {}


def test_build_v3_inputs_season_course_by_valida_disambiguates_two_cups_sharing_the_same_valida():
    """Regresión del bug real (ver plans/multicopa-identidad-valida.md):
    Copa Valle V4 (mayo) y Copa Let's Go V4 (septiembre) para el mismo
    atleta deben aparecer como DOS entradas distintas — un dict keyed por
    número de válida perdería una de las dos por colisión de clave."""
    state = {
        "analysis_kind": "season",
        "valida_nums": [],
        "metrics": {"progression": []},
        "field_context": {
            10: {
                "event_id": 10, "valida_num": 4, "event_date": "2026-05-01",
                "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
            },
            43: {
                "event_id": 43, "valida_num": 4, "event_date": "2026-09-13",
                "series_id": 9, "series_name": "Copa Let's Go Interdepartamental",
                "series_kind": "cup",
            },
        },
        "season": 2026,
        "season_validas_count": 2,
        "course_context_by_event": {
            10: {"terrain_type": "mixto"},
            43: {"terrain_type": "trocha"},
        },
    }
    inputs = _build_v3_inputs(state, "la deportista")

    assert set(inputs[0].course_by_valida.keys()) == {
        "Copa Valle · Válida IV",
        "Copa Let's Go Interdepartamental · Válida IV",
    }


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


def test_valida_label_prefixes_the_real_cup_name():
    """Hotfix multicopa: la etiqueta canónica antepone el nombre real de la
    copa (nunca el literal "Copa" a secas) cuando el dato está disponible."""
    label = _valida_label(_COPA_LETSGO_V4, None)
    assert label == "Copa Let's Go Interdepartamental · Válida IV"

    # Sin series_name/series_short_name en ninguna fuente, el resultado no
    # cambia frente al comportamiento previo al hotfix.
    legacy_row = {"series_kind": "cup", "valida_num": 4}
    assert _valida_label(legacy_row, None) == "Válida IV"


# ---------------------------------------------------------------------------
# Multicopa: identidad de válida (hotfix) — end-to-end, reproduce el bug real
# de plans/multicopa-identidad-valida.md: Copa Valle V4 (mayo)/V5 (agosto) y
# Copa Let's Go V4 (septiembre) para el mismo atleta.
# ---------------------------------------------------------------------------


class _RecordingV3Agent:
    """Agente v3 falso que solo registra las entradas recibidas."""

    def __init__(self) -> None:
        self.received_inputs: list = []

    async def invoke_v3(self, inputs, *, forbidden_names=None, **kwargs):
        from app.services.race.agents.analyst import V3CallResult
        from app.services.race.schemas import RunMetrics
        from tests.services.race.test_insight_v3 import make_insight

        self.received_inputs = list(inputs)
        return {
            i.valida_num: V3CallResult(
                insight=make_insight(),
                metrics=RunMetrics(
                    tokens_in=1, tokens_out=1, latency_ms=1,
                    cost_usd=0.0, prompt_version="race_analyst_v3",
                ),
                grounding_numbers=[],
            )
            for i in inputs
        }


_COPA_VALLE_V4 = {
    "event_id": 10, "valida_num": 4, "event_date": "2026-05-01",
    "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
    "position": 3,
}
_COPA_VALLE_V5 = {
    "event_id": 11, "valida_num": 5, "event_date": "2026-08-01",
    "series_id": 1, "series_name": "Copa Valle", "series_kind": "cup",
    "position": 2,
}
_COPA_LETSGO_V4 = {
    "event_id": 43, "valida_num": 4, "event_date": "2026-09-13",
    "series_id": 9, "series_name": "Copa Let's Go Interdepartamental",
    "series_kind": "cup", "position": 5,
}


@pytest.mark.asyncio
async def test_per_valida_run_never_sees_another_cup_that_shares_the_valida_num():
    """Un run anclado a Copa Let's Go V4 no debe ver la fila, el "Recorrido
    hasta acá" ni la etiqueta de Copa Valle — aunque ambas copas tengan una
    "Válida 4" el mismo año."""
    fake = _RecordingV3Agent()
    state = {
        "athlete_id": 7,
        "season": 2026,
        "event_id": 43,  # ancla a Copa Let's Go V4
        "series_id": 9,  # resuelto por load_race_data desde el ancla
        "valida_nums": [4],
        "prompt_version": "race_analyst_v3",
        "analysis_kind": "valida",
        "athlete_age": 13,
        "ltad_group": "juvenil",
        "athlete_sex": "F",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {
            "progression": [_COPA_VALLE_V4, _COPA_VALLE_V5, _COPA_LETSGO_V4]
        },
        "field_context": {10: _COPA_VALLE_V4, 11: _COPA_VALLE_V5, 43: _COPA_LETSGO_V4},
        "season_validas_count": 3,
        "forbidden_names": [],
        "club_forbidden_names": [],
        "_analyst_agent": fake,
    }

    await analyst_agent(state)

    assert len(fake.received_inputs) == 1
    input_ = fake.received_inputs[0]
    assert input_.race_row["event_id"] == 43
    assert all(r["event_id"] != 10 for r in input_.season_rows)
    assert all(r["event_id"] != 11 for r in input_.season_rows)
    assert input_.valida_label is not None
    assert "Let's Go" in input_.valida_label
    assert "Valle" not in input_.valida_label


@pytest.mark.asyncio
async def test_season_run_renders_both_cups_as_distinct_entries_sharing_the_valida_num():
    """El run de temporada (analysis_kind='season') sí ve ambas copas, pero
    como secciones/entradas separadas — nunca fusionadas en la misma fila ni
    con la misma etiqueta."""
    fake = _RecordingV3Agent()
    state = {
        "athlete_id": 7,
        "season": 2026,
        "valida_nums": None,
        "prompt_version": "race_season_summary_v3",
        "analysis_kind": "season",
        "athlete_age": 13,
        "ltad_group": "juvenil",
        "athlete_sex": "F",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {"progression": []},
        "field_context": {10: _COPA_VALLE_V4, 11: _COPA_VALLE_V5, 43: _COPA_LETSGO_V4},
        "course_context_by_event": {
            10: {"terrain_type": "mixto"},
            43: {"terrain_type": "trocha"},
        },
        "season_validas_count": 3,
        "forbidden_names": [],
        "club_forbidden_names": [],
        "_analyst_agent": fake,
    }

    await analyst_agent(state)

    input_ = fake.received_inputs[0]
    assert input_.analysis_kind == "season"
    assert {r["event_id"] for r in input_.season_rows} == {10, 11, 43}
    assert set(input_.course_by_valida.keys()) == {
        "Copa Valle · Válida IV",
        "Copa Let's Go Interdepartamental · Válida IV",
    }
