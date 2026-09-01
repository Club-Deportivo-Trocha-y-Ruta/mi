"""Tests de procedencia del modelo en ``persist_insight`` (feature 036, US2, T060).

Antes de este fix, ``AthleteAiInsight.model`` se escribía con el string fijo
``"gemini-2.5-flash-lite"`` sin importar qué proveedor/modelo hubiera
generado realmente el análisis (``RACE_AI_PROVIDER``/``RACE_AI_MODEL``).
Estos tests configuran un proveedor/modelo explícitamente DISTINTO del
default para probar que el valor persistido sigue a la configuración real
y no a un string hardcodeado — cubre v1 (fan-out por ``valida_nums``) y v2
(``per_valida_drafts``, una fila por válida).
"""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.persist_insight import persist_insight
from tests.services.race.ai.conftest import make_analysis_output


@pytest.fixture
def configured_non_default_model(monkeypatch):
    """Configura un proveedor/modelo real, deliberadamente distinto del
    default de ``google``/``gemini-3.1-flash-lite`` — si el nodo hardcodeara
    cualquier string fijo, este test lo detectaría."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "anthropic")
    monkeypatch.setattr(settings, "race_ai_model", "claude-sonnet-5")
    return "claude-sonnet-5"


@pytest.mark.asyncio
async def test_persist_insight_v1_persists_the_configured_model(
    configure_db_factory, fake_session, configured_non_default_model
):
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
    assert fake_session.added_objects[0].model == configured_non_default_model


@pytest.mark.asyncio
async def test_persist_insight_v1_fanout_persists_the_configured_model_on_every_row(
    configure_db_factory, fake_session, configured_non_default_model
):
    """Fan-out v1 (varias válidas, un solo draft compartido): TODAS las
    filas deben llevar el modelo configurado, no sólo la primera."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "draft_analysis": make_analysis_output(),
        "valida_nums": [1, 2, 3],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v1"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 3
    assert all(
        row.model == configured_non_default_model for row in fake_session.added_objects
    )


@pytest.mark.asyncio
async def test_persist_insight_v2_per_valida_persists_the_configured_model(
    configure_db_factory, fake_session, configured_non_default_model
):
    """v2 (``per_valida_drafts``): cada fila del fan-out por válida también
    debe llevar el modelo configurado."""
    configure_db_factory(fake_session)
    state = {
        "athlete_id": 1,
        "season": 2026,
        "coach_id": 99,
        "per_valida_drafts": {
            1: make_analysis_output(markdown="## Qué pasó\nVálida 1: A."),
            2: make_analysis_output(markdown="## Qué pasó\nVálida 2: B."),
        },
        "draft_analysis": None,
        "valida_nums": [1, 2],
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
        "principles": [],
        "metrics": {},
    }
    await persist_insight(state)

    assert len(fake_session.added_objects) == 2
    assert all(
        row.model == configured_non_default_model for row in fake_session.added_objects
    )


@pytest.mark.asyncio
async def test_persist_insight_defaults_to_google_gemini_when_unset(
    configure_db_factory, fake_session, monkeypatch
):
    """Sin override explícito, el modelo persistido sigue el default vigente
    (feature 036, T051/T061: google/gemini-3.1-flash-lite) — no el string
    "gemini-2.5-flash-lite" hardcodeado que este fix reemplaza."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_provider", "google")
    monkeypatch.setattr(settings, "race_ai_model", "")
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
    assert fake_session.added_objects[0].model == "gemini-3.1-flash-lite"
