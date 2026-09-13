"""Tests for the anthropometric critic pipeline step (feature 042, T052).

Covers `backend/app/services/ai/anthro/critic.py` (pipeline step 3), one
test per row of `specs/042-traceable-growth-ai/data-model.md` §3's
critic-outcome table ("Critic-call outcome -> persisted `critic_verdict`").

Vocabulary note (`critic.py`'s own module docstring, data-model.md §2.4):
this module returns a FIVE-value `critic_decision`
(`approved|revised_mechanical|needs_reanalysis|rejected|skipped`) that is
NOT the five-value `critic_verdict` persisted by `pipeline.py` (T039,
outside this file's ownership) -- e.g. both `needs_reanalysis` (after a
second analyst attempt) and `rejected` eventually become the persisted
`FLAGGED`, but only `pipeline.py` knows which. Every assertion below is
against `critic_decision`, the actual return contract of `run_critic`.

Scope boundary (IMPORTANT, see the docstring of
`test_approve_with_confidence_only_precheck_violation_...` below): the
data-model.md §3 row "approve, but a confidence-only precheck violation
fired -> confidence.level forced to low" is `pipeline.py`'s job, not
`critic.py`'s -- `critic.py`'s own docstring says so explicitly ("esa
decisión cruza precheck+critic y es de pipeline.py, no de este módulo").
That forcing is covered by `tests/anthro/test_pipeline.py` (T053, a
different task's ownership); this file tests `critic.py`'s actual, narrower
contract instead of asserting behaviour that lives one layer up.

`GenericFakeChatModel` (langchain-core) is used as the model double, one of
the two locations `contracts/llm-transport.md` §7 allows it in.

Fixtures use fictitious ages/sexes/categories only -- no athlete names, no
birth dates, no absolute calendar dates (CLAUDE.md / Ley 1581).
"""

from __future__ import annotations

import json
from unittest.mock import Mock

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.services.ai.anthro import critic as anthro_critic
from app.services.ai.anthro.prechecks import PrecheckResult, PrecheckViolation
from app.services.ai.anthro.schemas import AnthropometryInsightV1

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


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


def _draft(**overrides) -> AnthropometryInsightV1:
    payload = _valid_insight_dict()
    payload.update(overrides)
    return AnthropometryInsightV1.model_validate(payload)


def _context_blocks(**overrides) -> dict:
    base = dict(
        measurement_deltas_block="Talla: cambio moderado desde la medición anterior.",
        growth_summary_block="Fase: Pre-PHV. Rango de velocidad esperado: 5.0-8.0 cm/año.",
        previous_analysis_block=None,
    )
    base.update(overrides)
    return base


def _precheck_violation(
    rule_id: str, *, category: str = "style", must_block: bool = False
) -> PrecheckViolation:
    return PrecheckViolation(
        rule_id=rule_id,
        category=category,
        must_block=must_block,
        detail="Detalle breve de la violación, sin texto del atleta.",
    )


def _precheck_result(violations: list[PrecheckViolation]) -> PrecheckResult:
    violations_t = tuple(violations)
    return PrecheckResult(
        violations=violations_t, must_block=any(v.must_block for v in violations_t)
    )


def _state(
    *,
    draft: AnthropometryInsightV1 | None = None,
    context_blocks: dict | None = None,
    precheck_result: PrecheckResult | None = None,
    critic_prompt_version: str | None = None,
) -> dict:
    return {
        "analyst_draft": draft if draft is not None else _draft(),
        "context_blocks": context_blocks if context_blocks is not None else _context_blocks(),
        "precheck_result": precheck_result,
        "critic_prompt_version": critic_prompt_version,
    }


def _violation(rule_id: str, *, section: str = "changes") -> dict:
    return {
        "rule_id": rule_id,
        "section": section,
        "problem": "El texto no refleja correctamente el dato de la verdad de campo.",
        "suggested_fix": "Ajustar la frase para que coincida con el resumen de crecimiento.",
    }


def _critic_response_json(
    *,
    verdict: str,
    violations: list[dict] | None = None,
    revised_output: dict | None = None,
) -> str:
    payload: dict = {"verdict": verdict, "violations": violations or []}
    if revised_output is not None:
        payload["revised_output"] = revised_output
    return json.dumps(payload, ensure_ascii=False)


def _patch_factory(monkeypatch, chat_model, *, model_id: str = "fake-critic-model"):
    build_chat_llm_mock = Mock(return_value=chat_model)
    resolve_model_mock = Mock(return_value=model_id)
    monkeypatch.setattr(anthro_critic, "build_chat_llm", build_chat_llm_mock)
    monkeypatch.setattr(anthro_critic, "resolve_configured_model", resolve_model_mock)
    return build_chat_llm_mock, resolve_model_mock


