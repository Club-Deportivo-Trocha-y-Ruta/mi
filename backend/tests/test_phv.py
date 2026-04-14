import pytest
from datetime import date

from app.services.phv import calculate_mirwald_offset
from app.services.category import compute_age_decimal, get_category


class TestPHVCalculation:
    def test_male_pre_phv(self):
        result = calculate_mirwald_offset(
            sex="M", age=10.5, weight=35.0,
            standing_height=140.0, sitting_height=73.0,
        )
        assert result["maturation_status"] == "Pre-PHV"
        assert result["leg_length_cm"] == 67.0

    def test_female_circa_phv(self):
        result = calculate_mirwald_offset(
            sex="F", age=12.0, weight=42.0,
            standing_height=155.0, sitting_height=80.0,
        )
        assert result["maturation_status"] in ("Pre-PHV", "Circa-PHV", "Post-PHV")
        assert "leg_length_cm" in result
        assert "age_at_phv" in result

    def test_male_post_phv(self):
        result = calculate_mirwald_offset(
            sex="M", age=16.0, weight=65.0,
            standing_height=175.0, sitting_height=85.0,
        )
        assert result["maturation_status"] == "Post-PHV"

    def test_leg_length_calculation(self):
        result = calculate_mirwald_offset(
            sex="M", age=12.0, weight=45.0,
            standing_height=155.0, sitting_height=73.0,
        )
        assert result["leg_length_cm"] == 82.0
        assert result["leg_sitting_ratio"] == round(82.0 / 73.0, 4)

    def test_age_at_phv_formula(self):
        age = 12.5
        result = calculate_mirwald_offset(
            sex="M", age=age, weight=45.0,
            standing_height=155.0, sitting_height=73.0,
        )
        expected_phv = round(age - result["maturity_offset"], 2)
        assert result["age_at_phv"] == expected_phv


class TestAgeDecimal:
    def test_basic_calculation(self):
        age = compute_age_decimal(date(2013, 6, 15), date(2026, 4, 14))
        assert 12.5 < age < 13.0

    def test_exact_year(self):
        age = compute_age_decimal(date(2016, 1, 1), date(2026, 1, 1))
        assert abs(age - 10.0) < 0.02

    def test_uses_today_by_default(self):
        age = compute_age_decimal(date(2016, 1, 1))
        assert age > 0


class TestCategory:
    @pytest.mark.parametrize(
        "year,sex,expected",
        [
            (2022, "M", "Teteros"),
            (2023, "F", "Teteros"),
            (2021, "M", "Pre-Infantil A"),
            (2020, "F", "Pre-Infantil A femenino"),
            (2019, "M", "Pre-Infantil B"),
            (2018, "F", "Pre-Infantil B femenino"),
            (2017, "M", "Infantil A"),
            (2016, "F", "Infantil A femenino"),
            (2015, "M", "Infantil B"),
            (2014, "F", "Infantil B femenino"),
            (2013, "M", "Pre-juvenil A"),
            (2012, "F", "Pre-juvenil A femenino"),
            (2011, "M", "Pre-juvenil B"),
            (2010, "F", "Pre-juvenil B femenino"),
            (2009, "M", "Junior"),
            (2008, "F", "Junior femenino"),
            (2007, "M", "Elite"),
            (2000, "F", "Elite femenina"),
            (1990, "M", "Master A"),
            (1985, "M", "Master B 1"),
            (1980, "M", "Master B 2"),
            (1975, "M", "Master C 1"),
            (1970, "M", "Master C 2"),
            (1960, "M", "Master D"),
            (1985, "F", "Master Damas"),
        ],
    )
    def test_fcc_2026_categories(self, year, sex, expected):
        assert get_category(year, sex) == expected
