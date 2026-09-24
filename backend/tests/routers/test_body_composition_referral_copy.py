"""Referral-note pattern copy is neutral (feature 046, T069 audit finding F1).

`contracts/skinfolds-api.md` §6: the referral note "never contains a
percentage, a millimetre value, a label or an institution name";
`docs/21-body-composition/research-safeguards-referral.md` §4: "a plain
description of the observed pattern — no clinical or diagnostic terms".
The coach card copy (`COACH_REASON_COPY`) is an instruction to the coach
("conversa…", "considera remitir…", "compatible con baja disponibilidad
energética", "≤ P5 o ≥ P95") and must never be pasted into the note that a
family hands to a health professional.
"""
from __future__ import annotations

import re
from typing import get_args

import pytest

from app.routers.body_composition import (
    _REFERRAL_PATTERN_ES,
    _REFERRAL_PATTERN_FALLBACK,
    _referral_observed_pattern,
)
from app.schemas.body_composition import BAND_REASON_CODE

_FORBIDDEN_SUBSTRINGS = (
    "disponibilidad energética",
    "red-s",
    "diagnóstic",
    "conversa",
    "remit",
    "remisión",
    "dieta",
    "calor",
    "déficit",
    "profesional",
    "p5",
    "p95",
    "percentil",
    "%",
    "mm",
)


def test_every_band_reason_code_has_a_neutral_referral_sentence() -> None:
    assert set(_REFERRAL_PATTERN_ES) == set(get_args(BAND_REASON_CODE))


@pytest.mark.parametrize("reason_code", sorted(get_args(BAND_REASON_CODE)))
def test_referral_sentence_has_no_number_label_or_coach_instruction(reason_code: str) -> None:
    sentence = _referral_observed_pattern(reason_code)
    lowered = sentence.lower()
    assert re.search(r"\d", sentence) is None, sentence
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in lowered, (reason_code, forbidden)
    # Continues "El club ha observado …" — lowercase noun phrase, no final period.
    assert sentence[0].islower()
    assert not sentence.endswith(".")


def test_unknown_reason_code_falls_back_to_the_generic_sentence() -> None:
    assert _referral_observed_pattern("not_a_code") == _REFERRAL_PATTERN_FALLBACK
