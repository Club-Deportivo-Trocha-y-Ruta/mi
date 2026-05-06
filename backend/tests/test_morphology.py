"""Tests para servicio de métricas morfológicas (envergadura)."""

import pytest

from app.services.morphology import (
    APE_INDEX_INSTABILITY_ADVISORY,
    POSTURE_SCREENING_MESSAGE,
    calculate_arm_span_metrics,
)


class TestArmSpanMetricsNullCases:
    def test_returns_none_when_arm_span_is_none(self):
        assert (
            calculate_arm_span_metrics(
                arm_span_cm=None,
                standing_height_cm=150.0,
                maturation_status="Pre-PHV",
            )
            is None
        )

    def test_returns_none_when_height_is_zero(self):
        assert (
            calculate_arm_span_metrics(
                arm_span_cm=150.0,
                standing_height_cm=0.0,
                maturation_status="Pre-PHV",
            )
            is None
        )


class TestApeIndexCalculation:
    def test_ape_index_equal_returns_one(self):
        result = calculate_arm_span_metrics(150.0, 150.0, "Post-PHV")
        assert result["ape_index"] == 1.0

    def test_ape_index_higher_when_arm_span_longer(self):
        result = calculate_arm_span_metrics(160.0, 150.0, "Post-PHV")
        assert result["ape_index"] > 1.0

    def test_ape_index_lower_when_arm_span_shorter(self):
        result = calculate_arm_span_metrics(140.0, 150.0, "Post-PHV")
        assert result["ape_index"] < 1.0


class TestPostureScreeningFlag:
    def test_flag_off_when_delta_below_threshold(self):
        result = calculate_arm_span_metrics(151.5, 150.0, "Post-PHV")
        assert result["posture_screening_flag"] is False
        assert result["posture_screening_message"] is None

    def test_flag_on_when_arm_span_exceeds_height_by_more_than_3cm(self):
        result = calculate_arm_span_metrics(154.0, 150.0, "Post-PHV")
        assert result["posture_screening_flag"] is True
        assert result["posture_screening_message"] == POSTURE_SCREENING_MESSAGE
        assert "diagnosticar" not in POSTURE_SCREENING_MESSAGE.lower()

    def test_flag_on_when_arm_span_below_height_by_more_than_3cm(self):
        result = calculate_arm_span_metrics(146.0, 150.0, "Post-PHV")
        assert result["posture_screening_flag"] is True

    def test_flag_off_at_exact_threshold(self):
        # delta == 3.0 exacto NO dispara (umbral estricto >)
        result = calculate_arm_span_metrics(153.0, 150.0, "Post-PHV")
        assert result["posture_screening_flag"] is False


class TestBikeFitClassification:
    @pytest.mark.parametrize(
        "arm_span,height,expected",
        [
            (140.0, 150.0, "short_reach"),
            (150.0, 150.0, "standard"),
            (155.0, 150.0, "long_reach"),
        ],
    )
    def test_categories(self, arm_span, height, expected):
        result = calculate_arm_span_metrics(arm_span, height, "Post-PHV")
        assert result["bike_fit_category"] == expected
        assert result["bike_fit_guidance"]


class TestApeIndexAdvisory:
    def test_advisory_on_pre_phv(self):
        result = calculate_arm_span_metrics(150.0, 150.0, "Pre-PHV")
        assert result["ape_index_advisory"] == APE_INDEX_INSTABILITY_ADVISORY

    def test_advisory_on_circa_phv(self):
        result = calculate_arm_span_metrics(150.0, 150.0, "Circa-PHV")
        assert result["ape_index_advisory"] == APE_INDEX_INSTABILITY_ADVISORY

    def test_no_advisory_on_post_phv(self):
        result = calculate_arm_span_metrics(150.0, 150.0, "Post-PHV")
        assert result["ape_index_advisory"] is None

    def test_advisory_on_unknown_status(self):
        result = calculate_arm_span_metrics(150.0, 150.0, None)
        assert result["ape_index_advisory"] == APE_INDEX_INSTABILITY_ADVISORY


class TestDeltaSign:
    def test_positive_delta_when_arm_span_greater(self):
        result = calculate_arm_span_metrics(155.0, 150.0, "Post-PHV")
        assert result["arm_span_height_delta_cm"] == 5.0

    def test_negative_delta_when_arm_span_smaller(self):
        result = calculate_arm_span_metrics(145.0, 150.0, "Post-PHV")
        assert result["arm_span_height_delta_cm"] == -5.0
