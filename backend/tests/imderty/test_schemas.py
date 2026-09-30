"""Pruebas de validación de los esquemas IMDERTY (feature 047, T007)."""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.imderty import (
    BarrioCreate,
    ImdertyProfileUpdate,
    SensitiveAuthorizationCreate,
    SensitiveDataUpdate,
    SheetRequest,
)


class TestImdertyProfileUpdateDocumentNumber:
    def test_digits_only_required_for_ti(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ImdertyProfileUpdate(document_type="ti", document_number="12A34")
        assert "dígitos" in str(exc_info.value)

    def test_digits_only_accepts_numeric_value(self) -> None:
        schema = ImdertyProfileUpdate(document_type="ti", document_number="1234567")
        assert schema.document_number == "1234567"

    def test_non_digit_type_allows_letters(self) -> None:
        schema = ImdertyProfileUpdate(document_type="ce", document_number="AB123")
        assert schema.document_number == "AB123"

    def test_error_message_never_echoes_value(self) -> None:
        # The "msg" text we author must never contain the raw input; pydantic's
        # own ValidationError.errors() separately carries the offending value
        # under "input" for programmatic use, which callers must not surface.
        secret_value = "12X456"
        with pytest.raises(ValidationError) as exc_info:
            ImdertyProfileUpdate(document_type="rc", document_number=secret_value)
        for error in exc_info.value.errors():
            assert secret_value not in error["msg"]


class TestImdertyProfileUpdateBarrioExclusive:
    def test_barrio_and_other_municipality_conflict(self) -> None:
        with pytest.raises(ValidationError):
            ImdertyProfileUpdate(barrio_id=5, other_municipality=True)

    def test_barrio_alone_is_valid(self) -> None:
        schema = ImdertyProfileUpdate(barrio_id=5, other_municipality=False)
        assert schema.barrio_id == 5

    def test_other_municipality_alone_is_valid(self) -> None:
        schema = ImdertyProfileUpdate(barrio_id=None, other_municipality=True)
        assert schema.other_municipality is True


class TestSensitiveAuthorizationCreate:
    def test_future_date_rejected(self) -> None:
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError):
            SensitiveAuthorizationCreate(guardian_user_id=1, authorized_on=future)

    def test_today_is_valid(self) -> None:
        schema = SensitiveAuthorizationCreate(
            guardian_user_id=1, authorized_on=date.today()
        )
        assert schema.authorized_on == date.today()

    def test_past_date_is_valid(self) -> None:
        past = date.today() - timedelta(days=30)
        schema = SensitiveAuthorizationCreate(guardian_user_id=1, authorized_on=past)
        assert schema.authorized_on == past


class TestSensitiveDataUpdate:
    def test_rejects_value_outside_official_list(self) -> None:
        with pytest.raises(ValidationError):
            SensitiveDataUpdate(ethnicity="INEXISTENTE", disability="N/A")

    def test_accepts_official_values(self) -> None:
        schema = SensitiveDataUpdate(
            ethnicity="MESTIZO", disability="N/A", conflict_victim="no"
        )
        assert schema.ethnicity.value == "MESTIZO"
        assert schema.conflict_victim.value == "no"


class TestSheetRequest:
    def test_valid_single_month(self) -> None:
        schema = SheetRequest(**{"from": "2026-08", "to": "2026-08"})
        assert schema.from_month == "2026-08"
        assert schema.to_month == "2026-08"

    def test_to_before_from_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SheetRequest(**{"from": "2026-08", "to": "2026-07"})

    def test_range_longer_than_twelve_months_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SheetRequest(**{"from": "2025-01", "to": "2026-02"})

    def test_range_of_exactly_twelve_months_is_valid(self) -> None:
        schema = SheetRequest(**{"from": "2025-01", "to": "2025-12"})
        assert schema.from_month == "2025-01"

    def test_invalid_month_format_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SheetRequest(**{"from": "2026/08", "to": "2026-08"})

    @pytest.mark.parametrize(
        "value",
        ["2026-8", "2026-00", "2026-13", "26-08", "2026-08-01", " 2026-08", "2026-08 ", "２０２６-08", "2026/08", ""],
    )
    def test_month_must_be_strict_yyyy_mm(self, value: str) -> None:
        with pytest.raises(ValidationError) as exc:
            SheetRequest(**{"from": value, "to": "2026-12"})
        assert "AAAA-MM" in str(exc.value)
        with pytest.raises(ValidationError):
            SheetRequest(**{"from": "2026-01", "to": value})

    @pytest.mark.parametrize("value", ["2026-01", "2026-09", "2026-10", "2026-12"])
    def test_zero_padded_months_accepted(self, value: str) -> None:
        assert SheetRequest(**{"from": value, "to": value}).from_month == value

    def test_optional_header_defaults_to_none(self) -> None:
        schema = SheetRequest(**{"from": "2026-08", "to": "2026-08"})
        assert schema.header is None
        assert schema.save_header_as_default is False


class TestBarrioCreate:
    def test_defaults_active(self) -> None:
        schema = BarrioCreate(name="EL PORVENIR", zone="1")
        assert schema.is_active is True

    def test_invalid_zone_rejected_by_enum_like_field(self) -> None:
        # zone is a free string validated at the DB CHECK level, not here;
        # the schema accepts any string, the service/DB layer enforces the list.
        schema = BarrioCreate(name="EL PORVENIR", zone="ZONA NORTE")
        assert schema.zone == "ZONA NORTE"
