"""Tests for the anthropometric analyst pipeline step (feature 042, T052).

Covers `backend/app/services/ai/anthro/analyst.py` (pipeline step 2) per
`specs/042-traceable-growth-ai/tasks.md` T033/T052 and the JSON contract in
`contracts/insight-schema.md`.

`app.services.llm.factory.build_chat_llm` / `resolve_configured_model` are
imported by name into `analyst.py`'s module namespace, so they are
monkeypatched there directly (`anthro_analyst.build_chat_llm`, not the
factory module) — the same pattern used for the race stack's agents.
`GenericFakeChatModel` (langchain-core) is used as the model double, one of
the two locations `contracts/llm-transport.md` §7 allows it in (the other
is `tests/test_langchain_provider.py`).

Fixtures use fictitious ages/sexes/categories only — no athlete names, no
birth dates, no absolute calendar dates (CLAUDE.md / Ley 1581).
"""

from __future__ import annotations

import json
from unittest.mock import Mock

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.config import settings
from app.services.ai.anthro import analyst as anthro_analyst
from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.schemas import AnthropometryInsightV1

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _identity(**overrides) -> dict:
    base = dict(
        age_decimal=13.2,
        age_group="13-15",
        sex="M",
        category="Sub-15",
        audience="family",
    )
    base.update(overrides)
    return base


def _context_blocks(**overrides) -> dict:
    base = dict(
        measurement_deltas_block="Talla: cambio moderado desde la medición anterior.",
        longitudinal_series_block="Se cuenta con tres mediciones previas.",
        growth_summary_block="Fase: Pre-PHV. Rango de velocidad esperado: 5.0-8.0 cm/año.",
        training_load_block="Cuatro sesiones registradas en las últimas cuatro semanas.",
        previous_analysis_block=None,
    )
    base.update(overrides)
    return base


def _analysis_context(**identity_overrides) -> AnalysisContext:
    return AnalysisContext(
        identity=_identity(**identity_overrides),
        measurement_deltas=None,
        longitudinal_series=[],
        growth_summary={},
        training_load_window=None,
        previous_analysis=None,
    )


def _state(*, audience: str = "family", prompt_version: str | None = None) -> dict:
    return {
        "context_blocks": _context_blocks(),
        "analysis_context": _analysis_context(audience=audience),
        "prompt_version": prompt_version,
    }


def _valid_insight_dict(*, audience: str = "family") -> dict:
    return {
        "schema_version": "v1",
        "audience": audience,
        "summary_line": "Crecimiento estable esta quincena, sin cambios preocupantes.",
        "changes": ["La talla aumentó de forma moderada desde la medición anterior."],
        "meaning": ["Este cambio está dentro de lo esperado para esta etapa de desarrollo."],
        "next_weeks": ["Mantener la rutina de entrenamiento habitual."],
        "warning_signs": [],
        "confidence": {
            "level": "medium",
            "reason": "hay suficientes datos recientes para esta lectura",
        },
        "data_gaps": [],
        "word_count": 24,
    }


def _valid_insight_json(**overrides) -> str:
    payload = _valid_insight_dict()
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


class _RecordingFakeChatModel(GenericFakeChatModel):
    """`GenericFakeChatModel` that also records each prompt it received.

    `analyst.py` sends a single `HumanMessage` per call (`calls.py::call_llm`)
    — recording `messages[-1].content` per invocation is enough to inspect
    exactly what the repair attempt sent back to the model.
    """

    prompts_seen: list[str] = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts_seen.append(messages[-1].content)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _patch_factory(monkeypatch, chat_model, *, model_id: str = "fake-model-v1"):
    """Monkeypatches the factory symbols analyst.py imported by name, and
    returns the two mocks so a test can assert on how they were called."""
    build_chat_llm_mock = Mock(return_value=chat_model)
    resolve_model_mock = Mock(return_value=model_id)
    monkeypatch.setattr(anthro_analyst, "build_chat_llm", build_chat_llm_mock)
    monkeypatch.setattr(anthro_analyst, "resolve_configured_model", resolve_model_mock)
    return build_chat_llm_mock, resolve_model_mock


