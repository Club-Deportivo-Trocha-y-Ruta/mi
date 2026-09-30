"""Feature 048 (T027): bordes de las reglas de plausibilidad (research R5).

Pruebas puras del motor ``check_plausibility`` / ``flags_for_series``: cada
regla se prueba a ambos lados del umbral, sin BD ni reloj. Los valores viajan
como ``str``/``Decimal`` para que los bordes sean exactos.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.anthropometry_plausibility import (
    MeasureSet,
    check_plausibility,
    flags_for_series,
)

BASE_DATE = date(2026, 1, 1)


def ms(
    *,
    days: int = 0,
    weight: str = "40.0",
    standing: str = "150.0",
    sitting: str = "78.0",  # 0.52: dentro de [0.47, 0.57]
    arm_span: str | None = None,
) -> MeasureSet:
    return MeasureSet(
        evaluation_date=BASE_DATE + timedelta(days=days),
        weight_kg=Decimal(weight),
        standing_height_cm=Decimal(standing),
        sitting_height_cm=Decimal(sitting),
        arm_span_cm=Decimal(arm_span) if arm_span is not None else None,
    )


def codes(warnings) -> list[str]:
    return [w.code for w in warnings]


PREVIOUS = ms(days=0)


# ---------------------------------------------------------------------------
# height_decreased: current < previous - 1.0 cm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("standing", "expected"),
    [
        ("150.0", False),  # sin cambio
        ("149.0", False),  # -1.0 exacto: no dispara
        ("148.9", True),  # -1.1
        ("140.0", True),
    ],
)
def test_height_decreased_boundary(standing, expected):
    result = check_plausibility(ms(days=30, standing=standing, sitting="77.0"), PREVIOUS)
    assert ("height_decreased" in codes(result)) is expected


def test_height_decreased_reports_standing_height_measure():
    (warning,) = [w for w in check_plausibility(ms(days=30, standing="140.0", sitting="72.0"), PREVIOUS)
                  if w.code == "height_decreased"]
    assert warning.measure == "standing_height"


# ---------------------------------------------------------------------------
# height_velocity_implausible: intervalo >= 60 d y > 15 cm/año
# ---------------------------------------------------------------------------


def test_velocity_is_skipped_below_60_days_even_for_absurd_gain():
    previous = ms(days=0, standing="150.0")
    result = check_plausibility(ms(days=59, standing="153.0", sitting="79.0"), previous)  # 18.6 cm/año
    assert "height_velocity_implausible" not in codes(result)


def test_velocity_is_evaluated_from_60_days():
    previous = ms(days=0, standing="150.0")
    result = check_plausibility(ms(days=60, standing="153.0", sitting="79.0"), previous)  # 18.26 cm/año
    assert "height_velocity_implausible" in codes(result)


@pytest.mark.parametrize(
    ("current_standing", "expected"),
    [
        ("160.0", False),  # 60.0 cm en 1461 días = 15.0 cm/año exacto: no dispara
        ("160.4", True),  # 60.4 cm en 1461 días = 15.1 cm/año
    ],
)
def test_velocity_boundary_15_cm_per_year(current_standing, expected):
    previous = ms(days=0, standing="100.0", weight="20.0", sitting="52.0")
    current = MeasureSet(
        evaluation_date=BASE_DATE + timedelta(days=1461),  # 4 años de 365,25 días
        weight_kg=Decimal("20.0"),
        standing_height_cm=Decimal(current_standing),
        sitting_height_cm=Decimal("83.0"),
    )
    assert ("height_velocity_implausible" in codes(check_plausibility(current, previous))) is expected


def test_velocity_ignores_a_negative_gain():
    previous = ms(days=0, standing="150.0")
    result = check_plausibility(ms(days=200, standing="140.0", sitting="72.0"), previous)
    assert "height_velocity_implausible" not in codes(result)
    assert "height_decreased" in codes(result)


# ---------------------------------------------------------------------------
# weight_change_large: |Δ| / previous > 10 %, ambos sentidos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("weight", "expected"),
    [
        ("44.0", False),  # +10.0 %
        ("44.04", True),  # +10.1 %
        ("36.0", False),  # -10.0 %
        ("35.96", True),  # -10.1 %
        ("40.0", False),
    ],
)
def test_weight_change_boundary_both_directions(weight, expected):
    result = check_plausibility(ms(days=30, weight=weight), PREVIOUS)
    assert ("weight_change_large" in codes(result)) is expected


def test_weight_change_reports_weight_measure():
    (warning,) = check_plausibility(ms(days=30, weight="50.0"), PREVIOUS)
    assert (warning.code, warning.measure) == ("weight_change_large", "weight")


# ---------------------------------------------------------------------------
# sitting_ratio_atypical: sentado/de pie fuera de [0.47, 0.57]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sitting", "expected"),
    [
        ("70.5", False),  # 0.47 exacto
        ("85.5", False),  # 0.57 exacto
        ("70.4", True),  # 0.4693
        ("85.6", True),  # 0.5707
        ("112.5", True),  # 0.75: banco sin restar
    ],
)
def test_sitting_ratio_boundary(sitting, expected):
    result = check_plausibility(ms(days=30, sitting=sitting), PREVIOUS)
    assert ("sitting_ratio_atypical" in codes(result)) is expected


def test_sitting_ratio_reports_sitting_height_measure():
    (warning,) = check_plausibility(ms(days=30, sitting="112.5"), PREVIOUS)
    assert (warning.code, warning.measure) == ("sitting_ratio_atypical", "sitting_height")


# ---------------------------------------------------------------------------
# arm_span_ratio_atypical: envergadura/de pie fuera de [0.90, 1.10]; solo si hay envergadura
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arm_span", "expected"),
    [
        ("135.0", False),  # 0.90 exacto
        ("165.0", False),  # 1.10 exacto
        ("134.9", True),
        ("165.1", True),
        ("150.0", False),
    ],
)
def test_arm_span_ratio_boundary(arm_span, expected):
    result = check_plausibility(ms(days=30, arm_span=arm_span), PREVIOUS)
    assert ("arm_span_ratio_atypical" in codes(result)) is expected


def test_arm_span_none_never_warns_even_with_other_atypical_values():
    result = check_plausibility(ms(days=30, sitting="112.5", arm_span=None), PREVIOUS)
    assert "arm_span_ratio_atypical" not in codes(result)


def test_arm_span_reports_arm_span_measure():
    (warning,) = check_plausibility(ms(days=30, arm_span="120.0"), PREVIOUS)
    assert (warning.code, warning.measure) == ("arm_span_ratio_atypical", "arm_span")


# ---------------------------------------------------------------------------
# Primera evaluación y combinaciones
# ---------------------------------------------------------------------------


def test_first_evaluation_only_evaluates_ratio_rules():
    """Sin evaluación previa no hay reglas de cambio: solo proporciones."""
    result = check_plausibility(
        ms(weight="20.0", standing="150.0", sitting="112.5", arm_span="120.0"), None
    )
    assert codes(result) == ["sitting_ratio_atypical", "arm_span_ratio_atypical"]


def test_first_evaluation_with_normal_values_has_no_warnings():
    assert check_plausibility(ms(), None) == []


def test_all_five_rules_can_fire_together_in_stable_order():
    previous = ms(days=0, standing="150.0", weight="40.0")
    current = ms(days=30, standing="148.0", weight="50.0", sitting="112.5", arm_span="120.0")
    assert codes(check_plausibility(current, previous)) == [
        "height_decreased",
        "weight_change_large",
        "sitting_ratio_atypical",
        "arm_span_ratio_atypical",
    ]
    velocity = check_plausibility(
        ms(days=90, standing="160.0", sitting="83.0"), ms(days=0, standing="150.0")
    )
    assert codes(velocity) == ["height_velocity_implausible"]  # 10 cm en 90 d = 40.6 cm/año


def test_normal_growth_produces_no_warnings():
    # +3 cm y +1.5 kg en 180 días (6.1 cm/año, +3.75 %)
    assert check_plausibility(ms(days=180, standing="153.0", weight="41.5", sitting="79.5"), PREVIOUS) == []


# ---------------------------------------------------------------------------
# flags_for_series: misma definición que el dry-run
# ---------------------------------------------------------------------------


def _rec(record_id: int, *, days: int, **kwargs) -> SimpleNamespace:
    m = ms(days=days, **kwargs)
    return SimpleNamespace(
        id=record_id,
        evaluation_date=m.evaluation_date,
        weight_kg=m.weight_kg,
        standing_height_cm=m.standing_height_cm,
        sitting_height_cm=m.sitting_height_cm,
        arm_span_cm=m.arm_span_cm,
    )


def test_flags_for_series_matches_dry_run_and_first_record_only_gets_ratio_rules():
    records = [
        _rec(1, days=0, sitting="112.5"),  # primera: solo proporción
        _rec(2, days=30, standing="140.0", sitting="72.8"),  # bajó 10 cm
        _rec(3, days=60, standing="141.0", weight="52.0", sitting="73.3"),  # +30 % peso
    ]
    flags = flags_for_series(records)
    assert flags[1] == ["sitting_ratio_atypical"]
    assert flags[2] == ["height_decreased"]
    assert flags[3] == ["weight_change_large"]
    for previous, current in zip(records, records[1:], strict=False):
        assert flags[current.id] == codes(
            check_plausibility(
                MeasureSet(
                    current.evaluation_date, current.weight_kg, current.standing_height_cm,
                    current.sitting_height_cm, current.arm_span_cm,
                ),
                MeasureSet(
                    previous.evaluation_date, previous.weight_kg, previous.standing_height_cm,
                    previous.sitting_height_cm, previous.arm_span_cm,
                ),
            )
        )


def test_flags_for_series_does_not_depend_on_input_order():
    records = [_rec(1, days=0), _rec(2, days=30, standing="140.0", sitting="72.8")]
    assert flags_for_series(list(reversed(records))) == flags_for_series(records)


def test_flags_for_series_every_record_has_a_key_even_when_clean():
    flags = flags_for_series([_rec(1, days=0), _rec(2, days=180, standing="153.0", weight="41.5", sitting="79.5")])
    assert flags == {1: [], 2: []}


def test_flags_for_series_empty_input():
    assert flags_for_series([]) == {}
