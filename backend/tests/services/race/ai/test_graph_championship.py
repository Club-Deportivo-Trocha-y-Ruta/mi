"""Grafo race-analyst anclado a un campeonato nacional (feature 039, T031).

Reproduce el bug de research.md D9 / regla 2 de ``contracts/ai-context.md``:
la válida I de una copa y un campeonato (departamental o nacional) pueden
compartir ``sequence_number`` (spec 014), así que resolver la carrera
analizada por ``valida_num`` a secas — sin mirar el ancla
``state["event_id"]`` — puede devolver la fila equivocada cuando ambas
conviven en ``metrics.progression``.

Sigue la convención ``patched_pipeline`` / ``memory_checkpointer`` de
``test_graph.py``, pero con un ``RaceAnalystAgent`` REAL (no
``FakeAnalystAgent``) para ejercer el render del prompt v3 completo con un
``FakeChatLLM`` inyectado — así se puede inspeccionar tanto el
``AnalystV3Input`` construido por el nodo como el texto que de verdad
viajaría al LLM (``valida_label``).

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app.services.race.agents.analyst import PROMPT_VERSION_ANALYST_V3, RaceAnalystAgent
from app.services.race.ai.graph import build_graph
from app.services.race.ai.nodes import (
    analyst_agent as analyst_node_mod,
    compute_metrics as metrics_node_mod,
    load_race_data as load_node_mod,
    validate_input as validate_node_mod,
)
from tests.services.race.agents.conftest import FakeChatLLM, StubAIMessage
from tests.services.race.agents.test_analyst_v3 import VALID_PAYLOAD

# Válida I de copa y el Cto. Nacional comparten sequence_number=1 (spec 014)
# — la colisión que motiva esta feature.
CUP_EVENT_ID = 11
CN_EVENT_ID = 90


class _FinishedStatus:
    value = "finished"


class _CnResult:
    """Resultado ORM mínimo del atleta en el Cto. Nacional (anclado)."""

    id = 501
    event_id = CN_EVENT_ID
    category_id = 5
    competitor_id = 22
    athlete_id = 1
    position = 6
    race_time_ms = 3_900_000
    points_awarded = None
    status = _FinishedStatus()


FIELD_CONTEXT_CN = {
    CN_EVENT_ID: {
        "event_id": CN_EVENT_ID,
        "valida_num": 1,
        "event_date": "2026-07-05",
        "series_kind": "championship",
        "series_level": "national",
        "is_championship": True,
        "field_size": 45,
        "position": 6,
        "percentile": 88.9,
        "gap_to_p1_ms": 210_000,
        "gap_pct": 3.8,
        "gap_to_p3_ms": 90_000,
        "expected_position": 6,
        "delta_vs_expected": 0,
    },
}

# metrics.progression con la colisión: la válida I de copa aparece PRIMERO
# en la lista, antes que el campeonato — un resolver "primer match por
# valida_num" elegiría la fila equivocada.
PROGRESSION_ROWS_CN = [
    {
        "event_id": CUP_EVENT_ID,
        "valida_num": 1,
        "series_kind": "cup",
        "series_level": "departmental",
        "event_date": "2026-03-01",
        "position": 9,
        "race_time_ms": 4_200_000,
        "category_code": "PRE-JUVENIL",
    },
    {
        "event_id": CN_EVENT_ID,
        "valida_num": 1,
        "series_kind": "championship",
        "series_level": "national",
        "event_date": "2026-07-05",
        "position": 6,
        "race_time_ms": 3_900_000,
        "category_code": "PRE-JUVENIL",
    },
]


@pytest.fixture
def patched_championship_pipeline(monkeypatch):
    """Patchea la pipeline (DB + métricas de pelotón) para el lanzamiento
    anclado al Cto. Nacional — misma convención que ``patched_pipeline`` en
    ``test_graph.py``."""

    async def _fetch_results(db, aid, season, valida_nums=None):
        return [_CnResult()]

    async def _fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 0}

    async def _athlete_progression(db, cid):
        return pd.DataFrame(PROGRESSION_ROWS_CN)

    async def _podium_gap(db, cat, season):
        return pd.DataFrame()

    def _fake_field_metrics(**kwargs):
        return dict(FIELD_CONTEXT_CN)

    monkeypatch.setattr(validate_node_mod, "fetch_results_for_athlete", _fetch_results)
    monkeypatch.setattr(load_node_mod, "fetch_results_for_athlete", _fetch_results)
    monkeypatch.setattr(load_node_mod, "fetch_podium_context", _fetch_podium)
    monkeypatch.setattr(metrics_node_mod, "athlete_progression", _athlete_progression)
    monkeypatch.setattr(metrics_node_mod, "podium_gap", _podium_gap)
    monkeypatch.setattr(metrics_node_mod, "compute_field_metrics", _fake_field_metrics)


@pytest.mark.asyncio
async def test_graph_anchored_national_championship_resolves_race_row_by_event_id(
    memory_checkpointer,
    configure_db_factory,
    fake_session,
    patched_championship_pipeline,
    monkeypatch,
):
    """Lanzamiento v3 anclado al Cto. Nacional (event_id=CN, valida_num=1,
    colisión con la Válida I de copa).

    Se espera que falle hoy porque ``_build_v3_inputs`` resuelve
    ``race_row`` con ``next(r for r in progression_all if r["valida_num"]
    == valida_num)`` — el primer match de la lista (la válida de copa),
    sin mirar el ancla ``state["event_id"]`` ni ``series_kind``
    (research.md D9, regla 2 de ``contracts/ai-context.md``). El
    ``valida_label`` renderizado en el prompt tampoco usa todavía la forma
    corta de ``race_labels.build_race_label`` ("Cto. Nal.").
    """
    monkeypatch.setenv("RACE_AGENT_CRITIC_ENABLED", "false")
    monkeypatch.setenv("NOTIFICATION_SEND_EMAILS", "false")
    monkeypatch.delenv("RACE_HITL_ALWAYS", raising=False)
    configure_db_factory(fake_session)

    fake_llm = FakeChatLLM([StubAIMessage(content=json.dumps(VALID_PAYLOAD))])
    shared_agent = RaceAnalystAgent(llm=fake_llm, prompt_version=PROMPT_VERSION_ANALYST_V3)
    monkeypatch.setattr(analyst_node_mod, "RaceAnalystAgent", lambda *a, **kw: shared_agent)

    captured_inputs: list = []
    original_build_v3_inputs = analyst_node_mod._build_v3_inputs

    def _capturing_build(state, athlete_ref):
        inputs = original_build_v3_inputs(state, athlete_ref)
        captured_inputs.extend(inputs)
        return inputs

    monkeypatch.setattr(analyst_node_mod, "_build_v3_inputs", _capturing_build)

    g = build_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": "champ-1"}}

    await g.ainvoke(
        {
            "athlete_id": 1,
            "season": 2026,
            "coach_id": 99,
            "run_id": "champ-1",
            "explain_mode": False,
            "prompt_version": PROMPT_VERSION_ANALYST_V3,
            "analysis_kind": "valida",
            "valida_nums": [1],
            "event_id": CN_EVENT_ID,
            "athlete_age": 15,
            "ltad_group": "juvenil",
        },
        config=config,
    )

    assert captured_inputs, "el nodo analyst_agent no construyó ningún AnalystV3Input"
    input_ = captured_inputs[0]

    # Regla 1 (ai-context.md): ancla por event_id, nunca por valida_num a secas.
    assert input_.race_row is not None
    assert input_.race_row["event_id"] == CN_EVENT_ID

    # field_metrics ya se resolvía bien por ancla (comportamiento existente
    # de _field_metrics_by_valida) — se deja como control de que el fixture
    # está bien armado, no como el bug que este test persigue.
    assert input_.field_metrics["is_championship"] is True
    assert input_.field_metrics["series_level"] == "national"

    # El prompt renderizado (lo que de verdad ve el LLM) debe rotular la
    # carrera con la etiqueta corta de campeonato nacional.
    assert fake_llm.calls, "el FakeChatLLM nunca fue invocado"
    rendered_prompt = fake_llm.calls[0][0].content
    assert "Cto. Nal." in rendered_prompt
