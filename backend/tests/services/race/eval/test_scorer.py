"""Tests del :mod:`app.services.race.eval.scorer` — rule-based + composite.

Sin red, todos determinísticos. Cubren cada sub-rúbrica del scorer:

- themes presentes / faltantes
- forbidden term detectado / ausente
- word_count dentro / fuera de rango
- 5 secciones canónicas presentes / faltantes
- citations: must_cite True con 0 / 1+ cites; must_cite False
- composite_score: ponderación correcta + clamp [0, 1]
- edge cases: markdown vacío, case incompleto
"""
from __future__ import annotations

import pytest

from app.services.race.eval.scorer import (
    RULE_WEIGHTS,
    composite_score,
    rule_based_score,
)
from app.services.race.schemas import AnalysisOutput


def _make_output(markdown: str, citations: list[str] | None = None) -> AnalysisOutput:
    """Constructor mínimo para no acoplar tests a campos opcionales."""
    return AnalysisOutput(
        pseudonym="Atleta-X-Y-Z-001",
        sections={},  # no usado por el scorer (mira raw_markdown).
        citations_used=citations or [],
        recommendations=[],
        risk_flags=[],
        raw_markdown=markdown or "(vacío)",
        word_count=len([w for w in markdown.split() if w]) if markdown else 0,
    )


_FULL_MARKDOWN = (
    "## Evolución\n\nAtleta-X progresa.\n\n"
    "## Análisis Técnico\n\nCadencia 80 rpm.\n\n"
    "## Recomendaciones LTAD\n\n- Reco 1\n- Reco 2\n\n"
    "## Riesgos\n\n- Riesgo bajo\n\n"
    "## Próximos Pasos\n\nReevaluar.\n" + "palabra " * 60
)


def test_full_score_when_all_rubrics_pass() -> None:
    """Markdown completo + themes + sin forbidden + cites + 5 secciones → 1.0."""
    out = _make_output(_FULL_MARKDOWN, citations=["chunk_01"])
    case = {
        "expected_themes": ["progresa", "cadencia"],
        "forbidden_terms": ["suplementos"],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0, abs=1e-3)


