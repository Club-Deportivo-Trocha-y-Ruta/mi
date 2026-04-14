"""
Tests unitarios para app.services.growth.

Cubre:
  - calculate_z_score       : fórmula LMS de Cole & Green (1992), clamping, caso L=0
  - z_to_percentile         : conversión Z → percentil
  - classify_nutritional_status_height : límites Resolución 2465/2016 T/E
  - classify_nutritional_status_bmi    : límites Resolución 2465/2016 IMC/E
  - _lms_value_at_z         : inversa LMS (usada en curvas de referencia)
  - get_lms_params          : interpolación lineal + casos borde, con mock AsyncSession
  - calculate_growth_percentiles : integración con mock AsyncSession

Todos los tests de DB usan mocks — sin conexión real a MySQL.
"""

import math
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.anthropometry import NutritionalStatus
from app.models.growth import GrowthIndicator, GrowthSource
from app.services.growth import (
    GrowthPercentiles,
    _lms_value_at_z,
    calculate_growth_percentiles,
    calculate_z_score,
    classify_nutritional_status_bmi,
    classify_nutritional_status_height,
    get_lms_params,
    z_to_percentile,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _MockRow:
    """Simula una fila de GrowthReferenceLms con los atributos mínimos necesarios."""

    def __init__(self, age_months: float, L: float, M: float, S: float) -> None:
        self.age_months = age_months
        self.L = L
        self.M = M
        self.S = S


def _make_db_mock(rows: list[_MockRow]) -> AsyncMock:
    """Devuelve un AsyncSession mock cuyo .execute() retorna `rows`."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_db.execute.return_value = mock_result
    return mock_db


# ─────────────────────────────────────────────────────────────────────────────
# calculate_z_score
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateZScore:
    # Parámetros CDC reales para niño masculino 120.5 meses (aprox 10 años)
    L = 0.5056
    M = 138.82
    S = 0.0476

    def test_z_score_at_median(self):
        """Valor igual a la mediana M → Z ≈ 0.0."""
        z = calculate_z_score(self.M, self.L, self.M, self.S)
        assert abs(z) < 0.05

    def test_z_score_at_p3(self):
        """
        El valor correspondiente a P3 (Z_teorico = -1.8808) calculado con la inversa LMS
        debe producir un Z-score de ≈ -1.88 (tolerancia ±0.1).
        """
        value_p3 = _lms_value_at_z(self.L, self.M, self.S, -1.8808)
        z = calculate_z_score(value_p3, self.L, self.M, self.S)
        assert abs(z - (-1.8808)) < 0.1

    def test_z_score_at_p97(self):
        """
        El valor correspondiente a P97 (Z_teorico = +1.8808) debe producir Z ≈ +1.88.
        """
        value_p97 = _lms_value_at_z(self.L, self.M, self.S, 1.8808)
        z = calculate_z_score(value_p97, self.L, self.M, self.S)
        assert abs(z - 1.8808) < 0.1

    def test_z_score_clamped_to_minus_3(self):
        """Valor muy por debajo de la mediana → Z no puede ser < -3.0."""
        # Usamos un valor extremadamente pequeño (≈ mediana * 0.01)
        extreme_low = self.M * 0.01
        z = calculate_z_score(extreme_low, self.L, self.M, self.S)
        assert z == -3.0

    def test_z_score_clamped_to_plus_3(self):
        """Valor muy por encima de la mediana → Z no puede ser > +3.0."""
        extreme_high = self.M * 10.0
        z = calculate_z_score(extreme_high, self.L, self.M, self.S)
        assert z == 3.0

    def test_z_score_l_equals_zero(self):
        """Cuando L ≈ 0 la fórmula usa logaritmo natural: Z = ln(value/M) / S."""
        L0, M0, S0 = 0.0, 100.0, 0.1
        # value = M → Z debe ser 0
        z_at_median = calculate_z_score(M0, L0, M0, S0)
        assert abs(z_at_median) < 1e-9

        # value = M * exp(S * 1.5) → Z debe ser ≈ 1.5
        value_at_z15 = M0 * math.exp(S0 * 1.5)
        z = calculate_z_score(value_at_z15, L0, M0, S0)
        assert abs(z - 1.5) < 1e-6

    def test_z_score_l_near_zero_treated_as_zero(self):
        """L muy pequeño (|L| < 1e-10) activa la rama logarítmica."""
        L_tiny = 5e-11
        M0, S0 = 50.0, 0.08
        z = calculate_z_score(M0, L_tiny, M0, S0)
        assert abs(z) < 0.05  # valor = mediana → Z ≈ 0

    def test_z_score_positive_l_formula(self):
        """Con L > 0 la fórmula LMS estándar debe devolver resultado correcto."""
        L, M, S = 1.0, 100.0, 0.1
        # Con L=1 la fórmula es lineal: Z = (value/M - 1) / S
        value = 110.0  # (110/100 - 1) / 0.1 = 1.0
        z = calculate_z_score(value, L, M, S)
        assert abs(z - 1.0) < 1e-6

    def test_z_score_negative_l(self):
        """L negativo también sigue la fórmula LMS estándar sin usar la rama log."""
        L, M, S = -0.5, 15.0, 0.08
        # Solo verificamos que no usa la rama log y el resultado es un float en [-3, 3]
        z = calculate_z_score(M, L, M, S)
        assert abs(z) < 0.05  # value = M → Z ≈ 0 siempre


# ─────────────────────────────────────────────────────────────────────────────
# z_to_percentile
# ─────────────────────────────────────────────────────────────────────────────

class TestZToPercentile:
    def test_percentile_at_median(self):
        """Z=0 → percentil 50.0 (±0.1)."""
        p = z_to_percentile(0.0)
        assert abs(p - 50.0) < 0.1

    def test_percentile_at_p3(self):
        """Z=-1.8808 → percentil ≈ 3.0 (±0.5)."""
        p = z_to_percentile(-1.8808)
        assert abs(p - 3.0) < 0.5

    def test_percentile_at_p97(self):
        """Z=+1.8808 → percentil ≈ 97.0 (±0.5)."""
        p = z_to_percentile(1.8808)
        assert abs(p - 97.0) < 0.5

    def test_percentile_at_minus_3(self):
        """Z=-3.0 → percentil muy bajo (< 1.0)."""
        p = z_to_percentile(-3.0)
        assert p < 1.0

    def test_percentile_at_plus_3(self):
        """Z=+3.0 → percentil muy alto (> 99.0)."""
        p = z_to_percentile(3.0)
        assert p > 99.0

    def test_symmetry(self):
        """La distribución normal es simétrica: percentil(Z) + percentil(-Z) ≈ 100."""
        for z in [0.5, 1.0, 1.5, 2.0]:
            assert abs(z_to_percentile(z) + z_to_percentile(-z) - 100.0) < 0.01

    def test_percentile_is_float(self):
        """El resultado siempre es un float."""
        assert isinstance(z_to_percentile(0.0), float)


# ─────────────────────────────────────────────────────────────────────────────
# classify_nutritional_status_height (T/E)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyNutritionalStatusHeight:
    def test_talla_adecuada_at_zero(self):
        """Z=0.0 → talla_adecuada."""
        assert classify_nutritional_status_height(0.0) == NutritionalStatus.talla_adecuada

    def test_talla_adecuada_at_minus_one(self):
        """Z=-1.0 es el límite inferior de talla_adecuada (incluido)."""
        assert classify_nutritional_status_height(-1.0) == NutritionalStatus.talla_adecuada

    def test_talla_adecuada_at_two(self):
        """Z=2.0 es el límite superior de talla_adecuada (incluido)."""
        assert classify_nutritional_status_height(2.0) == NutritionalStatus.talla_adecuada

    def test_riesgo_retraso_talla(self):
        """Z=-1.5 → riesgo_retraso_talla."""
        assert classify_nutritional_status_height(-1.5) == NutritionalStatus.riesgo_retraso_talla

    def test_riesgo_retraso_talla_just_below_minus_one(self):
        """Z=-1.0001 cae en riesgo_retraso_talla."""
        assert classify_nutritional_status_height(-1.0001) == NutritionalStatus.riesgo_retraso_talla

    def test_retraso_talla(self):
        """Z=-3.5 → retraso_talla."""
        assert classify_nutritional_status_height(-3.5) == NutritionalStatus.retraso_talla

    def test_retraso_talla_at_minus_two(self):
        """Z=-2.0 es el límite superior de retraso_talla (no incluido — la condición es < -2.0)."""
        # Z=-2.0 NO es < -2.0, por lo que cae en riesgo_retraso_talla
        assert classify_nutritional_status_height(-2.0) == NutritionalStatus.riesgo_retraso_talla

    def test_retraso_talla_just_below_minus_two(self):
        """Z=-2.0001 → retraso_talla."""
        assert classify_nutritional_status_height(-2.0001) == NutritionalStatus.retraso_talla

    def test_talla_alta(self):
        """Z=2.5 → talla_alta."""
        assert classify_nutritional_status_height(2.5) == NutritionalStatus.talla_alta

    def test_talla_alta_just_above_two(self):
        """Z=2.0001 → talla_alta."""
        assert classify_nutritional_status_height(2.0001) == NutritionalStatus.talla_alta

    def test_returns_nutritional_status_instance(self):
        """El resultado siempre es un NutritionalStatus."""
        for z in [-4.0, -2.5, -1.5, 0.0, 1.0, 2.5]:
            result = classify_nutritional_status_height(z)
            assert isinstance(result, NutritionalStatus)


# ─────────────────────────────────────────────────────────────────────────────
# classify_nutritional_status_bmi (IMC/E)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyNutritionalStatusBMI:
    def test_adecuado_at_zero(self):
        """Z=0.0 → adecuado."""
        assert classify_nutritional_status_bmi(0.0) == NutritionalStatus.adecuado

    def test_adecuado_at_plus_half(self):
        """Z=0.5 → adecuado."""
        assert classify_nutritional_status_bmi(0.5) == NutritionalStatus.adecuado

    def test_adecuado_boundaries(self):
        """Z=-1.0 y Z=+1.0 son límites incluidos de adecuado."""
        assert classify_nutritional_status_bmi(-1.0) == NutritionalStatus.adecuado
        assert classify_nutritional_status_bmi(1.0) == NutritionalStatus.adecuado

    def test_sobrepeso(self):
        """Z=1.5 → sobrepeso."""
        assert classify_nutritional_status_bmi(1.5) == NutritionalStatus.sobrepeso

    def test_sobrepeso_just_above_one(self):
        """Z=1.0001 → sobrepeso."""
        assert classify_nutritional_status_bmi(1.0001) == NutritionalStatus.sobrepeso

    def test_sobrepeso_at_two(self):
        """Z=2.0 es el límite superior de sobrepeso (incluido — condición > 2.0 es para obesidad)."""
        assert classify_nutritional_status_bmi(2.0) == NutritionalStatus.sobrepeso

    def test_obesidad(self):
        """Z=2.5 → obesidad."""
        assert classify_nutritional_status_bmi(2.5) == NutritionalStatus.obesidad

    def test_obesidad_just_above_two(self):
        """Z=2.0001 → obesidad."""
        assert classify_nutritional_status_bmi(2.0001) == NutritionalStatus.obesidad

    def test_delgadez(self):
        """Z=-1.5 → delgadez."""
        assert classify_nutritional_status_bmi(-1.5) == NutritionalStatus.delgadez

    def test_delgadez_just_below_minus_one(self):
        """Z=-1.0001 → delgadez."""
        assert classify_nutritional_status_bmi(-1.0001) == NutritionalStatus.delgadez

    def test_delgadez_at_minus_two(self):
        """Z=-2.0 es el límite inferior de delgadez (incluido — condición >= -2.0)."""
        assert classify_nutritional_status_bmi(-2.0) == NutritionalStatus.delgadez

    def test_delgadez_severa(self):
        """Z=-2.5 → delgadez_severa."""
        assert classify_nutritional_status_bmi(-2.5) == NutritionalStatus.delgadez_severa

    def test_delgadez_severa_extreme(self):
        """Z=-3.5 → delgadez_severa (clamp no aplica aquí, la clasificación usa Z directo)."""
        assert classify_nutritional_status_bmi(-3.5) == NutritionalStatus.delgadez_severa

    def test_delgadez_severa_just_below_minus_two(self):
        """Z=-2.0001 → delgadez_severa."""
        assert classify_nutritional_status_bmi(-2.0001) == NutritionalStatus.delgadez_severa

    def test_returns_nutritional_status_instance(self):
        """El resultado siempre es un NutritionalStatus."""
        for z in [-4.0, -2.5, -1.5, 0.5, 1.5, 2.5]:
            result = classify_nutritional_status_bmi(z)
            assert isinstance(result, NutritionalStatus)


# ─────────────────────────────────────────────────────────────────────────────
# _lms_value_at_z (inversa LMS)
# ─────────────────────────────────────────────────────────────────────────────

class TestLmsValueAtZ:
    def test_z_zero_returns_median(self):
        """Z=0 siempre retorna M independiente de L y S."""
        for L, M, S in [(0.5056, 138.82, 0.0476), (-0.3, 17.5, 0.09), (0.0, 25.0, 0.1)]:
            assert abs(_lms_value_at_z(L, M, S, 0.0) - M) < 1e-6

    def test_l_zero_uses_exponential(self):
        """Cuando L=0: value = M * exp(S * z)."""
        L, M, S = 0.0, 100.0, 0.1
        z = 2.0
        expected = M * math.exp(S * z)
        assert abs(_lms_value_at_z(L, M, S, z) - expected) < 1e-9

    def test_l_nonzero_uses_power_formula(self):
        """Con L != 0: value = M * (1 + L*S*z)^(1/L)."""
        L, M, S = 1.0, 100.0, 0.1
        z = 1.0
        expected = M * (1 + L * S * z) ** (1.0 / L)  # = 110.0
        assert abs(_lms_value_at_z(L, M, S, z) - expected) < 1e-6

    def test_roundtrip_with_calculate_z_score(self):
        """
        _lms_value_at_z y calculate_z_score son inversas:
        calculate_z_score(_lms_value_at_z(L,M,S,z), L, M, S) ≈ z
        para z en [-2.5, 2.5] (fuera del rango de clamping).
        """
        L, M, S = 0.5056, 138.82, 0.0476
        for z_target in [-2.5, -1.8808, -1.0, 0.0, 1.0, 1.8808, 2.5]:
            value = _lms_value_at_z(L, M, S, z_target)
            z_recovered = calculate_z_score(value, L, M, S)
            assert abs(z_recovered - z_target) < 0.001, (
                f"Roundtrip falla para z={z_target}: recuperado={z_recovered}"
            )

    def test_base_negative_returns_zero(self):
        """Si (1 + L*S*z) <= 0, retorna 0.0 para evitar potencia de base negativa."""
        # Con L=2, S=0.5, z=-1.1: base = 1 + 2*0.5*(-1.1) = 1 - 1.1 = -0.1 <= 0
        result = _lms_value_at_z(2.0, 100.0, 0.5, -1.1)
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# get_lms_params (interpolación con mock AsyncSession)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLmsParams:
    # Tres puntos de referencia para las pruebas
    _rows = [
        _MockRow(120.0, 0.5000, 138.00, 0.0470),
        _MockRow(120.5, 0.5056, 138.82, 0.0476),
        _MockRow(121.0, 0.5100, 139.30, 0.0480),
    ]

    async def test_empty_table_returns_none(self):
        """BD vacía → retorna None."""
        db = _make_db_mock([])
        result = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.5)
        assert result is None

    async def test_exact_match_middle(self):
        """Edad coincide exactamente con el punto del medio → retorna ese punto."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.5)
        assert abs(L - 0.5056) < 1e-6
        assert abs(M - 138.82) < 1e-6
        assert abs(S - 0.0476) < 1e-6

    async def test_exact_match_first(self):
        """Edad coincide exactamente con el primer punto."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.0)
        assert abs(L - 0.5000) < 1e-6
        assert abs(M - 138.00) < 1e-6
        assert abs(S - 0.0470) < 1e-6

    async def test_exact_match_last(self):
        """Edad coincide exactamente con el último punto."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 121.0)
        assert abs(L - 0.5100) < 1e-6
        assert abs(M - 139.30) < 1e-6
        assert abs(S - 0.0480) < 1e-6

    async def test_below_range_uses_first_point(self):
        """Edad menor al mínimo → usa el primer punto disponible."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 50.0)
        assert abs(L - 0.5000) < 1e-6
        assert abs(M - 138.00) < 1e-6
        assert abs(S - 0.0470) < 1e-6

    async def test_above_range_uses_last_point(self):
        """Edad mayor al máximo → usa el último punto disponible."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 999.0)
        assert abs(L - 0.5100) < 1e-6
        assert abs(M - 139.30) < 1e-6
        assert abs(S - 0.0480) < 1e-6

    async def test_interpolation_midpoint(self):
        """
        Para age_months=120.25 (entre 120.0 y 120.5):
        t = 0.25/0.5 = 0.5
        L_interp = 0.5000 + 0.5 * (0.5056 - 0.5000) = 0.5028
        M_interp = 138.00 + 0.5 * (138.82 - 138.00) = 138.41
        S_interp = 0.0470 + 0.5 * (0.0476 - 0.0470) = 0.0473
        """
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.25)
        expected_L = 0.5000 + 0.5 * (0.5056 - 0.5000)
        expected_M = 138.00 + 0.5 * (138.82 - 138.00)
        expected_S = 0.0470 + 0.5 * (0.0476 - 0.0470)
        assert abs(L - expected_L) < 1e-6
        assert abs(M - expected_M) < 1e-6
        assert abs(S - expected_S) < 1e-6

    async def test_interpolation_at_60_percent(self):
        """
        Para age_months=120.3 (entre 120.0 y 120.5):
        t = 0.3/0.5 = 0.6
        """
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.3)
        t = 0.3 / 0.5
        expected_L = 0.5000 + t * (0.5056 - 0.5000)
        expected_M = 138.00 + t * (138.82 - 138.00)
        expected_S = 0.0470 + t * (0.0476 - 0.0470)
        assert abs(L - expected_L) < 1e-6
        assert abs(M - expected_M) < 1e-6
        assert abs(S - expected_S) < 1e-6

    async def test_interpolation_between_second_and_third(self):
        """Interpolación en el segundo intervalo (120.5 – 121.0)."""
        db = _make_db_mock(self._rows)
        L, M, S = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.75)
        t = 0.25 / 0.5
        expected_M = 138.82 + t * (139.30 - 138.82)
        assert abs(M - expected_M) < 1e-5

    async def test_returns_tuple_of_floats(self):
        """El resultado es una tupla de tres floats."""
        db = _make_db_mock(self._rows)
        result = await get_lms_params(db, GrowthIndicator.height_for_age, "M", 120.5)
        assert result is not None
        assert len(result) == 3
        for v in result:
            assert isinstance(v, float)

    async def test_db_execute_called_once(self):
        """Se ejecuta exactamente una query a la BD por llamada."""
        db = _make_db_mock(self._rows)
        await get_lms_params(db, GrowthIndicator.bmi_for_age, "F", 132.0, GrowthSource.WHO)
        db.execute.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# calculate_growth_percentiles (con mock AsyncSession)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateGrowthPercentiles:
    """
    Cada llamada a calculate_growth_percentiles ejecuta 3 queries (height, bmi, weight).
    El mock de _make_db_mock retorna los mismos rows para todas las queries.
    Para tests de percentil real usamos LMS realistas de CDC para niño masculino 120.5 meses.
    """

    # LMS CDC reales height_for_age masculino 120.5 meses
    _HEIGHT_LMS = _MockRow(120.5, 0.5056, 138.82, 0.0476)
    # LMS CDC reales bmi_for_age masculino 120.5 meses (valores aproximados)
    _BMI_LMS    = _MockRow(120.5, -0.6289, 16.34, 0.0899)
    # LMS CDC reales weight_for_age masculino 120.5 meses (valores aproximados)
    _WEIGHT_LMS = _MockRow(120.5, 0.6619, 33.73, 0.1347)

    def _make_multi_indicator_db(self) -> AsyncMock:
        """
        Mock que retorna LMS apropiado para cada indicador basándose en el orden de llamada.
        Las 3 queries se hacen en el orden: height_for_age, bmi_for_age, weight_for_age.
        """
        mock_db = AsyncMock()

        def _make_result(rows):
            r = MagicMock()
            r.scalars.return_value.all.return_value = rows
            return r

        mock_db.execute.side_effect = [
            _make_result([self._HEIGHT_LMS]),
            _make_result([self._BMI_LMS]),
            _make_result([self._WEIGHT_LMS]),
        ]
        return mock_db

    async def test_returns_growth_percentiles_dataclass(self):
        """El resultado es una instancia de GrowthPercentiles."""
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
        )
        assert isinstance(result, GrowthPercentiles)

    async def test_median_child_height_z_near_zero(self):
        """
        Niño 120.5 meses, talla exactamente en la mediana CDC (138.82 cm):
        height_z_score ≈ 0.0 (±0.05), height_percentile ≈ 50 (±1).
        """
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
        )
        assert result.height_z_score is not None
        assert result.height_percentile is not None
        assert abs(float(result.height_z_score)) < 0.05
        assert abs(float(result.height_percentile) - 50.0) < 1.0

    async def test_bmi_is_calculated_correctly(self):
        """BMI = weight / (height_m)^2, redondeado a 2 decimales."""
        db = self._make_multi_indicator_db()
        weight, height = 33.73, 138.82
        result = await calculate_growth_percentiles(
            db, weight_kg=weight, standing_height_cm=height,
            sex="M", age_months=120.5,
        )
        expected_bmi = round(weight / (height / 100) ** 2, 2)
        assert result.bmi == Decimal(str(expected_bmi))

    async def test_nutritional_status_height_is_string(self):
        """nutritional_status_height es un string con el valor del enum."""
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
        )
        assert result.nutritional_status_height is not None
        valid_values = {e.value for e in NutritionalStatus}
        assert result.nutritional_status_height in valid_values

    async def test_empty_db_returns_all_none_except_bmi(self):
        """Si la BD está vacía (sin datos LMS), todos los z-scores y percentiles son None."""
        db = _make_db_mock([])  # retorna [] para todas las queries
        result = await calculate_growth_percentiles(
            db, weight_kg=30.0, standing_height_cm=135.0,
            sex="M", age_months=120.0,
        )
        # BMI siempre se calcula (no depende de la BD)
        assert result.bmi is not None
        # El resto debe ser None
        assert result.height_z_score is None
        assert result.height_percentile is None
        assert result.bmi_z_score is None
        assert result.bmi_percentile is None
        assert result.weight_z_score is None
        assert result.weight_percentile is None
        assert result.nutritional_status_height is None
        assert result.nutritional_status_bmi is None

    async def test_three_db_queries_executed(self):
        """Se hacen exactamente 3 queries: height, bmi, weight."""
        db = self._make_multi_indicator_db()
        await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
        )
        assert db.execute.call_count == 3

    async def test_decimal_types_in_output(self):
        """Todos los campos numéricos no-None son Decimal."""
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
        )
        for attr in (
            "bmi", "height_z_score", "height_percentile",
            "bmi_z_score", "bmi_percentile", "weight_z_score", "weight_percentile",
        ):
            value = getattr(result, attr)
            if value is not None:
                assert isinstance(value, Decimal), f"{attr} debe ser Decimal, got {type(value)}"

    async def test_female_sex_accepted(self):
        """El servicio acepta sex='F' sin error."""
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=32.0, standing_height_cm=136.0,
            sex="F", age_months=120.5,
        )
        assert isinstance(result, GrowthPercentiles)

    async def test_who_source_accepted(self):
        """El servicio acepta source=GrowthSource.WHO sin error."""
        db = self._make_multi_indicator_db()
        result = await calculate_growth_percentiles(
            db, weight_kg=33.73, standing_height_cm=138.82,
            sex="M", age_months=120.5,
            source=GrowthSource.WHO,
        )
        assert isinstance(result, GrowthPercentiles)


