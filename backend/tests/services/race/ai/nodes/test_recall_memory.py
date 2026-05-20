"""Tests del nodo recall_memory."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.recall_memory import recall_memory


class _Row:
    def __init__(self, summary_text: str):
        self.summary_text = summary_text


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
