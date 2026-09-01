"""T054/T055/T056 (feature 036, Wave 3 / US2): Sección 1 exige síntesis.

Regression covered by this module:

- T054 — la Sección 1 pedía 5 campos enumerados con 5 verbos cerrados; el
  único output combinatoriamente seguro era "sujeto + verbo + dato" una vez
  por campo (spec.md US2). Ahora debe exigir combinar >=2 datos por idea y
  prohibir repetir una misma cifra en más de una oración.
- T055 — la Sección 1 exigía "número de vueltas completadas" pero
  ``AnalysisInput`` (schemas.py) no tiene ningún campo de vueltas: la única
  forma de cumplir la instrucción era la muletilla fabricada "Alcanzó el
  número máximo de vueltas previsto para la categoría". Ahora la Sección 1
  prohíbe expresamente esa afirmación.
- T056 — ninguna versión del prompt tenía un solo ejemplo few-shot. Ahora
  hay un par contrastivo (mal/bien) con datos ficticios.
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


# ---------------------------------------------------------------------------
# T054 — síntesis en vez de enumeración
# ---------------------------------------------------------------------------


def test_section1_demands_synthesis_not_a_field_checklist():
    out = _render()
    assert "combinar al menos dos datos" in out, (
        "La Sección 1 debe exigir combinar >=2 datos por idea (T054) en vez "
        "de una lista de campos a completar uno por oración."
    )
    # The old rigid enumeration ("SÍ incluir: campo1, campo2, ...campo5")
    # must be gone — replaced by "datos disponibles" framed as raw material.
    assert (
        "gap al líder, número de vueltas completadas, si hubo abandono"
        not in out
    ), "La vieja lista de 5 campos enumerados (checklist) sigue presente."


def test_section1_forbids_repeating_a_figure_across_sentences():
    out = _render()
    assert "PROHIBIDO repetir un mismo dato" in out, (
        "Falta la regla que prohíbe citar el mismo tiempo/posición/gap en "
        "más de una oración (Acceptance Scenario 2, US2)."
    )


def test_section1_verb_list_widened_without_evaluative_verbs():
    out = _render()
    # Original five must still be allowed (backward compatible)...
    for verb in ("completó", "registró", "finalizó", "participó", "alcanzó"):
        assert verb in out
    # ...but the list must now be visibly wider than the original five.
    widened = ("mostró", "sostuvo", "gestionó", "disputó", "ejecutó")
    assert any(v in out for v in widened), (
        "El listado de verbos permitidos debe ampliarse más allá de los "
        "cinco originales (T054)."
    )
    # No evaluative verb sneaks in alongside the wider list.
    for judgemental in ("brilló", "arrasó", "dominó", "fracasó"):
        assert judgemental not in out


# ---------------------------------------------------------------------------
# T055 — contradicción de vueltas resuelta en la fuente
# ---------------------------------------------------------------------------


def test_section1_forbids_lap_count_claim_outright():
    out = _render()
    assert "PROHIBIDO afirmar o insinuar el número de vueltas completadas" in out, (
        "T055: como no existe un dato de vueltas en AnalysisInput, la "
        "Sección 1 debe prohibir tajantemente esa afirmación en vez de "
        "seguir exigiéndola."
    )
    # The specific fabricated filler sentence from spec.md must be named as
    # forbidden, not silently left possible.
    assert "alcanzó el número máximo de vueltas previsto para la categoría" in out.lower()


# ---------------------------------------------------------------------------
# T056 — par contrastivo few-shot
# ---------------------------------------------------------------------------


def test_section1_has_contrastive_few_shot_example():
    out = _render()
    assert "Ejemplo de calibración" in out
    assert "Enumeración" in out and "evitar" in out
    assert "Síntesis" in out
    # The "bad" example must actually demonstrate the two named defects:
    # a repeated figure and the fabricated lap sentence.
    assert out.count("0:42:10") >= 2, (
        "El ejemplo 'malo' debe repetir la misma cifra de tiempo para "
        "ilustrar el defecto que la regla de no-repetición prohíbe."
    )
    assert "alcanzó el número máximo de vueltas previsto para la categoría" in out.lower()


def test_few_shot_uses_only_synthetic_data_no_real_identity():
    """Ley 1581 — los ejemplos deben usar datos ficticios y nunca un nombre."""
    out = _render()
    # The example must stay within the "la deportista" convention like the
    # rest of the prompt; it must not introduce a proper name.
    assert "datos ficticios" in out
    assert "la deportista" in out
