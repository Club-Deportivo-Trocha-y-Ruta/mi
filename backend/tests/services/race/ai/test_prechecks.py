"""Tests de :mod:`app.services.race.ai.prechecks` (feature 037, T202).

No importamos ``app.services.race.insight_v3`` (lo construye otro agente en
paralelo, T201) — usamos un stand-in Pydantic mínimo equivalente al
``InsightV3`` de data-model.md, suficiente para ejercer los prechecks que
solo acceden a los campos por atributo (duck typing documentado en
``prechecks.py``).
"""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel

from app.services.race.ai.prechecks import (
    PrecheckCategory,
    extract_numeric_tokens,
    run_prechecks,
)


class _CatalogRef(BaseModel):
    kind: str
    code: str
    label: Optional[str] = None


class _Action(BaseModel):
    text: str
    catalog_ref: Optional[_CatalogRef] = None


class _Observation(BaseModel):
    claim: str
    evidence: list[str] = []


class _FieldReading(BaseModel):
    summary: str = ""


class _Draft(BaseModel):
    headline: str
    observations: list[_Observation] = []
    actions: list[_Action] = []
    watch_signals: list[str] = []
    coach_question: str = "¿Cómo te sentiste hoy?"
    field_reading: Optional[_FieldReading] = None


def _draft(**kwargs) -> _Draft:
    base = dict(
        headline="Terminó 5ta con un gap de 12.3% al líder",
        observations=[
            _Observation(claim="Bajó su tiempo en 8.6% respecto a la válida anterior", evidence=["8.6%"])
        ],
        actions=[_Action(text="Trabajar cadencia en llano 2x/semana, 15 min")],
        coach_question="¿Cómo te sentiste en el último tramo?",
    )
    base.update(kwargs)
    return _Draft(**base)


# ---------------------------------------------------------------------------
# extract_numeric_tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("subió 8.6% en la última válida", {"8.6"}),
        ("bajó 8,6 % respecto a marzo", {"8.6"}),
        ("tiempo total 0:35:30", {"0:35:30"}),
        ("gap de 2:49 al líder", {"2:49"}),
        ("marca de 35:30 en la subida", {"35:30"}),
        ("terminó en la posición 5", {"5"}),
    ],
)
def test_extract_numeric_tokens_tolerant_formats(text, expected):
    assert extract_numeric_tokens(text) == expected


def test_extract_numeric_tokens_empty_text():
    assert extract_numeric_tokens("") == set()
    assert extract_numeric_tokens(None) == set()


# ---------------------------------------------------------------------------
# run_prechecks — draft None
# ---------------------------------------------------------------------------


def test_run_prechecks_none_draft_forces_block():
    result = run_prechecks(None)
    assert result.must_block is True
    assert result.sanitized_draft is None
    assert result.issues[0].category == PrecheckCategory.PRIVACY


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def test_grounding_violation_flags_number_not_in_ground_truth():
    draft = _draft(
        headline="Bajó su tiempo en 99.9% respecto a la anterior",
        observations=[_Observation(claim="Mejoró notablemente", evidence=["99.9%"])],
    )
    result = run_prechecks(draft, grounding_numbers=["8.6", "5"])
    grounding_issues = [i for i in result.issues if i.category == PrecheckCategory.GROUNDING]
    assert len(grounding_issues) == 1
    assert result.must_block is False


def test_grounding_ok_when_all_numbers_present_in_ground_truth():
    draft = _draft(
        headline="Terminó 5ta con gap de 8.6%",
        observations=[_Observation(claim="Consistente con 8.6% de la vez pasada", evidence=["8.6%"])],
    )
    result = run_prechecks(draft, grounding_numbers=["8.6", "5"])
    assert not any(i.category == PrecheckCategory.GROUNDING for i in result.issues)


def test_grounding_skipped_when_no_ground_truth_numbers_provided():
    """Sin ``grounding_numbers`` no podemos afirmar nada — no se reporta issue."""
    draft = _draft(headline="Terminó con un gap de 12%")
    result = run_prechecks(draft, grounding_numbers=[])
    assert not any(i.category == PrecheckCategory.GROUNDING for i in result.issues)


# ---------------------------------------------------------------------------
# Forbidden names (privacy)
# ---------------------------------------------------------------------------


def test_forbidden_name_triggers_privacy_must_block():
    draft = _draft(headline="Juan Pérez Ficticio terminó 5to")
    result = run_prechecks(draft, forbidden_names=["Juan Pérez Ficticio"])
    assert result.must_block is True
    assert any(i.category == PrecheckCategory.PRIVACY for i in result.issues)


def test_no_forbidden_name_present_is_clean():
    draft = _draft()
    result = run_prechecks(draft, forbidden_names=["Otro Nombre Ficticio"])
    assert not any(i.category == PrecheckCategory.PRIVACY for i in result.issues)


# ---------------------------------------------------------------------------
# LTAD rules
# ---------------------------------------------------------------------------


def test_ltad_cadence_below_60_blocks():
    draft = _draft(
        actions=[_Action(text="Trabajar cadencia sostenida de 45 rpm en llano")]
    )
    result = run_prechecks(draft)
    assert result.must_block is True
    assert any(i.category == PrecheckCategory.LTAD for i in result.issues)


def test_ltad_cadence_60_or_above_is_clean():
    draft = _draft(actions=[_Action(text="Trabajar cadencia sostenida de 85 rpm en llano")])
    result = run_prechecks(draft)
    assert not any(i.category == PrecheckCategory.LTAD for i in result.issues)


