"""Tests para la integración del bloque ``percentile_curves`` en
``newsletter_builder._build_percentile_charts_block``.

Garantiza:
1. El bloque aparece SOLO en pdf_only_blocks con las 3 claves (height/bmi/weight).
2. El bloque NO aparece (ni indirectamente) en email_blocks.
3. Se omite del snapshot si los 3 indicadores carecen de datos.
4. Si build_percentile_chart_ctx falla para height, se cataloga como
   ``growth_chart_unavailable`` pero bmi y weight siguen presentes.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.training.newsletter_builder import build_newsletter_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_athlete() -> SimpleNamespace:
    sex = SimpleNamespace(value="M")
    return SimpleNamespace(
        id=1,
        club_id=10,
        first_name="Ficticio",
        last_name="Atleta",
        birth_date=date(2014, 6, 1),
        sex=sex,
        height_cm=152.0,
    )


def _make_record(eval_date: date, h: float, w: float, age_at_phv: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=hash(eval_date),
        athlete_id=1,
        evaluation_date=eval_date,
        standing_height_cm=h,
        weight_kg=w,
        sitting_height_cm=h * 0.5,
        leg_length_cm=h * 0.5,
        arm_span_cm=h + 1.0,
        leg_sitting_ratio=1.0,
        bmi=20.0,
        height_z_score=0.1,
        height_percentile=55.0,
        bmi_z_score=0.2,
        bmi_percentile=58.0,
        weight_z_score=0.15,
        weight_percentile=56.0,
        nutritional_status=SimpleNamespace(value="adecuado"),
        nutritional_status_height=SimpleNamespace(value="talla_adecuada"),
        nutritional_status_bmi=SimpleNamespace(value="adecuado"),
        maturity_offset=0.0,
        age_at_phv=age_at_phv,
        maturation_status=SimpleNamespace(value="Pre-PHV"),
        training_implications=None,
        notes=None,
    )


def _make_scalars(items: list) -> Any:
    res = MagicMock()
    res.scalars.return_value = res
    res.all.return_value = items
    res.scalar_one_or_none.return_value = items[0] if items else None
    return res


def _build_mock_execute(athlete, records: list):
    """Side-effect que devuelve atleta primero y registros para la query antropo."""
    call_state = {"n": 0}

    async def mock_execute(stmt):
        call_state["n"] += 1
        stmt_str = str(stmt).lower()
        # 1ra llamada → atleta
        if call_state["n"] == 1:
            return _make_scalars([athlete])
        # Cualquier query a AnthropometricRecord → records
        if "anthropometric_records" in stmt_str:
            return _make_scalars(records)
        return _make_scalars([])

    return mock_execute


# ---------------------------------------------------------------------------
# B.1 percentile_curves vive en pdf_only_blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_percentile_curves_in_pdf_only_blocks():
    athlete = _make_athlete()
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0, age_at_phv=13.5),
        _make_record(date(2025, 12, 1), 145.0, 38.0, age_at_phv=13.5),
        _make_record(date(2026, 4, 1), 148.0, 40.0, age_at_phv=13.5),
    ]

    db = MagicMock()
    db.execute = _build_mock_execute(athlete, records)
    db.flush = AsyncMock()
    db.add = MagicMock()

    # Inyectamos un ctx fake para evitar dependencia de get_reference_curve real
    async def fake_ctx(db, athlete_id, birth_date, sex, records, indicator, phv_age_decimal=None):
        return {
            "enough_data": True,
            "reason_no_data": None,
            "indicator": indicator,
            "indicator_label_es": {"height": "Talla (cm)", "bmi": "IMC (kg/m²)", "weight": "Peso (kg)"}[indicator],
            "sex": sex,
            "viewbox": "0 0 400 260",
            "width": 400,
            "height": 260,
            "x_axis": {"min_months": 120.0, "max_months": 180.0, "ticks": [120.0, 132.0]},
            "y_axis": {"min": 130.0, "max": 165.0, "ticks": [130.0]},
            "curves": {
                "p3":  {"path": "M 42,200 L 50,180", "stroke_dasharray": "2,2", "color": "#e74c3c"},
                "p25": {"path": "M 42,180 L 50,160", "stroke_dasharray": "6,2", "color": "#f39c12"},
                "p50": {"path": "M 42,160 L 50,140", "stroke_dasharray": "",    "color": "#27ae60"},
                "p75": {"path": "M 42,140 L 50,120", "stroke_dasharray": "6,2", "color": "#f39c12"},
                "p97": {"path": "M 42,120 L 50,100", "stroke_dasharray": "2,2", "color": "#e74c3c"},
            },
            "athlete": {"polyline_points": "42,200 50,180", "points": [{"x": 42.0, "y": 200.0}]},
            "phv_marker": None,
        }

    with patch(
        "app.services.training.growth_chart_builder.build_percentile_chart_ctx",
        side_effect=fake_ctx,
    ):
        snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    pdf_blocks = snapshot["pdf_only_blocks"]
    assert "percentile_curves" in pdf_blocks
    curves = pdf_blocks["percentile_curves"]
    # 3 indicadores
    assert set(curves.keys()) == {"height", "bmi", "weight"}
    for ind in ("height", "bmi", "weight"):
        assert curves[ind]["enough_data"] is True


# ---------------------------------------------------------------------------
# B.2 percentile_curves NUNCA en email_blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_percentile_curves_NOT_in_email_blocks():
    athlete = _make_athlete()
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2025, 12, 1), 145.0, 38.0),
    ]

    db = MagicMock()
    db.execute = _build_mock_execute(athlete, records)
    db.flush = AsyncMock()
    db.add = MagicMock()

    async def fake_ctx(db, athlete_id, birth_date, sex, records, indicator, phv_age_decimal=None):
        return {
            "enough_data": True,
            "reason_no_data": None,
            "indicator": indicator,
            "indicator_label_es": "X",
            "sex": sex,
            "viewbox": "0 0 400 260",
            "width": 400,
            "height": 260,
            "x_axis": {"min_months": 0.0, "max_months": 0.0, "ticks": []},
            "y_axis": {"min": 0.0, "max": 0.0, "ticks": []},
            "curves": {"p50": {"path": "M 0,0", "stroke_dasharray": "", "color": "#000"}},
            "athlete": {"polyline_points": "0,0", "points": [{"x": 0.0, "y": 0.0}]},
            "phv_marker": None,
        }

    with patch(
        "app.services.training.growth_chart_builder.build_percentile_chart_ctx",
        side_effect=fake_ctx,
    ):
        snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    email_blocks = snapshot["email_blocks"]
    # Verificación dura: la clave no debe estar
    assert "percentile_curves" not in email_blocks
    # Verificación de serialización: el string completo no debe traer la key
    serialized = json.dumps(email_blocks, default=str)
    assert "percentile_curves" not in serialized
    assert "polyline_points" not in serialized
    assert "viewbox" not in serialized


# ---------------------------------------------------------------------------
# B.3 Bloque ausente cuando no hay datos suficientes para ningún indicador
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_percentile_curves_omitted_when_no_data():
    athlete = _make_athlete()
    db = MagicMock()
    # records vacíos
    db.execute = _build_mock_execute(athlete, [])
    db.flush = AsyncMock()
    db.add = MagicMock()

    snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)
    pdf_blocks = snapshot["pdf_only_blocks"]
    # Sin records → ningún indicador con enough_data → key ausente
    assert "percentile_curves" not in pdf_blocks


# ---------------------------------------------------------------------------
# B.4 growth_chart_unavailable cuando build_percentile_chart_ctx falla
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_growth_chart_unavailable_on_exception():
    """Si build_percentile_chart_ctx levanta, se cataloga el indicador
    como growth_chart_unavailable sin reventar el snapshot completo."""
    athlete = _make_athlete()
    records = [
        _make_record(date(2025, 6, 1), 142.0, 36.0),
        _make_record(date(2025, 12, 1), 145.0, 38.0),
        _make_record(date(2026, 4, 1), 148.0, 40.0),
    ]

    db = MagicMock()
    db.execute = _build_mock_execute(athlete, records)
    db.flush = AsyncMock()
    db.add = MagicMock()

    call_state = {"n": 0}

    async def fake_ctx(db, athlete_id, birth_date, sex, records, indicator, phv_age_decimal=None):
        call_state["n"] += 1
        # El primer indicador (height) lanza; los demás OK
        if indicator == "height":
            raise RuntimeError("get_reference_curve unavailable")
        return {
            "enough_data": True,
            "reason_no_data": None,
            "indicator": indicator,
            "indicator_label_es": "X",
            "sex": sex,
            "viewbox": "0 0 400 260",
            "width": 400,
            "height": 260,
            "x_axis": {"min_months": 0.0, "max_months": 0.0, "ticks": []},
            "y_axis": {"min": 0.0, "max": 0.0, "ticks": []},
            "curves": {"p50": {"path": "M 0,0", "stroke_dasharray": "", "color": "#000"}},
            "athlete": {"polyline_points": "0,0", "points": [{"x": 0.0, "y": 0.0}]},
            "phv_marker": None,
        }

    with patch(
        "app.services.training.growth_chart_builder.build_percentile_chart_ctx",
        side_effect=fake_ctx,
    ):
        snapshot = await build_newsletter_metrics(db, athlete.id, 2026, 4)

    curves = snapshot["pdf_only_blocks"]["percentile_curves"]
    # height fue marcado como unavailable
    assert curves["height"]["enough_data"] is False
    assert curves["height"]["reason_no_data"] == "growth_chart_unavailable"
    # bmi y weight siguen presentes con datos
    assert curves["bmi"]["enough_data"] is True
    assert curves["weight"]["enough_data"] is True
