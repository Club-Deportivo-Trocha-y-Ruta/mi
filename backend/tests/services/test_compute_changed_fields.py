"""Unit tests for `compute_changed_fields` / `_normalise` / `snapshot`
(contracts/audit-recording.md §2, §9 T2).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

import pytest

from app.services.audit import AuditContractError, compute_changed_fields, snapshot


class SessionStatus(str, Enum):
    PLANNED = "planned"
    EXECUTED = "executed"


def test_worked_example_from_contract_section_2_3() -> None:
    before = {"status": SessionStatus.PLANNED, "duration_min": 90, "location": "Pance"}
    after = {"status": SessionStatus.EXECUTED, "duration_min": 90, "location": "Cerro"}
    allow = frozenset(
        {"status", "session_kind", "scheduled_date", "duration_min", "calendar_event_id"}
    )

    changed, diff = compute_changed_fields(before, after, allow)

    assert changed == ["location", "status"]
    assert diff == {"status": ("planned", "executed")}


@pytest.mark.parametrize(
    ("before", "after", "expect_changed"),
    [
        (
            {"status": SessionStatus.PLANNED},
            {"status": SessionStatus.EXECUTED},
            True,
        ),
        (
            {"when": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)},
            {"when": datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)},
            True,
        ),
        (
            {"day": date(2026, 1, 1)},
            {"day": date(2026, 1, 2)},
            True,
        ),
        (
            {"amount": Decimal("45.50")},
            {"amount": Decimal("45.5")},
            True,
        ),
        (
            {"tags": {"a", "b"}},
            {"tags": {"b", "c"}},
            True,
        ),
    ],
)
def test_normalisation_one_case_each(before, after, expect_changed) -> None:
    key = next(iter(before))
    allow = frozenset({key})
    changed, diff = compute_changed_fields(before, after, allow)
    assert (key in changed) is expect_changed
    if expect_changed:
        assert key in diff


def test_decimal_semantically_equal_but_different_repr_reports_change() -> None:
    # Decimal("45.50") != Decimal("45.5") is False numerically-equal-but the
    # str() normalisation used for storage differs, so contract §2.2 says
    # this is reported. Accepted per contract: no Decimal column is
    # allow-listed anywhere, so only the field *name* is affected.
    before = {"amount": Decimal("45.50")}
    after = {"amount": Decimal("45.5")}
    changed, diff = compute_changed_fields(before, after, frozenset({"amount"}))
    assert changed == ["amount"]


def test_key_present_in_only_one_mapping_is_skipped() -> None:
    before = {"status": "planned", "duration_min": 90}
    after = {"status": "planned", "location": "Cerro"}
    changed, diff = compute_changed_fields(
        before, after, frozenset({"status", "duration_min", "location"})
    )
    assert changed == []
    assert diff == {}


def test_identical_mappings_return_empty() -> None:
    m = {"status": "planned", "duration_min": 90}
    changed, diff = compute_changed_fields(m, dict(m), frozenset({"status", "duration_min"}))
    assert changed == []
    assert diff == {}


def test_changed_fields_is_sorted_and_stable() -> None:
    before = {"z_field": 1, "a_field": 1, "m_field": 1}
    after = {"z_field": 2, "a_field": 2, "m_field": 2}
    allow = frozenset({"z_field", "a_field", "m_field"})

    changed_1, _ = compute_changed_fields(before, after, allow)
    changed_2, _ = compute_changed_fields(before, after, allow)

    assert changed_1 == ["a_field", "m_field", "z_field"]
    assert changed_1 == changed_2


def test_unserialisable_value_raises_audit_contract_error() -> None:
    class Unserialisable:
        pass

    before = {"blob": Unserialisable()}
    after = {"blob": Unserialisable()}
    with pytest.raises(AuditContractError):
        compute_changed_fields(before, after, frozenset({"blob"}))


def test_snapshot_reads_listed_attributes() -> None:
    class Obj:
        def __init__(self) -> None:
            self.status = "planned"
            self.duration_min = 90
            self.location = "Pance"

    obj = Obj()
    snap = snapshot(obj, "status", "duration_min")
    assert snap == {"status": "planned", "duration_min": 90}
    assert "location" not in snap
