"""Tests de ``persist_insight`` con drafts v3 (feature 037, T201).

Cubre: ``structured_json`` persistido, ``summary_text`` = markdown
renderizado, recomendaciones tipadas desde ``actions`` (sin regex),
``use_case`` por tipo de análisis, ``is_fallback`` desde el draft
estructurado y el modelo del rol analyst.

Datos 100 % ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import pytest

from app.services.race.ai.fallback import deterministic_fallback_v3
from app.services.race.ai.nodes.persist_insight import persist_insight
from app.services.race.insight_v3 import (
    insight_v3_sections,
    insight_v3_to_legacy_recommendations,
    render_insight_v3_markdown,
)
from app.services.race.schemas import AnalysisOutput
from tests.services.race.ai.conftest import make_analysis_output
from tests.services.race.test_insight_v3 import make_insight


def compat_output(insight, pseudonym: str = "AzulZorro") -> AnalysisOutput:
    """Réplica de lo que el nodo analyst v3 deja en ``per_valida_drafts``."""
    markdown = render_insight_v3_markdown(insight, "la deportista")
    return AnalysisOutput(
        pseudonym=pseudonym,
        sections=insight_v3_sections(insight),
        citations_used=[],
        recommendations=insight_v3_to_legacy_recommendations(insight),
        risk_flags=[],
        raw_markdown=markdown,
        word_count=len(markdown.split()),
    )


def v3_state(**overrides) -> dict:
    insight = overrides.pop("insight", None) or make_insight()
    state = {
        "athlete_id": 7,
        "season": 2026,
        "competitor_id": 22,
        "coach_id": 99,
        "event_id": 41,
        "analysis_kind": "valida",
        "per_valida_drafts": {4: compat_output(insight)},
        "per_valida_drafts_v3": {4: insight},
        "hitl_decision": {"decision": "approve"},
        "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v3"},
        "principles": [],
        "metrics": {},
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_persists_structured_json(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    await persist_insight(v3_state())

    row = fake_session.added_objects[0]
    assert row.structured_json["schema_version"] == "v3"
    assert row.structured_json["trend"] == "declining"
    assert row.structured_json["field_reading"]["percentile"] == 58.3


@pytest.mark.asyncio
async def test_summary_text_is_the_rendered_markdown(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    await persist_insight(v3_state())

    row = fake_session.added_objects[0]
    assert row.summary_text.startswith("## Hallazgo principal")
    assert "## Pregunta para el coach" in row.summary_text


@pytest.mark.asyncio
async def test_recommendations_come_from_actions(configure_db_factory, fake_session):
    """spec §problem 6: las recomendaciones ya no dependen de una regex."""
    configure_db_factory(fake_session)

    await persist_insight(v3_state())

    recs = fake_session.added_objects[0].recommendations_json
    assert len(recs) == 2
    assert recs[0]["category"] == "volume"
    assert recs[0]["horizon"] == "next_week"
    assert recs[1]["catalog_ref"] == {
        "kind": "interval_template",
        "code": "12",
        "label": None,
    }


@pytest.mark.asyncio
async def test_use_case_for_valida_analysis(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    await persist_insight(v3_state())

    assert fake_session.added_objects[0].use_case == "race_progression_v3"


@pytest.mark.asyncio
async def test_use_case_for_season_summary(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    insight = make_insight(field_reading=None)

    await persist_insight(
        v3_state(
            analysis_kind="season",
            insight=insight,
            per_valida_drafts={0: compat_output(insight)},
            per_valida_drafts_v3={0: insight},
        )
    )

    row = fake_session.added_objects[0]
    assert row.use_case == "season_summary_v3"
    assert row.valida_num == 0


@pytest.mark.asyncio
async def test_explicit_use_case_still_wins(configure_db_factory, fake_session):
    configure_db_factory(fake_session)

    await persist_insight(v3_state(use_case="race_progression"))

    assert fake_session.added_objects[0].use_case == "race_progression"


@pytest.mark.asyncio
async def test_is_fallback_comes_from_the_structured_draft(
    configure_db_factory, fake_session
):
    """El compat AnalysisOutput siempre es "real": el marcador vive en el v3."""
    configure_db_factory(fake_session)
    fallback = deterministic_fallback_v3()

    await persist_insight(
        v3_state(
            insight=fallback,
            per_valida_drafts={4: compat_output(fallback)},
            per_valida_drafts_v3={4: fallback},
        )
    )

    assert fake_session.added_objects[0].is_fallback is True


@pytest.mark.asyncio
async def test_real_v3_analysis_is_not_marked_as_fallback(
    configure_db_factory, fake_session
):
    configure_db_factory(fake_session)

    await persist_insight(v3_state())

    assert fake_session.added_objects[0].is_fallback is False


@pytest.mark.asyncio
async def test_model_uses_the_analyst_role(configure_db_factory, fake_session, monkeypatch):
    """AC-6.1: la fila reporta el modelo del rol que la generó."""
    from app.config import settings

    configure_db_factory(fake_session)
    monkeypatch.setattr(settings, "race_ai_analyst_model", "gemini-ficticio-analyst")

    await persist_insight(v3_state())

    assert fake_session.added_objects[0].model == "gemini-ficticio-analyst"


@pytest.mark.asyncio
async def test_v2_rows_keep_structured_json_empty(configure_db_factory, fake_session):
    """Sin drafts v3 nada cambia: ``structured_json`` queda en None."""
    configure_db_factory(fake_session)

    await persist_insight(
        {
            "athlete_id": 7,
            "season": 2026,
            "competitor_id": 22,
            "coach_id": 99,
            "per_valida_drafts": {4: make_analysis_output()},
            "hitl_decision": {"decision": "approve"},
            "aggregate_metrics": {"prompt_version_analyst": "race_analyst_v2"},
            "principles": [],
            "metrics": {},
        }
    )

    row = fake_session.added_objects[0]
    assert row.structured_json is None
    assert row.use_case == "race_progression"
