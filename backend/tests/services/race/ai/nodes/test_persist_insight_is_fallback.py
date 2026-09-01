"""Tests del discriminador ``is_fallback`` en ``persist_insight`` (feature 036, US4).

T027 (backend): la fila persistida por el failure path de
``deterministic_fallback`` debe quedar marcada (``is_fallback=True``); el
fallback N=1 (``deterministic_fallback_n1``, análisis legítimo bajo la
regla N=1) y un análisis real NUNCA deben marcarse. Cubre v1 (draft único,
fan-out compartido) y v2 (``per_valida_drafts``, un draft por válida que
puede fallar de forma independiente).
"""
from __future__ import annotations

import pytest

from app.services.race.ai.fallback import deterministic_fallback, deterministic_fallback_n1
from app.services.race.ai.nodes.persist_insight import persist_insight
from tests.services.race.ai.conftest import make_analysis_output


@pytest.mark.asyncio
async def test_persist_insight_v1_marks_failure_fallback(configure_db_factory, fake_session):
    """El draft del failure path (``deterministic_fallback``) marca is_fallback=True."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "draft_analysis": deterministic_fallback("AzulZorro"),
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 1
    assert fake_session.added_objects[0].is_fallback is True


@pytest.mark.asyncio
async def test_persist_insight_v1_does_not_mark_n1_fallback(configure_db_factory, fake_session):
    """El fallback N=1 es un análisis legítimo: NUNCA marca is_fallback."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "draft_analysis": deterministic_fallback_n1("VerdePuma"),
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 1
    assert fake_session.added_objects[0].is_fallback is False


@pytest.mark.asyncio
async def test_persist_insight_v1_does_not_mark_real_analysis(configure_db_factory, fake_session):
    """Un análisis real (no-fallback) queda con is_fallback=False."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "draft_analysis": make_analysis_output(),
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 1
    assert fake_session.added_objects[0].is_fallback is False


@pytest.mark.asyncio
async def test_persist_insight_v2_marks_is_fallback_per_valida_independently(
    configure_db_factory, fake_session
):
    """v2: cada válida puede fallar de forma independiente en invoke_per_valida.

    Válida 1 (failure fallback) → is_fallback=True. Válida 2 (análisis real)
    → is_fallback=False. Ambas filas comparten el mismo run.
    """
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "per_valida_drafts": {
            1: deterministic_fallback("AzulZorro"),
            2: make_analysis_output(markdown="## Qué pasó\nVálida 2: mejora en cadencia."),
        },
        "draft_analysis": None,
        "valida_nums": [1, 2],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    rows_by_valida = {row.valida_num: row for row in fake_session.added_objects}
    assert len(rows_by_valida) == 2
    assert rows_by_valida[1].is_fallback is True
    assert rows_by_valida[2].is_fallback is False


@pytest.mark.asyncio
async def test_persist_insight_v2_does_not_mark_n1_fallback(configure_db_factory, fake_session):
    """v2: el fallback N=1 tampoco marca is_fallback cuando llega vía per_valida_drafts."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "per_valida_drafts": {1: deterministic_fallback_n1("RojoLobo")},
        "draft_analysis": None,
        "valida_nums": [1],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 1
    assert fake_session.added_objects[0].is_fallback is False
