"""Feature 046 (T065): analyst/critic v2 prompts and their wiring.

Covers `contracts/ai-body-composition-leaf.md` §2: the v2 analyst prompt adds
an optional "Composición corporal" section only when the qualitative leaf
exists (family = reassurance-first, no numbers, no diet talk; coach = pattern
+ suggested conversation), the v2 critic prompt lists R13/R14, the default
`AI_ANTHRO_PROMPT_VERSION` is v2 with v1 still valid, and the critic version
follows the analyst version so a rollback drags both. Synthetic fixtures only.
"""

from __future__ import annotations

import re

import pytest

from app.config import Settings
from app.services.ai.anthro import critic as anthro_critic
from app.services.ai.anthro.context import _render_body_composition_block
from app.services.ai.anthro.prompts.loader import render_prompt

_LEAF_ROJO = {
    "sets_count": 3,
    "weeks_since_prev_set": 14,
    "sum_change_code": "down_real",
    "growth_explanation_code": "none",
    "ffm_trend_code": "flat",
    "band": "rojo",
    "band_reason_code": "energy_availability_pattern",
    "family_band": "ambar",
    "reference_context_code": "low",
    "sites_declined_count": 1,
}


def _analyst_vars(audience: str, body_composition_block: str | None) -> dict:
    return {
        "audience": audience,
        "age_group": "13-15",
        "age_decimal": 13.4,
        "sex": "F",
        "category": "Infantil B femenino",
        "measurement_deltas_block": "Cambio de talla: +2.0 cm (significativo).",
        "longitudinal_series_block": None,
        "growth_summary_block": "Fase de maduración: Circa-PHV.",
        "training_load_block": None,
        "previous_analysis_block": None,
        "body_composition_block": body_composition_block,
    }


_NUMERIC_BODY_COMP = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm)\b")


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_v2_without_leaf_has_no_body_composition_section(audience: str) -> None:
    text = render_prompt("anthropometry_analyst_v2", _analyst_vars(audience, None))
    assert "## Composición corporal" not in text
    assert "Integra la composición corporal" not in text


def test_v2_family_section_is_reassurance_first_and_never_coach_band() -> None:
    block = _render_body_composition_block(_LEAF_ROJO, "family")
    text = render_prompt("anthropometry_analyst_v2", _analyst_vars("family", block))
    assert "## Composición corporal (pliegues cutáneos)" in text
    assert "tranquilizar" in text
    assert "En observación" in text
    # Coach-only content never reaches the family prompt.
    assert "rojo" not in text.lower()
    assert "Banda del entrenador" not in text
    assert "disponibilidad energética" not in text
    assert "considerar remitir" not in text
    # No body-composition number is ever rendered.
    assert not _NUMERIC_BODY_COMP.search(text)


def test_v2_coach_section_names_pattern_and_conversation() -> None:
    block = _render_body_composition_block(_LEAF_ROJO, "coach")
    text = render_prompt("anthropometry_analyst_v2", _analyst_vars("coach", block))
    assert "Banda del entrenador: rojo" in text
    assert "conversación" in text
    assert "profesional de salud" in text
    assert "prefirió no medir" in text
    assert not _NUMERIC_BODY_COMP.search(text)


@pytest.mark.parametrize("audience", ["family", "coach"])
def test_v2_forbids_diet_and_weight_goals_for_both_audiences(audience: str) -> None:
    text = render_prompt("anthropometry_analyst_v2", _analyst_vars(audience, None))
    assert "sin metas de peso, sin dieta" in text
    for term in ("dieta", "bajar de peso", "adelgazar", "déficit calórico", "restricción"):
        assert term in text


def test_v1_still_renders_with_the_same_vars() -> None:
    """Rollback path: v1 ignores the extra `body_composition_block` var."""
    block = _render_body_composition_block(_LEAF_ROJO, "family")
    text = render_prompt("anthropometry_analyst_v1", _analyst_vars("family", block))
    assert "Composición corporal" not in text


def test_critic_v2_lists_r13_and_r14() -> None:
    text = render_prompt(
        "anthropometry_critic_v2",
        {"draft_json": "{}", "ground_truth": "x", "precheck_summary": "ninguno"},
    )
    assert "R13 `body_comp_numeric_leak_to_family`" in text
    assert "R14 `diet_or_weight_loss_language`" in text
    assert "R01-R14" in text


def test_default_prompt_version_is_v2_and_v1_is_allowed() -> None:
    assert Settings(_env_file=None).ai_anthro_prompt_version == "anthropometry_analyst_v2"
    assert (
        Settings(_env_file=None, ai_anthro_prompt_version="v1").ai_anthro_prompt_version
        == "anthropometry_analyst_v1"
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"analyst_prompt_version": "anthropometry_analyst_v1"}, "anthropometry_critic_v1"),
        ({"analyst_prompt_version": "anthropometry_analyst_v2"}, "anthropometry_critic_v2"),
        ({}, "anthropometry_critic_v2"),
        (
            {
                "analyst_prompt_version": "anthropometry_analyst_v2",
                "critic_prompt_version": "anthropometry_critic_v1",
            },
            "anthropometry_critic_v1",
        ),
    ],
)
def test_critic_version_follows_analyst_version(state: dict, expected: str) -> None:
    assert anthro_critic._resolve_critic_prompt_version(state) == expected


def test_critic_ground_truth_includes_body_composition_block_when_present() -> None:
    block = _render_body_composition_block(_LEAF_ROJO, "coach")
    with_leaf = anthro_critic._render_ground_truth(
        {"growth_summary_block": "g", "body_composition_block": block}
    )
    without_leaf = anthro_critic._render_ground_truth({"growth_summary_block": "g"})
    assert "## Composición corporal" in with_leaf
    assert "Composición corporal" not in without_leaf
