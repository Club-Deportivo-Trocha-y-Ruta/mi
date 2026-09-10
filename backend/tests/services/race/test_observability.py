"""Tests del observador Langfuse local (``app/services/race/observability.py``).

Offline: el cliente exporta a un ``InMemorySpanExporter`` con un
``TracerProvider`` propio (sin proveedor OTel global ni red). Los textos de
prueba son sintéticos — ningún dato real de menores.
"""

from __future__ import annotations

import ast
import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from app.config import Settings, settings
from app.services.race import observability
from app.services.race.agents._llm import call_llm
from app.services.race.agents.chat import RaceChatAgent, _SessionStore
from app.services.race.ai import runner
from app.services.race.observability import REDACTED

NAME_SENTINEL = "SENTINELA_NOMBRE_MENOR"
HITL_SENTINEL = "SENTINELA_BORRADOR_HITL"


class _FakeChatModel(GenericFakeChatModel):
    model: str = "fake-race-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_FakeChatModel":
        return self


def _llm(*contents: str) -> _FakeChatModel:
    return _FakeChatModel(
        messages=iter(
            AIMessage(
                content=c,
                usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            )
            for c in contents
        )
    )


@pytest.fixture
def exporter(monkeypatch):
    from langfuse._client.resource_manager import LangfuseResourceManager
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    span_exporter = InMemorySpanExporter()
    create_client = observability._create_client
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-test")
    monkeypatch.setattr(settings, "langfuse_base_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "langfuse_capture_content", False)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(
        observability,
        "_create_client",
        lambda: create_client(tracer_provider=TracerProvider(), span_exporter=span_exporter),
    )
    LangfuseResourceManager.reset()
    yield span_exporter
    LangfuseResourceManager.reset()


def _finished_spans(span_exporter) -> list[Any]:
    observability._client.flush()
    return list(span_exporter.get_finished_spans())


def _generations(spans: list[Any]) -> list[Any]:
    return [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]


def _all_attribute_text(spans: list[Any]) -> str:
    return " ".join(f"{s.status.description} {dict(s.attributes)}" for s in spans)


class _State(TypedDict, total=False):
    forbidden_names: list[str]
    prompt_version: str
    analysis_kind: str
    out: str
    decision: str


def _hitl_graph(llm: _FakeChatModel):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    async def analyst(state: _State) -> dict:
        response = await llm.ainvoke([HumanMessage(content="prompt seudonimizado de Atleta A")])
        return {"out": response.content}

    def gate(state: _State) -> dict:
        return {"decision": interrupt({"draft_markdown": HITL_SENTINEL})}

    builder = StateGraph(_State)
    builder.add_node("analyst", analyst)
    builder.add_node("gate", gate)
    builder.add_edge(START, "analyst")
    builder.add_edge("analyst", "gate")
    builder.add_edge("gate", END)
    return builder.compile(checkpointer=InMemorySaver())


async def _start_and_resume(run_id: str, llm: _FakeChatModel) -> list[BaseException | None]:
    graph = _hitl_graph(llm)
    errors: list[BaseException | None] = []

    async def graph_factory():
        return graph

    async def on_complete(rid, exc, result_state):
        errors.append(exc)

    runner.set_graph_factory(graph_factory)
    try:
        initial_state = {
            "forbidden_names": [NAME_SENTINEL],
            "prompt_version": "race_analyst_v3",
            "analysis_kind": "valida",
        }
        await (await runner.submit_run(run_id, initial_state, on_complete=on_complete))
        await (await runner.resume_run(run_id, "approve", on_complete=on_complete))
    finally:
        runner.set_graph_factory(None)
        await runner._reset_for_tests()
    return errors


# ---------------------------------------------------------------------------
# Apagado / configuración
# ---------------------------------------------------------------------------


async def test_disabled_yields_nothing_and_never_builds_client(monkeypatch):
    calls: list[Any] = []
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_create_client", lambda **kw: calls.append(kw))

    assert observability.get_callbacks() == []
    assert observability.trace_id_for("run-1") is None
    with observability.llm_tracing(trace_name="race-analysis", session_id="run-1") as tracing:
        assert tracing == {}
    observability.shutdown()

    assert calls == []


def test_module_never_imports_langfuse_at_top_level():
    tree = ast.parse(Path(observability.__file__).read_text(encoding="utf-8"))
    modules = [
        alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names
    ] + [node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)]

    assert not any(module.startswith("langfuse") for module in modules)


def test_enabled_without_keys_warns_once_and_stays_disabled(monkeypatch, caplog):
    calls: list[Any] = []
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_warned_missing_keys", False)
    monkeypatch.setattr(observability, "_create_client", lambda **kw: calls.append(kw))

    with caplog.at_level(logging.WARNING, logger="app.services.race.observability"):
        assert observability.get_callbacks() == []
        assert observability.get_callbacks() == []

    warnings = [r for r in caplog.records if "LANGFUSE_PUBLIC_KEY" in r.getMessage()]
    assert len(warnings) == 1
    assert calls == []


def test_langfuse_enabled_rejected_in_production():
    with pytest.raises(ValidationError, match="LANGFUSE_ENABLED"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="0" * 64,
            email_provider="resend",
            resend_api_key="re_xxx",
            langfuse_enabled=True,
        )


