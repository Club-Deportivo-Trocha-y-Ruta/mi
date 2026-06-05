"""T019 — Layout / pagination regression tests for the individual newsletter PDF.

These tests render the newsletter template with WeasyPrint and use pdfplumber
to inspect the resulting PDF bytes.  They assert:

  (a) The "Evolución en la temporada" heading and chart content appear on the
      same page (no orphaned heading).
  (b) The rendered PDF does NOT contain the Ley 1581 boxed notice text that
      was removed in T018.
  (c) Page count is within an expected upper bound and no non-last page is
      clearly near-empty (< 10 % of body text vs. the median non-last page).
  (d) The @bottom-right running page counter ("Página X de Y") appears on
      every page.

Rendering is synchronous (DocumentGenerator._generate_pdf) — no async needed.
pdfplumber is used for per-page text extraction.
"""

from __future__ import annotations

import io

import pdfplumber
import pytest

from app.schemas.notification import DocumentFormat, DocumentRequest, DocumentTemplate
from app.services.notification.document_generator import DocumentGenerator
from app.services.notification.template_registry import TemplateRegistry

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

ATHLETE_FIRST = "Carlos"
ATHLETE_LAST = "G"

_EMAIL_BLOCKS: dict = {
    "period": {"year": 2026, "month": 5},
    "attendance": {
        "sessions_present": 7,
        "sessions_total": 8,
        "attendance_pct": 87.5,
        "attendance_pct_prev_month": 80.0,
        "streak_days": 4,
    },
    "technical": {
        "focos_tecnicos": ["Frenada controlada", "Curvas largas"],
        "avg_rpe": 6.2,
        "avg_rubric_effort": 3.8,
        "avg_rubric_attitude": 4.1,
        "avg_rubric_technique": 3.5,
        "total_training_hours": 14,
    },
    "race_results": {
        "has_races": True,
        "results": [
            {
                "valida_num": 4,
                "city": "Cali",
                "position": 3,
                "category_code": "M13",
                "race_time_ms": 3_720_000,
                "gap_to_winner_pct": 8.4,
                "points_awarded": 40,
            }
        ],
    },
    "calendar": {
        "next_training_sessions": [],
        "next_race_events": [
            {
                "valida": "V — CD",
                "date": "2026-06-12",
                "location": "Ginebra",
                "priority": "A",
            }
        ],
    },
    "photos": {"count": 0, "items": []},
    "badges": {
        "items": [
            {"badge_type": "attendance_90"},
            {"badge_type": "top10"},
        ]
    },
    "support_at_home": {
        "tips": [
            {
                "category": "hidratacion",
                "title": "Hidratación",
                "text": "Recordar tomar agua antes, durante y después del entrenamiento.",
            },
            {
                "category": "sueno",
                "title": "Sueño",
                "text": "Respetar al menos 8–9 horas de sueño en noches previas al entrenamiento.",
            },
        ]
    },
}

_CHARTS_CTX: dict = {
    "has_data": True,
    "low_confidence": False,
    # SVG macros expect {x: valida_num (int), y: value|null}
    "positions": [
        {"x": 1, "y": 5},
        {"x": 2, "y": 4},
        {"x": 3, "y": 3},
        {"x": 4, "y": 3},
    ],
    "gap_pcts": [
        {"x": 1, "y": 15.2},
        {"x": 2, "y": 12.1},
        {"x": 3, "y": 9.8},
        {"x": 4, "y": 8.4},
    ],
    "points_accumulated": [
        {"x": 1, "y": 20},
        {"x": 2, "y": 45},
        {"x": 3, "y": 70},
        {"x": 4, "y": 110},
    ],
}

_ANTHRO_RECORD = {
    "evaluation_date": "2026-05-10",
    "weight_kg": 45.2,
    "standing_height_cm": 158.5,
    "bmi": 18.0,
    "height_z_score": -0.12,
    "height_percentile": 45.2,
    "bmi_z_score": 0.05,
    "bmi_percentile": 52.0,
    "maturity_offset": -0.82,
    "maturation_status": "Pre-PHV",
    "age_at_phv": None,
    "maturation_pedagogy": (
        "En fase pre-PHV: priorizar coordinación y habilidades técnicas "
        "antes del pico de crecimiento."
    ),
    "training_implications": (
        "Evitar cargas de fuerza máxima. "
        "Enfatizar trabajo técnico y aeróbico extenso."
    ),
    "unavailable_reasons": {},
}

