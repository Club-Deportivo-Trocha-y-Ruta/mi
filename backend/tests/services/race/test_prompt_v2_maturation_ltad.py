"""US2 (feature 011): prompt renders maturation only when known + correct LTAD block."""
from __future__ import annotations

from app.services.race.prompts import render_prompt


def _ctx(**over):
    base = {
        "athlete_pseudonym": "la deportista",
        "age": 13,
        "ltad_group": "juvenil",
        "valida_num": 4,
        "maturation_status": None,
        "progression_table": "| v | p |\n| - | - |\n| 4 | 2 |",
        "podium_context": "_(sin datos)_",
        "race_meta": None,
        "memory_recent_insights": [],
        "principles": "[1] X.",
        "explain_mode": False,
        "is_season_summary": False,
        "is_first_in_season": False,
        "season_progression": [],
        "season_comparative": [],
        "progression_assessment": "stable",
    }
    base.update(over)
    return base


def test_no_maturation_line_and_instruction_when_absent():
    out = render_prompt("race_analyst_v2", _ctx(maturation_status=None), strict=False)
    assert "- **Fase madurativa:** sin registro antropométrico" in out
    assert "PROHIBIDO afirmar fase madurativa" in out


def test_maturation_line_present_when_known():
    out = render_prompt(
        "race_analyst_v2", _ctx(maturation_status="Circa-PHV"), strict=False
    )
    assert "- **Fase madurativa:** Circa-PHV" in out
    assert "PROHIBIDO afirmar fase madurativa" not in out


def test_juvenil_block_rendered_for_juvenil_group():
    out = render_prompt("race_analyst_v2", _ctx(ltad_group="juvenil"), strict=False)
    assert "13-15 años (juvenil)" in out
    assert "10-12 años (mini-bambino / bambino)" not in out
