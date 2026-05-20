"""Tests del nodo rehydrate_names."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes import rehydrate_names as mod
from tests.services.race.ai.conftest import make_analysis_output


class _NameRow:
    def __init__(self, first, last):
        self.first_name = first
        self.last_name = last


@pytest.mark.asyncio
async def test_rehydrate_replaces_pseudonym(configure_db_factory, fake_session):
    fake_session.row_responses["FROM athletes"] = [_NameRow("Juan", "Perez")]
    configure_db_factory(fake_session)

    draft = make_analysis_output(
        pseudonym="AzulZorro",
        markdown="AzulZorro mostró progresión.",
    )
    state = {
        "draft_analysis": draft,
        "mapping": {"AzulZorro": 1},
    }
    update = await mod.rehydrate_names(state)
    assert "Juan Perez" in update["final_analysis"].raw_markdown
    assert "AzulZorro" not in update["final_analysis"].raw_markdown
    # Pseudónimo original sigue en el campo .pseudonym (trazabilidad).
    assert update["final_analysis"].pseudonym == "AzulZorro"


@pytest.mark.asyncio
async def test_rehydrate_no_mapping_passthrough():
    draft = make_analysis_output(markdown="Sin pseudónimo.")
    state = {"draft_analysis": draft, "mapping": {}}
    update = await mod.rehydrate_names(state)
    assert update["final_analysis"].raw_markdown == "Sin pseudónimo."


@pytest.mark.asyncio
async def test_rehydrate_handles_no_draft():
    update = await mod.rehydrate_names({"draft_analysis": None, "mapping": {}})
    assert "final_analysis" not in update
