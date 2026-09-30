"""Feature 048 (T051): the field guide PDF gains «Antes de medir» and the four
basic measures before the skinfold sections; still athlete-independent."""

from __future__ import annotations

import re

from jinja2 import Environment, FileSystemLoader

from app.routers.body_composition import (
    _build_field_guide_basic_measures,
    _build_field_guide_precheck,
    _build_field_guide_sites,
)
from app.services.notification.document_generator import _TEMPLATES_ROOT

_LABELS = ("Peso", "Talla de pie", "Talla sentado", "Envergadura")


def _render() -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_ROOT)), autoescape=True)
    return env.get_template("documents/pdf/skinfold_field_guide.html").render(
        sites=_build_field_guide_sites(),
        precheck=_build_field_guide_precheck(),
        basic_measures=_build_field_guide_basic_measures(),
        generated_at="2026-09-29",
    )


def test_context_has_four_measures_with_existing_png():
    measures = _build_field_guide_basic_measures()
    assert [m["label"] for m in measures] == list(_LABELS)
    for m in measures:
        assert m["illustration"] == f"documents/pdf/diagrams/img/anthro_{m['key']}.png"
        assert (_TEMPLATES_ROOT / m["illustration"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_rendered_html_has_precheck_and_measures_before_first_skinfold():
    html = _render()
    assert "Antes de medir" in html
    first_skinfold = html.index("Tríceps")
    assert html.index("Antes de medir") < first_skinfold
    for label in _LABELS:
        assert html.index(label) < first_skinfold
    for key in ("weight", "standing_height", "sitting_height", "arm_span"):
        pos = html.index(f"anthro_{key}.png")
        assert pos < first_skinfold
    for item in _build_field_guide_precheck():
        assert item in html


def test_rendered_html_has_no_athlete_fields():
    html = _render().lower()
    for token in ("athlete", "birth", "nombre del deportista:", "fecha de nacimiento"):
        assert token not in re.sub(r"ningún deportista|de ningún deportista", "", html)