# ---------------------------------------------------------------------------
# 1. Well-formed JSON validates into AnthropometryInsightV1
# ---------------------------------------------------------------------------


async def test_well_formed_json_validates_into_insight(monkeypatch):
    payload = _valid_insight_dict(audience="coach")
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=json.dumps(payload, ensure_ascii=False))])
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state(audience="coach"))

    assert result["analyst_failed"] is False
    assert result["analyst_error"] is None
    insight = result["analyst_draft"]
    assert isinstance(insight, AnthropometryInsightV1)
    assert insight.audience == "coach"
    assert insight.summary_line == payload["summary_line"]
    assert insight.confidence.level.value == "medium"


# ---------------------------------------------------------------------------
# 2. JSON fenced in a ```json block is extracted tolerantly
# ---------------------------------------------------------------------------


async def test_json_fenced_in_code_block_is_extracted_tolerantly(monkeypatch):
    payload = _valid_insight_dict()
    fenced = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content=fenced)]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    assert result["analyst_draft"] is not None
    assert result["analyst_draft"].summary_line == payload["summary_line"]


async def test_json_with_surrounding_prose_is_extracted_tolerantly(monkeypatch):
    """Some providers wrap the JSON in a sentence despite the prompt's
    JSON-only instruction — the parser trims to the first/last brace."""
    payload = _valid_insight_dict()
    wrapped = "Aquí está el análisis:\n" + json.dumps(payload, ensure_ascii=False) + "\nListo."
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content=wrapped)]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    assert result["analyst_draft"].summary_line == payload["summary_line"]


# ---------------------------------------------------------------------------
# 3. Invalid/unparseable response -> exactly ONE retry, error appended to the
#    second prompt; after the second failure, failure is reported WITHOUT
#    building a fallback (fallback.py's job, out of this module's ownership).
# ---------------------------------------------------------------------------


async def test_invalid_response_triggers_exactly_one_retry_with_error_appended(monkeypatch):
    chat_model = _RecordingFakeChatModel(
        messages=iter(
            [
                AIMessage(content="esto no es un objeto JSON"),
                # Second attempt: valid JSON syntax but fails schema
                # validation (missing required fields) -- exercises the
                # ValidationError branch of `_validation_error_summary`.
                AIMessage(content=json.dumps({"audience": "family"})),
            ]
        )
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is True
    assert result["analyst_draft"] is None
    assert result["analyst_error"]  # non-empty summary of the last failure

    # Exactly one retry happened: two calls total, never a third.
    assert len(chat_model.prompts_seen) == 2

    first_prompt, second_prompt = chat_model.prompts_seen
    # The repair prompt embeds the ORIGINAL prompt plus the validator's
    # error summary from the FIRST failed attempt (not the second) plus the
    # failed draft itself, so the model can self-correct.
    assert "Corrección obligatoria" in second_prompt
    assert "La respuesta del analista no contiene un objeto JSON." in second_prompt
    assert "esto no es un objeto JSON" in second_prompt
    assert second_prompt.startswith(first_prompt)

    # The step itself never constructs a fallback-shaped insight -- that is
    # exclusively fallback.py's responsibility (data-model.md §3).
    assert "analyst_fallback" not in result


async def test_second_failure_error_reflects_pydantic_validation_not_first_failure(monkeypatch):
    """After a JSON-syntax failure then a schema-validation failure, the
    REPORTED error is the second (final) attempt's error -- the caller only
    sees the last failure, matching `run_analyst`'s `last_error` semantics."""
    chat_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(content="no json aquí"),
                AIMessage(content=json.dumps({"audience": "family"})),
            ]
        )
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is True
    # A Pydantic field/message summary, not the JSON-syntax message from the
    # first attempt.
    assert "La respuesta del analista no contiene un objeto JSON." not in result["analyst_error"]
    assert ":" in result["analyst_error"]  # "campo: mensaje" format


