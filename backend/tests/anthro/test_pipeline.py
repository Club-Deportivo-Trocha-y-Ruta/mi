"""Tests for the anthropometric pipeline orchestrator (feature 042, T053).

Covers `backend/app/services/ai/anthro/pipeline.py::run_analysis` against
every persisted `critic_verdict` branch of the state machine documented
verbatim in `specs/042-traceable-growth-ai/data-model.md` §3 — that table is
the exact specification this file verifies, not this docstring.

Only the LLM-calling seams (`context.build_context`, `analyst.run_analyst`,
`critic.run_critic`) and the deterministic `prechecks.run_prechecks` are
monkeypatched — the latter so the `must_block` / confidence-only branches
are deterministic without needing a draft that trips one of prechecks.py's
real regexes (that catalogue is `tests/anthro/test_prechecks.py`'s own
ownership, T051). `guardrails_step.guardrails_step`,
`fallback.build_fallback_insight` and `persist.persist` run for REAL against
an in-memory aiosqlite session with the real `athlete_ai_explanations` and
`audit_log` tables, so the assertions about `structured_json`, the family
gate and the summed token/cost/latency accounting exercise the genuine
integration rather than a second copy of the pipeline's own bookkeeping.

`LANGFUSE_ENABLED=false` is already forced by `tests/conftest.py`, so
`langfuse_trace_id is None` below is the real behaviour of
`app/services/llm/observability.py` (`trace_id_for` degrades to `None` with
tracing off), never a mock.

Fixtures use fictitious ids, no athlete names, and no absolute dates in any
generated text (CLAUDE.md privacy rule).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.ai_explanation import AthleteAIExplanation
from app.services.ai.anthro import persist as anthro_persist
from app.services.ai.anthro import pipeline as anthro_pipeline
from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.guardrails_step import FAMILY_DELIVERABLE_VERDICTS
from app.services.ai.anthro.pipeline import run_analysis
from app.services.ai.anthro.prechecks import PrecheckResult, PrecheckViolation
from app.services.ai.anthro.schemas import (
    AnthropometryCriticIssue,
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)

_USE_CASE = "measurement_analysis"

# ---------------------------------------------------------------------------
# `persist.py` writes with `mysql_insert(...).on_duplicate_key_update(...)`,
# a MySQL-dialect statement that does not compile against aiosqlite
# (`sqlalchemy.exc.UnsupportedCompilationError` on `OnDuplicateClause`) — the
# offline lane cannot execute that literal upsert. Same shim already
# established by `tests/test_ai_explanation_audit.py` (duplicated here
# rather than imported, to keep this file's ownership self-contained):
# monkeypatch ONLY the `persist.mysql_insert` factory with a double that
# translates the exact call sequence `persist.py` uses (`.values()` ->
# `.inserted.<col>` -> `.on_duplicate_key_update()`) onto
# `sqlalchemy.dialects.sqlite.insert(...).on_conflict_do_update(...)` — a
# real, compilable upsert on the same unique key. Everything else in
# `persist.py` (the pre-SELECT, the `record_audit` call) runs unmocked.
# ---------------------------------------------------------------------------


class _SqliteUpsertShim:
    def __init__(self, table):
        self._stmt = sqlite_insert(table)

    def values(self, **kwargs):
        self._stmt = self._stmt.values(**kwargs)
        return self

    @property
    def inserted(self):
        return self._stmt.excluded

    def on_duplicate_key_update(self, **kwargs):
        return self._stmt.on_conflict_do_update(
            index_elements=["athlete_id", "anthropometric_record_id", "use_case"],
            set_=kwargs,
        )


@pytest.fixture(autouse=True)
def _sqlite_upsert_shim(monkeypatch):
    monkeypatch.setattr(anthro_persist, "mysql_insert", _SqliteUpsertShim)


# ---------------------------------------------------------------------------
# DB fixture — real `athlete_ai_explanations` + `audit_log` tables so
# `persist.py` (T038) and its `record_audit` call run completely unmocked.
# ---------------------------------------------------------------------------

_TABLES = ("athlete_ai_explanations", "audit_log")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _athlete(*, athlete_id: int = 1, club_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(id=athlete_id, club_id=club_id)


def _target_record(*, record_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=record_id, maturation_status="Pre-PHV")


def _actor(*, actor_id: int = 2) -> SimpleNamespace:
    return SimpleNamespace(id=actor_id, role=None)


def _context(*, audience: str = "family") -> AnalysisContext:
    return AnalysisContext(
        identity={
            "age_decimal": 12.5,
            "age_group": "13-15",
            "sex": "M",
            "category": "sub-15",
            "audience": audience,
        },
        measurement_deltas=None,
        longitudinal_series=[],
        growth_summary={},
        training_load_window=None,
        previous_analysis=None,
    )


def _insight(
    *,
    audience: str = "family",
    summary_line: str = "El crecimiento de esta temporada avanza dentro de lo esperado.",
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    confidence_reason: str = "Hay datos suficientes para esta observación.",
) -> AnthropometryInsightV1:
    """A "clean" insight that never trips a guardrails rule — no numbers, no
    exact dates, no diagnostic/comparative/supplement vocabulary — so the
    real `guardrails_step` defense exercised below always reports zero
    violations and never rejects, for either audience."""
    return AnthropometryInsightV1(
        audience=audience,
        summary_line=summary_line,
        changes=["La talla y el peso avanzan de forma constante."],
        meaning=["Este ritmo corresponde a un desarrollo típico para esta etapa."],
        next_weeks=["Continuar con la rutina habitual de entrenamiento y seguimiento."],
        warning_signs=[],
        confidence=Confidence(level=confidence_level, reason=confidence_reason),
        data_gaps=[],
        word_count=20,
    )


def _issue(rule_id: str) -> AnthropometryCriticIssue:
    return AnthropometryCriticIssue(
        rule_id=rule_id,
        section="meaning",
        problem="Observación genérica de prueba.",
        suggested_fix="Corrección genérica de prueba.",
    )


_RECORD_IDS = iter(range(1, 10_000))


def _state(
    *,
    audience: str = "family",
    db: AsyncSession,
    record_id: int | None = None,
) -> dict[str, Any]:
    rid = record_id if record_id is not None else next(_RECORD_IDS)
    return {
        "athlete": _athlete(),
        "target_record": _target_record(record_id=rid),
        "use_case": _USE_CASE,
        "audience": audience,
        "club_id": None,  # keeps `_resolve_forbidden_names` a no-DB no-op
        "db": db,
        "actor": _actor(),
    }


async def _fake_build_context(state: dict, config: dict | None = None) -> dict:
    return {
        "analysis_context": _context(audience=state["audience"]),
        "context_blocks": {
            "measurement_deltas_block": None,
            "longitudinal_series_block": None,
            "growth_summary_block": "resumen de crecimiento de prueba",
            "training_load_block": None,
            "previous_analysis_block": None,
        },
    }


def _analyst_result(
    *,
    draft: AnthropometryInsightV1 | None,
    failed: bool = False,
    tokens_in: int = 100,
    tokens_out: int = 50,
    cost_usd: float = 0.001,
) -> dict:
    return {
        "analyst_draft": draft,
        "analyst_prompt_version": "anthropometry_analyst_v1",
        "analyst_tokens_in": tokens_in,
        "analyst_tokens_out": tokens_out,
        "analyst_latency_ms": 10,
        "analyst_cost_usd": cost_usd,
        "analyst_failed": failed,
        "analyst_error": "llamada fallida: TimeoutError" if failed else None,
    }


def _critic_result(
    *,
    decision: str,
    output: AnthropometryInsightV1,
    violations: list[AnthropometryCriticIssue] | None = None,
    tokens_in: int = 20,
    tokens_out: int = 10,
    cost_usd: float = 0.0005,
) -> dict:
    return {
        "critic_raw_verdict": None,
        "critic_decision": decision,
        "critic_output": output,
        "critic_violations": violations or [],
        "critic_prompt_version": "anthropometry_critic_v1",
        "critic_tokens_in": tokens_in,
        "critic_tokens_out": tokens_out,
        "critic_latency_ms": 5,
        "critic_cost_usd": cost_usd,
        "critic_skipped": decision == "skipped",
        "critic_error": None,
    }


def _clean_precheck(*, violations: tuple[PrecheckViolation, ...] = ()) -> PrecheckResult:
    return PrecheckResult(violations=violations, must_block=False)


def _blocking_precheck() -> PrecheckResult:
    violation = PrecheckViolation(
        rule_id="R02",
        category="ltad",
        must_block=True,
        detail="Etiqueta diagnóstica detectada.",
    )
    return PrecheckResult(violations=(violation,), must_block=True)


def _confidence_only_precheck() -> PrecheckResult:
    violation = PrecheckViolation(
        rule_id="R08",
        category="style",
        must_block=False,
        detail="Elogio desproporcionado sobre un cambio no significativo.",
    )
    return PrecheckResult(violations=(violation,), must_block=False)


def _sequenced(results: list[dict]) -> Callable[..., Any]:
    """An async stub that returns `results` in order, one per call, and
    records every `state` it was called with on `.calls` — used for both
    `run_analyst` and `run_critic` (identical `(state, config=None)` shape),
    so a test can assert call counts and inspect what a re-invocation saw."""
    calls: list[dict] = []
    iterator = iter(results)

    async def _fn(state: dict, config: dict | None = None) -> dict:
        calls.append(state)
        return next(iterator)

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def _sequenced_precheck(results: list[PrecheckResult]) -> Callable[..., PrecheckResult]:
    """`run_prechecks` is sync (never awaited by pipeline.py) — a separate,
    non-async sequencing helper mirrors that."""
    iterator = iter(results)

    def _fn(*args: Any, **kwargs: Any) -> PrecheckResult:
        return next(iterator)

    return _fn


async def _load_row(db: AsyncSession, *, athlete_id: int, record_id: int) -> AthleteAIExplanation:
    result = await db.execute(
        select(AthleteAIExplanation).where(
            AthleteAIExplanation.athlete_id == athlete_id,
            AthleteAIExplanation.anthropometric_record_id == record_id,
            AthleteAIExplanation.use_case == _USE_CASE,
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# 0. Family gate contract itself (data-model.md §6, invariant 2)
# ---------------------------------------------------------------------------


def test_family_deliverable_verdicts_matches_data_model_contract():
    assert FAMILY_DELIVERABLE_VERDICTS == frozenset({"approved", "revised"})


# ---------------------------------------------------------------------------
# 1. HAPPY — approved
# ---------------------------------------------------------------------------


async def test_approved_happy_path(db_session, monkeypatch):
    draft = _insight()
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _clean_precheck())
    monkeypatch.setattr(anthro_pipeline, "run_analyst", _sequenced([_analyst_result(draft=draft)]))
    critic_stub = _sequenced([_critic_result(decision="approved", output=draft)])
    monkeypatch.setattr(anthro_pipeline, "run_critic", critic_stub)

    state = _state(db=db_session, record_id=1)
    result = await run_analysis(state)

    assert len(critic_stub.calls) == 1
    assert result["critic_verdict"] == "approved"
    assert result["family_deliverable"] is True
    assert result["insight"].confidence.level == ConfidenceLevel.MEDIUM  # untouched
    assert result["tokens_in"] == 100 + 20
    assert result["tokens_out"] == 50 + 10
    assert result["cost_usd"] == pytest.approx(0.001 + 0.0005, abs=1e-9)
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0
    assert result["langfuse_trace_id"] is None  # LANGFUSE_ENABLED=false, real behaviour

    row = await _load_row(db_session, athlete_id=1, record_id=1)
    assert row.schema_version == "v2"
    assert row.critic_verdict == "approved"
    assert row.text  # NOT NULL, always populated
    assert row.structured_json is not None
    validated = AnthropometryInsightV1.model_validate(row.structured_json)
    assert validated.summary_line == draft.summary_line
    assert row.tokens_in == 120
    assert row.tokens_out == 60
    assert float(row.cost_usd) == pytest.approx(0.0015, abs=1e-6)
    assert row.latency_ms == result["latency_ms"]
    assert row.langfuse_trace_id is None
    assert row.prompt_version == "anthropometry_analyst_v1"


async def test_approved_with_confidence_only_precheck_violation_forces_low(db_session, monkeypatch):
    """data-model.md §3: `approve` + a non-blocking precheck violation still
    persists as APPROVED, but confidence is deterministically forced to
    "low" regardless of what the analyst/critic reported."""
    draft = _insight(
        confidence_level=ConfidenceLevel.HIGH,
        confidence_reason="El analista reporta alta confianza en esta lectura.",
    )
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _confidence_only_precheck())
    monkeypatch.setattr(anthro_pipeline, "run_analyst", _sequenced([_analyst_result(draft=draft)]))
    monkeypatch.setattr(
        anthro_pipeline, "run_critic", _sequenced([_critic_result(decision="approved", output=draft)])
    )

    result = await run_analysis(_state(db=db_session, record_id=2))

    assert result["critic_verdict"] == "approved"
    assert result["family_deliverable"] is True
    assert result["insight"].confidence.level == ConfidenceLevel.LOW

    row = await _load_row(db_session, athlete_id=1, record_id=2)
    assert AnthropometryInsightV1.model_validate(row.structured_json).confidence.level == (
        ConfidenceLevel.LOW
    )


# ---------------------------------------------------------------------------
# 2. REVISED — mechanical critic fix (no second analyst call)
# ---------------------------------------------------------------------------


async def test_revised_via_mechanical_critic_fix(db_session, monkeypatch):
    draft = _insight(summary_line="Borrador original del analista sobre esta medición.")
    revised = _insight(summary_line="Version corregida mecanicamente por el critico.")
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _clean_precheck())
    analyst_stub = _sequenced([_analyst_result(draft=draft)])
    monkeypatch.setattr(anthro_pipeline, "run_analyst", analyst_stub)
    monkeypatch.setattr(
        anthro_pipeline,
        "run_critic",
        _sequenced(
            [_critic_result(decision="revised_mechanical", output=revised, violations=[_issue("R04")])]
        ),
    )

    result = await run_analysis(_state(db=db_session, record_id=3))

    assert len(analyst_stub.calls) == 1  # NO second analyst call for a mechanical fix
    assert result["critic_verdict"] == "revised"
    assert result["family_deliverable"] is True
    assert result["insight"].summary_line == revised.summary_line

    row = await _load_row(db_session, athlete_id=1, record_id=3)
    assert row.critic_verdict == "revised"
    assert AnthropometryInsightV1.model_validate(row.structured_json).summary_line == (
        revised.summary_line
    )


# ---------------------------------------------------------------------------
# 3. REVISED — single bounded analyst re-invocation
# ---------------------------------------------------------------------------


async def test_revised_via_single_analyst_reinvocation(db_session, monkeypatch):
    draft1 = _insight(summary_line="Primer intento del analista sobre esta medicion.")
    draft2 = _insight(summary_line="Segundo intento del analista, ya corregido.")
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(
        anthro_pipeline, "run_prechecks", _sequenced_precheck([_clean_precheck(), _clean_precheck()])
    )
    analyst_stub = _sequenced([_analyst_result(draft=draft1), _analyst_result(draft=draft2)])
    monkeypatch.setattr(anthro_pipeline, "run_analyst", analyst_stub)
    critic_stub = _sequenced(
        [
            _critic_result(decision="needs_reanalysis", output=draft1, violations=[_issue("R05")]),
            _critic_result(decision="approved", output=draft2),
        ]
    )
    monkeypatch.setattr(anthro_pipeline, "run_critic", critic_stub)

    result = await run_analysis(_state(db=db_session, record_id=4))

    assert len(analyst_stub.calls) == 2  # the ONE permitted re-invocation, never more
    assert len(critic_stub.calls) == 2
    # the re-invocation received the critic's violations, injected into the
    # single free-text slot the analyst prompt reserves for it
    # (pipeline.py::_augment_context_blocks_with_critic_feedback).
    reanalysis_state = analyst_stub.calls[1]
    assert "R05" in reanalysis_state["context_blocks"]["previous_analysis_block"]

    assert result["critic_verdict"] == "revised"
    assert result["family_deliverable"] is True
    assert result["insight"].summary_line == draft2.summary_line
    # tokens/cost summed across BOTH analyst calls AND both critic calls
    assert result["tokens_in"] == 100 * 2 + 20 * 2
    assert result["tokens_out"] == 50 * 2 + 10 * 2
    assert result["cost_usd"] == pytest.approx((0.001 * 2) + (0.0005 * 2), abs=1e-9)

    row = await _load_row(db_session, athlete_id=1, record_id=4)
    assert row.critic_verdict == "revised"
    assert row.tokens_in == result["tokens_in"]
    assert row.tokens_out == result["tokens_out"]
    assert float(row.cost_usd) == pytest.approx(result["cost_usd"], abs=1e-6)


# ---------------------------------------------------------------------------
# 4. FLAGGED — two ways in
# ---------------------------------------------------------------------------


async def test_flagged_when_second_attempt_still_not_approved(db_session, monkeypatch):
    """FR-013 "at most one revision": a re-invocation whose own critic pass
    does not land on approve/mechanical-revise is FLAGGED with the SECOND
    draft — never the fallback template, never a third attempt."""
    draft1 = _insight(summary_line="Primer intento con una observacion interpretativa.")
    draft2 = _insight(summary_line="Segundo intento, todavia con una observacion.")
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(
        anthro_pipeline, "run_prechecks", _sequenced_precheck([_clean_precheck(), _clean_precheck()])
    )
    analyst_stub = _sequenced([_analyst_result(draft=draft1), _analyst_result(draft=draft2)])
    monkeypatch.setattr(anthro_pipeline, "run_analyst", analyst_stub)
    critic_stub = _sequenced(
        [
            _critic_result(decision="needs_reanalysis", output=draft1, violations=[_issue("R01")]),
            _critic_result(decision="rejected", output=draft2, violations=[_issue("R01")]),
        ]
    )
    monkeypatch.setattr(anthro_pipeline, "run_critic", critic_stub)

    result = await run_analysis(_state(db=db_session, record_id=5))

    assert len(analyst_stub.calls) == 2
    assert len(critic_stub.calls) == 2
    assert result["critic_verdict"] == "flagged"
    assert result["family_deliverable"] is False
    assert result["insight"].summary_line == draft2.summary_line

    row = await _load_row(db_session, athlete_id=1, record_id=5)
    assert row.critic_verdict == "flagged"
    assert row.schema_version == "v2"
    assert row.structured_json is not None
    validated = AnthropometryInsightV1.model_validate(row.structured_json)
    assert validated.summary_line == draft2.summary_line


async def test_flagged_direct_reject_no_second_analyst_call(db_session, monkeypatch):
    """FR-013: "at most one revision" is spent on `revise`, never on
    `reject` — a direct `reject` never triggers a second analyst call."""
    draft = _insight()
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _clean_precheck())
    analyst_stub = _sequenced([_analyst_result(draft=draft)])
    monkeypatch.setattr(anthro_pipeline, "run_analyst", analyst_stub)
    critic_stub = _sequenced(
        [_critic_result(decision="rejected", output=draft, violations=[_issue("R02")])]
    )
    monkeypatch.setattr(anthro_pipeline, "run_critic", critic_stub)

    result = await run_analysis(_state(db=db_session, record_id=6))

    assert len(analyst_stub.calls) == 1
    assert len(critic_stub.calls) == 1
    assert result["critic_verdict"] == "flagged"
    assert result["family_deliverable"] is False

    row = await _load_row(db_session, athlete_id=1, record_id=6)
    assert row.critic_verdict == "flagged"
    assert AnthropometryInsightV1.model_validate(row.structured_json) is not None


# ---------------------------------------------------------------------------
# 5. FALLBACK — two ways in, critic NEVER invoked either way
# ---------------------------------------------------------------------------


async def test_fallback_when_analyst_fails_twice(db_session, monkeypatch):
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)

    async def _unexpected_critic(state: dict, config: dict | None = None) -> dict:
        raise AssertionError("the critic must never be invoked after an analyst failure")

    def _unexpected_prechecks(*args: Any, **kwargs: Any) -> PrecheckResult:
        raise AssertionError("prechecks must never run when the analyst itself failed")

    monkeypatch.setattr(anthro_pipeline, "run_critic", _unexpected_critic)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", _unexpected_prechecks)
    monkeypatch.setattr(
        anthro_pipeline, "run_analyst", _sequenced([_analyst_result(draft=None, failed=True)])
    )

    result = await run_analysis(_state(db=db_session, record_id=7, audience="family"))

    assert result["critic_verdict"] == "fallback"
    assert result["family_deliverable"] is False
    assert result["insight"].confidence.level == ConfidenceLevel.LOW
    assert result["insight"].data_gaps  # the fallback data-gap marker is present

    row = await _load_row(db_session, athlete_id=1, record_id=7)
    assert row.critic_verdict == "fallback"
    assert row.schema_version == "v2"
    assert row.structured_json is not None
    # A fallback row is STILL a valid AnthropometryInsightV1 — this is what
    # lets the frontend's v2 renderer handle it with zero special-casing.
    validated = AnthropometryInsightV1.model_validate(row.structured_json)
    assert validated.confidence.level == ConfidenceLevel.LOW


async def test_fallback_when_precheck_must_block(db_session, monkeypatch):
    """FR-014: a `must_block` precheck violation skips the critic call
    entirely — "to avoid spending a call whose verdict cannot change the
    outcome". This is the key assertion the task brief calls out."""
    draft = _insight()
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_analyst", _sequenced([_analyst_result(draft=draft)]))
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _blocking_precheck())

    critic_calls: list[dict] = []

    async def _unexpected_critic(state: dict, config: dict | None = None) -> dict:
        critic_calls.append(state)
        raise AssertionError("the critic must never be invoked when a precheck must_block fired")

    monkeypatch.setattr(anthro_pipeline, "run_critic", _unexpected_critic)

    result = await run_analysis(_state(db=db_session, record_id=8))

    assert critic_calls == []  # the critic was never invoked
    assert result["critic_verdict"] == "fallback"
    assert result["family_deliverable"] is False
    assert result["insight"].confidence.level == ConfidenceLevel.LOW

    row = await _load_row(db_session, athlete_id=1, record_id=8)
    assert row.critic_verdict == "fallback"
    assert row.structured_json is not None
    AnthropometryInsightV1.model_validate(row.structured_json)


