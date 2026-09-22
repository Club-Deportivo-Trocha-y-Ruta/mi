"""Tests del módulo ``app.services.race.normalizer``.

Cobertura:
- ``parse_time``: H:MM:SS → ms, DNF/DSQ/DNS, MINUS_LAPS singular/plural.
- ``is_trocha_y_ruta``: variantes válidas, falsos positivos cortos, vacíos.
- ``normalize_club``: placeholder ``0``, casing, tildes.
- ``parse_category_header``: 26 categorías + colisión INF_A vs INF_A_F.
- T025 (feature 044, US2): alias de categorías históricas 2024/2025 →
  ``contracts/category-mapping.md``, y derivación de ``mapping_kind``.

TDD (T025): al escribir estas clases, ``normalizer.py`` todavía no tiene los
12 alias de ``HEADER_TO_CODE``, ni ``HEADER_ALIASES``, ni
``mapping_kind_for`` (T028, agente data-analyst, pendiente) — deben fallar
por ``ImportError``/``KeyError`` hoy, no por un error de este archivo.
"""
from __future__ import annotations

from types import SimpleNamespace

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

    @pytest.mark.parametrize(
        ("raw", "laps"),
        [
            # Variantes medidas en las actas 2024–2025 (feature 044, T024b).
            ("(- 1 VUELTA)", 1),
            ("-1 vuelta", 1),
            ("-1 Vuelta", 1),
            ("-2 VUELTAS", 2),
            ("-1 vuelta-", 1),
            ("(1- VUELTA", 1),
            ("(2 VUELTAS)", 2),
            ("(-3 VUELTAS=", 3),
            ("()-1 VUELTA)", 1),
            ("(-2 VULETAS)", 2),
            ("(-3 VIELTAS)", 3),
            ("(-1vuelta)", 1),
            ("(-2  VUELTAS)", 2),
            ("-3 vueltas (lap)", 3),
            ("-1", 1),
            ("-4", 4),
        ],
    )
    def test_minus_laps_variants(self, raw, laps):
        status, ms, got = parse_time(raw)
        assert status == ResultStatus.MINUS_LAPS
        assert ms is None
        assert got == laps

    @pytest.mark.parametrize("raw", ["1", "(1)", "-0", "VUELTA", "-1 VALLE", "-1 VELETA"])
    def test_minus_laps_rejects_ambiguous(self, raw):
        """Un número sin signo ni palabra de vuelta, o cero vueltas, no es
        un déficit de vueltas."""
        with pytest.raises(ValueError):
            parse_time(raw)

    def test_mm_ss(self):
        """Categorías cortas: ``MM:SS`` sin horas."""
        assert parse_time("13:07") == (ResultStatus.FINISHED, 787_000, 0)
        assert parse_time("9:58") == (ResultStatus.FINISHED, 598_000, 0)

    def test_mm_ss_rejects_overflow(self):
        with pytest.raises(ValueError):
            parse_time("13:60")

    def test_stray_apostrophe_in_seconds(self):
        """``0:16:'08`` (errata del acta) se lee como ``0:16:08``."""
        assert parse_time("0:16:'08") == (ResultStatus.FINISHED, 968_000, 0)

    def test_hours_out_of_xco_range_raise(self):
        """Una hora ≥ 10 no es un tiempo XCO plausible: ``ValueError`` y el
        ingestor conserva la fila con tiempo nulo."""
        with pytest.raises(ValueError):
            parse_time("12:02:00")

    def test_empty_is_classified_without_time(self):
        """``""`` = clasificado sin tiempo (R-01 punto 4, R-05)."""
        assert parse_time("") == (ResultStatus.FINISHED, None, 0)
        assert parse_time("   ") == (ResultStatus.FINISHED, None, 0)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_time("???")
        with pytest.raises(ValueError):
            parse_time("1:2")

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

    def test_header_to_code_has_38_entries_after_044_aliases(self):
        """Sanity check: 26 originales (edge-cases §1) + 12 alias históricos
        del contrato de la 044 (8 renombres + 4 propios de temporada) = 38.

        Reemplaza el sanity check previo de "26 entries" — T028 agrega los
        alias al MISMO dict (``HEADER_TO_CODE``, no uno separado), así que
        el tamaño total debe crecer. Si este test falla con
        ``len == 26``, T028 todavía no corrió.
        """
        assert len(HEADER_TO_CODE) == 38


# ---------------------------------------------------------------------------
# T025 (feature 044, US2) — alias de categorías históricas 2024/2025
# ---------------------------------------------------------------------------


