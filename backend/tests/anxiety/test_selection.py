"""Unit tests for age-driven instrument selection (US1, FR-002/003)."""
from __future__ import annotations

import pytest

from app.services.anxiety.selection import select_instrument


def test_under_13_defaults_to_sas2():
    sel = select_instrument(11)
    assert sel.instrument == "sas2"
    assert sel.warning is None
    assert sel.override_used is False


def test_13_to_15_defaults_to_csai2r():
    sel = select_instrument(14)
    assert sel.instrument == "csai2r"
    assert sel.warning is None


def test_boundary_age_13_is_csai2r():
    assert select_instrument(13).instrument == "csai2r"


def test_under_13_override_to_csai2r_warns():
    sel = select_instrument(11, override="csai2r")
    assert sel.instrument == "csai2r"
    assert sel.override_used is True
    assert sel.warning is not None
    assert "13" in sel.warning


def test_13_15_override_no_warning():
    sel = select_instrument(14, override="csai2")
    assert sel.instrument == "csai2"
    assert sel.warning is None
    assert sel.override_used is True


def test_unknown_override_raises():
    with pytest.raises(ValueError):
        select_instrument(14, override="bdi")
