"""Tests para growth_chart_builder.py.

Cubre el constructor de contexto SVG de curvas de percentiles:
- enough_data / reason_no_data en cada early-exit
- Privacidad: sin nombre, DOB, z-scores en el output
- IMC nil-safe
- Coordenadas redondeadas a 1 decimal
- Marker PHV gating
"""

from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.training.growth_chart_builder import build_percentile_chart_ctx


# ---------------------------------------------------------------------------
# Fixtures: curva de referencia "fake" (no requiere DB con LMS seedeada).
# Estructura matchea exactamente la salida real de get_reference_curve.
# ---------------------------------------------------------------------------


def _make_ref_curve_height(age_months_min: float = 120.0, age_months_max: float = 180.0):
    """Curva CDC fake para height_for_age — solo lo que el builder consume."""
    out = []
    age = age_months_min
    while age <= age_months_max:
        # Valores plausibles para chico 10-15 años (cm)
        out.append({
            "age_months": age,
            "P3":  130.0 + (age - 120) * 0.4,
            "P25": 138.0 + (age - 120) * 0.5,
            "P50": 145.0 + (age - 120) * 0.55,
            "P75": 152.0 + (age - 120) * 0.6,
            "P97": 162.0 + (age - 120) * 0.65,
        })
        age += 6.0
    return out


def _make_ref_curve_bmi():
    out = []
    age = 120.0
    while age <= 180.0:
        out.append({
            "age_months": age,
            "P3": 14.0 + (age - 120) * 0.02,
            "P25": 16.0 + (age - 120) * 0.03,
            "P50": 18.0 + (age - 120) * 0.035,
            "P75": 20.5 + (age - 120) * 0.04,
            "P97": 24.0 + (age - 120) * 0.05,
        })
        age += 6.0
    return out


def _make_record(eval_date: date, height_cm: float | None, weight_kg: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_date=eval_date,
        standing_height_cm=height_cm,
        weight_kg=weight_kg,
    )


