"""Tests del nodo ``analyst_agent`` en su rama v3 (feature 037, T201).

Verifican el cableado state → ``AnalystV3Input`` (referencia de género,
métricas de pelotón por válida, ventana de entrenamiento, catálogo,
diálogo del coach) y las claves que el nodo emite: las nuevas
(``per_valida_drafts_v3``, ``grounding_numbers``) y las de compatibilidad
(``per_valida_drafts``, ``draft_analysis``).

Datos 100 % ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import pytest

from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V3,
    PROMPT_VERSION_SEASON_SUMMARY_V3,
    V3CallResult,
)
from app.services.race.ai.fallback import is_fallback_output
from app.services.race.ai.nodes.analyst_agent import _resolve_athlete_ref, analyst_agent
from app.services.race.schemas import RunMetrics
from tests.services.race.test_insight_v3 import make_insight

FIELD_CONTEXT = {
    41: {
        "event_id": 41,
        "valida_num": 4,
        "event_date": "2026-05-10",
        "series_kind": "cup",
        "series_level": "departmental",
        "is_championship": False,
        "field_size": 18,
        "position": 7,
        "percentile": 58.3,
        "gap_pct": 9.4,
        "gap_to_p3_ms": 192000,
        "expected_position": 5,
        "delta_vs_expected": -2,
    },
    42: {
        "event_id": 42,
        "valida_num": 5,
        "event_date": "2026-06-14",
        "series_kind": "cup",
        "series_level": "departmental",
        "is_championship": False,
        "field_size": 20,
        "position": 6,
        "percentile": 63.2,
        "gap_pct": 8.1,
        "gap_to_p3_ms": 150000,
        "expected_position": 6,
        "delta_vs_expected": 0,
    },
}

TRAINING_WINDOW = {
    "window_days": 28,
    "date_from": "2026-04-12",
    "date_to": "2026-05-10",
    "sessions_in_window": 8,
    "attended": 5,
    "absent": 2,
    "excused": 1,
    "attendance_pct": 62.5,
    "rpe_mean": 4.1,
    "technical_foci": ["Descensos y bermas"],
    "coach_feedback": ["Buena actitud en el circuito técnico."],
}


class FakeV3Agent:
    """Agente falso que registra las entradas y devuelve un insight fijo."""

    def __init__(self, insight=None, prompt_version=PROMPT_VERSION_ANALYST_V3):
        self._insight = insight or make_insight()
        self._prompt_version = prompt_version
        self.received_inputs: list = []
        self.received_forbidden: list[str] = []

    async def invoke_v3(self, inputs, *, forbidden_names=None, **kwargs):
        self.received_inputs = list(inputs)
        self.received_forbidden = list(forbidden_names or [])
        return {
            i.valida_num: V3CallResult(
                insight=self._insight,
                metrics=RunMetrics(
                    tokens_in=900,
                    tokens_out=300,
                    latency_ms=1200,
                    cost_usd=0.0018,
                    prompt_version=self._prompt_version,
                ),
                grounding_numbers=["58.3", "9.4"],
            )
            for i in inputs
        }


def base_state(**overrides) -> dict:
    state = {
        "athlete_id": 7,
        "season": 2026,
        "event_id": 41,
        "valida_nums": [4],
        "prompt_version": PROMPT_VERSION_ANALYST_V3,
        "analysis_kind": "valida",
        "athlete_age": 13,
        "ltad_group": "juvenil",
        "athlete_sex": "F",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {
            "progression": [
                {
                    "valida_num": 4,
                    "event_date": "2026-05-10",
                    "category_code": "PRE-JUVENIL",
                    "position": 7,
                    "race_time_ms": 2530000,
                    "gap_to_winner_ms": 243000,
                    "gap_to_winner_pct": 9.4,
                }
            ]
        },
        "field_context": FIELD_CONTEXT,
        "training_window": TRAINING_WINDOW,
        "anthro_context": None,
        "catalog_context": {"technique_skills": [{"code": "D", "name": "Descensos"}]},
        "coach_dialogue": [{"headline": "Insight previo", "coach_answer": "Todo normal."}],
        "memory": ["Válida III: gap 8.4%"],
        "season_validas_count": 5,
        "forbidden_names": ["Nombre Ficticio"],
        "club_forbidden_names": ["Nombre Ficticio", "Otro Nombre"],
        "event_conditions": {4: {"climate": "soleado"}},
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Referencia de género (spec §problem 7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sex", "expected"),
    [("M", "el deportista"), ("m", "el deportista"), ("F", "la deportista"), (None, "la deportista")],
)
def test_resolve_athlete_ref(sex, expected):
    assert _resolve_athlete_ref({"athlete_sex": sex}) == expected


@pytest.mark.asyncio
async def test_v3_input_carries_the_gendered_reference():
    fake = FakeV3Agent()
    await analyst_agent(base_state(athlete_sex="M", _analyst_agent=fake))
    assert fake.received_inputs[0].athlete_ref == "el deportista"


@pytest.mark.asyncio
async def test_v2_input_also_carries_the_gendered_reference():
    """El fix de género aplica también al flujo v2 (no solo al v3)."""
    captured = {}

    class _FakeV2Agent:
        async def invoke_per_valida(self, pairs, **kwargs):
            captured["input"] = pairs[0][1]
            from tests.services.race.ai.conftest import (
                make_analysis_output,
                make_zero_metrics,
            )

            return {pairs[0][0]: (make_analysis_output(), make_zero_metrics("race_analyst_v2"))}

    await analyst_agent(
        base_state(
            prompt_version="race_analyst_v2",
            athlete_sex="M",
            _analyst_agent=_FakeV2Agent(),
        )
    )
    assert captured["input"].athlete_ref == "el deportista"


# ---------------------------------------------------------------------------
# Cableado del contexto
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v3_input_matches_field_metrics_by_valida():
    fake = FakeV3Agent()
    await analyst_agent(base_state(valida_nums=[4, 5], _analyst_agent=fake))

    by_valida = {i.valida_num: i for i in fake.received_inputs}
    assert by_valida[4].field_metrics["percentile"] == 58.3
    assert by_valida[5].field_metrics["percentile"] == 63.2
    assert by_valida[4].race_row["position"] == 7
    # La válida 5 no tiene fila de progresión en el state → None, no inventada.
    assert by_valida[5].race_row is None


@pytest.mark.asyncio
async def test_v3_input_carries_athlete_context_blocks():
    fake = FakeV3Agent()
    await analyst_agent(base_state(_analyst_agent=fake))

    input_ = fake.received_inputs[0]
    assert input_.training_window["attendance_pct"] == 62.5
    assert input_.catalog_context["technique_skills"][0]["code"] == "D"
    assert input_.coach_dialogue[0]["coach_answer"] == "Todo normal."
    assert input_.memory_recent_insights == ["Válida III: gap 8.4%"]
    assert input_.season_rows[0]["valida_num"] == 4
    assert "Clima: soleado" in input_.race_meta


@pytest.mark.asyncio
async def test_v3_uses_the_club_wide_forbidden_names():
    """El scrubbing v3 usa el superset del club, no solo al atleta analizado."""
    fake = FakeV3Agent()
    await analyst_agent(base_state(_analyst_agent=fake))
    assert fake.received_forbidden == ["Nombre Ficticio", "Otro Nombre"]


@pytest.mark.asyncio
async def test_v3_rejects_more_than_four_validas():
    with pytest.raises(ValueError):
        await analyst_agent(
            base_state(valida_nums=[1, 2, 3, 4, 5], _analyst_agent=FakeV3Agent())
        )


# ---------------------------------------------------------------------------
# Salidas del nodo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v3_emits_structured_and_compat_drafts():
    fake = FakeV3Agent()
    update = await analyst_agent(base_state(_analyst_agent=fake))

    assert set(update["per_valida_drafts_v3"]) == {4}
    assert update["grounding_numbers"][4] == ["58.3", "9.4"]

    compat = update["per_valida_drafts"][4]
    assert compat.pseudonym == "AzulZorro"
    assert compat.raw_markdown.startswith("## Hallazgo principal")
    assert [r.category.value for r in compat.recommendations] == ["volume", "technique"]
    assert compat.word_count > 0
    assert update["draft_analysis"] is compat


@pytest.mark.asyncio
async def test_v3_accumulates_metrics():
    update = await analyst_agent(base_state(valida_nums=[4, 5], _analyst_agent=FakeV3Agent()))
    aggregate = update["aggregate_metrics"]
    assert aggregate["tokens_in_total"] == 1800
    assert aggregate["prompt_version_analyst"] == PROMPT_VERSION_ANALYST_V3
    assert aggregate["analysis_kind"] == "valida"


@pytest.mark.asyncio
async def test_v3_without_validas_emits_the_deterministic_fallback():
    update = await analyst_agent(
        base_state(valida_nums=[], _analyst_agent=FakeV3Agent())
    )
    assert is_fallback_output(update["per_valida_drafts_v3"][0]) is True
    assert update["grounding_numbers"] == {0: []}


# ---------------------------------------------------------------------------
# Temporada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_season_kind_builds_a_single_input_keyed_at_zero():
    fake = FakeV3Agent(prompt_version=PROMPT_VERSION_SEASON_SUMMARY_V3)
    update = await analyst_agent(
        base_state(
            analysis_kind="season",
            prompt_version=PROMPT_VERSION_SEASON_SUMMARY_V3,
            valida_nums=[4, 5],
            _analyst_agent=fake,
        )
    )

    assert len(fake.received_inputs) == 1
    input_ = fake.received_inputs[0]
    assert input_.valida_num == 0
    assert input_.analysis_kind == "season"
    assert input_.race_row is None
    assert input_.field_metrics is None
    assert len(input_.season_rows) == 2
    assert set(update["per_valida_drafts_v3"]) == {0}


@pytest.mark.asyncio
async def test_season_kind_ignores_the_valida_cap():
    """La temporada agrega todas las carreras en una sola llamada."""
    fake = FakeV3Agent(prompt_version=PROMPT_VERSION_SEASON_SUMMARY_V3)
    update = await analyst_agent(
        base_state(
            analysis_kind="season",
            prompt_version=PROMPT_VERSION_SEASON_SUMMARY_V3,
            valida_nums=[1, 2, 3, 4, 5, 6],
            _analyst_agent=fake,
        )
    )
    assert set(update["per_valida_drafts_v3"]) == {0}
