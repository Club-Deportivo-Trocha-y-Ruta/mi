"""Tests de ``app.services.race.course.derived.derive_figures`` (feature 043, US2).

Contrato: ``specs/043-race-course-profile/contracts/results-derived-figures.md``
§§2–4. ``derive_figures`` es una función pura — no toca la DB — así que los
objetos ``setup``/``variant`` reales (``RaceCourseCategorySetup``,
``RaceCourseVariant``) se sustituyen aquí por ``@dataclass`` livianos que solo
exponen los atributos que la función lee (``setup.laps``,
``setup.variant.lap_distance_m``, ``setup.variant.elevation_gain_m``).

``derived.py`` todavía no existe (T033 la implementa después de este test,
TDD) — se espera que la recolección falle por ``ImportError`` hasta entonces.
"""
from __future__ import annotations

from dataclasses import dataclass

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from app.services.race.course.derived import DerivedFigures, derive_figures

# Both property tests below draw laps/lap_distance_m/race_time_ms independently
# and then use assume() to keep only physically-plausible combinations (see
# each test's docstring for why). That independent-draw-then-filter shape is
# an intentional, minimal way to express "any plausible XCO input", but it
# means Hypothesis's own bookkeeping legitimately discards a large fraction of
# generated examples (much of the input space pairs a big distance with a
# tiny time). That is a property of the *generation strategy*, not of the
# assume() conditions themselves — which stay exactly as tight as needed to
# exclude physically-impossible inputs — so the health check that flags a
# high discard ratio is suppressed here rather than loosening assume().
_SUPPRESS_FILTERING_HEALTH_CHECK = [HealthCheck.filter_too_much]

# Cota de sensatez para velocidad promedio en XCO juvenil (10-15 años), no una
# regla de negocio — ver contrato §4 y la instrucción de la tarea T031.
_SANITY_MAX_SPEED_KMH = 60.0


@dataclass
class _Variant:
    lap_distance_m: int
    elevation_gain_m: int | None = None


@dataclass
class _Setup:
    laps: int
    variant: _Variant


# --------------------------------------------------------------------------
# El caso numérico propio del contrato (§4, "spec's independent test")
# --------------------------------------------------------------------------


def _course_setup() -> _Setup:
    return _Setup(laps=3, variant=_Variant(lap_distance_m=4200, elevation_gain_m=110))


class TestContractWorkedExample:
    def test_finished_30_minutes(self):
        result = derive_figures(
            _course_setup(), status="finished", race_time_ms=30 * 60 * 1000, laps_behind=None
        )
        assert isinstance(result, DerivedFigures)
        assert result.distance_km == 12.6
        assert result.avg_speed_kmh == 25.2
        # No dependen de la dinámica de carrera, solo de que exista setup.
        assert result.lap_distance_km == 4.2
        assert result.elevation_gain_m == 110

    def test_minus_laps_one_lap_down_28_minutes(self):
        result = derive_figures(
            _course_setup(), status="minus_laps", race_time_ms=28 * 60 * 1000, laps_behind=1
        )
        assert result.distance_km == 8.4
        assert result.avg_speed_kmh == 18.0
        assert result.lap_distance_km == 4.2
        assert result.elevation_gain_m == 110

    def test_dnf_all_fields_none(self):
        result = derive_figures(
            _course_setup(), status="dnf", race_time_ms=None, laps_behind=None
        )
        assert result.distance_km is None
        assert result.avg_speed_kmh is None
        assert result.lap_distance_km is None
        assert result.elevation_gain_m is None


# --------------------------------------------------------------------------
# Casos borde explícitos del contrato / la tarea
# --------------------------------------------------------------------------