def test_ltad_supplements_blocks():
    draft = _draft(actions=[_Action(text="Agregar suplementos proteicos a la dieta")])
    result = run_prechecks(draft)
    assert result.must_block is True


def test_ltad_hours_over_age_blocks():
    draft = _draft(actions=[_Action(text="Entrenar 14 horas por semana")])
    result = run_prechecks(draft, athlete_age=12)
    assert result.must_block is True


def test_ltad_hours_under_age_is_clean():
    draft = _draft(actions=[_Action(text="Entrenar 6 horas por semana")])
    result = run_prechecks(draft, athlete_age=12)
    assert not any(i.category == PrecheckCategory.LTAD for i in result.issues)


def test_ltad_more_than_5_days_blocks():
    draft = _draft(actions=[_Action(text="Entrenar 6 días por semana")])
    result = run_prechecks(draft)
    assert result.must_block is True


def test_ltad_fcmax_test_under_13_blocks():
    draft = _draft(actions=[_Action(text="Hacer un test de FC máxima este mes")])
    result = run_prechecks(draft, athlete_age=11)
    assert result.must_block is True


def test_ltad_fcmax_test_over_13_is_not_flagged_by_this_rule():
    draft = _draft(actions=[_Action(text="Hacer un test de FC máxima este mes")])
    result = run_prechecks(draft, athlete_age=14)
    assert not any(i.category == PrecheckCategory.LTAD for i in result.issues)


def test_ltad_diagnosis_language_blocks():
    draft = _draft(observations=[_Observation(claim="El atleta padece anemia leve", evidence=["1"])])
    result = run_prechecks(draft)
    assert result.must_block is True
    assert any(i.category == PrecheckCategory.PRIVACY for i in result.issues)


def test_ltad_outcome_goal_blocks():
    draft = _draft(headline="La meta es ganar el podio en la próxima válida")
    result = run_prechecks(draft)
    assert result.must_block is True


# ---------------------------------------------------------------------------
# catalog_ref
# ---------------------------------------------------------------------------


def test_catalog_ref_missing_code_is_stripped_and_flagged():
    draft = _draft(
        actions=[
            _Action(
                text="Practicar la habilidad técnica en el próximo entreno",
                catalog_ref=_CatalogRef(kind="technique_skill", code="Z"),
            )
        ]
    )
    catalog_context = {"technique_skills": [{"code": "A"}, {"code": "B"}]}
    result = run_prechecks(draft, catalog_context=catalog_context)
    assert any(i.category == PrecheckCategory.CATALOG for i in result.issues)
    assert result.must_block is False
    assert result.sanitized_draft.actions[0].catalog_ref is None


def test_catalog_ref_valid_code_is_kept():
    draft = _draft(
        actions=[
            _Action(
                text="Practicar la habilidad técnica en el próximo entreno",
                catalog_ref=_CatalogRef(kind="technique_skill", code="A"),
            )
        ]
    )
    catalog_context = {"technique_skills": [{"code": "A"}, {"code": "B"}]}
    result = run_prechecks(draft, catalog_context=catalog_context)
    assert not any(i.category == PrecheckCategory.CATALOG for i in result.issues)
    assert result.sanitized_draft.actions[0].catalog_ref.code == "A"


def test_catalog_ref_no_catalog_context_is_not_flagged():
    """Sin catálogo cargado no podemos validar — no se penaliza."""
    draft = _draft(
        actions=[
            _Action(
                text="Practicar",
                catalog_ref=_CatalogRef(kind="technique_skill", code="Z"),
            )
        ]
    )
    result = run_prechecks(draft, catalog_context=None)
    assert not any(i.category == PrecheckCategory.CATALOG for i in result.issues)


# ---------------------------------------------------------------------------
# coach_question
# ---------------------------------------------------------------------------


def test_coach_question_without_question_mark_flagged():
    draft = _draft(coach_question="Cómo te sentiste hoy")
    result = run_prechecks(draft)
    assert any(i.category == PrecheckCategory.STYLE for i in result.issues)
    assert result.must_block is False


def test_coach_question_empty_flagged():
    draft = _draft(coach_question="")
    result = run_prechecks(draft)
    assert any(i.category == PrecheckCategory.STYLE for i in result.issues)


def test_coach_question_valid_is_clean():
    draft = _draft(coach_question="¿Qué sentiste distinto en la última subida?")
    result = run_prechecks(draft)
    assert not any(i.category == PrecheckCategory.STYLE for i in result.issues)


# ---------------------------------------------------------------------------
# Solapamiento (Jaccard) con headlines previos
# ---------------------------------------------------------------------------


def test_headline_overlap_with_previous_flagged():
    draft = _draft(headline="Terminó quinta con mejora notable en la subida técnica")
    previous = ["Terminó quinta con mejora notable en la subida técnica"]
    result = run_prechecks(draft, previous_headlines=previous)
    assert any(i.category == PrecheckCategory.STYLE for i in result.issues)


def test_headline_no_overlap_with_previous_is_clean():
    draft = _draft(headline="Mejoró su posición relativa en el pelotón principal")
    previous = ["Bajó su cadencia en la última recta de meta"]
    result = run_prechecks(draft, previous_headlines=previous)
    assert not any(
        i.category == PrecheckCategory.STYLE and "headline" in i.issue.section
        for i in result.issues
    )
