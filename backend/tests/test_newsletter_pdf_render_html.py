"""Template-level regression tests for the newsletter PDF (spec 024, E2E findings).

These render the PDF Jinja template to an HTML string (NOT a PDF), so they run
without WeasyPrint's system libraries (pango/glib) — unlike the full PDF render
tests. They pin two bugs the E2E surfaced that unit tests missed:

1. Dates in ``email_blocks`` are persisted as ISO strings in the JSON snapshot,
   not ``date`` objects; the ``date_es`` filter must not crash on them.
2. The streak KPI must read ``streak_sessions`` (post-rename), so the streak is
   actually shown; and it must appear only once (the duplicated line was removed).
"""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.notification.document_generator import (
    _TEMPLATES_ROOT,
    _format_hms,
    _render_markdown,
)
from app.services.utils.dates_es import format_date_es

_TEMPLATE = "documents/pdf/athlete_monthly_newsletter.html"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown"] = _render_markdown
    env.filters["hms"] = _format_hms
    env.filters["date_es"] = format_date_es
    return env


def _context() -> dict:
    """Realistic context: dates as ISO strings (as persisted in JSON), new keys."""
    return {
        "athlete_first_name": "Atleta",
        "athlete_last_name": "Prueba",
        "email_blocks": {
            "period": {"year": 2026, "month": 6, "label": "Junio 2026"},
            "attendance": {
                "sessions_total": 10,
                "sessions_present": 10,
                "attendance_pct": 100.0,
                "attendance_pct_prev_month": 90.0,
                "streak_sessions": 10,
            },
            "technical": {
                "focos_tecnicos": ["Frenado"],
                "focus_groups": [{"slug": "frenado", "name": "Frenado modulado", "session_count": 3}],
                "avg_rpe": 4.6,
                "total_training_hours": 12.0,
                "weekly_hours_avg": 2.6,
                "ltad_limit_hours": 12.3,
                "ltad_status": "ok",
            },
            "race_results": {"results": []},
            "calendar": {
                "next_training_sessions": [
                    {"date": "2026-07-02", "technical_focus": "Vo2", "location": "Pista", "duration_min": 120}
                ],
                "next_race_events": [
                    {"valida": "V", "date": "2026-08-01", "location": "Palmira", "priority": "B"}
                ],
            },
            "photos": {"count": 0, "items": []},
            "badges": {"count": 0, "items": []},
            "support_at_home": {"age_band": "13-15", "rotation_index": 0, "tips": []},
        },
        "pdf_only_blocks": {
            "anthropometry": {"has_records": False, "records": []},
            "charts_context": {"has_data": False, "has_championship": False},
        },
    }


def test_pdf_template_renders_with_iso_string_dates_without_crashing():
    """Regression: date_es on ISO strings from the JSON snapshot must not raise."""
    html = _env().get_template(_TEMPLATE).render(**_context())
    # Spanish-formatted dates present (not raw ISO, not a crash).
    assert "1 de agosto de 2026" in html
    assert "2 de julio de 2026" in html


def test_pdf_template_shows_streak_from_streak_sessions_key():
    """Regression: streak KPI reads streak_sessions (post-rename), not streak_days."""
    html = _env().get_template(_TEMPLATE).render(**_context())
    assert "Sesiones seguidas" in html
    # The streak value (10) is rendered in the KPI card.
    assert ">10</p>" in html


def test_pdf_template_streak_appears_only_once():
    """Regression: the duplicated 'Racha de asistencia consecutiva' line is gone."""
    html = _env().get_template(_TEMPLATE).render(**_context())
    assert "Racha de asistencia consecutiva" not in html


def test_pdf_template_weekly_hours_use_decimal_comma():
    """B14/T014: es-CO decimal comma in the LTAD hours line."""
    html = _env().get_template(_TEMPLATE).render(**_context())
    assert "2,6 h/sem" in html
    assert "12,3 h/sem" in html


def test_pdf_template_renders_with_legacy_streak_days_key():
    """FR-015: pre-024 snapshots (streak_days) still render the streak."""
    ctx = _context()
    ctx["email_blocks"]["attendance"] = {
        "sessions_total": 8,
        "sessions_present": 8,
        "attendance_pct": 100.0,
        "attendance_pct_prev_month": None,
        "streak_days": 8,
    }
    html = _env().get_template(_TEMPLATE).render(**ctx)
    assert "Sesiones seguidas" in html
    assert ">8</p>" in html