# ---------------------------------------------------------------------------
# Row 1: approve, no confidence-only precheck violations -> draft unmodified
# ---------------------------------------------------------------------------


async def test_approve_with_no_precheck_violations_keeps_draft_unmodified(monkeypatch):
    draft = _draft()
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=_critic_response_json(verdict="approve"))])
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft, precheck_result=_precheck_result([])))

    assert result["critic_decision"] == "approved"
    assert result["critic_output"] is draft
    assert result["critic_violations"] == []
    assert result["critic_skipped"] is False
    assert result["critic_error"] is None


# ---------------------------------------------------------------------------
# Row 2: approve WITH confidence-only precheck violations -> data-model.md
# §3 says the PERSISTED row forces confidence to "low"; see the module
# docstring above for why that assertion does not belong in THIS file.
# ---------------------------------------------------------------------------


async def test_approve_with_confidence_only_precheck_violation_is_not_forced_here(monkeypatch):
    """`critic.py`'s own contract for an "approve" verdict: `critic_output`
    is the draft, untouched, REGARDLESS of what `precheck_result` carries.
    The confidence-forcing described by data-model.md §3 row 2 happens one
    layer up, in `pipeline.py` (see this module's docstring, section on the
    "approved" `critic_decision`) -- it combines this step's output with the
    precheck result itself, which `run_critic` only ever uses to render
    `precheck_summary` text for the critic's own prompt, never to alter its
    decision or its output.
    """
    draft = _draft(confidence={"level": "high", "reason": "el patrón es muy claro en esta lectura"})
    # R07 (word budget) is in the "degrade-only" set - a confidence-only,
    # non-blocking precheck violation (golden-eval-case.md §3).
    confidence_only_violation = _precheck_violation("R07", category="style", must_block=False)
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=_critic_response_json(verdict="approve"))])
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(
        _state(draft=draft, precheck_result=_precheck_result([confidence_only_violation]))
    )

    assert result["critic_decision"] == "approved"
    assert result["critic_output"] is draft
    assert result["critic_output"].confidence.level.value == "high"


# ---------------------------------------------------------------------------
# Row 3: revise, every violation mechanical + schema-valid revised_output ->
# adopted directly, no second analyst call.
# ---------------------------------------------------------------------------


async def test_revise_all_mechanical_with_valid_revised_output_adopted_directly(monkeypatch):
    draft = _draft()
    revised_payload = _valid_insight_dict()
    revised_payload["summary_line"] = "Crecimiento estable; se corrigió una referencia de fecha."
    violations = [_violation("R04"), _violation("R10")]
    chat_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content=_critic_response_json(
                        verdict="revise", violations=violations, revised_output=revised_payload
                    )
                )
            ]
        )
    )
    build_chat_llm_mock, _ = _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "revised_mechanical"
    assert result["critic_output"] is not draft
    assert result["critic_output"].summary_line == revised_payload["summary_line"]
    assert len(result["critic_violations"]) == 2
    # A single LLM call happened (the critic's own) -- run_critic never
    # imports or invokes analyst.py; adopting revised_output is direct.
    build_chat_llm_mock.assert_called_once()


async def test_revise_all_mechanical_without_revised_output_falls_to_needs_reanalysis(monkeypatch):
    """Conservative fallback (critic.py docstring): a "revise" verdict whose
    violations are all mechanical but that supplies NO `revised_output` is
    NOT adopted blindly -- it is treated as needing re-analysis."""
    draft = _draft()
    violations = [_violation("R06")]
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=_critic_response_json(verdict="revise", violations=violations))])
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "needs_reanalysis"
    assert result["critic_output"] is draft


# ---------------------------------------------------------------------------
# Row 4: revise with any interpretive violation -> reports re-analysis needed
# ---------------------------------------------------------------------------


async def test_revise_with_interpretive_violation_reports_needs_reanalysis(monkeypatch):
    draft = _draft()
    # Mixed set: one mechanical (R04) + one interpretive (R02) -- ANY
    # interpretive violation routes to needs_reanalysis, even alongside
    # mechanical ones and even with a (here absent) revised_output.
    violations = [_violation("R04"), _violation("R02")]
    chat_model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content=_critic_response_json(
                        verdict="revise",
                        violations=violations,
                        revised_output=_valid_insight_dict(),
                    )
                )
            ]
        )
    )
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "needs_reanalysis"
    # The entry draft is returned as-is (a reference for the caller to
    # re-invoke the analyst with, not a final result) -- revised_output is
    # never adopted when any violation is interpretive.
    assert result["critic_output"] is draft
    assert len(result["critic_violations"]) == 2


# ---------------------------------------------------------------------------
# Row 5: reject -> no second analyst call (FR-013's single revision is spent
# on "revise", not "reject")
# ---------------------------------------------------------------------------


