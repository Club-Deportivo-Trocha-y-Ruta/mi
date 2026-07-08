"""Tests for the shared Spanish date-formatting helper (spec 024, R8)."""

from datetime import date, datetime

from app.services.utils.dates_es import format_date_es


def test_format_date_es_basic():
    assert format_date_es(date(2026, 8, 1)) == "1 de agosto de 2026"


def test_format_date_es_none_returns_empty_string():
    assert format_date_es(None) == ""


def test_format_date_es_all_months_have_correct_spanish_names():
    expected = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre",
    }
    for month, name in expected.items():
        result = format_date_es(date(2026, month, 15))
        assert result == f"15 de {name} de 2026"


def test_format_date_es_march_has_accent_free_spelling():
    # "marzo" has no accent, but this pins the exact rendering nonetheless.
    assert format_date_es(date(2026, 3, 19)) == "19 de marzo de 2026"


def test_format_date_es_single_digit_day_not_zero_padded():
    assert format_date_es(date(2026, 6, 5)) == "5 de junio de 2026"


def test_format_date_es_double_digit_day():
    assert format_date_es(date(2026, 12, 25)) == "25 de diciembre de 2026"


def test_format_date_es_locale_independent_no_strftime_percent_b():
    # Regression guard for the bug this helper replaces (strftime("%B") is
    # locale-fragile — see race_insight_dispatcher / calendar notifications).
    result = format_date_es(date(2026, 1, 1))
    assert "de enero de" in result
    assert "January" not in result


# --- Regression: E2E found the PDF crashed because email_blocks persists dates
#     as ISO strings in the JSON snapshot, not as `date` objects (spec 024). ---


def test_format_date_es_accepts_iso_string():
    assert format_date_es("2026-08-01") == "1 de agosto de 2026"


def test_format_date_es_accepts_iso_datetime_string():
    assert format_date_es("2026-06-12T00:00:00") == "12 de junio de 2026"


def test_format_date_es_accepts_datetime_object():
    assert format_date_es(datetime(2026, 5, 15, 9, 30)) == "15 de mayo de 2026"


def test_format_date_es_empty_string_returns_empty():
    assert format_date_es("") == ""


def test_format_date_es_unparseable_string_returned_as_is():
    # Graceful degradation — never raise during template render.
    assert format_date_es("no es fecha") == "no es fecha"