# ─────────────────────────────────────────────────────────────────────────────
# Casos de integración: calculate_z_score ↔ clasificaciones (tabla del workflow)
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkflowReferenceTable:
    """
    Verifica todos los casos de la tabla del workflow usando los mismos
    parámetros LMS CDC de referencia.
    """
    L = 0.5056
    M = 138.82
    S = 0.0476

    def test_workflow_z_score_median(self):
        """Fila 1: value=M → Z ≈ 0.0 (±0.05)."""
        z = calculate_z_score(self.M, self.L, self.M, self.S)
        assert abs(z) < 0.05

    def test_workflow_z_score_p3(self):
        """Fila 2: value=P3_calculado → Z ≈ -1.88 (±0.1)."""
        p3_value = _lms_value_at_z(self.L, self.M, self.S, -1.8808)
        z = calculate_z_score(p3_value, self.L, self.M, self.S)
        assert abs(z - (-1.8808)) < 0.1

    def test_workflow_z_score_p97(self):
        """Fila 3: value=P97_calculado → Z ≈ +1.88 (±0.1)."""
        p97_value = _lms_value_at_z(self.L, self.M, self.S, 1.8808)
        z = calculate_z_score(p97_value, self.L, self.M, self.S)
        assert abs(z - 1.8808) < 0.1

    def test_workflow_percentile_median(self):
        """Fila 4: Z=0.0 → percentil 50.0 (±0.1)."""
        assert abs(z_to_percentile(0.0) - 50.0) < 0.1

    def test_workflow_percentile_p3(self):
        """Fila 5: Z=-1.8808 → percentil ≈ 3.0 (±0.5)."""
        assert abs(z_to_percentile(-1.8808) - 3.0) < 0.5

    def test_workflow_bmi_adecuado(self):
        """Fila 6: Z=0.5 (bmi_for_age) → adecuado."""
        assert classify_nutritional_status_bmi(0.5) == NutritionalStatus.adecuado

    def test_workflow_bmi_sobrepeso(self):
        """Fila 7: Z=1.5 (bmi_for_age) → sobrepeso."""
        assert classify_nutritional_status_bmi(1.5) == NutritionalStatus.sobrepeso

    def test_workflow_bmi_obesidad(self):
        """Fila 8: Z=2.5 (bmi_for_age) → obesidad."""
        assert classify_nutritional_status_bmi(2.5) == NutritionalStatus.obesidad

    def test_workflow_height_riesgo(self):
        """Fila 9: Z=-1.5 (height_for_age) → riesgo_retraso_talla."""
        assert classify_nutritional_status_height(-1.5) == NutritionalStatus.riesgo_retraso_talla

    def test_workflow_height_retraso(self):
        """Fila 10: Z=-3.5 → retraso_talla."""
        assert classify_nutritional_status_height(-3.5) == NutritionalStatus.retraso_talla

    def test_workflow_height_adecuada(self):
        """Fila 11: Z=0.0 → talla_adecuada."""
        assert classify_nutritional_status_height(0.0) == NutritionalStatus.talla_adecuada

    def test_workflow_height_alta(self):
        """Fila 12: Z=2.5 → talla_alta."""
        assert classify_nutritional_status_height(2.5) == NutritionalStatus.talla_alta

    def test_workflow_bmi_delgadez(self):
        """Fila 13: Z=-2.5 → delgadez_severa (umbral colombiano < -2 = delgadez_severa)."""
        assert classify_nutritional_status_bmi(-2.5) == NutritionalStatus.delgadez_severa

    def test_workflow_bmi_delgadez_severa(self):
        """Fila 14: Z=-3.5 → delgadez_severa."""
        assert classify_nutritional_status_bmi(-3.5) == NutritionalStatus.delgadez_severa