# ---------------------------------------------------------------------------
# 6. SKIPPED — critic timed out, no blocking issue
# ---------------------------------------------------------------------------


async def test_skipped_when_critic_unavailable(db_session, monkeypatch):
    draft = _insight(
        confidence_level=ConfidenceLevel.HIGH,
        confidence_reason="El analista reporta alta confianza en esta lectura.",
    )
    skipped_output = draft.model_copy(
        update={
            "confidence": Confidence(
                level=ConfidenceLevel.LOW,
                reason="La revision automatica no estuvo disponible para esta medicion.",
            )
        }
    )
    monkeypatch.setattr(anthro_pipeline, "build_context", _fake_build_context)
    monkeypatch.setattr(anthro_pipeline, "run_prechecks", lambda *a, **k: _clean_precheck())
    monkeypatch.setattr(anthro_pipeline, "run_analyst", _sequenced([_analyst_result(draft=draft)]))
    monkeypatch.setattr(
        anthro_pipeline,
        "run_critic",
        _sequenced([_critic_result(decision="skipped", output=skipped_output)]),
    )

    result = await run_analysis(_state(db=db_session, record_id=9))

    assert result["critic_verdict"] == "skipped"
    assert result["family_deliverable"] is False
    assert result["insight"].confidence.level == ConfidenceLevel.LOW

    row = await _load_row(db_session, athlete_id=1, record_id=9)
    assert row.critic_verdict == "skipped"
    assert row.schema_version == "v2"
    assert row.structured_json is not None
    validated = AnthropometryInsightV1.model_validate(row.structured_json)
    assert validated.confidence.level == ConfidenceLevel.LOW
