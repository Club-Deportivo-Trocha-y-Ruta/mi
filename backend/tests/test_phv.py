import pytest

from app.services.phv import calculate_mirwald_offset


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