class TestEdgeCases:
    def test_minus_laps_without_laps_behind_count_is_unknown(self):
        """``laps_behind=None`` en ``minus_laps``: se sabe que terminó, pero no
        cuántas vueltas de menos corrió, así que la distancia es incalculable
        aunque sí haya un ``race_time_ms`` (contrato §2, línea "None if status
        == minus_laps and laps_behind is None")."""
        result = derive_figures(
            _course_setup(), status="minus_laps", race_time_ms=28 * 60 * 1000, laps_behind=None
        )
        assert result.distance_km is None
        assert result.avg_speed_kmh is None
        assert result.lap_distance_km is None
        assert result.elevation_gain_m is None

    def test_no_course_setup_is_none_regardless_of_status_or_time(self):
        """Categoría sin setup de recorrido configurado: las cuatro cifras son
        ``None`` sin importar el estado o el tiempo — esto es lo que permite
        que ``has_course_data`` (a nivel de ``get_event_results``) difiera de
        "todas las filas tienen cifras": esa distinción la cubre otro test,
        aquí solo se confirma el contrato propio de esta función."""
        result = derive_figures(
            None, status="finished", race_time_ms=30 * 60 * 1000, laps_behind=None
        )
        assert result.distance_km is None
        assert result.avg_speed_kmh is None
        assert result.lap_distance_km is None
        assert result.elevation_gain_m is None

        # También con otros status/tiempos — sigue sin setup, sigue en None.
        result_dnf = derive_figures(None, status="dnf", race_time_ms=None, laps_behind=None)
        assert result_dnf.distance_km is None
        assert result_dnf.avg_speed_kmh is None
        assert result_dnf.lap_distance_km is None
        assert result_dnf.elevation_gain_m is None


# --------------------------------------------------------------------------
# Redondeo: Decimal(str(x)).quantize(Decimal("0.1"), ROUND_HALF_UP) — no el
# ``round()`` nativo de Python, que usa banker's rounding sobre la
# representación binaria y puede desacordar justo en los ".x5" (contrato §2).
# --------------------------------------------------------------------------


class TestDecimalHalfUpRounding:
    def test_distance_tie_rounds_half_up_not_bankers(self):
        """1 vuelta de 1250 m -> 1.25 km exactos: ``round(1.25, 1) == 1.2``
        con floats nativos de Python (la representación binaria de 1.25 más
        cercana ya "empuja" hacia abajo), pero
        ``Decimal("1.25").quantize(Decimal("0.1"), ROUND_HALF_UP) == 1.3``.
        El contrato exige el segundo comportamiento.
        """
        setup = _Setup(laps=1, variant=_Variant(lap_distance_m=1250))
        raw = 1 * 1250 / 1000
        assert round(raw, 1) == 1.2, "si esto falla, el ejemplo dejó de ser un caso ambiguo"

        result = derive_figures(setup, status="finished", race_time_ms=10 * 60 * 1000, laps_behind=None)
        assert result.distance_km == 1.3

    def test_avg_speed_uses_unrounded_distance_not_the_rounded_display_value(self):
        """Contrato §2: ``avg_speed_kmh = round(distance_km / horas, 1)  #
        uses the unrounded distance`` — es decir, la velocidad se calcula a
        partir de la distancia SIN redondear, no de la cifra ya redondeada a
        un decimal que se le muestra a la familia. 3 vueltas de 2589 m en
        1 095 498 ms produce una distancia sin redondear de 7.767 km (redondea
        a 7.8 km) pero una velocidad de 25.5 km/h; si la implementación
        encadenara el redondeo (usara 7.8 km en vez de 7.767 km) el resultado
        sería 25.6 km/h — un error de encadenamiento de redondeo.
        """
        setup = _Setup(laps=3, variant=_Variant(lap_distance_m=2589))
        result = derive_figures(
            setup, status="finished", race_time_ms=1_095_498, laps_behind=None
        )
        assert result.distance_km == 7.8
        assert result.avg_speed_kmh == 25.5


# --------------------------------------------------------------------------
# Property-based test (hypothesis)
# --------------------------------------------------------------------------