class TestHistoricalAliasResolution:
    """Cada fila de la tabla de alias de ``contracts/category-mapping.md``,
    probada con y sin tildes y con y sin guion donde aplica (el CSV y el PDF
    difieren en eso — ver instrucción T025)."""

    @pytest.mark.parametrize(
        "header,expected_code",
        [
            # --- Renombres puros → código activo 2026 -----------------------
            ("CAT: ELITE HOMBRES", "ELITE_M"),
            ("CAT: ELITE DAMAS", "ELITE_F"),
            ("CAT: JUNIOR DAMAS", "JUN_F"),
            ("CAT: MASTER DAMAS", "MAS_F"),
            ("CAT: INFANTIL A NINAS", "INF_A_F"),
            ("CAT: INFANTIL A NIÑAS", "INF_A_F"),  # con tilde
            ("CAT: INFANTIL B NINAS", "INF_B_F"),
            ("CAT: INFANTIL B NIÑAS", "INF_B_F"),  # con tilde
            ("CAT: PREJUVENIL A DAMAS", "PJUV_A_F"),
            ("CAT: PRE-JUVENIL A DAMAS", "PJUV_A_F"),  # con guion
            ("CAT: PREJUVENIL B DAMAS", "PJUV_B_F"),
            ("CAT: PRE-JUVENIL B DAMAS", "PJUV_B_F"),  # con guion
            # --- Propios de temporada → código inactivo (nunca 2026) --------
            ("CAT: MASTER B", "MAS_B_2025"),
            ("CAT: MASTER C", "MAS_C_2025"),
            ("CAT: PREINFANTIL NINAS", "PRE_F_U"),
            ("CAT: PREINFANTIL NIÑAS", "PRE_F_U"),  # con tilde
            ("CAT: PRE-INFANTIL NINAS", "PRE_F_U"),  # con guion
            ("CAT: PRE-INFANTIL NIÑAS", "PRE_F_U"),  # con guion + tilde
            ("CAT: PREINFANTIL FEMENINO", "PRE_F_U"),
            ("CAT: PRE-INFANTIL FEMENINO", "PRE_F_U"),  # con guion
        ],
    )
    def test_alias_resolves_to_contract_code(self, header: str, expected_code: str):
        assert parse_category_header(header) == expected_code

    def test_renames_still_collide_correctly_with_2026_forms(self):
        """Un alias y su forma 2026 nativa deben resolver al MISMO code —
        el catálogo no se duplica, sólo se amplía el vocabulario aceptado."""
        assert parse_category_header("CAT: ELITE HOMBRES") == parse_category_header(
            "CAT: ELITE"
        )
        assert parse_category_header(
            "CAT: INFANTIL A NIÑAS"
        ) == parse_category_header("CAT: INFANTIL A FEMENINO")


class TestHeaderAliasesFrozenset:
    """``HEADER_ALIASES`` marca cuáles keys de ``HEADER_TO_CODE`` son alias
    (no las 26 originales) — usado por ``mapping_kind_for`` para distinguir
    ``exact`` de ``rename``/``season_specific``."""

    def test_contains_exactly_the_12_alias_headers(self):
        from app.services.race.normalizer import HEADER_ALIASES

        assert HEADER_ALIASES == frozenset(
            {
                "elite hombres",
                "elite damas",
                "junior damas",
                "master damas",
                "infantil a ninas",
                "infantil b ninas",
                "prejuvenil a damas",
                "prejuvenil b damas",
                "master b",
                "master c",
                "preinfantil ninas",
                "preinfantil femenino",
            }
        )

    def test_aliases_disjoint_from_original_26(self):
        """Ningún alias reemplaza/colisiona con una de las 26 keys nativas
        2026 — son vocabulario ADICIONAL, no un rename del dict existente."""
        from app.services.race.normalizer import HEADER_ALIASES

        original_26 = {
            "teteros sin pedales", "teteros con pedales",
            "preinfantil a", "preinfantil a femenino",
            "preinfantil b", "preinfantil b femenino",
            "infantil a", "infantil a femenino",
            "infantil b", "infantil b femenino",
            "prejuvenil a", "prejuvenil a femenino",
            "prejuvenil b", "prejuvenil b femenino",
            "junior", "junior femenino",
            "elite", "elite femenino",
            "promocional",
            "master a", "master b1", "master b2", "master c1", "master c2",
            "master d", "master femenino",
        }
        assert len(original_26) == 26
        assert HEADER_ALIASES.isdisjoint(original_26)
        assert HEADER_ALIASES <= set(HEADER_TO_CODE.keys())


class TestMappingKindDerivation:
    """``mapping_kind_for(header, category)`` — contrato: ``exact`` para una
    de las 26 keys originales; ``rename`` para un alias que resuelve a una
    categoría ``is_active=True``; ``season_specific`` para un alias que
    resuelve a ``is_active=False``; ``unknown`` cuando no resolvió (``category
    is None``)."""

    def test_exact_for_one_of_the_26_original_headers(self):
        from app.services.race.normalizer import mapping_kind_for

        active_category = SimpleNamespace(is_active=True)
        assert mapping_kind_for("CAT: INFANTIL A", active_category) == "exact"

    def test_rename_for_alias_resolving_to_active_category(self):
        from app.services.race.normalizer import mapping_kind_for

        active_category = SimpleNamespace(is_active=True)  # p.ej. ELITE_M
        assert mapping_kind_for("CAT: ELITE HOMBRES", active_category) == "rename"

    def test_season_specific_for_alias_resolving_to_inactive_category(self):
        from app.services.race.normalizer import mapping_kind_for

        inactive_category = SimpleNamespace(is_active=False)  # p.ej. MAS_B_2025
        assert mapping_kind_for("CAT: MASTER B", inactive_category) == "season_specific"

    def test_season_specific_for_preinfantil_grupo_unico(self):
        from app.services.race.normalizer import mapping_kind_for

        inactive_category = SimpleNamespace(is_active=False)  # PRE_F_U
        assert (
            mapping_kind_for("CAT: PREINFANTIL FEMENINO", inactive_category)
            == "season_specific"
        )

    def test_unknown_when_unresolved(self):
        from app.services.race.normalizer import mapping_kind_for

        assert mapping_kind_for("CAT: SUPER ELITE COSMICO", None) == "unknown"
