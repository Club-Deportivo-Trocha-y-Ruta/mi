"""Family-audience body-composition prompt block carries family-safe codes only
(feature 046, T069 privacy audit finding F3).

Spec clarification Q4 / FR-025: a population-reference extreme is coach-only
context ("reference-only ámbar is coach-only; the family sees 'En su curva
esperada'"). The analyst v2 prompt already tells the family-audience model not
to mention the reference, the declined sites or the number of sets — the
family block therefore must not hand those lines to the provider at all
(defense in depth: what the model never receives it cannot leak). The coach
block keeps them.

Synthetic fixtures only (no athlete/club data).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.schemas.body_composition import BodyCompositionReading, ReferenceContext
from app.services.ai.anthro import context as anthro_context


def _reference_only_reading() -> BodyCompositionReading:
    # Coach: ámbar by reference only (single set, triceps >= P95, two sites
    # declined) -> family_band verde (contract §3c).
    return BodyCompositionReading(
        sets_count=1,
        sum_change_code="none",
        weight_change_code="unavailable",
        height_growth_code="unavailable",
        velocity_code="unavailable",
        bmi_z_change_code="unavailable",
        reference_triceps=ReferenceContext(percentile=None, code="high_extreme"),
        reference_subscapular=ReferenceContext(percentile=None, code="normal"),
        ffm_trend_code="unavailable",
        sites_declined_count=2,
        band="ambar",
        family_band="verde",
        band_reason_code="reference_extreme",
        legs_missing=["previous_set"],
    )


def _leaf() -> dict:
    leaf = anthro_context._build_body_composition_dict(
        SimpleNamespace(evaluation_date=date(2026, 6, 1)), None, _reference_only_reading()
    )
    assert leaf is not None
    return leaf


def test_family_block_omits_reference_declined_sites_and_set_count() -> None:
    block = anthro_context._render_body_composition_block(_leaf(), "family")
    assert block is not None
    lowered = block.lower()
    assert "referencia" not in lowered
    assert "por encima de lo habitual" not in lowered
    assert "prefirió no medir" not in lowered
    assert "sets de pliegues" not in lowered
    assert "observación" not in lowered
    assert "En su curva esperada" in block


def test_coach_block_keeps_reference_and_declined_sites() -> None:
    block = anthro_context._render_body_composition_block(_leaf(), "coach")
    assert block is not None
    assert "referencia poblacional" in block
    assert "prefirió no medir" in block
    assert "Sets de pliegues registrados" in block
