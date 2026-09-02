"""Tests del nodo recall_memory."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.services.race.ai.nodes.recall_memory import recall_memory


class _Row:
    def __init__(self, summary_text: str):
        self.summary_text = summary_text


class _MappingRow:
    """Fila fake que expone ``_mapping`` (mismo shape que un ``Row`` real)."""

    def __init__(self, mapping: dict):
        self._mapping = mapping


@pytest.mark.asyncio
async def test_recall_memory_returns_up_to_3(configure_db_factory, fake_session):
    fake_session.row_responses["athlete_ai_insights"] = [
        _Row("Resumen 1"),
        _Row("Resumen 2"),
        _Row("Resumen 3"),
    ]
    configure_db_factory(fake_session)
    update = await recall_memory({"athlete_id": 1})
    assert update["memory"] == ["Resumen 1", "Resumen 2", "Resumen 3"]


@pytest.mark.asyncio
async def test_recall_memory_handles_empty(configure_db_factory, fake_session):
    configure_db_factory(fake_session)
    update = await recall_memory({"athlete_id": 1})
    assert update["memory"] == []


@pytest.mark.asyncio
async def test_recall_memory_truncates_long_summaries(configure_db_factory, fake_session):
    long_str = "x" * 1000
    fake_session.row_responses["athlete_ai_insights"] = [_Row(long_str)]
    configure_db_factory(fake_session)
    update = await recall_memory({"athlete_id": 1})
    assert len(update["memory"][0]) == 500


# ---------------------------------------------------------------------------
# coach_dialogue (feature 037, T104)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_memory_coach_dialogue_maps_fields(
    configure_db_factory, fake_session
):
    """Fila v3 con structured_json + respuesta del coach → item completo."""
    structured = {
        "headline": "Mejoró el ritmo en el último tramo",
        "coach_question": "¿Hubo algo distinto en la semana previa?",
    }
    fake_session.row_responses["structured_json"] = [
        _MappingRow(
            {
                "structured_json": json.dumps(structured),
                "coach_answer_text": "Tuvo examen el jueves.",
                "coach_rating": 1,
                "generated_at": datetime(2026, 8, 1, 12, 0, 0),
                "valida_num": 3,
                "sequence_number": 3,
                "location": "Ginebra",
                "series_kind": "cup",
                "series_level": "departmental",
            }
        )
    ]
    configure_db_factory(fake_session)

    update = await recall_memory({"athlete_id": 42})

    assert update["coach_dialogue"] == [
        {
            "headline": "Mejoró el ritmo en el último tramo",
            "coach_question": "¿Hubo algo distinto en la semana previa?",
            "coach_answer_text": "Tuvo examen el jueves.",
            "coach_rating": 1,
            "valida_label": "Válida III — Ginebra",
            "generated_at": "2026-08-01T12:00:00",
        }
    ]


@pytest.mark.asyncio
async def test_recall_memory_coach_dialogue_empty_when_no_v3_rows(
    configure_db_factory, fake_session
):
    """Sin filas ``structured_json`` (todos v1/v2) → coach_dialogue=[]."""
    configure_db_factory(fake_session)

    update = await recall_memory({"athlete_id": 42})

    assert update["coach_dialogue"] == []
    assert update["memory"] == []


@pytest.mark.asyncio
async def test_recall_memory_coach_dialogue_degrades_on_query_failure(
    configure_db_factory, fake_session
):
    """Fila con structured_json inválido (no dict) se descarta sin romper."""
    fake_session.row_responses["structured_json"] = [
        _MappingRow(
            {
                "structured_json": "no es json",
                "coach_answer_text": None,
                "coach_rating": None,
                "generated_at": None,
                "valida_num": None,
                "sequence_number": None,
                "location": None,
                "series_kind": None,
                "series_level": None,
            }
        )
    ]
    configure_db_factory(fake_session)

    update = await recall_memory({"athlete_id": 42})

    assert update["coach_dialogue"] == []
