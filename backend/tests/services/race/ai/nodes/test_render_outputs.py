"""Tests del nodo render_outputs."""
from __future__ import annotations

import pytest

from app.services.race.ai.nodes.render_outputs import render_outputs
from tests.services.race.ai.conftest import make_analysis_output


@pytest.mark.asyncio
async def test_render_prepends_header_if_no_h1():
    final = make_analysis_output(markdown="## Sección\nbody")
    update = await render_outputs({"final_analysis": final, "season": 2026})
    md = update["rendered_markdown"]
    assert "# Análisis de carrera — temporada 2026" in md
    assert "## Sección" in md


@pytest.mark.asyncio
async def test_render_does_not_duplicate_h1():
    final = make_analysis_output(markdown="# Mi título\nbody")
    update = await render_outputs({"final_analysis": final, "season": 2026})
    md = update["rendered_markdown"]
    assert md.count("# ") <= 2  # solo el original (más eventuales subheads)
    assert md.startswith("# Mi título")


@pytest.mark.asyncio
async def test_render_marks_failed_when_no_analysis():
    update = await render_outputs({})
    assert update.get("status") == "failed"
    assert "sin análisis disponible" in update["rendered_markdown"].lower()
    assert any(
        e.get("error") == "EmptyRender" for e in update.get("errors") or []
    )


@pytest.mark.asyncio
async def test_render_marks_failed_when_raw_markdown_empty():
    final = make_analysis_output(markdown="   ")
    update = await render_outputs({"final_analysis": final, "season": 2026})
    assert update.get("status") == "failed"
    assert any(
        e.get("error") == "EmptyRender" for e in update.get("errors") or []
    )


@pytest.mark.asyncio
async def test_render_respects_no_data_markdown_from_validate():
    md = "# Análisis de carrera — temporada 2026\n\n_Sin carreras registradas._\n"
    update = await render_outputs(
        {
            "no_data_for_season": True,
            "rendered_markdown": md,
            "season": 2026,
        }
    )
    assert update["rendered_markdown"] == md
    assert update.get("status") != "failed"


@pytest.mark.asyncio
async def test_render_synthesizes_no_data_markdown_when_missing():
    update = await render_outputs(
        {"no_data_for_season": True, "season": 2026}
    )
    assert "Sin carreras registradas para temporada 2026" in update["rendered_markdown"]
    assert update.get("status") == "no_data"
