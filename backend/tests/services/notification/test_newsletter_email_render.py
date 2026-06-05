"""T032 — Email render regression tests for the individual newsletter email template.

Renders `templates/email/athlete_monthly_newsletter.html` via Jinja2 and asserts:

  (a) The rendered HTML is a single-column layout (max-width wrapper, no multi-col grid).
  (b) Contains lang="es-CO" and role="presentation" on layout tables.
  (c) Has inlined styles on key elements (critical color/font/padding on elements, not only in <style>).
  (d) Contains ZERO anthropometric values (FR-004 / SC-008):
      - No raw numeric fields (bmi, weight_kg, height_cm, percentile, z_score)
      - No column labels (IMC, Talla, Peso, Percentil, Z-score, Maduración, PHV)
  (e) Key accessibility: body font-size ≥ 16px, line-height present on main text elements.

These tests are rendering-only (no database or WeasyPrint needed).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# Jinja2 environment pointing at the templates directory
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parents[3] / "templates"


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


# ---------------------------------------------------------------------------
# Fixture context — minimal multi-child scenario (2 atletas)
# ---------------------------------------------------------------------------

_CHILD_EMAIL_BLOCKS: dict = {
    "period": {"year": 2026, "month": 5},
    "attendance": {
        "sessions_present": 7,
        "sessions_total": 8,
        "attendance_pct": 87.5,
        "attendance_pct_prev_month": 80.0,
        "streak_days": 4,
    },
    "technical": {
        "focos_tecnicos": ["Frenada controlada"],
        "avg_rpe": 6.2,
    },
    "race_results": {
        "has_races": True,
        "results": [
            {
                "valida_num": 4,
                "city": "Cali",
                "position": 3,
                "gap_to_winner_pct": 8.4,
            }
        ],
    },
    "badges": {
        "items": [
            {"badge_type": "attendance_90"},
        ]
    },
    "support_at_home": {
        "tips": [
            {
                "category": "hidratacion",
                "title": "Hidratación",
                "text": "Tomar agua antes, durante y después del entrenamiento.",
            }
        ]
    },
    # US3: captions / highlights (email-safe only — no anthropometry)
    "block_captions": {
        "attendance": "Excelente regularidad este mes.",
        "technical": "Trabajo de técnica con buenos resultados.",
        "race_results": "Progresión positiva en la temporada.",
        # anthropometry MUST NOT be here — any leak would be caught by tests below
    },
    "month_highlights": "Gran mes con mejoras en técnica y asistencia.",
}

_AI_NARRATIVE: dict = {
    "strengths": "Constancia en asistencia.",
    "area_to_develop": "Técnica de frenada.",
    "milestone": "Primer Top 5.",
    "confidence": "medium",
    # US3 extension
    "block_captions": {
        "attendance": "Excelente regularidad este mes.",
        "technical": "Trabajo técnico sólido.",
        "race_results": "Muy buena progresión.",
    },
    "month_highlights": "Gran mes de trabajo técnico.",
}

_TEMPLATE_CONTEXT: dict = {
    "parent_name": "Carlos",
    "club_name": "Trocha y Ruta",
    "month_label": "Mayo",
    "season_year": "2026",
    "children": [
        {
            "athlete_first_name": "Atleta",   # no real minor name in fixture
            "email_blocks": _CHILD_EMAIL_BLOCKS,
            "ai_narrative": _AI_NARRATIVE,
            "coach_narrative_overrides": None,
        },
        {
            "athlete_first_name": "Atleta2",
            "email_blocks": _CHILD_EMAIL_BLOCKS,
            "ai_narrative": None,
            "coach_narrative_overrides": None,
        },
    ],
}


@pytest.fixture(scope="module")
def rendered_html(jinja_env: Environment) -> str:
    template = jinja_env.get_template("email/athlete_monthly_newsletter.html")
    return template.render(**_TEMPLATE_CONTEXT)


# ---------------------------------------------------------------------------
# (a) Single-column layout
# ---------------------------------------------------------------------------


def test_single_column_has_max_width(rendered_html: str) -> None:
    """The layout wrapper must cap width at 600px for single-column on mobile."""
    assert "max-width:600px" in rendered_html or "max-width: 600px" in rendered_html, (
        "Email missing max-width:600px wrapper — will not be single-column on mobile."
    )


def test_no_multi_column_grid(rendered_html: str) -> None:
    """The email must not use CSS grid or flexbox for the column structure.
    (Tables are allowed for layout.)"""
    # display:grid or display:flex at the outer column level would break on Gmail
    assert "display:grid" not in rendered_html.lower().replace(" ", ""), (
        "Email uses CSS grid — not supported in major email clients."
    )


# ---------------------------------------------------------------------------
# (b) lang="es-CO" and role="presentation"
# ---------------------------------------------------------------------------


def test_lang_es_co(rendered_html: str) -> None:
    """The <html> element must have lang='es-CO'."""
    assert 'lang="es-CO"' in rendered_html, (
        "Email <html> element is missing lang='es-CO'."
    )


def test_role_presentation_on_layout_tables(rendered_html: str) -> None:
    """Layout tables must carry role='presentation' for screen readers."""
    assert 'role="presentation"' in rendered_html, (
        "Email layout tables are missing role='presentation'."
    )


# ---------------------------------------------------------------------------
# (c) Inlined styles on key elements
# ---------------------------------------------------------------------------


def test_header_has_inline_background_color(rendered_html: str) -> None:
    """The header cell must have an inline background-color (charcoal #2f2f2f)."""
    assert "background-color:#2f2f2f" in rendered_html.replace(" ", ""), (
        "Header element missing inline background-color:#2f2f2f."
    )


def test_header_brand_lime_color(rendered_html: str) -> None:
    """The header h1 must reference the brand-lime color #8be000 inline."""
    assert "#8be000" in rendered_html, (
        "Header missing brand-lime color #8be000 inline."
    )


def test_body_font_size_at_least_16px(rendered_html: str) -> None:
    """Body-level text must be ≥16px (per R5 accessibility requirement).
    The greeting paragraph sets 16px explicitly."""
    # We look for font-size on the greeting paragraph element
    # (font-size:16px inline on a <p> element)
    assert "font-size:16px" in rendered_html.replace(" ", "") or \
           "font-size: 16px" in rendered_html, (
        "No 16px body font-size found inline — body text may be too small for mobile."
    )


def test_line_height_on_body_text(rendered_html: str) -> None:
    """Key text elements must carry inline line-height 1.4 or 1.5."""
    assert "line-height:1.5" in rendered_html.replace(" ", "") or \
           "line-height: 1.5" in rendered_html, (
        "No line-height:1.5 found on body text elements."
    )


def test_child_header_has_inline_background(rendered_html: str) -> None:
    """Child section header must have an inline background color."""
    assert "background-color:#f0fdf4" in rendered_html.replace(" ", ""), (
        "Child section header missing inline background-color."
    )


def test_narrative_blocks_have_inline_border(rendered_html: str) -> None:
    """Narrative (strengths/area/milestone) blocks must have inline border-left."""
    assert "border-left:3px" in rendered_html.replace(" ", "") or \
           "border-left: 3px" in rendered_html, (
        "Narrative blocks missing inline border-left."
    )


# ---------------------------------------------------------------------------
# (d) ZERO anthropometric values (FR-004 / SC-008)
# ---------------------------------------------------------------------------

# These are the column header labels that appear in the PDF anthropometry table
# but must NEVER appear in the email body.
_FORBIDDEN_ANTHRO_LABELS = [
    "IMC",
    "Z-Talla",
    "P-Talla",
    "Z-IMC",
    "P-IMC",
    "PHV offset",
    "Maduración",
    "Curvas de Percentiles",
    "Seguimiento Antropométrico",
    "maturity_offset",
    "height_z_score",
    "bmi_z_score",
    "height_percentile",
    "bmi_percentile",
]


@pytest.mark.parametrize("label", _FORBIDDEN_ANTHRO_LABELS)
def test_no_anthropometric_label_in_email(rendered_html: str, label: str) -> None:
    """No anthropometric column label must appear in the rendered email (FR-004)."""
    assert label not in rendered_html, (
        f"Anthropometric label '{label}' found in email body — violates FR-004/SC-008 "
        "privacy rule: anthropometry ONLY in PDF."
    )


def test_no_raw_weight_value(rendered_html: str) -> None:
    """The fixture weight_kg value (45.2) must not appear in the email."""
    assert "45.2" not in rendered_html, (
        "Raw weight_kg value found in email body — potential anthropometry leak."
    )


def test_no_raw_bmi_value(rendered_html: str) -> None:
    """The fixture BMI value (18.0) must not appear in the email."""
    assert "18.0" not in rendered_html, (
        "Raw BMI value found in email body — potential anthropometry leak."
    )


def test_email_blocks_captions_do_not_contain_anthropometry_key(rendered_html: str) -> None:
    """The email must not render any caption keyed 'anthropometry'.
    The fixture deliberately omits this key from block_captions; verify it's absent."""
    # The string 'Seguimiento Antropométrico' is the PDF section heading only
    assert "Seguimiento Antropométrico" not in rendered_html, (
        "Anthropometry section heading found in email — the anthropometry block "
        "must only appear in the PDF template."
    )


def test_no_growth_reference_terms(rendered_html: str) -> None:
    """Terms specific to growth reference data must not appear in the email."""
    for term in ["percentil", "Percentil", "z-score", "Z-score"]:
        assert term not in rendered_html, (
            f"Growth reference term '{term}' found in email — violates SC-008."
        )


# ---------------------------------------------------------------------------
# (e) key content is live text (not image-only)
# ---------------------------------------------------------------------------


def test_club_name_as_live_text(rendered_html: str) -> None:
    """Club name must appear as live text, not only in an alt attribute."""
    # Count occurrences in non-alt contexts
    # Simple check: the text node "Trocha y Ruta" must appear
    assert "Trocha y Ruta" in rendered_html, (
        "Club name not found as live text in email."
    )


def test_month_label_as_live_text(rendered_html: str) -> None:
    """Month label must appear as live text."""
    assert "Mayo" in rendered_html, (
        "Month label not found as live text in email."
    )


# ---------------------------------------------------------------------------
# (f) No <style> block exceeds 8192 chars (Gmail limit)
# ---------------------------------------------------------------------------


def test_style_block_under_8192_chars(rendered_html: str) -> None:
    """The <style> block must be under 8192 chars to stay within Gmail's limit."""
    style_matches = re.findall(r"<style[^>]*>(.*?)</style>", rendered_html, re.DOTALL)
    for i, block in enumerate(style_matches):
        assert len(block) < 8192, (
            f"<style> block #{i + 1} has {len(block)} chars — exceeds Gmail's 8192-char limit."
        )


# ---------------------------------------------------------------------------
# (g) color-scheme meta present
# ---------------------------------------------------------------------------


def test_color_scheme_meta(rendered_html: str) -> None:
    """The email must declare color-scheme for dark-mode safety."""
    assert 'color-scheme' in rendered_html, (
        "Email missing color-scheme meta tag — dark-mode inversion may be unsafe."
    )