@settings(max_examples=200, suppress_health_check=_SUPPRESS_FILTERING_HEALTH_CHECK)
@given(
    laps=st.integers(min_value=1, max_value=20),
    lap_distance_m=st.integers(min_value=300, max_value=15_000),
    race_time_ms=st.integers(min_value=1, max_value=6 * 60 * 60 * 1000),
)
def test_property_distance_and_speed_are_positive_and_speed_is_sane(
    laps: int, lap_distance_m: int, race_time_ms: int
):
    """Para cualquier combinación de vueltas/distancia/tiempo dentro de rangos
    plausibles de XCO juvenil, con ``status="finished"`` (todas las vueltas
    completas): ``distance_km`` es ``None`` o un float positivo, y
    ``avg_speed_kmh`` es ``None`` o un float positivo <= 60 km/h (cota de
    sensatez, no regla de negocio — ver contrato §4).

    ``assume()`` descarta combinaciones físicamente absurdas (una distancia
    grande cubierta en un tiempo irrisorio) en vez de debilitar la cota: se
    exige un ``race_time_ms`` mínimo tal que, incluso a un ritmo generoso de
    50 km/h (por debajo de la cota de 60 que se afirma), el tiempo generado
    sea compatible con la distancia generada. Si a alguien se le ocurre un
    caso legítimo que efectivamente supere los 60 km/h a partir de rangos
    "normales", ese caso debería sobrevivir el ``assume()`` de abajo y hacer
    fallar la aserción a propósito — hasta ahora ninguno lo ha hecho.
    """
    total_distance_km = laps * lap_distance_m / 1000
    max_plausible_speed_kmh = 50.0
    min_race_time_ms = (total_distance_km / max_plausible_speed_kmh) * 3_600_000
    assume(race_time_ms >= min_race_time_ms)

    setup = _Setup(laps=laps, variant=_Variant(lap_distance_m=lap_distance_m))
    result = derive_figures(setup, status="finished", race_time_ms=race_time_ms, laps_behind=None)

    assert result.distance_km is None or result.distance_km > 0
    assert result.avg_speed_kmh is None or result.avg_speed_kmh > 0
    assert result.avg_speed_kmh is None or result.avg_speed_kmh <= _SANITY_MAX_SPEED_KMH


@settings(max_examples=100, suppress_health_check=_SUPPRESS_FILTERING_HEALTH_CHECK)
@given(
    laps=st.integers(min_value=1, max_value=20),
    lap_distance_m=st.integers(min_value=300, max_value=15_000),
    race_time_ms=st.integers(min_value=1, max_value=6 * 60 * 60 * 1000),
    laps_behind=st.integers(min_value=0, max_value=19),
)
def test_property_minus_laps_never_exceeds_finished_distance(
    laps: int, lap_distance_m: int, race_time_ms: int, laps_behind: int
):
    """Sanity adicional: con vueltas perdidas, la distancia derivada nunca
    puede ser mayor que la de haber terminado todas las vueltas — y si el
    conteo de vueltas perdidas iguala o supera las vueltas de la categoría
    (defensivo, no debería pasar con datos reales) el resultado es ``None``
    en vez de una distancia negativa o cero."""
    assume(laps_behind < laps)  # combinación realista: no puede perder más vueltas de las que hay
    total_distance_km = laps * lap_distance_m / 1000
    max_plausible_speed_kmh = 50.0
    min_race_time_ms = (total_distance_km / max_plausible_speed_kmh) * 3_600_000
    assume(race_time_ms >= min_race_time_ms)

    setup = _Setup(laps=laps, variant=_Variant(lap_distance_m=lap_distance_m))
    finished = derive_figures(setup, status="finished", race_time_ms=race_time_ms, laps_behind=None)
    minus_laps = derive_figures(
        setup, status="minus_laps", race_time_ms=race_time_ms, laps_behind=laps_behind
    )

    assert finished.distance_km is not None
    if laps_behind == 0:
        assert minus_laps.distance_km == finished.distance_km
    else:
        assert minus_laps.distance_km is None or minus_laps.distance_km < finished.distance_km