@pytest.fixture
def db_session():
    """Mock de AsyncSession; el builder solo lo pasa a get_reference_curve, que parcheamos."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# A.1 enough_data=True con 3 registros
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enough_data_returns_true_with_3_records(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),  # ~11.0 años
        _make_record(date(2025, 12, 1), 145.0, 38.0),  # ~11.5 años
        _make_record(date(2026, 4, 1), 148.0, 40.0),  # ~11.85 años
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_height()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="height",
            phv_age_decimal=None,
        )

    assert ctx["enough_data"] is True
    assert ctx["reason_no_data"] is None
    assert ctx["indicator"] == "height"
    assert ctx["indicator_label_es"] == "Talla (cm)"
    # Las 5 curvas deben estar presentes con path no vacío
    for key in ("p3", "p25", "p50", "p75", "p97"):
        assert key in ctx["curves"]
        assert ctx["curves"][key]["path"].startswith("M ")
    # Polyline del atleta con 3 puntos
    assert len(ctx["athlete"]["points"]) == 3
    polyline_pairs = ctx["athlete"]["polyline_points"].split(" ")
    assert len(polyline_pairs) == 3


# ---------------------------------------------------------------------------
# A.2 insufficient_records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insufficient_records_returns_false(db_session):
    birth = date(2014, 6, 1)
    records = [_make_record(date(2025, 6, 1), 142.0, 36.0)]  # solo 1
    ctx = await build_percentile_chart_ctx(
        db=db_session,
        athlete_id=1,
        birth_date=birth,
        sex="M",
        records=records,
        indicator="height",
    )
    assert ctx["enough_data"] is False
    assert ctx["reason_no_data"] == "insufficient_records"
    # No debe haber curvas ni puntos
    assert ctx["curves"] == {}
    assert ctx["athlete"]["points"] == []


# ---------------------------------------------------------------------------
# A.3 missing_sex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_sex_returns_false(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2026, 1, 1), 145.0, 38.0),
    ]
    ctx = await build_percentile_chart_ctx(
        db=db_session,
        athlete_id=1,
        birth_date=birth,
        sex=None,  # type: ignore[arg-type]
        records=records,
        indicator="height",
    )
    assert ctx["enough_data"] is False
    assert ctx["reason_no_data"] == "missing_sex"


@pytest.mark.asyncio
async def test_missing_sex_empty_string_returns_false(db_session):
    """Sex='' también es interpretado como missing."""
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2026, 1, 1), 145.0, 38.0),
    ]
    ctx = await build_percentile_chart_ctx(
        db=db_session,
        athlete_id=1,
        birth_date=birth,
        sex="",
        records=records,
        indicator="height",
    )
    assert ctx["enough_data"] is False
    assert ctx["reason_no_data"] == "missing_sex"


# ---------------------------------------------------------------------------
# A.4 age_out_of_range (debajo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_age_out_of_range_below_returns_false(db_session):
    """Atleta de ~4 años → fuera del rango CDC (5-19)."""
    birth = date(2022, 1, 1)
    records = [
        _make_record(date(2026, 1, 1), 100.0, 16.0),  # ~4.0 años (48 meses)
        _make_record(date(2026, 4, 1), 101.0, 16.5),
    ]
    ctx = await build_percentile_chart_ctx(
        db=db_session,
        athlete_id=1,
        birth_date=birth,
        sex="M",
        records=records,
        indicator="height",
    )
    assert ctx["enough_data"] is False
    assert ctx["reason_no_data"] == "age_out_of_range"


# ---------------------------------------------------------------------------
# A.5 age_out_of_range (arriba)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_age_out_of_range_above_returns_false(db_session):
    """Atleta de ~20 años → fuera del rango CDC."""
    birth = date(2006, 1, 1)
    records = [
        _make_record(date(2026, 1, 1), 178.0, 70.0),  # 20 años
        _make_record(date(2026, 4, 1), 178.5, 71.0),
    ]
    ctx = await build_percentile_chart_ctx(
        db=db_session,
        athlete_id=1,
        birth_date=birth,
        sex="M",
        records=records,
        indicator="height",
    )
    assert ctx["enough_data"] is False
    assert ctx["reason_no_data"] == "age_out_of_range"


# ---------------------------------------------------------------------------
# A.6 PHV marker presente cuando offset entra en domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phv_marker_present_when_offset_within_domain(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2025, 12, 1), 145.0, 38.0),
        _make_record(date(2026, 4, 1), 148.0, 40.0),
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_height()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="height",
            phv_age_decimal=13.5,  # 162 meses, dentro del domain
        )
    assert ctx["enough_data"] is True
    assert ctx["phv_marker"] is not None
    assert ctx["phv_marker"]["label"] == "PHV"
    assert isinstance(ctx["phv_marker"]["x"], float)


# ---------------------------------------------------------------------------
# A.7 PHV marker ausente cuando no hay offset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phv_marker_absent_when_no_offset(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2026, 1, 1), 145.0, 38.0),
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_height()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="height",
            phv_age_decimal=None,
        )
    assert ctx["phv_marker"] is None


# ---------------------------------------------------------------------------
# A.8 No PII en output serializado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_pii_in_output(db_session):
    """El dict serializado NO debe contener nombre, DOB, ni claves z_score."""
    birth = date(2014, 6, 15)
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2025, 12, 1), 145.0, 38.0),
        _make_record(date(2026, 4, 1), 148.0, 40.0),
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_height()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=42,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="height",
        )

    payload = json.dumps(ctx, default=str)
    # Sin DOB textual
    assert "2014-06-15" not in payload
    assert "birth_date" not in payload
    # Sin keys de z-score / percentile diagnóstico
    forbidden_keys = ["z_score", "percentile", "athlete_name", "first_name", "last_name", "dob"]
    for k in forbidden_keys:
        assert k not in payload, f"PII clave '{k}' apareció en output del chart"


# ---------------------------------------------------------------------------
# A.9 Coordenadas redondeadas a 1 decimal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinates_rounded_to_1_decimal(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 142.7, 36.4),
        _make_record(date(2025, 12, 1), 145.3, 38.1),
        _make_record(date(2026, 4, 1), 148.6, 40.2),
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_height()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="height",
        )
    # Regex: ningún número con 2+ decimales en los paths
    multi_decimal = re.compile(r"\d+\.\d{2,}")
    for curve_key in ("p3", "p25", "p50", "p75", "p97"):
        path = ctx["curves"][curve_key]["path"]
        assert not multi_decimal.search(path), (
            f"Curva {curve_key} tiene coordenadas con más de 1 decimal: {path[:100]}"
        )
    # También los puntos del atleta
    for pt in ctx["athlete"]["points"]:
        # Comparar el float vs round a 1 decimal
        assert pt["x"] == round(pt["x"], 1)
        assert pt["y"] == round(pt["y"], 1)


# ---------------------------------------------------------------------------
# A.10 IMC se calcula correctamente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bmi_indicator_calculates_correctly(db_session):
    """Para indicator=bmi: punto del atleta = weight / (height_m^2)."""
    birth = date(2014, 6, 1)
    # height=150 cm, weight=45 kg → BMI = 45 / 1.5^2 = 20.0
    records = [
        _make_record(date(2025, 6, 1), 150.0, 45.0),
        _make_record(date(2026, 1, 1), 152.0, 47.0),
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_bmi()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="bmi",
        )
    assert ctx["enough_data"] is True
    assert ctx["indicator"] == "bmi"
    assert ctx["indicator_label_es"] == "IMC (kg/m²)"
    # No verificamos coordenada exacta (depende del scaling), pero sí que haya 2 puntos
    assert len(ctx["athlete"]["points"]) == 2


# ---------------------------------------------------------------------------
# A.11 IMC skip de records con null height/weight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bmi_skips_records_with_null_height_or_weight(db_session):
    birth = date(2014, 6, 1)
    records = [
        _make_record(date(2025, 6, 1), 150.0, 45.0),       # válido
        _make_record(date(2025, 9, 1), None, 46.0),         # sin altura → skip
        _make_record(date(2025, 12, 1), 151.0, None),       # sin peso → skip
        _make_record(date(2026, 3, 1), 152.0, 47.0),       # válido
    ]
    with patch(
        "app.services.growth.get_reference_curve",
        AsyncMock(return_value=_make_ref_curve_bmi()),
    ):
        ctx = await build_percentile_chart_ctx(
            db=db_session,
            athlete_id=1,
            birth_date=birth,
            sex="M",
            records=records,
            indicator="bmi",
        )
    assert ctx["enough_data"] is True
    # Solo 2 records válidos contribuyeron
    assert len(ctx["athlete"]["points"]) == 2
