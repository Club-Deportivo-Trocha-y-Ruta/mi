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
async def test_render_fallback_when_no_analysis():
    update = await render_outputs({})
    assert "sin análisis disponible" in update["rendered_markdown"].lower()