def test_missing_theme_penalizes_themes_subscore() -> None:
    """Si falta un theme → resta exactamente RULE_WEIGHTS['themes'] (0.25)."""
    out = _make_output(_FULL_MARKDOWN, citations=["chunk_01"])
    case = {
        "expected_themes": ["progresa", "cadencia", "termino_inexistente_xyz"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0 - RULE_WEIGHTS["themes"], abs=1e-3)


def test_forbidden_term_detected_penalizes_forbidden_subscore() -> None:
    """Forbidden encontrado → resta 0.25 exacto."""
    md = _FULL_MARKDOWN + "\nSe recomienda suplementos de creatina."
    out = _make_output(md, citations=["chunk_01"])
    case = {
        "expected_themes": ["progresa"],
        "forbidden_terms": ["suplementos"],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    expected = 1.0 - RULE_WEIGHTS["forbidden"]
    assert score == pytest.approx(expected, abs=1e-3)


def test_word_count_too_short_fails_subscore() -> None:
    """word_count < 50 → penaliza 0.20."""
    out = _make_output(_FULL_MARKDOWN)  # raw markdown completo, pero word_count bajo
    # Forzamos word_count bajo manualmente sin tocar el markdown — el scorer
    # mira el campo del schema, no recalcula.
    out = AnalysisOutput(
        pseudonym=out.pseudonym,
        sections=out.sections,
        citations_used=["chunk_01"],
        recommendations=[],
        risk_flags=[],
        raw_markdown=_FULL_MARKDOWN,
        word_count=30,
    )
    case = {
        "expected_themes": ["progresa"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0 - RULE_WEIGHTS["word_count"], abs=1e-3)


def test_word_count_above_max_fails_subscore() -> None:
    """word_count > max_words → penaliza 0.20."""
    out = AnalysisOutput(
        pseudonym="X",
        sections={},
        citations_used=["chunk_01"],
        recommendations=[],
        risk_flags=[],
        raw_markdown=_FULL_MARKDOWN,
        word_count=2000,  # excede max_words=600
    )
    case = {
        "expected_themes": ["progresa"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0 - RULE_WEIGHTS["word_count"], abs=1e-3)


def test_missing_sections_fails_subscore() -> None:
    """Markdown sin las 5 secciones canónicas → penaliza 0.15."""
    md = "Texto plano sin headings, " + "palabra " * 60
    out = _make_output(md, citations=["chunk_01"])
    case = {
        "expected_themes": [],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    # Pierde sections (0.15). Themes vacíos → pass; forbidden vacío → pass;
    # word_count ≥50 + ≤600 → pass; citations 1 con must_cite → pass.
    assert score == pytest.approx(1.0 - RULE_WEIGHTS["sections"], abs=1e-3)


def test_zero_citations_with_must_cite_true_fails_subscore() -> None:
    """must_cite=True con 0 cites → penaliza 0.15."""
    out = _make_output(_FULL_MARKDOWN, citations=[])
    case = {
        "expected_themes": ["progresa"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0 - RULE_WEIGHTS["citations"], abs=1e-3)


def test_zero_citations_with_must_cite_false_does_not_penalize() -> None:
    """must_cite=False → siempre 1.0 en sub-score citations."""
    out = _make_output(_FULL_MARKDOWN, citations=[])
    case = {
        "expected_themes": ["progresa"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": False,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0, abs=1e-3)


def test_empty_markdown_yields_low_score() -> None:
    """Markdown efectivamente vacío → pierde varios sub-scores.

    AnalysisOutput requiere ``raw_markdown`` con min_length=1, así que
    usamos ``" "`` (un espacio en blanco).
    """
    out = AnalysisOutput(
        pseudonym="X",
        sections={},
        citations_used=[],
        recommendations=[],
        risk_flags=[],
        raw_markdown=" ",
        word_count=0,
    )
    case = {
        "expected_themes": ["termino_unico_xyz"],  # ausente → falla themes
        "forbidden_terms": ["palabra_prohibida_xyz"],  # ausente → pasa forbidden
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    # themes 0 + forbidden 0.25 + word_count 0 + sections 0 + citations 0 = 0.25
    assert score == pytest.approx(RULE_WEIGHTS["forbidden"], abs=1e-3)


def test_case_incomplete_uses_safe_defaults() -> None:
    """Caso sin claves esperadas → defaults permisivos, no crash."""
    out = _make_output(_FULL_MARKDOWN, citations=["chunk_01"])
    case: dict = {}  # ninguna clave; defensa por defaults
    score = rule_based_score(out, case)
    # themes vacío → pass (0.25), forbidden vacío → pass (0.25), word_count ok (0.20),
    # sections completas (0.15), must_cite=False default → pass (0.15) = 1.0
    assert score == pytest.approx(1.0, abs=1e-3)


def test_case_insensitive_theme_matching() -> None:
    """Theme con mayúsculas debe matchear contenido en minúsculas."""
    md = _FULL_MARKDOWN + "\nLa evolución del atleta es positiva."
    out = _make_output(md, citations=["chunk_01"])
    case = {
        "expected_themes": ["EVOLUCIÓN", "Atleta"],
        "forbidden_terms": [],
        "max_words": 600,
        "must_cite": True,
    }
    score = rule_based_score(out, case)
    assert score == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# composite_score
# ---------------------------------------------------------------------------


def test_composite_weighted_average() -> None:
    """composite = 0.4 * rule + 0.6 * judge — fórmula exacta."""
    assert composite_score(1.0, 0.0) == pytest.approx(0.4)
    assert composite_score(0.0, 1.0) == pytest.approx(0.6)
    assert composite_score(0.5, 0.5) == pytest.approx(0.5)
    assert composite_score(1.0, 1.0) == pytest.approx(1.0)


def test_composite_clamps_inputs_out_of_range() -> None:
    """Inputs fuera de [0, 1] se clampean defensivamente."""
    assert composite_score(2.0, -1.0) == pytest.approx(0.4)  # rule=1, judge=0
    assert composite_score(-0.5, 1.5) == pytest.approx(0.6)  # rule=0, judge=1
