"""Tests unitarios para app.services.race.race_labels.build_race_label.

Función pura — sin IO, sin base de datos.  Cubre todos los contratos del
módulo: copas con numerales romanos, campeonatos (ignorando sequence_number),
ciudad None/vacía/whitespace y número fuera de rango.
"""
import pytest

from app.models.race_series import RaceSeriesKind
from app.services.race.race_labels import build_race_label


# ---------------------------------------------------------------------------
# Copa (cup) — numerales romanos del 1 al 7
# ---------------------------------------------------------------------------


class TestCupRomanNumerals:
    """Verifica conversión correcta de sequence_number a numeral romano."""

    def test_sequence_1_yields_roman_I(self):
        result = build_race_label(RaceSeriesKind.cup, 1, "Sevilla")
        assert result == "Válida I — Sevilla"

    def test_sequence_4_yields_roman_IV(self):
        result = build_race_label(RaceSeriesKind.cup, 4, "Cali")
        assert result == "Válida IV — Cali"

    def test_sequence_7_yields_roman_VII(self):
        result = build_race_label(RaceSeriesKind.cup, 7, "Yumbo")
        assert result == "Válida VII — Yumbo"

    def test_all_roman_numerals_1_to_7(self):
        """Todos los numerales del rango soportado deben ser correctos."""
        expected = {
            1: "I",
            2: "II",
            3: "III",
            4: "IV",
            5: "V",
            6: "VI",
            7: "VII",
        }
        for n, roman in expected.items():
            label = build_race_label(RaceSeriesKind.cup, n, "Ciudad Ficticia")
            assert label == f"Válida {roman} — Ciudad Ficticia", (
                f"sequence_number={n} debe producir {roman}"
            )


# ---------------------------------------------------------------------------
# Copa — fallback fuera de rango
# ---------------------------------------------------------------------------


class TestCupOutOfRange:
    """sequence_number fuera del rango 1–7 debe renderizarse como entero."""

    def test_sequence_8_falls_back_to_integer_string(self):
        result = build_race_label(RaceSeriesKind.cup, 8, "Palmira")
        assert result == "Válida 8 — Palmira"

    def test_sequence_0_falls_back_to_integer_string(self):
        result = build_race_label(RaceSeriesKind.cup, 0, "Ginebra")
        assert result == "Válida 0 — Ginebra"


# ---------------------------------------------------------------------------
# Campeonato (championship) — sequence_number ignorado
# ---------------------------------------------------------------------------


class TestChampionship:
    """Para campeonatos, siempre 'Cto. Dep.' y sequence_number no importa."""

    def test_championship_sequence_1_with_city(self):
        result = build_race_label(RaceSeriesKind.championship, 1, "Ginebra")
        assert result == "Cto. Dep. — Ginebra"

    def test_championship_sequence_number_ignored_when_5(self):
        """Pasar sequence_number=5 aún produce el prefijo correcto."""
        result = build_race_label(RaceSeriesKind.championship, 5, "Ginebra")
        assert result == "Cto. Dep. — Ginebra"

    def test_championship_sequence_number_ignored_consistency(self):
        """sequence_number distinto no cambia la etiqueta del campeonato."""
        label_1 = build_race_label(RaceSeriesKind.championship, 1, "Buga")
        label_99 = build_race_label(RaceSeriesKind.championship, 99, "Buga")
        assert label_1 == label_99 == "Cto. Dep. — Buga"


# ---------------------------------------------------------------------------
# Ciudad nula, vacía y whitespace
# ---------------------------------------------------------------------------


class TestNullOrEmptyCity:
    """Cuando city es None, vacío o solo espacios, se omite el sufijo completo."""

    def test_cup_none_city_omits_suffix(self):
        result = build_race_label(RaceSeriesKind.cup, 4, None)
        assert result == "Válida IV"

    def test_championship_none_city_omits_suffix(self):
        result = build_race_label(RaceSeriesKind.championship, 1, None)
        assert result == "Cto. Dep."

    def test_cup_empty_string_city_omits_suffix(self):
        result = build_race_label(RaceSeriesKind.cup, 2, "")
        assert result == "Válida II"

    def test_cup_whitespace_city_omits_suffix(self):
        """Una cadena de solo espacios se debe tratar como None."""
        result = build_race_label(RaceSeriesKind.cup, 3, "  ")
        assert result == "Válida III"

    def test_championship_whitespace_city_omits_suffix(self):
        result = build_race_label(RaceSeriesKind.championship, 1, "  ")
        assert result == "Cto. Dep."


# ---------------------------------------------------------------------------
# Em-dash exacto U+2014 con espacios
# ---------------------------------------------------------------------------


class TestEmDashFormat:
    """El separador entre prefijo y ciudad debe ser U+2014 con espacios a cada lado."""

    def test_em_dash_is_u2014_not_hyphen(self):
        label = build_race_label(RaceSeriesKind.cup, 1, "La Cumbre")
        # Debe contener ' — ' (espacio + U+2014 + espacio)
        assert " — " in label

    def test_em_dash_not_a_hyphen(self):
        label = build_race_label(RaceSeriesKind.cup, 1, "La Cumbre")
        # El guion simple '-' no debe usarse como separador
        assert " - " not in label

    def test_championship_em_dash_is_u2014(self):
        label = build_race_label(RaceSeriesKind.championship, 1, "Ginebra")
        assert " — " in label
