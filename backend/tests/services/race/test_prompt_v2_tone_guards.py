"""T058 (feature 036, Wave 3 / US2): el rewrite de la Sección 1 no debe

regresar las salvaguardas de tono sobre el menor. El audit de la feature
036 califica estas reglas como lo más sólido del prompt actual — este
módulo las fija con una prueba explícita para que un futuro cambio de
estilo no pueda borrarlas sin que un test se ponga en rojo.

Cubre, en el prompt renderizado:
- Ninguna palabra de juicio de valor sobre el desempeño/cuerpo del atleta.
- Ninguna comparación de mérito ni atribución causal subjetiva.
- Prohibición general de diagnóstico médico.
- Prohibición general de nombres reales / alias / dorsal.
"""
from __future__ import annotations

from app.services.race.prompts import render_prompt


def _base_ctx(**over):
    ctx = {
        "athlete_pseudonym": "la deportista",
        "age": 12,
        "ltad_group": "bambino",
        "valida_num": 3,
        "maturation_status": "Circa-PHV",
        "progression_table": "| valida | pos |\n| --- | --- |\n| 3 | 5 |",
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


def _render() -> str:
    return render_prompt("race_analyst_v2", _base_ctx(), strict=False)


def test_forbidden_evaluative_adjectives_list_intact():
    out = _render()
    assert "adjetivos valorativos" in out
    for word in (
        "destacada",
        "decepcionante",
        "brillante",
        "mediocre",
        "excelente",
        "pobre",
    ):
        assert word in out, f"Falta '{word}' en la lista de adjetivos prohibidos."


def test_forbidden_merit_comparisons_and_subjective_causal_claims_intact():
    out = _render()
    assert "comparaciones de mérito" in out
    assert "atribuciones causales subjetivas" in out


def test_no_medical_diagnosis_rule_intact():
    out = _render()
    assert "Sin diagnóstico médico" in out


def test_no_real_names_rule_intact():
    out = _render()
    assert "PROHIBIDO usar nombres reales" in out
    assert "NUNCA pseudónimo, alias ni dorsal" in out


def test_fun_first_principle_intact():
    """CONSTRAINTS_PRINCIPIOS_CLUB #7 — el disfrute nunca se subordina al resultado."""
    out = _render()
    assert "Diversión primero" in out
