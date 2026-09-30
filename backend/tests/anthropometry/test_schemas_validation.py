"""Feature 048 (T009): validación de servidor de la captura antropométrica y
omisión de `can_modify`/`plausibility_flags` en la respuesta.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.anthropometry import (
    AnthropometryCreate,
    AnthropometryOut,
    AnthropometryUpdate,
    PlausibilityCheckIn,
    PlausibilityCheckOut,
    RosterRowOut,
)

VALID: dict[str, Any] = {
    "evaluation_date": date(2026, 9, 1),
    "weight_kg": "41.2",
    "standing_height_cm": "152.3",
    "sitting_height_cm": "78.1",
    "arm_span_cm": None,
}


def _error_types(exc: ValidationError) -> list[str]:
    return [e["type"] for e in exc.errors()]


@pytest.mark.parametrize("schema", [AnthropometryCreate, AnthropometryUpdate, PlausibilityCheckIn])
def test_valid_payload_accepted(schema: type) -> None:
    obj = schema(**VALID)
    assert obj.weight_kg == Decimal("41.2")
    assert obj.notes is None
    assert obj.arm_span_cm is None


@pytest.mark.parametrize(
    ("field", "value", "ok"),
    [
        ("weight_kg", "20", True),
        ("weight_kg", "150", True),
        ("weight_kg", "19.99", False),
        ("weight_kg", "150.01", False),
        ("standing_height_cm", "100", True),
        ("standing_height_cm", "99.9", False),
        ("standing_height_cm", "220.1", False),
        ("sitting_height_cm", "50", None),  # rango ok; la proporción lo rechaza
        ("sitting_height_cm", "49.9", False),
        ("sitting_height_cm", "120.1", False),
        ("arm_span_cm", "100", True),
        ("arm_span_cm", "220", True),
        ("arm_span_cm", "99.9", False),
        ("arm_span_cm", "220.1", False),
    ],
)
@pytest.mark.parametrize("schema", [AnthropometryCreate, AnthropometryUpdate, PlausibilityCheckIn])
def test_hard_ranges(schema: type, field: str, value: str, ok: bool | None) -> None:
    payload = {**VALID, field: value}
    if field == "standing_height_cm":
        # Mantener la proporción sentado/pie dentro de [0.40, 0.65].
        payload["sitting_height_cm"] = "55"
    if ok is None:
        with pytest.raises(ValidationError) as exc:
            schema(**payload)
        assert _error_types(exc.value) == ["sitting_ratio_impossible"]
    elif ok:
        schema(**payload)
    else:
        with pytest.raises(ValidationError) as exc:
            schema(**payload)
        assert field in {e["loc"][0] for e in exc.value.errors()}


@pytest.mark.parametrize(
    ("sitting", "standing", "ok"),
    [
        ("60", "150", True),  # 0.40 exacto
        ("97.5", "150", True),  # 0.65 exacto
        ("59.9", "150", False),
        ("97.6", "150", False),
        ("112", "150", False),  # banco sin restar (≈ 0.75)
    ],
)
def test_sitting_ratio_impossible(sitting: str, standing: str, ok: bool) -> None:
    payload = {**VALID, "sitting_height_cm": sitting, "standing_height_cm": standing}
    if ok:
        AnthropometryCreate(**payload)
        return
    with pytest.raises(ValidationError) as exc:
        AnthropometryCreate(**payload)
    errors = exc.value.errors()
    assert [e["type"] for e in errors] == ["sitting_ratio_impossible"]
    # El mensaje nunca incluye los valores recibidos.
    assert sitting not in errors[0]["msg"] and standing not in errors[0]["msg"]


def test_future_date_rejected() -> None:
    with pytest.raises(ValidationError):
        AnthropometryUpdate(**{**VALID, "evaluation_date": date.today() + timedelta(days=1)})


def test_plausibility_check_in_record_id_optional() -> None:
    assert PlausibilityCheckIn(**VALID).record_id is None
    assert PlausibilityCheckIn(**VALID, record_id=7).record_id == 7


def test_plausibility_out_rejects_unknown_codes() -> None:
    out = PlausibilityCheckOut(
        warnings=[{"code": "weight_change_large", "measure": "weight"}],
        previous_evaluation_date=None,
    )
    assert out.warnings[0].measure == "weight"
    with pytest.raises(ValidationError):
        PlausibilityCheckOut(warnings=[{"code": "made_up", "measure": "weight"}])
    with pytest.raises(ValidationError):
        PlausibilityCheckOut(warnings=[{"code": "height_decreased", "measure": "knee"}])


def test_roster_row_shape() -> None:
    row = RosterRowOut(
        athlete_id=1,
        full_name="Deportista Demo",
        category="Infantil",
        sex="F",
        birth_date=date(2014, 1, 1),
        last_evaluation_date=None,
        has_record_on_date=False,
        skinfolds_eligible=True,
    )
    assert set(row.model_dump()) == {
        "athlete_id",
        "full_name",
        "category",
        "sex",
        "birth_date",
        "last_evaluation_date",
        "has_record_on_date",
        "skinfolds_eligible",
    }


# ---------------------------------------------------------------------------
# Omisión de claves (padres) vs. valores presentes (coach/admin)
# ---------------------------------------------------------------------------

_OUT_BASE: dict[str, Any] = {
    "id": 1,
    "athlete_id": 1,
    "evaluation_date": date(2026, 9, 1),
    "weight_kg": 41.2,
    "standing_height_cm": 152.3,
    "arm_span_cm": None,
    "sitting_height_cm": 78.1,
    "leg_length_cm": 74.2,
    "leg_sitting_ratio": 0.95,
    "maturity_offset": -1.2,
    "age_at_phv": 13.1,
    "maturation_status": "Pre-PHV",
    "training_implications": None,
    "evaluated_by": 1,
    "created_at": datetime(2026, 9, 1, 10, 0, 0),
    "notes": None,
}


def _client(can_modify: bool | None, flags: list[str] | None) -> TestClient:
    app = FastAPI()

    @app.get("/records", response_model=list[AnthropometryOut])
    def records() -> list[AnthropometryOut]:
        out = AnthropometryOut(**_OUT_BASE)
        out.can_modify = can_modify
        out.plausibility_flags = flags
        return [out]

    return TestClient(app)


def test_parent_payload_omits_flag_keys_but_keeps_other_nulls() -> None:
    item = _client(None, None).get("/records").json()[0]
    assert "can_modify" not in item
    assert "plausibility_flags" not in item
    # Los demás campos None se siguen enviando como null (contrato actual).
    assert "notes" in item and item["notes"] is None
    assert "arm_span_cm" in item and item["arm_span_cm"] is None
    assert "skinfolds" in item and item["skinfolds"] is None


def test_coach_payload_includes_flag_keys_even_when_false_or_empty() -> None:
    item = _client(False, []).get("/records").json()[0]
    assert item["can_modify"] is False
    assert item["plausibility_flags"] == []

    item = _client(True, ["height_decreased"]).get("/records").json()[0]
    assert item["can_modify"] is True
    assert item["plausibility_flags"] == ["height_decreased"]


@pytest.mark.parametrize("schema", [AnthropometryCreate, AnthropometryUpdate])
def test_notes_capped_at_2000_chars(schema: type) -> None:
    """privacy-audit P-1: un texto sin límite podía llegar a MySQL y filtrar
    valores en el traceback de un DataError; ahora es un 422 limpio."""
    assert schema(**VALID, notes="x" * 2000).notes == "x" * 2000
    with pytest.raises(ValidationError) as exc:
        schema(**VALID, notes="x" * 2001)
    assert "string_too_long" in _error_types(exc.value)