def test_langfuse_enabled_allowed_outside_production():
    assert Settings(_env_file=None, langfuse_enabled=True).langfuse_enabled is True


def test_default_test_lane_forces_tracing_off():
    assert os.environ["LANGFUSE_ENABLED"] == "false"
    assert Settings().langfuse_enabled is False


def test_mask_redacts_everything_unless_generation_content_allowed(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_capture_content", True)

    assert observability._mask(data=None) is None
    assert observability._mask(data={"prompt": NAME_SENTINEL}) == REDACTED


# ---------------------------------------------------------------------------
# Trazas con cliente real + exporter en memoria
# ---------------------------------------------------------------------------


async def test_one_generation_per_call_with_usage_and_model_redacted_by_default(exporter):
    llm = _llm("Atleta A mejoró su vuelta")

    with observability.llm_tracing(
        trace_name="race-eval-judge", session_id="case_001", tags=["judge-v2"]
    ) as tracing:
        result = await call_llm(llm, "prompt de prueba de Atleta A", config=tracing)

    assert (result.tokens_in, result.tokens_out) == (11, 7)
    (generation,) = _generations(_finished_spans(exporter))
    attrs = generation.attributes
    assert attrs["langfuse.observation.model.name"] == "fake-race-model"
    assert json.loads(attrs["langfuse.observation.usage_details"]) == {
        "input": 11,
        "output": 7,
        "total": 18,
    }
    assert attrs["langfuse.observation.input"] == REDACTED
    assert attrs["langfuse.observation.output"] == REDACTED
    assert attrs["langfuse.observation.metadata"] == REDACTED
    assert attrs["langfuse.trace.name"] == "race-eval-judge"
    assert attrs["session.id"] == "case_001"


async def test_graph_run_traces_nested_llm_once_under_pinned_trace_across_resume(exporter):
    run_id = "5b0c7a3e-0000-4000-8000-000000000001"

    errors = await _start_and_resume(run_id, _llm("salida seudonimizada"))

    assert errors == [None, None]
    spans = _finished_spans(exporter)
    assert len(_generations(spans)) == 1
    expected_trace_id = observability.trace_id_for(run_id)
    assert {format(s.context.trace_id, "032x") for s in spans} == {expected_trace_id}
    tags = {tag for s in spans for tag in s.attributes.get("langfuse.trace.tags", ())}
    assert {"prompt:race_analyst_v3", "kind:valida", "hitl-resume"} <= tags
    assert {s.attributes.get("session.id") for s in spans} == {run_id}
    text = _all_attribute_text(spans)
    assert NAME_SENTINEL not in text
    assert HITL_SENTINEL not in text


async def test_capture_content_shows_pseudonymized_generation_but_never_graph_state(
    exporter, monkeypatch
):
    monkeypatch.setattr(settings, "langfuse_capture_content", True)

    await _start_and_resume("5b0c7a3e-0000-4000-8000-000000000002", _llm("salida Atleta A"))

    spans = _finished_spans(exporter)
    (generation,) = _generations(spans)
    assert "Atleta A" in generation.attributes["langfuse.observation.input"]
    assert "Atleta A" in generation.attributes["langfuse.observation.output"]
    chains = [s for s in spans if s.attributes.get("langfuse.observation.type") == "chain"]
    assert chains
    assert all(s.attributes.get("langfuse.observation.input") in (None, REDACTED) for s in chains)
    text = _all_attribute_text(spans)
    assert NAME_SENTINEL not in text
    assert HITL_SENTINEL not in text


async def test_chat_trace_stays_redacted_even_with_capture_content(exporter, monkeypatch):
    monkeypatch.setattr(settings, "langfuse_capture_content", True)

    @tool
    def stub_tool() -> str:
        """Herramienta de prueba."""
        return "ok"

    agent = RaceChatAgent(
        llm=_llm(f"Respuesta sobre {NAME_SENTINEL}"),
        tools=[stub_tool],
        session_store=_SessionStore(),
    )
    response = await agent.chat(session_id="chat-session-1", query=f"¿Cómo va {NAME_SENTINEL}?")

    assert NAME_SENTINEL in response.answer
    spans = _finished_spans(exporter)
    (generation,) = _generations(spans)
    assert generation.attributes["langfuse.trace.name"] == "race-chat"
    assert generation.attributes["session.id"] == observability.anonymous_session_id(
        "chat-session-1"
    )
    assert generation.attributes["langfuse.observation.input"] == REDACTED
    assert generation.attributes["langfuse.observation.output"] == REDACTED
    assert json.loads(generation.attributes["langfuse.observation.usage_details"])["input"] == 11
    assert NAME_SENTINEL not in _all_attribute_text(spans)


async def test_handler_creation_failure_degrades_to_untraced_run(exporter, monkeypatch):
    def broken_handler_class():
        raise RuntimeError("handler roto")

    monkeypatch.setattr(observability, "_handler_class", broken_handler_class)

    assert observability.get_callbacks() == []
    with observability.llm_tracing(trace_name="race-eval-judge", session_id="case_002") as tracing:
        assert tracing == {}
        result = await call_llm(_llm("ok"), "prompt", config=tracing)

    assert result.text == "ok"
    assert _generations(_finished_spans(exporter)) == []
