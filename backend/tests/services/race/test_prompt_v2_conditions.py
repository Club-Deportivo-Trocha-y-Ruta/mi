"""US1 (feature 011): race_analyst_v2 prompt renders conditions only when recorded.

Regression: the prompt's Sección-1 unconditionally demanded "condiciones de
clima, tipo de pista" → with no data the model fabricated them.
"""
from __future__ import annotations

from app.services.race.prompts import render_prompt


def _base_ctx(**over):
    ctx = {
        "athlete_pseudonym": "la deportista",
        "age": 12,
        "ltad_group": "bambino",
        "valida_num": 4,
        "maturation_status": "Circa-PHV",
        "progression_table": "| valida | pos |\n| --- | --- |\n| 4 | 2 |",
        "podium_context": "_(sin datos)_",
        "race_meta": None,
        "memory_recent_insights": [],
        "principles": "[1] Principio LTAD.",
        "explain_mode": False,
        "is_season_summary": False,
        "is_first_in_season": False,
        "season_progression": [],
        "season_comparative": [],
        "progression_assessment": "stable",
    }
    ctx.update(over)
    return ctx


def test_conditions_section_present_with_recorded_values():
    race_meta = (
        "- Clima: Nublado\n- Temperatura: 25 °C\n"
        "- Superficie de la pista: Húmeda\n- Altitud: 1000 msnm"
    )
    out = render_prompt("race_analyst_v2", _base_ctx(race_meta=race_meta), strict=False)
    assert "## Condiciones de carrera" in out
    assert "Nublado" in out
    assert "Húmeda" in out
    assert "1000 msnm" in out
    # When recorded, the Sección-1 instruction DOES include conditions.
    assert "condiciones de carrera registradas" in out


def test_no_conditions_section_and_veto_when_unrecorded():
    out = render_prompt("race_analyst_v2", _base_ctx(race_meta=None), strict=False)
    # No formatted conditions block.
    assert "## Condiciones de carrera — SIN REGISTRO" in out
    assert "PROHIBIDO mencionar clima, pista o terreno" in out
    # Sección-1 no longer demands conditions when none recorded.
    assert "condiciones de carrera registradas" not in out
