"""Unit tests directos de ``_resolve_age``/``_resolve_ltad`` — feature
"adult athlete path".

Cubre el resolver de edad compartido por v1/v2/v3 (rango plausible 6-80,
antes 6-20 — un atleta adulto real caía en el fallback=12) y el resolver de
grupo LTAD (acepta ``LTADGroup.ADULTO`` desde ``state["ltad_group"]``).

Datos 100% ficticios (privacidad de menores, CLAUDE.md).
"""
from __future__ import annotations

import logging

import pytest

from app.services.race.ai.nodes.analyst_agent import _resolve_age, _resolve_ltad
from app.services.race.schemas import LTADGroup


@pytest.mark.parametrize("age", [6, 12, 18, 31, 65, 80])
def test_resolve_age_within_plausible_range_passes_through(age):
    assert _resolve_age({"athlete_age": age}) == age


@pytest.mark.parametrize("age", [5, 81, 0, -1, 200])
def test_resolve_age_outside_plausible_range_falls_back_with_warning(age, caplog):
    with caplog.at_level(logging.WARNING):
        result = _resolve_age({"athlete_age": age})
    assert result == 12
    assert any("usando fallback=12" in r.message for r in caplog.records)


def test_resolve_age_missing_falls_back_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        result = _resolve_age({})
    assert result == 12
    assert any("usando fallback=12" in r.message for r in caplog.records)


def test_resolve_age_non_int_falls_back():
    """Un float o string en state (dato corrupto) también cae al fallback —
    ``isinstance(age, int)`` es estricto a propósito."""
    assert _resolve_age({"athlete_age": 31.0}) == 12
    assert _resolve_age({"athlete_age": "31"}) == 12


def test_resolve_ltad_accepts_adulto_string():
    assert _resolve_ltad({"ltad_group": "adulto"}) == LTADGroup.ADULTO


def test_resolve_ltad_accepts_adulto_enum_instance():
    assert _resolve_ltad({"ltad_group": LTADGroup.ADULTO}) == LTADGroup.ADULTO


def test_resolve_ltad_falls_back_to_bambino_on_invalid_value(caplog):
    with caplog.at_level(logging.WARNING):
        result = _resolve_ltad({"ltad_group": "no-existe"})
    assert result == LTADGroup.BAMBINO
