"""Tests unitarios para app.services.race.race_labels.build_race_label.

Función pura — sin IO, sin base de datos.  Cubre todos los contratos del
módulo: copas con numerales romanos, campeonatos (ignorando sequence_number),
ciudad None/vacía/whitespace y número fuera de rango.
"""

from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.services.race.race_labels import build_race_label, series_display_name


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


# ---------------------------------------------------------------------------
# Campeonato Nacional (feature 023) — parámetro `level`
# ---------------------------------------------------------------------------


class TestChampionshipLevel:
    """Cobertura del parámetro ``level`` (departmental | national, spec 023)."""

    def test_championship_national_with_city(self):
        result = build_race_label(
            RaceSeriesKind.championship,
            1,
            "Pereira",
            level=RaceSeriesLevel.national,
        )
        assert result == "Cto. Nal. — Pereira"

    def test_championship_national_no_city(self):
        result = build_race_label(
            RaceSeriesKind.championship,
            1,
            None,
            level=RaceSeriesLevel.national,
        )
        assert result == "Cto. Nal."

    def test_championship_departmental_regression(self):
        """Regresión: nivel departamental explícito conserva 'Cto. Dep.'."""
        result = build_race_label(
            RaceSeriesKind.championship,
            1,
            "Ginebra",
            level=RaceSeriesLevel.departmental,
        )
        assert result == "Cto. Dep. — Ginebra"

    def test_cup_level_ignored(self):
        """Las copas no exponen nivel: el parámetro no debe alterar la etiqueta."""
        result = build_race_label(
            RaceSeriesKind.cup,
            4,
            "Cali",
            level=RaceSeriesLevel.national,
        )
        assert result == "Válida IV — Cali"

    def test_backward_compat_default_is_departmental(self):
        """Llamar sin `level` debe seguir produciendo el comportamiento departamental."""
        result = build_race_label(RaceSeriesKind.championship, 1, "Ginebra")
        assert result == "Cto. Dep. — Ginebra"


# ---------------------------------------------------------------------------
# series_label (hotfix identidad de válida) — prefijo "{series_label} · "
# ---------------------------------------------------------------------------


class TestSeriesLabelPrefix:
    """Cobertura del parámetro ``series_label`` (hotfix multicopa)."""

    def test_cup_with_series_label_prefixes(self):
        result = build_race_label(
            RaceSeriesKind.cup, 4, "Alcalá", series_label="Copa Let's Go"
        )
        assert result == "Copa Let's Go · Válida IV — Alcalá"

    def test_championship_with_series_label_prefixes(self):
        result = build_race_label(
            RaceSeriesKind.championship, 1, "Ginebra", series_label="Cto. Depto. Valle"
        )
        assert result == "Cto. Depto. Valle · Cto. Dep. — Ginebra"

    def test_cup_no_city_with_series_label(self):
        result = build_race_label(RaceSeriesKind.cup, 4, None, series_label="Copa Let's Go")
        assert result == "Copa Let's Go · Válida IV"

    def test_series_label_none_is_output_unchanged(self):
        """Omitir ``series_label`` (default ``None``) no debe cambiar nada
        frente a todo llamador previo a este cambio."""
        result = build_race_label(RaceSeriesKind.cup, 4, "Cali")
        assert result == "Válida IV — Cali"

    def test_series_label_empty_or_whitespace_omitted(self):
        result_empty = build_race_label(RaceSeriesKind.cup, 4, "Cali", series_label="")
        result_ws = build_race_label(RaceSeriesKind.cup, 4, "Cali", series_label="   ")
        assert result_empty == "Válida IV — Cali"
        assert result_ws == "Válida IV — Cali"


# ---------------------------------------------------------------------------
# series_display_name (hotfix identidad de válida)
# ---------------------------------------------------------------------------


class TestSeriesDisplayName:
    def test_prefers_short_name_when_present(self):
        assert series_display_name("Copa Let's Go Interdepartamental XCO", "Let's Go") == "Let's Go"

    def test_falls_back_to_name_when_short_name_missing(self):
        assert series_display_name("Copa Valle de Ciclomontañismo", None) == "Copa Valle de Ciclomontañismo"

    def test_falls_back_to_name_when_short_name_blank(self):
        assert series_display_name("Copa Valle de Ciclomontañismo", "   ") == "Copa Valle de Ciclomontañismo"

    def test_none_when_both_missing(self):
        assert series_display_name(None, None) is None

    def test_none_when_both_blank(self):
        assert series_display_name("  ", "") is None
