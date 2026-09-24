"""Property tests for the feature 042 prompt seam (T054).

Covers the seam between `app/services/ai/anthro/context.py` (the six
pre-formatted `*_block` strings), `app/services/ai/anthro/analyst.py::
_prompt_context` and `app/services/ai/anthro/prompts/loader.py::render_prompt`
— i.e. the exact string that leaves this process and reaches the configured
LLM provider. This is the privacy guarantee `specs/042-traceable-growth-ai`
exists to keep (CLAUDE.md: "no real name, birth date, medical detail, or
identifying data of a minor in ... AI-provider prompts";
`contracts/analysis-context.md` §3 "Forbidden, explicitly").

All fixtures are synthetic: hypothesis-generated names/dates/numbers, never a
real club member, athlete, or date. No DB is used — the helpers below call
`context.py`'s own private per-block renderers directly (same functions
`build_context()` calls internally, see `context.py:443-450`) on
already-sanitized leaves, so a test failure here means the renderer itself
leaks, not a fixture-construction mistake.

Four properties (per `specs/042-traceable-growth-ai/tasks.md` T054):

1. No club-forbidden name ever appears in the rendered prompt.
2. No z-score, percentile, raw band value, or absolute date (ISO, dd/mm/yyyy,
   Spanish month name) ever appears in the rendered prompt, even when the
   upstream leaves are deliberately constructed to carry them.
3. Coach free text (and its length) never reaches the prompt.
4. `sanitize_insight_context()`'s output keys are always a subset of
   `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.ai_explanation import AthleteAIExplanation
from app.schemas.body_composition import BodyCompositionReading, ReferenceContext
from app.services.ai.anthro import analyst as anthro_analyst
from app.services.ai.models import LLMMessage, LLMRequest
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.anthro import context as anthro_context
from app.services.ai.anthro import pipeline as anthro_pipeline
from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.prompts.loader import render_prompt
from app.services.ai.context_builders import (
    ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS,
    sanitize_insight_context,
)

# ---------------------------------------------------------------------------
# Shared helpers — mirror `context.py::build_context`'s final assembly
# (lines 434-450) exactly, so a passing test here is evidence about the real
# pipeline, not about a hand-rolled substitute.
# ---------------------------------------------------------------------------


def _blocks_from_context(context: AnalysisContext) -> dict:
    return {
        "identity_block": anthro_context._render_identity_block(context.identity),
        "measurement_deltas_block": anthro_context._render_measurement_deltas_block(
            context.measurement_deltas
        ),
        "longitudinal_series_block": anthro_context._render_longitudinal_series_block(
            context.longitudinal_series
        ),
        "growth_summary_block": anthro_context._render_growth_summary_block(
            context.growth_summary
        ),
        "training_load_block": anthro_context._render_training_load_block(
            context.training_load_window
        ),
        "previous_analysis_block": anthro_context._render_previous_analysis_block(
            context.previous_analysis
        ),
    }


def _render_prompt_for_context(context: AnalysisContext) -> str:
    """Full seam: `context_blocks` -> `analyst._prompt_context` -> `render_prompt`.

    Exactly the two calls `analyst.run_analyst()` makes before invoking the
    LLM (`analyst.py:237-238`) — this is the literal string a real run would
    send to the provider.
    """
    state = {"context_blocks": _blocks_from_context(context), "analysis_context": context}
    prompt_vars, prompt_version = anthro_analyst._prompt_context(state)
    return render_prompt(prompt_version, prompt_vars)


def _sanitized_context(
    *,
    identity: dict,
    measurement_deltas: dict | None,
    growth_summary: dict,
    longitudinal_series: list[dict],
    training_load_window: dict | None,
    previous_analysis: dict | None,
) -> AnalysisContext:
    """Applies `sanitize_insight_context` to every leaf, exactly as
    `build_context()` does (`context.py:388-432`), before assembling the
    `AnalysisContext`. Callers pass deliberately "dirty" leaves (allowed keys
    mixed with keys that must never reach the prompt) to prove the allow-list
    boundary — not the value of any one field — is what keeps the seam clean.
    """
    return AnalysisContext(
        identity=sanitize_insight_context(identity),
        measurement_deltas=(
            sanitize_insight_context(measurement_deltas)
            if measurement_deltas is not None
            else None
        ),
        longitudinal_series=[sanitize_insight_context(p) for p in longitudinal_series],
        growth_summary=sanitize_insight_context(growth_summary),
        training_load_window=(
            sanitize_insight_context(training_load_window)
            if training_load_window is not None
            else None
        ),
        previous_analysis=(
            sanitize_insight_context(previous_analysis) if previous_analysis is not None else None
        ),
    )


def _base_identity(audience: str) -> dict:
    return {
        "age_decimal": 12.5,
        "age_group": "10-12",
        "sex": "M",
        "category": "Sub-13",
        "audience": audience,
    }


_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

# General-purpose "any absolute date, in any of the three formats the feature
# must never emit" detector — independent of (and deliberately not imported
# from) `prechecks.py::_CALENDAR_DATE_PATTERN`, so this test does not merely
# echo that module's own opinion of itself.
_ABSOLUTE_DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    rf"|\b\d{{1,2}}\s+de\s+(?:{'|'.join(_MONTHS_ES)})(?:\s+de\s+\d{{4}})?\b"
    rf"|\b(?:{'|'.join(_MONTHS_ES)})\s+de\s+\d{{4}}\b",
    re.IGNORECASE,
)


def _iso_date(d: date) -> str:
    return d.isoformat()


def _dmy_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _spanish_date(d: date) -> str:
    return f"{d.day} de {_MONTHS_ES[d.month - 1]} de {d.year}"


_DATE_FORMATTERS = (_iso_date, _dmy_date, _spanish_date)

_dates_strategy = st.dates(min_value=date(2010, 1, 1), max_value=date(2030, 12, 31))
_forbidden_date_strings = st.builds(
    lambda d, fmt: fmt(d), _dates_strategy, st.sampled_from(_DATE_FORMATTERS)
)

# Synthetic club-member-like names: two capitalized words, letters only
# (no real athlete/parent from the club — CLAUDE.md). Mirrors the pattern
# already used for this exact purpose in
# `tests/services/race/ai/test_anonymize_conditions.py`.
_name_word = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), min_codepoint=65, max_codepoint=0x17F),
    min_size=4,
    max_size=10,
).filter(lambda s: s.isalpha())
_forbidden_name = st.builds(lambda a, b: f"{a} {b}", _name_word, _name_word)


# ---------------------------------------------------------------------------
# Property 1 — a club-forbidden name never survives into the rendered prompt.
# ---------------------------------------------------------------------------
#
# The only free-text field the allow-list admits into a prompt is
# `previous_analysis.summary_line` (`contracts/analysis-context.md` §2.6) —
# the athlete's OWN previous structured summary, carried forward for
# continuity (FR-010). Every other leaf is built exclusively from enums,
# booleans, and numbers computed by this codebase, never free text, so this
# is the one deliberate vector through which a name could re-enter a future
# prompt (e.g. a name that became club-forbidden only after an earlier,
# already-approved analysis was persisted). This test constructs that exact
# fixture — a previous structured row whose `summary_line` carries a
# synthetic forbidden name — and renders the next prompt from it.


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    name=_forbidden_name,
    weeks_since=st.integers(min_value=0, max_value=520),
    audience=st.sampled_from(["family", "coach"]),
)
def test_forbidden_name_in_previous_summary_never_reaches_rendered_prompt(
    name, weeks_since, audience
):
    previous_row = AthleteAIExplanation(
        structured_json={
            "summary_line": f"Se observa un patrón similar al comentado sobre {name} la vez anterior.",
            "confidence": {"level": "medium"},
        },
        generated_at=datetime.now(timezone.utc) - timedelta(weeks=weeks_since),
    )
    # Fixture validity: the name really is in the stored row we start from.
    assert name in previous_row.structured_json["summary_line"]

    # The real pipeline loads the club's forbidden-names list BEFORE building
    # the context and threads it in (pipeline.py), precisely so this seam can
    # scrub it. Passing it here is what makes this test exercise the seam the
    # way production does — an exact-match list is the only defence that works
    # on an arbitrarily shaped name, which is what this strategy generates.
    previous_analysis = anthro_context._build_previous_analysis_dict(
        previous_row, date.today(), [name]
    )
    assert previous_analysis is not None, (
        "fixture bug: _build_previous_analysis_dict returned None — the test "
        "proves nothing about the seam unless previous_analysis was built"
    )
    assert name not in previous_analysis["summary_line"], (
        "the scrub must happen at the context-building seam, before the "
        "summary line is ever rendered into a prompt"
    )

    context = _sanitized_context(
        identity=_base_identity(audience),
        measurement_deltas=None,
        growth_summary={},
        longitudinal_series=[],
        training_load_window=None,
        previous_analysis=previous_analysis,
    )

    prompt_text = _render_prompt_for_context(context)

    # THE ASSERTION FEATURE 042 EXISTS TO KEEP TRUE.
    assert not re.search(rf"\b{re.escape(name)}\b", prompt_text, re.IGNORECASE), (
        f"Forbidden name {name!r} leaked into the rendered analyst prompt via "
        "the previous_analysis continuity block (context.py:_render_previous_"
        "analysis_block embeds summary_line verbatim, with no forbidden-name "
        "scrub at the context-building seam — R06 only screens the CURRENT "
        "draft's own output post-generation, never the text re-injected "
        "into the NEXT prompt via previous_analysis)."
    )


# ---------------------------------------------------------------------------
# Property 2 — z-score / percentile / raw band value / absolute date never
# reach the rendered prompt, even when deliberately present upstream.
# ---------------------------------------------------------------------------


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    zscore=st.floats(min_value=-4.0, max_value=4.0, allow_nan=False, allow_infinity=False),
    percentile=st.floats(min_value=1.0, max_value=99.0, allow_nan=False, allow_infinity=False),
    band_value=st.floats(min_value=10.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    date_str=_forbidden_date_strings,
    audience=st.sampled_from(["family", "coach"]),
)
def test_zscore_percentile_band_and_absolute_dates_never_reach_rendered_prompt(
    zscore, percentile, band_value, date_str, audience
):
    # Distinctive, high-precision string forms: astronomically unlikely to
    # coincidentally match any static template text or any of the
    # deliberately-fixed allowed values used below (unlike a bare "2" or
    # "40", which really can appear inside "0-2"/"1-4" cardinality prose).
    zscore_str = f"{zscore:.5f}"
    percentile_str = f"{percentile:.5f}"
    band_value_str = f"{band_value:.5f}"

    identity = {
        **_base_identity(audience),
        "birth_date": date_str,  # forbidden: absolute date
        "height_z_score": zscore_str,  # forbidden: not on the allow-list
    }
    measurement_deltas = {
        "weeks_since_prev_measurement": 12,
        "delta_height_cm": 0.9,
        "delta_weight_kg": 1.1,
        "delta_height_significant": True,
        "delta_weight_significant": False,
        "crossed_phv_phase": False,
        "prev_maturation_status": "Pre-PHV",
        "phase_crossing_corroborated": False,
        "weight_percentile": percentile_str,  # forbidden
        "evaluation_date": date_str,  # forbidden
    }
    growth_summary = {
        "stage": "Pre-PHV",
        "expected_velocity_range_cm_year": (5.0, 8.0),
        "height_band": "adecuada",
        "alerts": [],
        "measurement_due_status": "al_dia",
        "raw_height_band_value": band_value_str,  # forbidden: raw band value
        "bmi_percentile": percentile_str,  # forbidden
        "created_at": date_str,  # forbidden
    }
    longitudinal_point = {
        "weeks_offset_from_latest": 4,
        "height_cm": 148.0,
        "weight_kg": 38.0,
        "maturation_status_at_point": "Pre-PHV",
        "delta_height_cm_from_prior_point": None,
        "sitting_height_cm": band_value_str,  # forbidden: excluded per point
        "z_score": zscore_str,  # forbidden
        "evaluation_date": date_str,  # forbidden
    }
    training_load_window = {
        "sessions_count_28d": 3,
        "avg_rpe_28d": 6.0,
        "hours_28d": 2.5,
        "logged_at": date_str,  # forbidden
    }
    previous_analysis = {
        "insight_schema_version": "v1",
        "summary_line": "La tendencia se mantiene igual que en la lectura anterior.",
        "confidence_level": "medium",
        "weeks_since": 6,
        "generated_at": date_str,  # forbidden
        "percentile": percentile_str,  # forbidden
    }

    context = _sanitized_context(
        identity=identity,
        measurement_deltas=measurement_deltas,
        growth_summary=growth_summary,
        longitudinal_series=[longitudinal_point],
        training_load_window=training_load_window,
        previous_analysis=previous_analysis,
    )

    # Sanity: the allow-list really did drop something in every leaf, or this
    # test would pass vacuously without ever exercising the filter.
    assert "birth_date" not in context.identity
    assert "evaluation_date" not in (context.measurement_deltas or {})
    assert "raw_height_band_value" not in context.growth_summary
    assert "sitting_height_cm" not in context.longitudinal_series[0]
    assert "logged_at" not in (context.training_load_window or {})
    assert "generated_at" not in (context.previous_analysis or {})

    blocks = _blocks_from_context(context)
    prompt_text = _render_prompt_for_context(context)

    for forbidden_value, label in (
        (zscore_str, "z-score"),
        (percentile_str, "percentile"),
        (band_value_str, "raw band value"),
        (date_str, "absolute date"),
    ):
        assert forbidden_value not in prompt_text, (
            f"Forbidden {label} {forbidden_value!r} leaked into the rendered prompt."
        )

    # Format-agnostic backstop: no ISO/dd-mm-yyyy/Spanish-month date of ANY
    # kind survives in a context-DERIVED block. Checked against the six
    # `*_block` strings individually, never the full templated prompt: the
    # static template legitimately contains an instructional example in this
    # exact shape ("... nunca una fecha ... como 'en marzo de 2027' ...",
    # `anthropometry_analyst_v1.md` rule 2) — that is the template teaching
    # the model NOT to invent a date, not a leaked context value, and a
    # whole-prompt scan would misfire on it.
    for block_name, block_text in blocks.items():
        if not block_text:
            continue
        match = _ABSOLUTE_DATE_PATTERN.search(block_text)
        assert match is None, (
            f"Absolute-date-shaped text leaked into {block_name}: {match.group(0)!r}"
        )


# ---------------------------------------------------------------------------
# Property 3 — coach free text (and its length) never reaches the prompt.
# ---------------------------------------------------------------------------
#
# `training_load_window` is the only leaf sourced from a loader
# (`load_training_window`) whose underlying rows a coach could theoretically
# annotate with free text. `context.py` never passes that loader's dict
# through wholesale — it cherry-picks exactly three numeric keys
# (`context.py:418-424`). This test proves that guarantee holds even when
# the loader's return value is adversarially stuffed with coach free text
# under plausible key names, AND that no field encoding the free text's
# LENGTH exists in the context that reaches the prompt (spec.md Assumptions:
# "Coach free text never reaches the tracing tool in any form, including its
# length" — the same non-negotiable applies a fortiori to the prompt itself,
# which is a strictly wider exposure surface than a local trace).


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    coach_text=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), blacklist_characters="0123456789"),
        min_size=15,
        max_size=200,
    ),
    audience=st.sampled_from(["family", "coach"]),
)
def test_coach_free_text_never_reaches_prompt_not_even_its_length(coach_text, audience):
    loader_return = {
        "sessions_in_window": 5,
        "rpe_mean": 6.5,
        "training_hours": 4.0,
        # Adversarial: a hypothetical future loader change that starts
        # returning coach free text (or its length) under plausible keys.
        "coach_notes": coach_text,
        "training_implications": coach_text,
        "notes_length": len(coach_text),
    }
    # Exactly what context.py's build_context() does with the loader's
    # return value — cherry-pick three numeric keys, nothing else
    # (context.py:418-424) — never `sanitize_insight_context(loader_return)`,
    # which would be a weaker, key-name-dependent defense.
    training_load_window = {
        "sessions_count_28d": loader_return["sessions_in_window"],
        "avg_rpe_28d": loader_return["rpe_mean"],
        "hours_28d": loader_return["training_hours"],
    }

    context = _sanitized_context(
        identity=_base_identity(audience),
        measurement_deltas=None,
        growth_summary={},
        longitudinal_series=[],
        training_load_window=training_load_window,
        previous_analysis=None,
    )

    # Structural guarantee: no length-derived (or any other coach-authored)
    # field exists in the context at all, not merely "the text is absent".
    assert set(context.training_load_window) == {
        "sessions_count_28d",
        "avg_rpe_28d",
        "hours_28d",
    }

    prompt_text = _render_prompt_for_context(context)

    assert coach_text not in prompt_text
    # `len(coach_text)` is deliberately NOT checked as a prompt substring:
    # the template already contains many unrelated numbers (the club's
    # "10-15 años" age range, RPE/hours figures, cardinality ranges), so a
    # small integer coincidentally matching one of them would be a false
    # positive, not evidence of a length leak. The structural assertion
    # above — the context's `training_load_window` has EXACTLY the three
    # named keys, `notes_length` included nowhere — is the real, non-fragile
    # proof that no length-derived field ever entered the context that seeds
    # this prompt.


# ---------------------------------------------------------------------------
# Property 4 — sanitize_insight_context() output is always allow-listed.
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    ctx=st.dictionaries(
        keys=st.one_of(
            st.sampled_from(sorted(ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS)),
            st.text(min_size=1, max_size=24),
        ),
        values=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=40),
            st.booleans(),
            st.none(),
            st.lists(st.text(max_size=10), max_size=3),
        ),
        max_size=20,
    )
)
def test_sanitize_insight_context_output_always_subset_of_allowlist(ctx):
    sanitized = sanitize_insight_context(ctx)
    leaked = set(sanitized.keys()) - ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS
    assert not leaked, f"sanitize_insight_context() let non-allow-listed keys through: {leaked}"
    # Every value that DID survive is untouched (key-based filter only) and
    # came straight from the input for that same key — pinning the
    # filter's contract so a future rewrite cannot start transforming values
    # while claiming compliance with this test.
    for key, value in sanitized.items():
        assert value is ctx[key] or value == ctx[key]


# ---------------------------------------------------------------------------
# Property 5 (feature 046, T062) — for random synthetic skinfold sets/
# readings, the rendered family prompt block and the fake-provider request
# never contain a digit immediately followed by `%`/`mm`, nor a
# club-forbidden name.
# ---------------------------------------------------------------------------

_NUMERIC_UNIT_LEAK_PATTERN = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|mm)")

_reading_field_strategy = st.fixed_dictionaries(
    {
        "sets_count": st.integers(min_value=1, max_value=9),
        "sum_change_code": st.sampled_from(["none", "within_noise", "up_real", "down_real"]),
        "band": st.sampled_from(["verde", "ambar", "rojo"]),
        "family_band": st.sampled_from(["verde", "ambar"]),
        "band_reason_code": st.sampled_from(
            [
                "energy_availability_pattern",
                "sum_down_unexplained",
                "sum_up_unexplained",
                "sum_up_velocity_low",
                "reference_extreme",
                "bmi_z_drop",
                "velocity_low_persistent",
                "expected_pubertal_gain",
                "pre_spurt_accumulation",
                "post_phv_lean_gain",
                "first_set",
                "no_real_change",
                "stable",
            ]
        ),
        "ffm_trend_code": st.sampled_from(["up", "flat", "down", "unavailable"]),
        "reference_code_tri": st.sampled_from(
            ["low_extreme", "low", "normal", "high", "high_extreme", "unavailable"]
        ),
        "reference_code_sub": st.sampled_from(
            ["low_extreme", "low", "normal", "high", "high_extreme", "unavailable"]
        ),
        "sites_declined_count": st.integers(min_value=0, max_value=6),
        "weeks_since_prev_set": st.one_of(st.none(), st.integers(min_value=0, max_value=520)),
    }
)


def _reading_from_fields(fields: dict) -> BodyCompositionReading:
    return BodyCompositionReading(
        sets_count=fields["sets_count"],
        sum_change_code=fields["sum_change_code"],
        weight_change_code="up",
        height_growth_code="growing",
        velocity_code="within_or_above",
        bmi_z_change_code="ok",
        reference_triceps=ReferenceContext(percentile=None, code=fields["reference_code_tri"]),
        reference_subscapular=ReferenceContext(percentile=None, code=fields["reference_code_sub"]),
        ffm_trend_code=fields["ffm_trend_code"],
        sites_declined_count=fields["sites_declined_count"],
        band=fields["band"],
        family_band=fields["family_band"],
        band_reason_code=fields["band_reason_code"],
        legs_missing=[],
        next_due_date=None,
        days_until_due=None,
    )


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(fields=_reading_field_strategy, name=_forbidden_name)
def test_family_body_composition_block_and_fake_request_never_leak_numbers_or_names(
    fields, name
):
    reading = _reading_from_fields(fields)
    record = SimpleNamespace(evaluation_date=date(2026, 6, 1))
    previous_record = (
        SimpleNamespace(evaluation_date=date(2026, 4, 1))
        if fields["weeks_since_prev_set"] is not None
        else None
    )

    leaf = anthro_context._build_body_composition_dict(record, previous_record, reading)
    assert leaf is not None
    sanitized_leaf = sanitize_insight_context(leaf)

    family_block = anthro_context._render_body_composition_block(sanitized_leaf, "family")
    assert family_block is not None

    assert not _NUMERIC_UNIT_LEAK_PATTERN.search(family_block), (
        f"Family body-composition block leaked a numeric %/mm value: {family_block!r}"
    )
    assert name not in family_block

    # The fake-provider request is the literal string that would leave this
    # process for a real provider (same seam as properties 1-3 above).
    fake = FakeLLMProvider()
    request = LLMRequest(
        system="Eres un asistente de análisis antropométrico.",
        messages=(LLMMessage(role="user", content=family_block),),
    )
    asyncio.run(fake.complete(request))
    sent_text = fake.last_request.messages[-1].content
    assert not _NUMERIC_UNIT_LEAK_PATTERN.search(sent_text)
    assert name not in sent_text


# ---------------------------------------------------------------------------
# Property 1b — the pipeline actually threads the list into the seam.
# ---------------------------------------------------------------------------
#
# Property 1 proves the scrub works WHEN it is given the club list. This one
# proves the wiring exists: if a future refactor reorders pipeline.py so the
# list is loaded after build_context (as it originally was, which is how the
# leak got in), the scrub silently receives an empty list and Property 1 keeps
# passing while production leaks again.


class _StopPipeline(Exception):
    """Corta la corrida apenas se observó el estado — no interesa el resto."""


async def _async_value(value):
    return value


async def test_pipeline_carga_la_lista_prohibida_antes_de_construir_el_contexto(monkeypatch):
    seen: dict = {}

    async def _fake_build_context(state, config=None):
        seen["forbidden_names"] = state.get("forbidden_names")
        raise _StopPipeline()

    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(
        anthro_pipeline, "_resolve_forbidden_names", lambda state: _async_value(["Nombre Prohibido"])
    )

    state = {
        "athlete": SimpleNamespace(id=1),
        "target_record": SimpleNamespace(id=2),
        "use_case": "anthropometric_record_analysis",
        "audience": "family",
    }
    with pytest.raises(_StopPipeline):
        await anthro_pipeline.run_analysis(state)

    assert seen["forbidden_names"] == ["Nombre Prohibido"], (
        "pipeline.run_analysis must resolve the club forbidden-names list BEFORE "
        "calling build_context and pass it in state, or previous_analysis."
        "summary_line reaches the provider unscrubbed"
    )
