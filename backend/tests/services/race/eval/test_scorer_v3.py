"""Tests del :mod:`app.services.race.eval.scorer_v3` — rule scorer del eval v3.

Offline y determinísticos (ninguno llama al proveedor). Cubren cada
sub-rúbrica con pares mínimos que difieren en una sola cosa, más las dos
decisiones de diseño que no son obvias:

- el grounding se mide contra los **bloques de datos** del caso, no contra
  el prompt completo (que trae el ejemplo resuelto con cifras ficticias);
- las reglas de privacidad/LTAD y de catálogo se delegan en
  ``ai/prechecks.py`` en vez de reimplementarse acá.

Todos los datos son ficticios (feature 037, T401).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.services.race.eval.scorer_v3 import (
    RULE_WEIGHTS_V3,
    case_data_blocks,
    case_grounding_numbers,
    composite_score,
    rule_based_score_v3,
    rule_subscores_v3,
)
from app.services.race.insight_v3 import InsightV3

# ---------------------------------------------------------------------------
# Fixtures ficticias (mismo shape que golden_v3/case_*.json)
# ---------------------------------------------------------------------------

_CASE: dict[str, Any] = {
    "case_id": "t01",
    "description": "Caso sintético para tests del scorer v3.",
    "input": {
        "valida_num": 2,
        "analysis_kind": "valida",
        "athlete_ref": "la deportista",
        "age": 12,
        "ltad_group": "bambino",
        "season": 2026,
        "validas_count": 2,
        "valida_label": "Válida 2 · Copa Valle",
        "race_row": {
            "valida_num": 2,
            "event_date": "2026-02-28",
            "category_code": "INF_B",
            "position": 4,
            "race_time_ms": 1800000,
            "gap_to_winner_ms": 60000,
            "gap_to_winner_pct": 3.45,
        },
        "field_metrics": {
            "valida_num": 2,
            "is_championship": False,
            "field_size": 10,
            "position": 4,
            "percentile": 66.7,
            "gap_to_p1_ms": 60000,
            "gap_pct": 3.45,
            "gap_to_p3_ms": 22000,
            "expected_position": 5,
            "delta_vs_expected": 1,
            "field_strength": 5.5,
            "coverage_with_prior": 0.7,
        },
        "season_rows": [],
        "race_meta": None,
        "anthro_context": None,
        "training_window": {
            "window_days": 28,
            "date_from": "2026-01-31",
            "date_to": "2026-02-28",
            "sessions_in_window": 11,
            "attended": 9,
            "attendance_pct": 81.8,
            "rpe_mean": 4.2,
        },
        "coach_dialogue": [],
        "catalog_context": {
            "interval_templates": [
                {"id": "12", "name": "Frenado modulado", "mesocycle_phase": "base"}
            ],
        },
        "memory_recent_insights": [],
    },
    "expected_themes": ["asistencia", "frenado"],
    "forbidden_terms": ["suplementos", "Mariana"],
    "expected_headline_keywords": ["asistencia", "esperada"],
    "must_reference_catalog": True,
    "max_words": 450,
}


def _draft(**overrides: Any) -> InsightV3:
    """``InsightV3`` perfecto para :data:`_CASE`, con overrides opcionales."""
    payload: dict[str, Any] = {
        "schema_version": "v3",
        "headline": "Terminó un puesto por encima de la posición esperada sosteniendo la asistencia en 81.8%.",
        "field_reading": {
            "percentile": 66.7,
            "expected_position": 5,
            "actual_position": 4,
            "delta_vs_expected": 1,
            "gap_to_p3_hhmmss": "0:00:22",
            "series_label": "Válida 2 · Copa Valle",
            "summary": "Rindió por encima de su índice previo en un pelotón medio.",
        },
        "trend": "improving",
        "observations": [
            {
                "claim": "El avance se apoya en la continuidad de la ventana previa y no en un pico de intensidad.",
                "evidence": ["asistencia 81.8%", "RPE medio 4.2"],
                "domain": "training",
                "confidence": "high",
            },
            {
                "claim": "La diferencia con el frente se juega en pocos segundos dentro de un pelotón parejo.",
                "evidence": ["gap 3.45% al líder", "pelotón de 10"],
                "domain": "field",
                "confidence": "medium",
            },
        ],
        "actions": [
            {
                "text": "Trabajar frenado modulado dos veces por semana con marcas de referencia.",
                "category": "technique",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": {"kind": "interval_template", "code": "12", "label": None},
                "derived_from": 1,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ],
        "watch_signals": [],
        "coach_question": "¿Cambió algo en la rutina de la semana previa que explique la continuidad?",
        "data_gaps": ["Sin antropometría registrada en la ventana."],
        "principles_cited": [],
    }
    payload.update(overrides)
    return InsightV3.model_validate(payload)


# ---------------------------------------------------------------------------
# Pesos y camino feliz
# ---------------------------------------------------------------------------


def test_weights_sum_to_one() -> None:
    """Los pesos deben sumar 1.0: un score >1 o <1 haría el threshold arbitrario."""
    assert sum(RULE_WEIGHTS_V3.values()) == pytest.approx(1.0)


def test_perfect_draft_scores_one() -> None:
    """Draft que cumple las 8 sub-rúbricas → 1.0."""
    assert rule_based_score_v3(_draft(), _CASE) == pytest.approx(1.0)


def test_accepts_plain_dict_as_output() -> None:
    """El scorer acepta el dict serializado, no solo el modelo Pydantic."""
    as_dict = _draft().model_dump(mode="json")
    assert rule_based_score_v3(as_dict, _CASE) == pytest.approx(1.0)


def test_unparseable_output_scores_zero() -> None:
    """Un output que no valida como ``InsightV3`` puntúa 0.0 (no explota)."""
    assert rule_based_score_v3({"headline": "sin observaciones"}, _CASE) == 0.0
    assert rule_based_score_v3(None, _CASE) == 0.0


# ---------------------------------------------------------------------------
# Grounding (0.25)
# ---------------------------------------------------------------------------


def test_grounding_is_proportional_to_ungrounded_numbers() -> None:
    """Una cifra inventada baja el sub-score sin colapsarlo a 0."""
    good = rule_subscores_v3(_draft(), _CASE)["grounding"]
    bad = rule_subscores_v3(
        _draft(
            observations=[
                {
                    "claim": "El avance se apoya en la continuidad de la ventana previa.",
                    "evidence": ["asistencia 81.8%", "cadencia media 91 rpm"],
                    "domain": "training",
                    "confidence": "high",
                },
                {
                    "claim": "La diferencia con el frente se juega en pocos segundos.",
                    "evidence": ["gap 3.45% al líder", "pelotón de 10"],
                    "domain": "field",
                    "confidence": "medium",
                },
            ]
        ),
        _CASE,
    )["grounding"]
    assert good == pytest.approx(1.0)
    assert 0.0 < bad < 1.0


def test_draft_without_any_number_gets_zero_grounding() -> None:
    """Evidencia sin cifras = prosa genérica, el defecto que v3 vino a corregir."""
    draft = _draft(
        headline="La continuidad del trabajo semanal explica el avance frente al pelotón.",
        observations=[
            {
                "claim": "El avance se apoya en la continuidad de la ventana previa.",
                "evidence": ["asistencia sostenida"],
                "domain": "training",
                "confidence": "high",
            },
            {
                "claim": "La diferencia con el frente es corta.",
                "evidence": ["pelotón parejo"],
                "domain": "field",
                "confidence": "medium",
            },
        ],
    )
    assert rule_subscores_v3(draft, _CASE)["grounding"] == 0.0


def test_grounding_without_reference_numbers_does_not_penalize() -> None:
    """Sin verdad de referencia no hay nada que contrastar → 1.0."""
    subs = rule_subscores_v3(_draft(), _CASE, grounding_numbers=[])
    assert subs["grounding"] == pytest.approx(1.0)


def test_grounding_reference_comes_from_data_blocks_not_from_the_prompt_example() -> None:
    """Las cifras del ejemplo resuelto del prompt v3 NO cuentan como grounding.

    ``race_analyst_v3.md`` trae un ejemplo con percentil 58.3, gap a P3
    0:03:12 y asistencia 62.5%. Si la referencia se tomara del prompt
    renderizado (como hace el precheck de producción, a propósito más
    permisivo), un modelo que copiara esas cifras pasaría la rúbrica que
    existe justamente para detectarlo.
    """
    ground = set(case_grounding_numbers(_CASE))
    assert "81.8" in ground and "3.45" in ground  # datos reales del caso
    assert "58.3" not in ground and "62.5" not in ground  # ejemplo del prompt
    assert "0:03:12" not in ground


def test_case_data_blocks_render_times_as_hhmmss() -> None:
    """Los ms se comparan en el formato que ve el modelo (``0:30:00``), no en crudo."""
    blocks = case_data_blocks(_CASE)
    assert "0:30:00" in blocks  # race_time_ms 1800000
    assert "0:01:00" in blocks  # gap_to_winner_ms 60000
    assert "1800000" not in blocks


# ---------------------------------------------------------------------------
# Forbidden / LTAD (0.15) — delegado en prechecks
# ---------------------------------------------------------------------------


def test_forbidden_term_zeroes_its_subscore() -> None:
    """Un término prohibido del caso anula la rúbrica completa."""
    draft = _draft(
        actions=[
            {
                "text": "Agregar suplementos a la rutina semanal.",
                "category": "nutrition",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": {"kind": "interval_template", "code": "12", "label": None},
                "derived_from": 0,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ]
    )
    assert rule_subscores_v3(draft, _CASE)["forbidden"] == 0.0


def test_ltad_violation_detected_by_prechecks_zeroes_forbidden() -> None:
    """Regla LTAD violada (6 días/semana) sin aparecer en ``forbidden_terms``.

    El caso no lista "6 días" como término prohibido: la detección viene de
    ``prechecks.run_prechecks``, que es la misma regla que corre el critic
    en producción.
    """
    draft = _draft(
        actions=[
            {
                "text": "Entrenar 6 días por semana durante el próximo mes.",
                "category": "volume",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": {"kind": "interval_template", "code": "12", "label": None},
                "derived_from": 0,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ]
    )
    subs = rule_subscores_v3(draft, _CASE)
    assert subs["forbidden"] == 0.0


def test_outcome_goal_zeroes_forbidden_even_without_case_term() -> None:
    """Meta de resultado ("podio") → issue LTAD de los prechecks."""
    draft = _draft(
        watch_signals=["Si sostiene la asistencia puede pelear el podio en la próxima."]
    )
    assert rule_subscores_v3(draft, _CASE)["forbidden"] == 0.0


# ---------------------------------------------------------------------------
# Catálogo (0.10)
# ---------------------------------------------------------------------------


def test_unknown_catalog_ref_penalizes_catalog_subscore() -> None:
    """Un ``catalog_ref`` inexistente baja la rúbrica (AC-3.1)."""
    draft = _draft(
        actions=[
            {
                "text": "Trabajar una skill que no existe en el catálogo del club.",
                "category": "technique",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": {"kind": "interval_template", "code": "Z", "label": None},
                "derived_from": 0,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ]
    )
    assert rule_subscores_v3(draft, _CASE)["catalog"] == 0.0


def test_no_catalog_ref_when_case_requires_one_halves_the_subscore() -> None:
    """``must_reference_catalog=True`` sin ninguna ref → media rúbrica."""
    draft = _draft(
        actions=[
            {
                "text": "Trabajar frenado modulado dos veces por semana.",
                "category": "technique",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": None,
                "derived_from": 1,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ]
    )
    assert rule_subscores_v3(draft, _CASE)["catalog"] == pytest.approx(0.5)


def test_no_catalog_ref_is_fine_when_case_does_not_require_it() -> None:
    """``must_reference_catalog=False`` no exige referencia."""
    case = copy.deepcopy(_CASE)
    case["must_reference_catalog"] = False
    draft = _draft(
        actions=[
            {
                "text": "Trabajar frenado modulado dos veces por semana.",
                "category": "technique",
                "priority": "high",
                "horizon": "next_week",
                "catalog_ref": None,
                "derived_from": 1,
            },
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": None,
                "derived_from": 0,
            },
        ]
    )
    assert rule_subscores_v3(draft, case)["catalog"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Headline (0.10)
# ---------------------------------------------------------------------------


def test_template_headline_scores_zero() -> None:
    """"La deportista finalizó…" es el defecto de v2 (descripción, no causa)."""
    draft = _draft(
        headline="La deportista finalizó en la posición 4 con asistencia 81.8% en la ventana."
    )
    assert rule_subscores_v3(draft, _CASE)["headline"] == 0.0


def test_headline_without_expected_keyword_scores_zero() -> None:
    """Un headline causal sobre otro tema tampoco cumple: el caso pide un ángulo."""
    draft = _draft(
        headline="El barro del circuito explica el tiempo perdido en la segunda vuelta."
    )
    assert rule_subscores_v3(draft, _CASE)["headline"] == 0.0


def test_headline_keyword_match_is_case_insensitive() -> None:
    draft = _draft(
        headline="Sostener la ASISTENCIA en 81.8% explica el salto frente al pelotón."
    )
    assert rule_subscores_v3(draft, _CASE)["headline"] == 1.0


# ---------------------------------------------------------------------------
# Themes (0.10) y coach_question (0.05)
# ---------------------------------------------------------------------------


def test_themes_are_proportional_not_all_or_nothing() -> None:
    """Con 2 themes, perder uno deja 0.5 (a diferencia del scorer v2)."""
    draft = _draft(
        actions=[
            {
                "text": "Sostener la frecuencia actual de sesiones hasta la próxima válida.",
                "category": "volume",
                "priority": "med",
                "horizon": "next_race",
                "catalog_ref": {"kind": "interval_template", "code": "12", "label": None},
                "derived_from": 0,
            },
            {
                "text": "Agregar un bloque corto de juego al calentamiento.",
                "category": "technique",
                "priority": "low",
                "horizon": "next_week",
                "catalog_ref": None,
                "derived_from": 1,
            },
        ]
    )
    assert rule_subscores_v3(draft, _CASE)["themes"] == pytest.approx(0.5)


def test_coach_question_must_end_with_question_mark() -> None:
    """Pydantic no exige el '?': lo exige la rúbrica (AC-4.1)."""
    draft = _draft(coach_question="Contame cómo llegó a la carrera.")
    assert rule_subscores_v3(draft, _CASE)["coach_question"] == 0.0
    assert rule_subscores_v3(_draft(), _CASE)["coach_question"] == 1.0


# ---------------------------------------------------------------------------
# Word limits (0.10) y schema (0.15)
# ---------------------------------------------------------------------------


def test_overlong_claim_and_headline_penalize_word_limits() -> None:
    """Los presupuestos del prompt (30/45/20/40 palabras) se miden por campo."""
    long_claim = " ".join(["ab"] * 50)
    draft = _draft(
        headline=" ".join(["ab"] * 35),
        observations=[
            {
                "claim": long_claim,
                "evidence": ["asistencia 81.8%"],
                "domain": "training",
                "confidence": "high",
            },
            {
                "claim": "La diferencia con el frente se juega en pocos segundos.",
                "evidence": ["gap 3.45% al líder"],
                "domain": "field",
                "confidence": "medium",
            },
        ],
    )
    assert rule_subscores_v3(draft, _CASE)["word_limits"] == pytest.approx(3 / 5)


def test_total_word_budget_is_measured_on_the_rendered_markdown() -> None:
    """``max_words`` se compara contra el markdown que verá el coach."""
    case = copy.deepcopy(_CASE)
    case["max_words"] = 60
    subs = rule_subscores_v3(_draft(), case)
    assert subs["word_limits"] == pytest.approx(4 / 5)


def test_missing_field_reading_when_case_has_field_metrics_penalizes_schema() -> None:
    """Con métricas de pelotón en el input, ``field_reading=null`` es incoherente."""
    draft = _draft(field_reading=None)
    assert rule_subscores_v3(draft, _CASE)["schema"] == pytest.approx(0.75)


def test_season_case_expects_null_field_reading() -> None:
    """En un resumen de temporada no hay carrera: ``field_reading`` debe ser null."""
    case = copy.deepcopy(_CASE)
    case["input"]["analysis_kind"] = "season"
    case["input"]["valida_num"] = 0
    case["input"]["race_row"] = None
    case["input"]["field_metrics"] = None
    assert rule_subscores_v3(_draft(field_reading=None), case)["schema"] == pytest.approx(1.0)
    assert rule_subscores_v3(_draft(), case)["schema"] == pytest.approx(0.75)


def test_deterministic_fallback_is_penalized_by_schema() -> None:
    """El fallback v3 es schema-válido pero no es un análisis: no debe puntuar como tal."""
    from app.services.race.ai.fallback import deterministic_fallback_v3

    subs = rule_subscores_v3(deterministic_fallback_v3(), _CASE)
    assert subs["schema"] < 1.0
    assert rule_based_score_v3(deterministic_fallback_v3(), _CASE) < 0.75


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def test_composite_reuses_the_v2_formula() -> None:
    """0.4 rule + 0.6 judge — una sola fórmula para los dos evals."""
    assert composite_score(1.0, 0.5) == pytest.approx(0.7)
    assert composite_score(0.0, 0.0) == 0.0