# ---------------------------------------------------------------------------
# 4. role="analyst" / stack="app" reach the factory -- AI_ANALYST_MODEL
#    applies, RACE_AI_* is never consulted (analyst.py never requests
#    stack="race"; the factory's own inheritance rule is covered separately
#    by tests/test_llm_factory.py, T021).
# ---------------------------------------------------------------------------


async def test_role_analyst_and_stack_app_reach_the_shared_factory(monkeypatch):
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content=_valid_insight_json())]))
    build_chat_llm_mock, resolve_model_mock = _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    build_chat_llm_mock.assert_called_once_with(role="analyst", stack="app")
    resolve_model_mock.assert_called_once_with(role="analyst", stack="app")
    # Neither call ever asked for stack="race" -- the only path by which a
    # RACE_AI_* setting could enter this step's model resolution.
    for call in (*build_chat_llm_mock.call_args_list, *resolve_model_mock.call_args_list):
        assert call.kwargs.get("stack") != "race"


async def test_llm_built_once_and_reused_across_the_retry(monkeypatch):
    """`build_chat_llm` is called ONCE per `run_analyst` invocation, before
    the attempt loop -- a retry reuses the same client, it doesn't rebuild
    it (analyst.py:`llm = build_chat_llm(...)` is outside the `for` loop)."""
    chat_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(content="no json"),
                AIMessage(content=_valid_insight_json()),
            ]
        )
    )
    build_chat_llm_mock, _ = _patch_factory(monkeypatch, chat_model)

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    build_chat_llm_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Tokens, latency and cost are returned for the pipeline to accumulate
# ---------------------------------------------------------------------------


async def test_tokens_latency_and_cost_are_returned_for_the_pipeline_to_accumulate(monkeypatch):
    reply = AIMessage(
        content=_valid_insight_json(),
        usage_metadata={"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
    )
    chat_model = GenericFakeChatModel(messages=iter([reply]))
    _patch_factory(monkeypatch, chat_model, model_id="gemini-3.1-flash-lite")
    monkeypatch.setattr(settings, "ai_provider", "google")

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    assert result["analyst_tokens_in"] == 120
    assert result["analyst_tokens_out"] == 40
    assert isinstance(result["analyst_latency_ms"], int)
    assert result["analyst_latency_ms"] >= 0
    # "gemini-3.1-flash-lite" has no per-model rate registered (only the
    # analyst/critic role models do, pricing.py) -- falls back to the
    # "google" provider rate (0.25 / 1.50 USD per 1M tokens).
    expected_cost = round(120 * 0.25 / 1_000_000 + 40 * 1.50 / 1_000_000, 6)
    assert result["analyst_cost_usd"] == expected_cost


async def test_tokens_and_cost_accumulate_across_the_retry(monkeypatch):
    """Both attempts of a retried call cost tokens -- the final result sums
    them, it does not report only the last (successful) attempt's cost."""
    first_reply = AIMessage(
        content="no json",
        usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55},
    )
    second_reply = AIMessage(
        content=_valid_insight_json(),
        usage_metadata={"input_tokens": 70, "output_tokens": 35, "total_tokens": 105},
    )
    chat_model = GenericFakeChatModel(messages=iter([first_reply, second_reply]))
    _patch_factory(monkeypatch, chat_model)
    monkeypatch.setattr(settings, "ai_provider", "google")

    result = await anthro_analyst.run_analyst(_state())

    assert result["analyst_failed"] is False
    assert result["analyst_tokens_in"] == 50 + 70
    assert result["analyst_tokens_out"] == 5 + 35
    assert result["analyst_cost_usd"] > 0