_PDF_ONLY_BLOCKS: dict = {
    "anthropometry": {
        "has_records": True,
        "records": [_ANTHRO_RECORD],
        "latest": _ANTHRO_RECORD,
    },
    "charts_context": _CHARTS_CTX,
    "percentile_curves": None,  # no SVG curves in this fixture
}

_AI_NARRATIVE: dict = {
    "strengths": "Constancia en asistencia y mejora progresiva en posiciones.",
    "area_to_develop": "Técnica de frenada en curvas cerradas.",
    "milestone": "Primer Top 5 en la temporada.",
    "confidence": "medium",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _render_pdf() -> bytes:
    """Render the newsletter PDF synchronously and return raw bytes."""
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)

    context = {
        "athlete_first_name": ATHLETE_FIRST,
        "athlete_last_name": ATHLETE_LAST,
        "club_name": "Trocha y Ruta",
        "month_label": "Mayo 2026",
        "season_year": "2026",
        "email_blocks": _EMAIL_BLOCKS,
        "pdf_only_blocks": _PDF_ONLY_BLOCKS,
        "ai_narrative": _AI_NARRATIVE,
        "coach_narrative_overrides": None,
        "generated_at": "2026-06-05 10:00 COT",
        "initials": "CG",
        "category_label": "Sub-13 Masculino",
        "category_code": "M13",
    }

    request = DocumentRequest(
        template=DocumentTemplate.ATHLETE_MONTHLY_NEWSLETTER,
        format=DocumentFormat.PDF,
        context=context,
        filename_hint="test_layout",
    )

    # Bypass context-validation for test simplicity (extra keys allowed)
    spec = registry.get_document_spec(request.template.value)
    enriched = generator._enrich_context(context)
    doc = generator._generate_pdf(spec, enriched, request)
    return doc.data


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    return _render_pdf()


@pytest.fixture(scope="module")
def pdf_pages(pdf_bytes: bytes) -> list[pdfplumber.page.Page]:  # type: ignore[name-defined]
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    return pdf.pages


# ---------------------------------------------------------------------------
# Assertion (a): charts heading and content on the same page
# ---------------------------------------------------------------------------


def test_charts_heading_and_content_same_page(pdf_pages):
    """The 'Evolución en la temporada' heading must appear on the same page
    as chart content (captions appear nearby in the charts row)."""
    heading_text = "Evolución en la temporada"
    caption_texts = [
        "Posición menor",   # caption under line_positions chart
        "distancia al primero",  # caption under gap_pct chart
        "Puntos acumulados",  # caption under points_accumulated chart
    ]

    heading_page = None
    for i, page in enumerate(pdf_pages):
        text = page.extract_text() or ""
        if heading_text in text:
            heading_page = i
            break

    assert heading_page is not None, (
        f"Heading '{heading_text}' not found in any page of the PDF"
    )

    heading_page_text = pdf_pages[heading_page].extract_text() or ""
    # At least one chart caption must appear on the same page as the heading
    found_captions = [c for c in caption_texts if c in heading_page_text]
    assert found_captions, (
        f"Heading '{heading_text}' is on page {heading_page + 1} but no chart "
        f"caption was found on that page. Captions looked for: {caption_texts}. "
        "This indicates an orphaned heading — the break-inside:avoid wrapper is not working."
    )


# ---------------------------------------------------------------------------
# Assertion (b): Ley 1581 boxed block is absent
# ---------------------------------------------------------------------------

_LEY_1581_STRINGS = [
    "Ley 1581/2012 (Habeas Data)",
    "Prohibida su reproducción o distribución",
    "privacidad@trochyruta.com",
]


def test_ley_1581_box_removed(pdf_pages):
    """The Ley 1581 boxed notice that was removed in T018 must not appear
    in the rendered PDF text."""
    all_text = "\n".join(
        (page.extract_text() or "") for page in pdf_pages
    )
    for fragment in _LEY_1581_STRINGS:
        assert fragment not in all_text, (
            f"Ley 1581 boxed block fragment still present in PDF: '{fragment}'. "
            "T018 removal may not have applied correctly."
        )


# ---------------------------------------------------------------------------
# Assertion (c): page count bound and no near-empty non-last pages
# ---------------------------------------------------------------------------

_MAX_EXPECTED_PAGES = 6  # generous upper bound for this fixture


def test_page_count_within_bound(pdf_pages):
    """PDF page count must be within the expected range for this fixture."""
    assert 1 <= len(pdf_pages) <= _MAX_EXPECTED_PAGES, (
        f"PDF has {len(pdf_pages)} pages; expected 1–{_MAX_EXPECTED_PAGES}. "
        "An unexpected forced page break may have been introduced."
    )