async def test_reject_reports_rejected_without_a_second_call(monkeypatch):
    draft = _draft()
    violations = [_violation("R01")]
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=_critic_response_json(verdict="reject", violations=violations))])
    )
    build_chat_llm_mock, _ = _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "rejected"
    assert result["critic_output"] is draft
    assert len(result["critic_violations"]) == 1
    build_chat_llm_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Row 6: critic call fails / times out / returns unparseable JSON -> skipped:
# draft kept unrevised, confidence forced to low, reason amended in español
# neutro (FR-014).
# ---------------------------------------------------------------------------


async def test_critic_call_failure_skips_with_confidence_forced_low(monkeypatch):
    class _RaisingFakeChatModel(GenericFakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise TimeoutError("tiempo agotado")

    draft = _draft(confidence={"level": "high", "reason": "los datos son contundentes"})
    chat_model = _RaisingFakeChatModel(messages=iter([]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "skipped"
    assert result["critic_skipped"] is True
    assert result["critic_error"]
    assert result["critic_raw_verdict"] is None

    output = result["critic_output"]
    assert output is not draft  # a copy -- the original draft is untouched
    assert output.confidence.level.value == "low"
    assert "revisión automática" in output.confidence.reason.lower()
    # español neutro, no provider/model detail leaked into the family/coach
    # facing reason.
    for token in ("timeout", "anthropic", "google", "openai", "TimeoutError"):
        assert token.lower() not in output.confidence.reason.lower()
    for field in ("summary_line", "changes", "meaning", "next_weeks", "warning_signs"):
        assert getattr(output, field) == getattr(draft, field)
    # The original draft object is never mutated in place.
    assert draft.confidence.level.value == "high"


async def test_critic_unparseable_json_skips_with_confidence_forced_low(monkeypatch):
    draft = _draft()
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content="esto no es json balanceado")]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "skipped"
    assert result["critic_skipped"] is True
    assert result["critic_error"]
    assert result["critic_output"].confidence.level.value == "low"
    assert result["critic_output"] is not draft


async def test_critic_schema_invalid_json_skips_with_confidence_forced_low(monkeypatch):
    """A balanced JSON object that fails `AnthropometryCriticVerdict`
    validation (e.g. an unknown `verdict` value) is treated the same as
    unparseable JSON -- `skipped`, never an uncaught `ValidationError`."""
    draft = _draft()
    bad_payload = json.dumps({"verdict": "maybe", "violations": []})
    chat_model = GenericFakeChatModel(messages=iter([AIMessage(content=bad_payload)]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state(draft=draft))

    assert result["critic_decision"] == "skipped"
    assert result["critic_output"].confidence.level.value == "low"


# ---------------------------------------------------------------------------
# Row 7 (cross-cutting): role="critic" / stack="app" reach the factory ->
# AI_CRITIC_MODEL applies.
# ---------------------------------------------------------------------------


async def test_role_critic_and_stack_app_reach_the_shared_factory(monkeypatch):
    chat_model = GenericFakeChatModel(
        messages=iter([AIMessage(content=_critic_response_json(verdict="approve"))])
    )
    build_chat_llm_mock, resolve_model_mock = _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state())

    assert result["critic_decision"] == "approved"
    build_chat_llm_mock.assert_called_once_with(role="critic", stack="app")
    resolve_model_mock.assert_called_once_with(role="critic", stack="app")
    for call in (*build_chat_llm_mock.call_args_list, *resolve_model_mock.call_args_list):
        assert call.kwargs.get("stack") != "race"


# ---------------------------------------------------------------------------
# Tokens/latency/cost bookkeeping, including the zero-cost skipped-by-
# call-failure path (no response was ever received to meter).
# ---------------------------------------------------------------------------


async def test_skipped_by_call_failure_reports_zero_usage(monkeypatch):
    class _RaisingFakeChatModel(GenericFakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise ConnectionError("socket cerrado")

    chat_model = _RaisingFakeChatModel(messages=iter([]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state())

    assert result["critic_tokens_in"] == 0
    assert result["critic_tokens_out"] == 0
    assert result["critic_cost_usd"] == 0.0


async def test_approved_call_reports_usage_from_the_response(monkeypatch):
    reply = AIMessage(
        content=_critic_response_json(verdict="approve"),
        usage_metadata={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
    )
    chat_model = GenericFakeChatModel(messages=iter([reply]))
    _patch_factory(monkeypatch, chat_model)

    result = await anthro_critic.run_critic(_state())

    assert result["critic_tokens_in"] == 200
    assert result["critic_tokens_out"] == 30
    assert result["critic_cost_usd"] > 0
    assert isinstance(result["critic_latency_ms"], int)
