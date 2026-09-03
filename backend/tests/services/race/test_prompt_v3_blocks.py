"""Tests de los prompts v3 (feature 037, T201).

Verifican que ``race_analyst_v3.md`` y ``race_season_summary_v3.md``
renderizan con ``strict=True`` tanto con TODOS los bloques de datos
presentes como con todos ausentes — el modo estricto es el que corre en
producción, así que una variable que el contexto no define rompe el run.

Datos 100 % ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import pytest

from app.services.race.agents.analyst import (
    PROMPT_VERSION_ANALYST_V3,
    PROMPT_VERSION_SEASON_SUMMARY_V3,
    AnalystV3Input,
    RaceAnalystAgent,
    series_label_v3,
)
from app.services.race.prompts import render_prompt

FIELD_METRICS_V4 = {
    "event_id": 41,
    "valida_num": 4,
    "event_date": "2026-05-10",
    "series_kind": "cup",
    "series_level": "departmental",
    "is_championship": False,
    "field_size": 18,
    "position": 7,
    "percentile": 58.3,
    "race_time_ms": 2530000,
    "gap_to_p1_ms": 243000,
    "gap_pct": 9.4,
    "gap_to_p3_ms": 192000,
    "category_median_time_ms": 2600000,
    "gap_to_median_pct": -2.7,
    "laps_behind": 0,
    "prior_index": 8.1,
    "expected_position": 5,
    "delta_vs_expected": -2,
    "field_strength": 10.2,
    "coverage_with_prior": 0.7,
}

FIELD_METRICS_CHAMPIONSHIP = {
    **FIELD_METRICS_V4,
    "event_id": 42,
    "valida_num": 99,
    "event_date": "2026-06-14",
    "series_kind": "championship",
    "series_level": "departmental",
    "is_championship": True,
    "position": 9,
    "percentile": 48.0,
    "expected_position": None,
    "delta_vs_expected": None,
    "field_strength": None,
    "coverage_with_prior": 0.3,
}

RACE_ROW = {
    "valida_num": 4,
    "event_date": "2026-05-10",
    "category_code": "PRE-JUVENIL",
    "position": 7,
    "race_time_ms": 2530000,
    "points_awarded": 24,
    "gap_to_winner_ms": 243000,
    "gap_to_winner_pct": 9.4,
}

TRAINING_WINDOW = {
    "window_days": 28,
    "date_from": "2026-04-12",
    "date_to": "2026-05-10",
    "sessions_in_window": 8,
    "attended": 5,
    "absent": 2,
    "excused": 1,
    "attendance_pct": 62.5,
    "training_hours": 7.5,
    "rpe_mean": 4.1,
    "rpe_last7_mean": 3.8,
    "rpe_prev21_mean": 4.3,
    "rubric_effort_mean": 4.0,
    "rubric_attitude_mean": 4.5,
    "rubric_technique_mean": 3.2,
    "technical_foci": ["Descensos y bermas", "Frenada"],
    "interval_sessions": 0,
    "days_since_last_session": 3,
    "days_since_previous_race": 21,
    "coach_feedback": ["Buena actitud en el circuito técnico."],
    "strava_load": None,
}

ANTHRO_CONTEXT = {
    "records_count": 3,
    "latest": {
        "evaluation_date": "2026-03-01",
        "days_before_event": 70,
        "maturity_offset_years": -0.4,
        "age_at_phv": 13.2,
        "maturation_status": "Circa-PHV",
        "height_percentile": 61.0,
    },
    "previous": None,
    "growth_velocity_cm_per_year": 7.2,
    "months_from_phv": -4.8,
    "flags": ["approaching_circa_phv"],
}

CATALOG_CONTEXT = {
    "interval_templates": [
        {"id": 8, "name": "Rodaje ondulado", "age_band": "12-13", "mesocycle_phase": "base"}
    ],
}

COACH_DIALOGUE = [
    {
        "generated_at": "2026-04-20",
        "valida_label": "Válida III · Copa",
        "headline": "Mejoró el gap pese a un pelotón más fuerte",
        "coach_question": "¿Hubo cambios en el descanso previo?",
        "coach_answer": "Estuvo en semana de exámenes.",
        "coach_rating": 1,
    }
]


def full_input(**overrides) -> AnalystV3Input:
    """Entrada v3 con TODOS los bloques de datos poblados."""
    base = {
        "valida_num": 4,
        "analysis_kind": "valida",
        "athlete_ref": "el deportista",
        "age": 13,
        "ltad_group": "juvenil",
        "season": 2026,
        "validas_count": 5,
        "race_row": RACE_ROW,
        "field_metrics": FIELD_METRICS_V4,
        "season_rows": [FIELD_METRICS_V4, FIELD_METRICS_CHAMPIONSHIP],
        "race_meta": "- Clima: soleado\n- Superficie de la pista: Seca",
        "anthro_context": ANTHRO_CONTEXT,
        "training_window": TRAINING_WINDOW,
        "coach_dialogue": COACH_DIALOGUE,
        "catalog_context": CATALOG_CONTEXT,
        "memory_recent_insights": ["Válida III: gap 8.4%, percentil 58.3"],
    }
    base.update(overrides)
    return AnalystV3Input(**base)


def render(input_: AnalystV3Input, name: str) -> str:
    context = RaceAnalystAgent()._build_v3_context(input_)
    return render_prompt(name, context, strict=True)


# ---------------------------------------------------------------------------
# Bloques presentes / ausentes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt_name", [PROMPT_VERSION_ANALYST_V3, PROMPT_VERSION_SEASON_SUMMARY_V3]
)
def test_renders_strict_with_every_block_present(prompt_name):
    assert render(full_input(), prompt_name)


@pytest.mark.parametrize(
    "prompt_name", [PROMPT_VERSION_ANALYST_V3, PROMPT_VERSION_SEASON_SUMMARY_V3]
)
def test_renders_strict_with_every_block_absent(prompt_name):
    """Sin ningún dato opcional el prompt sigue renderizando en modo estricto."""
    text = render(AnalystV3Input(valida_num=0), prompt_name)
    assert "SIN DATO" in text


def test_analyst_prompt_includes_all_data_blocks():
    text = render(full_input(), PROMPT_VERSION_ANALYST_V3)
    assert "- Posición: 7" in text  # fila de carrera
    assert "- Percentil: 58.3" in text  # field metrics
    assert "- Asistencia: 62.5%" in text  # ventana de entrenamiento
    assert "Circa-PHV" in text  # maduración
    assert "- Clima: soleado" in text  # condiciones
    assert "`8` Rodaje ondulado" in text  # catálogo
    assert "El coach respondió: Estuvo en semana de exámenes." in text  # diálogo
    assert "Válida III: gap 8.4%" in text  # memoria


def test_analyst_prompt_flags_missing_blocks_explicitly():
    """Cada bloque ausente produce un aviso, no un hueco silencioso."""
    text = render(AnalystV3Input(valida_num=4), PROMPT_VERSION_ANALYST_V3)
    assert "## Resultado de la carrera — SIN DATO" in text
    assert "## Lectura del pelotón — SIN DATO" in text
    assert "## Ventana de entrenamiento previa — SIN DATO" in text
    assert "## Maduración — SIN DATO" in text
    assert "## Condiciones registradas — SIN DATO" in text
    assert "PROHIBIDO mencionar clima" in text


def test_expected_position_absent_is_declared_not_invented():
    """AC-2.2: con <50 % de cobertura la expectativa no se calcula."""
    text = render(
        full_input(field_metrics=FIELD_METRICS_CHAMPIONSHIP), PROMPT_VERSION_ANALYST_V3
    )
    assert "Posición esperada: no calculable" in text


# ---------------------------------------------------------------------------
# Método y reglas
# ---------------------------------------------------------------------------


def test_prompt_demands_verbatim_numbers():
    """La regla anti-invención de cifras es explícita (AC-1.1)."""
    text = render(full_input(), PROMPT_VERSION_ANALYST_V3)
    assert "copiado tal cual" in text
    assert "`headline`, `claim` o `evidence`" in text


def test_prompt_uses_athlete_ref_and_never_a_pseudonym():
    text = render(full_input(athlete_ref="el deportista"), PROMPT_VERSION_ANALYST_V3)
    assert "el deportista" in text
    assert "la deportista" not in text


def test_prompt_carries_one_worked_example_and_the_output_schema():
    text = render(full_input(), PROMPT_VERSION_ANALYST_V3)
    assert "Ejemplo resuelto (datos ficticios" in text
    assert '"schema_version": "v3"' in text
    assert "observations` 2-4" in text


def test_prompt_declares_the_closed_principle_catalog():
    text = render(full_input(), PROMPT_VERSION_ANALYST_V3)
    assert "3. Progresión técnica en MTB/XCO" in text


# ---------------------------------------------------------------------------
# Resumen de temporada
# ---------------------------------------------------------------------------


def test_season_prompt_renders_the_season_table():
    text = render(
        full_input(valida_num=0, analysis_kind="season"), PROMPT_VERSION_SEASON_SUMMARY_V3
    )
    assert "| válida | fecha | serie | posición | pelotón | percentil |" in text
    assert "| 4 | 2026-05-10 | Válida 4 · Copa | 7 | 18 | 58.3 | 9.4% |" in text
    assert "Cto. Departamental" in text


def test_season_prompt_asks_for_three_priorities_and_one_question():
    text = render(
        full_input(valida_num=0, analysis_kind="season"), PROMPT_VERSION_SEASON_SUMMARY_V3
    )
    assert "3 prioridades para el próximo mesociclo" in text
    assert "Exactamente una pregunta" in text
    assert "nunca** se comparan puesto a puesto" in text


def test_season_prompt_states_the_season_and_race_count():
    text = render(
        full_input(valida_num=0, analysis_kind="season"), PROMPT_VERSION_SEASON_SUMMARY_V3
    )
    assert "Temporada: 2026" in text
    assert "Carreras con resultado en la temporada: 5" in text


# ---------------------------------------------------------------------------
# Etiquetas de serie
# ---------------------------------------------------------------------------


def test_series_label_marks_championships():
    assert series_label_v3(FIELD_METRICS_CHAMPIONSHIP) == "Cto. Departamental"
    assert series_label_v3(FIELD_METRICS_V4) == "Válida 4 · Copa"
    assert series_label_v3(None) == ""