def test_no_near_empty_non_last_pages(pdf_pages):
    """No non-last page should be nearly empty (< 10 % of the median
    non-last page's word count).  This catches blank pages caused by
    a forced break landing on an empty page."""
    if len(pdf_pages) <= 1:
        return  # nothing to compare

    word_counts = [
        len((page.extract_text() or "").split())
        for page in pdf_pages
    ]
    non_last = word_counts[:-1]
    if not non_last:
        return

    median_wc = sorted(non_last)[len(non_last) // 2]
    if median_wc == 0:
        return  # all non-last pages are empty — something else is wrong

    threshold = max(1, int(median_wc * 0.10))

    near_empty = [
        (i + 1, wc)
        for i, wc in enumerate(non_last)
        if wc < threshold
    ]
    assert not near_empty, (
        f"Near-empty non-last pages detected (< {threshold} words): {near_empty}. "
        "Likely caused by a forced page break leaving an almost-blank page."
    )


# ---------------------------------------------------------------------------
# Assertion (d): page counter appears on every page
# ---------------------------------------------------------------------------


def test_page_counter_on_every_page(pdf_pages):
    """The @bottom-right 'Página X de Y' counter must appear on every page."""
    missing = []
    for i, page in enumerate(pdf_pages):
        text = page.extract_text() or ""
        # WeasyPrint renders counter(page) as the literal page number.
        # We check for "Página" which is always the prefix.
        if "Página" not in text:
            missing.append(i + 1)

    assert not missing, (
        f"@bottom-right page counter missing on pages: {missing}. "
        "The @page running footer may have been accidentally removed."
    )


# ---------------------------------------------------------------------------
# Regression: the dense anthropometry table must NOT overflow the page width,
# even when cells carry "unavailable" markers (out-of-LMS-range records).
# Guards the bug where verbose unavailable_reason text widened the 10-column
# table past the A4 right margin (feature 003 post-review fix).
# ---------------------------------------------------------------------------


def _render_pdf_out_of_range() -> bytes:
    """Render with a record whose LMS-derived values are unavailable."""
    registry = TemplateRegistry()
    generator = DocumentGenerator(registry)

    rec = dict(_ANTHRO_RECORD)
    rec.update(
        {
            "bmi": None,
            "height_z_score": None,
            "height_percentile": None,
            "bmi_z_score": None,
            "bmi_percentile": None,
            "unavailable_reasons": {
                "bmi": "Se requiere peso y talla para calcularlo",
                "height_lms": "Fuera del rango de tablas de referencia para esta edad",
                "bmi_lms": "Se requiere IMC calculado",
            },
        }
    )

    pdf_only = {
        "anthropometry": {"has_records": True, "records": [rec, rec], "latest": rec},
        "charts_context": _CHARTS_CTX,
        "percentile_curves": None,
    }
    context = {
        "athlete_first_name": ATHLETE_FIRST,
        "athlete_last_name": ATHLETE_LAST,
        "club_name": "Trocha y Ruta",
        "month_label": "Mayo 2026",
        "season_year": "2026",
        "email_blocks": _EMAIL_BLOCKS,
        "pdf_only_blocks": pdf_only,
        "ai_narrative": _AI_NARRATIVE,
        "coach_narrative_overrides": None,
        "generated_at": "2026-06-05 10:00 COT",
        "initials": "CG",
        "category_label": "Sub-13 Masculino",
        "category_code": "M13",
    }
    request = DocumentRequest(
        template=DocumentTemplate.ATHLETE_MONTHLY_NEWSLETTER,
        format=DocumentFormat.PDF,
        context=context,
        filename_hint="test_overflow",
    )
    spec = registry.get_document_spec(request.template.value)
    enriched = generator._enrich_context(context)
    doc = generator._generate_pdf(spec, enriched, request)
    return doc.data


def test_anthropometry_table_does_not_overflow_page_width():
    pdf = pdfplumber.open(io.BytesIO(_render_pdf_out_of_range()))
    overflow: list[tuple[int, str, float, float]] = []
    for i, page in enumerate(pdf.pages):
        right_edge = page.width  # words past the physical page edge are clipped
        for w in page.extract_words():
            if w["x1"] > right_edge + 0.5:
                overflow.append((i + 1, w["text"], round(w["x1"], 1), round(right_edge, 1)))

    assert not overflow, (
        "Text overflows the page right edge (table too wide): "
        + "; ".join(f"p{pg} '{t}' x1={x1}>{re}" for pg, t, x1, re in overflow[:8])
    )
    # And the compact marker + last column are present (not clipped away).
    all_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    assert "n/d" in all_text
    assert "Maduración" in all_text
