"""Tests de ``app.services.race.insight_v3`` (feature 037, T201).

Cubre el contrato de data-model.md §InsightV3, el renderizado de plan.md
§Rendering y la extracción de tokens numéricos que alimenta el precheck de
grounding del critic.

Todos los datos son ficticios: ningún nombre, peso, IMC ni estado
nutricional de un menor real aparece en estos fixtures.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.race.insight_v3 import (
    ActionCategory,
    ActionV3,
    CatalogKind,
    CatalogRef,
    EvidenceDomain,
    FieldReading,
    Horizon,
    InsightV3,
    Observation,
    Priority,
    extract_numeric_tokens,
    insight_v3_sections,
    insight_v3_to_legacy_recommendations,
    normalize_numeric_token,
    render_insight_v3_markdown,
)


def make_insight(**overrides) -> InsightV3:
    """Insight v3 válido con datos ficticios."""
    payload = {
        "headline": "Cayó 2 puestos respecto de lo esperado tras la ventana con menor asistencia",
        "field_reading": FieldReading(
            percentile=58.3,
            expected_position=5,
            actual_position=7,
            delta_vs_expected=-2,
            gap_to_p3_hhmmss="0:03:12",
            series_label="Válida IV · Copa",
            summary="Rindió por debajo de su índice previo en un pelotón de fuerza media.",
        ),
        "trend": "declining",
        "observations": [
            Observation(
                claim="El retroceso coincide con la ventana de entrenamiento más floja.",
                evidence=["asistencia 62.5% en la ventana", "RPE medio 4.1"],
                domain=EvidenceDomain.TRAINING,
                confidence="medium",
            ),
            Observation(
                claim="El tiempo perdido se concentra en el terreno técnico.",
                evidence=["gap a P3 0:03:12"],
                domain=EvidenceDomain.FIELD,
                confidence="low",
            ),
        ],
        "actions": [
            ActionV3(
                text="Recuperar 4 sesiones semanales antes de la próxima válida.",
                category=ActionCategory.VOLUME,
                priority=Priority.HIGH,
                horizon=Horizon.NEXT_WEEK,
                catalog_ref=None,
                derived_from=0,
            ),
            ActionV3(
                text="Dos bloques de 20 min de descensos por semana.",
                category=ActionCategory.TECHNIQUE,
                priority=Priority.MED,
                horizon=Horizon.NEXT_RACE,
                catalog_ref=CatalogRef(kind=CatalogKind.TECHNIQUE_SKILL, code="D"),
                derived_from=1,
            ),
        ],
        "watch_signals": ["Si la asistencia sigue bajo 70%, revisar carga escolar."],
        "coach_question": "¿Hubo algo distinto en las tres semanas previas?",
        "data_gaps": ["Sin registro antropométrico reciente."],
        "principles_cited": ["3. Progresión técnica en MTB/XCO"],
    }
    payload.update(overrides)
    return InsightV3(**payload)


# ---------------------------------------------------------------------------
# Contrato del modelo
# ---------------------------------------------------------------------------


def test_schema_version_is_fixed_to_v3():
    assert make_insight().schema_version == "v3"


@pytest.mark.parametrize("count", [1, 5])
def test_observations_cardinality_is_enforced(count):
    """data-model: 2..4 observaciones. Fuera de rango → ValidationError."""
    obs = Observation(
        claim="Afirmación de prueba.",
        evidence=["gap 9.4%"],
        domain=EvidenceDomain.RACE,
        confidence="low",
    )
    with pytest.raises(ValidationError):
        make_insight(observations=[obs] * count)


@pytest.mark.parametrize("count", [1, 4])
def test_actions_cardinality_is_enforced(count):
    """data-model: 2..3 acciones."""
    action = ActionV3(
        text="Acción de prueba semanal.",
        category=ActionCategory.RECOVERY,
        priority=Priority.LOW,
        horizon=Horizon.SEASON,
    )
    with pytest.raises(ValidationError):
        make_insight(actions=[action] * count)


def test_observation_requires_at_least_one_evidence():
    with pytest.raises(ValidationError):
        Observation(
            claim="Sin respaldo numérico.",
            evidence=[],
            domain=EvidenceDomain.RACE,
            confidence="low",
        )


def test_headline_over_200_chars_is_rejected():
    with pytest.raises(ValidationError):
        make_insight(headline="x" * 201)


def test_tactics_is_a_valid_v3_category():
    """``tactics`` no existe en el enum legacy pero sí en v3 (data-model)."""
    action = ActionV3(
        text="Practicar el posicionamiento en la primera vuelta.",
        category=ActionCategory.TACTICS,
        priority=Priority.MED,
        horizon=Horizon.NEXT_RACE,
    )
    assert action.category.value == "tactics"


def test_unknown_field_is_rejected():
    """``extra=forbid``: un campo inventado por el modelo no se persiste."""
    with pytest.raises(ValidationError):
        InsightV3.model_validate(
            {**make_insight().model_dump(), "confianza_global": "alta"}
        )


# ---------------------------------------------------------------------------
# Rendering (plan.md §Rendering)
# ---------------------------------------------------------------------------


def test_render_emits_the_expected_sections_in_order():
    md = render_insight_v3_markdown(make_insight(), "la deportista")
    headings = [line for line in md.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Hallazgo principal",
        "## Lectura del pelotón",
        "## Observaciones",
        "## Acciones",
        "## Señales a vigilar",
        "## Pregunta para el coach",
        "## Vacíos de datos",
    ]


def test_render_uses_athlete_ref_in_field_reading():
    md = render_insight_v3_markdown(make_insight(), "el deportista")
    assert "el deportista terminó en P7 frente a P5 esperada (-2 lugares)" in md
    assert "la deportista" not in md


def test_render_omits_empty_sections():
    """Sin field_reading, sin señales y sin vacíos no hay heading huérfano."""
    md = render_insight_v3_markdown(
        make_insight(field_reading=None, watch_signals=[], data_gaps=[])
    )
    assert "## Lectura del pelotón" not in md
    assert "## Señales a vigilar" not in md
    assert "## Vacíos de datos" not in md
    assert "## Hallazgo principal" in md


def test_render_action_bullet_is_parseable_by_the_legacy_regex():
    """El bullet renderizado sigue casando con ``_REC_BULLET_RE`` (T101)."""
    from app.services.race.agents.analyst import _parse_recommendations

    sections = insight_v3_sections(make_insight())
    recs = _parse_recommendations(sections["actions"])
    assert [r.category.value for r in recs] == ["volume", "technique"]
    assert [r.priority.value for r in recs] == ["high", "med"]


def test_render_includes_catalog_ref_in_the_action_bullet():
    md = render_insight_v3_markdown(make_insight())
    assert "catálogo=technique_skill:D" in md


def test_render_joins_multiple_evidence_items():
    md = render_insight_v3_markdown(make_insight())
    assert "evidencia: asistencia 62.5% en la ventana; RPE medio 4.1" in md


# ---------------------------------------------------------------------------
# Compat con el schema legacy
# ---------------------------------------------------------------------------


def test_legacy_recommendations_keep_text_category_priority():
    recs = insight_v3_to_legacy_recommendations(make_insight())
    assert len(recs) == 2
    assert recs[0].category.value == "volume"
    assert recs[1].priority.value == "med"


def test_legacy_recommendations_downgrade_tactics_to_technique():
    """``tactics`` no existe en RecommendationCategory: se degrada, no se pierde."""
    insight = make_insight(
        actions=[
            ActionV3(
                text="Practicar el posicionamiento en la primera vuelta.",
                category=ActionCategory.TACTICS,
                priority=Priority.MED,
                horizon=Horizon.NEXT_RACE,
            ),
            ActionV3(
                text="Sostener dos días de descanso.",
                category=ActionCategory.RECOVERY,
                priority=Priority.LOW,
                horizon=Horizon.NEXT_WEEK,
            ),
        ]
    )
    recs = insight_v3_to_legacy_recommendations(insight)
    assert len(recs) == 2
    assert recs[0].category.value == "technique"


# ---------------------------------------------------------------------------
# Grounding numérico
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8,6", "8.6"),
        ("8.60", "8.6"),
        ("12.0", "12"),
        ("02:49", "2:49"),
        ("0:35:30", "0:35:30"),
        ("-2", "-2"),
    ],
)
def test_normalize_numeric_token(raw, expected):
    assert normalize_numeric_token(raw) == expected


def test_extract_numeric_tokens_keeps_times_whole():
    """Un tiempo no debe partirse en 0/35/30 o el grounding pierde el token."""
    tokens = extract_numeric_tokens("Tiempo 0:35:30 con gap 2:49.")
    assert "0:35:30" in tokens
    assert "2:49" in tokens


def test_extract_numeric_tokens_is_format_tolerant():
    prompt_tokens = extract_numeric_tokens("- Asistencia: 62.5%\n- RPE medio: 4.10")
    draft_tokens = extract_numeric_tokens("asistencia 62,5 % y RPE 4.1")
    assert draft_tokens <= prompt_tokens


def test_extract_numeric_tokens_on_empty_text():
    assert extract_numeric_tokens("") == set()
