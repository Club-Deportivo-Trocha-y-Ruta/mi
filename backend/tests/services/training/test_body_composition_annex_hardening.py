"""`stage_log_builder.body_composition_annex` only ever yields the fixed family
copy (feature 046, T069 privacy audit finding F4).

The family newsletter PDF renders whatever the persisted `metrics_snapshot`
holds. The annex helper re-maps it onto `FAMILY_COPY` so a tampered or
unexpected snapshot (coach-only rojo label, numbers in the sentence) never
reaches the family PDF. Synthetic data only.
"""
from __future__ import annotations

import pytest

from app.services.body_composition import FAMILY_COPY, NEWSLETTER_NOTICE
from app.services.training.stage_log_builder import body_composition_annex


def _snapshot(block: object) -> dict:
    return {"pdf_only_blocks": {"body_composition": block}}


@pytest.mark.parametrize("band", ["verde", "ambar"])
def test_known_family_label_returns_the_fixed_copy(band: str) -> None:
    annex = body_composition_annex(
        _snapshot(
            {
                "family_label": FAMILY_COPY[band]["family_label"],
                "family_sentence": "Texto alterado con 18 % y 32 mm",
                "notice_text": "otro aviso",
                "band": "rojo",
            }
        )
    )
    assert annex == {
        "family_label": FAMILY_COPY[band]["family_label"],
        "family_sentence": FAMILY_COPY[band]["family_sentence"],
        "notice_text": NEWSLETTER_NOTICE,
    }


@pytest.mark.parametrize(
    "block",
    [
        {"family_label": "Requiere acompañamiento profesional", "family_sentence": "x", "notice_text": "y"},
        {"family_label": None},
        "not-a-dict",
        None,
    ],
)
def test_unexpected_block_is_dropped(block: object) -> None:
    assert body_composition_annex(_snapshot(block)) is None


def test_missing_block_is_none() -> None:
    assert body_composition_annex({}) is None
    assert body_composition_annex({"pdf_only_blocks": None}) is None
