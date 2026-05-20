"""Tests del módulo ``app.services.race.normalizer``.

Cobertura:
- ``parse_time``: H:MM:SS → ms, DNF/DSQ/DNS, MINUS_LAPS singular/plural.
- ``is_trocha_y_ruta``: variantes válidas, falsos positivos cortos, vacíos.
- ``normalize_club``: placeholder ``0``, casing, tildes.
- ``parse_category_header``: 26 categorías + colisión INF_A vs INF_A_F.
"""
from __future__ import annotations

import pytest

from app.models.race_result import ResultStatus
from app.services.race.normalizer import (
    HEADER_TO_CODE,
    is_trocha_y_ruta,
    normalize_club,
    normalize_name,
    parse_category_header,
    parse_time,
)


# ---------------------------------------------------------------------------
# parse_time — formato H:MM:SS → milisegundos
# ---------------------------------------------------------------------------


class TestParseTime:
    def test_hms_basic(self):
        """0:03:32 → (FINISHED, 212000, 0)."""
        status, ms, laps = parse_time("0:03:32")
        assert status == ResultStatus.FINISHED
        assert ms == 212_000
        assert laps == 0

    def test_hms_complex(self):
        """1:30:00 → 5_400_000 ms."""
        status, ms, laps = parse_time("1:30:00")
        assert status == ResultStatus.FINISHED
        assert ms == 5_400_000
        assert laps == 0

    def test_hms_seconds_only(self):
        """0:00:45 → 45_000 ms."""
        _, ms, _ = parse_time("0:00:45")
        assert ms == 45_000

    def test_hms_rejects_overflow(self):
        """Minutos o segundos ≥ 60 lanzan ValueError."""
        with pytest.raises(ValueError):
            parse_time("0:60:00")
        with pytest.raises(ValueError):
            parse_time("0:00:60")

    def test_dnf(self):
        status, ms, laps = parse_time("DNF")
        assert status == ResultStatus.DNF
        assert ms is None
        assert laps == 0

    def test_dnf_lowercase(self):
        status, _, _ = parse_time("dnf")
        assert status == ResultStatus.DNF

    def test_dsq(self):
        status, ms, laps = parse_time("DSQ")
        assert status == ResultStatus.DSQ
        assert ms is None
        assert laps == 0

    def test_dns(self):
        """DNS aceptado por compat (edge-cases §4.7 + Paso 2 enum)."""
        status, ms, laps = parse_time("DNS")
        assert status == ResultStatus.DNS
        assert ms is None
        assert laps == 0

    def test_minus_one_lap_singular(self):
        """(-1 VUELTA) singular."""
        status, ms, laps = parse_time("(-1 VUELTA)")
        assert status == ResultStatus.MINUS_LAPS
        assert ms is None
        assert laps == 1

    def test_minus_two_laps_plural(self):
        """(-2 VUELTAS) plural."""
        status, ms, laps = parse_time("(-2 VUELTAS)")
        assert status == ResultStatus.MINUS_LAPS
        assert laps == 2

    def test_minus_three_laps(self):
        """(-3 VUELTAS)."""
        _, _, laps = parse_time("(-3 VUELTAS)")
        assert laps == 3

    def test_minus_laps_extra_whitespace(self):
        """(- 1 VUELTA) con espacio extra — tolerar variantes futuras."""
        # Regex actual no tolera espacio entre `(-` y digit; documentamos.
        with pytest.raises(ValueError):
            parse_time("(- 1 VUELTA)")

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_time("???")
        with pytest.raises(ValueError):
            parse_time("32:00")  # falta H:

    def test_none_raises(self):
        with pytest.raises(ValueError):
            parse_time(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_trocha_y_ruta — detección fuzzy del club TyR
# ---------------------------------------------------------------------------


class TestIsTrochaYRuta:
    def test_canonical_with_club_prefix(self):
        """Variante más común en PDFs Válida IV."""
        assert is_trocha_y_ruta("Club Trocha y Ruta") is True

    def test_upper_no_prefix(self):
        """TROCHA Y RUTA sin prefijo Club — caso bib 1414 §4.12."""
        assert is_trocha_y_ruta("TROCHA Y RUTA") is True

    def test_lowercase_canonical(self):
        assert is_trocha_y_ruta("trocha y ruta") is True

    def test_misspelling_trochy(self):
        """'trochy ruta' — variante documentada en TYR_VARIANTS."""
        assert is_trocha_y_ruta("trochy ruta") is True

    def test_no_spaces(self):
        """'trochayruta' sin espacios."""
        assert is_trocha_y_ruta("trochayruta") is True

    def test_with_extra_whitespace(self):
        """Espacios múltiples internos."""
        assert is_trocha_y_ruta("  Club   Trocha  y  Ruta  ") is True

    def test_unicode_normalization(self):
        """Tildes en variantes hipotéticas (no observado en V-IV)."""
        # El normalize_club aplica unidecode antes del fuzzy
        assert is_trocha_y_ruta("Club Trochá y Rutá") is True

    def test_rejects_cana_y_trapiche(self):
        """Caña y Trapiche tiene 'y' común pero no es TyR."""
        assert is_trocha_y_ruta("Club Caña y Trapiche") is False

    def test_rejects_otro(self):
        """Bug edge-cases §4.15 + descubrimiento Paso 3: partial_ratio
        sin guard de longitud daría 85.7 — debe rechazar."""
        assert is_trocha_y_ruta("Otro") is False

    def test_rejects_zero(self):
        """Placeholder '0' nunca es TyR (edge-cases §4.3)."""
        assert is_trocha_y_ruta("0") is False

    def test_rejects_empty(self):
        assert is_trocha_y_ruta("") is False

    def test_rejects_none(self):
        assert is_trocha_y_ruta(None) is False  # type: ignore[arg-type]

    def test_rejects_sin_club(self):
        """'Sin club' es otro placeholder común."""
        assert is_trocha_y_ruta("Sin club") is False

    def test_rejects_independiente(self):
        assert is_trocha_y_ruta("Independiente") is False
        assert is_trocha_y_ruta("INDEPENDIENTE") is False

    def test_rejects_super_amigos(self):
        """Club Súper Amigos Bike — competidor habitual del calendario."""
        assert is_trocha_y_ruta("Club Súper Amigos Bike") is False

    def test_threshold_param_strict_rejects_partial(self):
        """El threshold es ajustable (paso 4 puede afinar).

        ``"Club Trocha"`` (sin "y Ruta") da ``partial_ratio=100`` contra
        ``"trocha y ruta"`` (porque "trocha" es subcadena), pero con threshold
        muy permisivo (>=85) lo aceptamos. Si elevamos el umbral, debería
        aceptarse pero ``ratio`` exacta no llegaría — sirve para demostrar
        que el threshold se respeta.
        """
        # Con threshold normal (85), una variante exacta debe pasar
        assert is_trocha_y_ruta("trochy ruta", threshold=85) is True
        # Con threshold imposible (101), nada pasa
        assert is_trocha_y_ruta("Club Trocha y Ruta", threshold=101) is False


# ---------------------------------------------------------------------------
# normalize_club — placeholders y casing
# ---------------------------------------------------------------------------


class TestNormalizeClub:
    def test_zero_treated_as_empty(self):
        """edge-cases §4.3: '0' → ''."""
        assert normalize_club("0") == ""

    def test_dash_treated_as_empty(self):
        assert normalize_club("-") == ""

    def test_na_variants_empty(self):
        assert normalize_club("n/a") == ""
        assert normalize_club("N/A") == ""

    def test_empty_input(self):
        assert normalize_club("") == ""
        assert normalize_club(None) == ""  # type: ignore[arg-type]

    def test_unicode_lowered(self):
        assert normalize_club("CLUB Súper") == "club super"

    def test_collapses_whitespace(self):
        assert normalize_club("  Club   X  ") == "club x"


# ---------------------------------------------------------------------------
# normalize_name — caracteres comunes en nombres latinos
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("Matías García") == "matias garcia"

    def test_punctuation_removed(self):
        """Punto y coma se quitan (preserva espacio)."""
        assert normalize_name("García, Matías.") == "garcia matias"

    def test_apostrophe_preserved(self):
        """Apóstrofe se preserva (apellidos como D'Alessandro)."""
        out = normalize_name("D'Alessandro")
        assert "'" in out

    def test_hyphen_preserved(self):
        """Guión se preserva (Saint-Étienne)."""
        out = normalize_name("Saint-Étienne")
        assert "-" in out

    def test_empty(self):
        assert normalize_name("") == ""
        assert normalize_name(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse_category_header — mapping 26 codes
# ---------------------------------------------------------------------------


class TestParseCategoryHeader:
    @pytest.mark.parametrize(
        "header,expected_code",
        [
            ("CAT: TETEROS SIN PEDALES", "TET_SP"),
            ("CAT: TETEROS CON PEDALES", "TET_CP"),
            ("CAT: PREINFANTIL A", "PRE_A"),
            ("CAT: PREINFANTIL A FEMENINO", "PRE_A_F"),
            ("CAT: PREINFANTIL B", "PRE_B"),
            ("CAT: PREINFANTIL B FEMENINO", "PRE_B_F"),
            ("CAT: INFANTIL A", "INF_A"),
            ("CAT: INFANTIL A FEMENINO", "INF_A_F"),
            ("CAT: INFANTIL B", "INF_B"),
            ("CAT: INFANTIL B FEMENINO", "INF_B_F"),
            ("CAT: PREJUVENIL A", "PJUV_A"),
            ("CAT: PREJUVENIL A FEMENINO", "PJUV_A_F"),
            ("CAT: PREJUVENIL B", "PJUV_B"),
            ("CAT: PREJUVENIL B FEMENINO", "PJUV_B_F"),
            ("CAT: JUNIOR", "JUN_M"),
            ("CAT: JUNIOR FEMENINO", "JUN_F"),
            ("CAT: ELITE", "ELITE_M"),
            ("CAT: ELITE FEMENINO", "ELITE_F"),
            ("CAT: PROMOCIONAL", "PROMO"),
            ("CAT: MASTER A", "MAS_A"),
            ("CAT: MASTER B1", "MAS_B1"),
            ("CAT: MASTER B2", "MAS_B2"),
            ("CAT: MASTER C1", "MAS_C1"),
            ("CAT: MASTER C2", "MAS_C2"),
            ("CAT: MASTER D", "MAS_D"),
            ("CAT: MASTER FEMENINO", "MAS_F"),
        ],
    )
    def test_all_26_canonical(self, header: str, expected_code: str):
        assert parse_category_header(header) == expected_code

    def test_infantil_a_not_infantil_a_femenino(self):
        """Critical: edge-cases §4.4 — debe distinguir INF_A de INF_A_F."""
        assert parse_category_header("CAT: INFANTIL A") == "INF_A"
        assert parse_category_header("CAT: INFANTIL A FEMENINO") == "INF_A_F"

    def test_case_insensitive_prefix(self):
        """``cat:`` minúscula también se acepta."""
        assert parse_category_header("cat: infantil a") == "INF_A"

    def test_extra_whitespace_tolerated(self):
        assert parse_category_header("  CAT:   INFANTIL  A  ") == "INF_A"

    def test_unicode_tolerated(self):
        """Tilde en hipotético 'PREJUVÉNIL' (no observado, defensivo)."""
        assert parse_category_header("CAT: PREJUVÉNIL A") == "PJUV_A"

    def test_no_match_returns_none(self):
        """Categoría desconocida → None (parser loggea warning)."""
        assert parse_category_header("CAT: SUPER ELITE COSMICO") is None

    def test_no_cat_prefix_returns_none(self):
        assert parse_category_header("INFANTIL A") is None
        assert parse_category_header("") is None

    def test_header_to_code_has_26_entries(self):
        """Sanity check: el dict tiene exactamente 26 entries (edge-cases §1)."""
        assert len(HEADER_TO_CODE) == 26
