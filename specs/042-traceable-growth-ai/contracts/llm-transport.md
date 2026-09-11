# Contract — shared LLM factory, `LangChainProvider` adapter, exception mapping

**New package**: `backend/app/services/llm/` (`factory.py`, `calls.py`, `pricing.py`,
`observability.py`, `observability_metadata.py`) — stack-neutral, extracted from
`backend/app/services/race/agents/_llm.py`, `pricing.py`, `backend/app/services/race/
observability.py` (lead ruling 2).
**Shims**: those three race modules become thin re-export modules — not deleted, not renamed at
their import path.
**Adapter**: `backend/app/services/ai/providers/langchain_provider.py` (new, lead ruling 1).
**Anthropometry pipeline's own LLM calls**: `backend/app/services/ai/anthro/{analyst.py,
critic.py}` call the shared factory **directly**, bypassing the adapter entirely — see §3, this is
not an oversight.
**Related contracts**: `config-env.md` (the `Settings` fields this module resolves),
`trace-metadata-allowlist.md` (the observability half of this package).
**Requirements covered**: FR-017, FR-025; User Story 2.

---

## 0. Two call paths through one factory — do not conflate them

| | `LangChainProvider` adapter | Anthropometry `analyst.py`/`critic.py` |
|---|---|---|
| Who uses it | The five bridged legacy use cases (session assistant clarify/draft, monthly report, monthly report blocks, newsletter v2), behind `AI_USE_LANGCHAIN` (`config-env.md` §1). | The new pipeline only. |
| Interface | Implements `app.services.ai.protocols.LLMProvider` (`ChatCompletion` + `StructuredOutput`) — `complete(LLMRequest) -> LLMResponse`, `complete_json(req, schema) -> dict`. | None — calls `app/services/llm/calls.py::call_llm(llm, prompt, ...)` directly, exactly as `race/agents/analyst.py`/`critic.py` already do. |
| Why the difference | The five legacy use cases have call sites (`use_case.run(...)` in five different routers, ~40 privacy tests reading `fake.last_request`) that must keep working unchanged — the Protocol is the seam that makes that possible. | `PHVExplainerUseCase`/`AnthropometricRecordExplainerUseCase`, the only two use cases that previously called through the Protocol for anthropometry, are **deleted** at the end of W2 (`architecture.md` §Wave 1) — there is no legacy call site to preserve, so there is nothing to adapt. Going through the Protocol here would add a translation layer with no consumer on the other side. |
| Test double | `FakeLLMProvider` (§4). | `GenericFakeChatModel` injected via a pipeline-level factory override (§5), same pattern as `race/ai/runner.py::set_graph_factory`. |

Getting this backwards — routing the anthropometry pipeline through the adapter, or bridging a
legacy use case with a direct `build_chat_llm()` call — is the single most likely design mistake
in this feature; call it out in code review.

## 1. `app/services/llm/factory.py`

```python
@dataclass(frozen=True)
class ProviderConfig:
    provider: str                  # "anthropic" | "google" | "openai" | "claude-cli"
    model: str
    api_key: str | None
    temperature: float | None      # None = builder omits it entirely (§4)
    max_output_tokens: int
    timeout: float
    base_url: str | None


def build_chat_llm(config: ProviderConfig): ...
    # pure dispatch — reads NOTHING from app.config.settings. Every value
    # the builder needs is already on `config`. This is the fix for the
    # latent coupling `_llm.py:89,113` had (config-env.md's new
    # `race_ai_temperature` field).


def resolve_app_config(*, role: str | None = None, **overrides) -> ProviderConfig:
    """App stack (app/services/ai/, including anthro/). NEVER reads a
    RACE_AI_* setting — the one-way inheritance rule, config-env.md §0."""


def resolve_race_config(*, role: str | None = None, **overrides) -> ProviderConfig:
    """Race stack. Reproduces today's exact behaviour: RACE_AI_PROVIDER ->
    AI_PROVIDER inheritance, RACE_AI_ANALYST_MODEL/RACE_AI_CRITIC_MODEL
    per-role lookup, the _resolve_race_api_key fallback to AI_API_KEY when
    the resolved provider matches AI_PROVIDER, and now race_ai_temperature
    instead of the app's ai_temperature."""


def resolve_configured_model(
    *, stack: Literal["app", "race"], provider: str | None = None,
    model: str | None = None, role: str | None = None,
) -> str:
    """Non-instantiating variant — resolves the model_id without building a
    client, for persist.py to record what WOULD run without paying
    construction cost. `stack` selects which resolver's precedence chain
    applies; everything else matches resolve_configured_model's existing
    docstring in race/agents/_llm.py:275-312 (feature 036/037 rationale for
    why this helper exists at all — a single source of truth for 'the
    model configured today', not re-derived here)."""
```

`DEFAULT_MODEL_BY_PROVIDER` (`_llm.py:34-50`) moves verbatim — same dict, same comment about
staying in sync with `pricing.py`'s rate table.

### 1.1 Per-role resolution for the app stack (new — mirrors the race precedent)

```text
explicit argument
  -> AI_<ROLE>_MODEL         (role in {analyst, critic}; "" = unset)
    -> AI_MODEL               (non-empty default, chain stops here)
      -> DEFAULT_MODEL_BY_PROVIDER[provider]   (unreachable in practice)
```

Identical shape to the race stack's own `_ROLE_MODEL_SETTING`/`_resolve_role_model`
(`_llm.py:185-212`), parametrised over `AI_ANALYST_MODEL`/`AI_CRITIC_MODEL` instead of
`RACE_AI_ANALYST_MODEL`/`RACE_AI_CRITIC_MODEL` (`config-env.md` §1). `role=None` (the five bridged
use cases, which have no per-role concept) always resolves straight to `AI_MODEL`, exactly as
`role=None` does for the race stack's `"chat"` role today.

## 2. `app/services/llm/calls.py`, `pricing.py`, `observability.py` — moved verbatim

`call_llm`, `extract_text`, `extract_usage`, `LLMCallResult` (`_llm.py:315-415`);
`compute_cost_usd`, `estimate_tokens_from_chars` (`pricing.py`); the Langfuse client singleton,
`llm_tracing`, `get_callbacks`, `trace_id_for`, `shutdown` (`observability.py`) — same code, same
public names, new module path. No behavioural change beyond `trace-metadata-allowlist.md`'s mask
and session-id fixes, which land in `observability.py` itself, not in this move.

### 2.1 Shims — not a rename

```python
# backend/app/services/race/agents/_llm.py  (entire file body)
from app.services.llm.factory import (
    DEFAULT_MODEL_BY_PROVIDER, build_chat_llm, resolve_configured_model,
)
from app.services.llm.calls import LLMCallResult, call_llm, extract_text, extract_usage
```

Same pattern for `race/agents/pricing.py` and `race/observability.py`. **Why shims, not a
rewrite of every import site**: tests patch by module path —
`tests/services/race/agents/test_llm_helpers.py`, `tests/services/race/agents/test_chat.py`,
`tests/services/race/ai/test_analyst_agent_v2_season_context_prompt.py`,
`tests/evals/test_race_analyst_eval.py` all `monkeypatch.setattr("app.services.race.agents._llm.
build_chat_llm", ...)`. As long as the race modules keep importing these names **from their own
module** (not re-exporting via `__all__` tricks that break `monkeypatch.setattr`'s attribute
lookup), every existing patch target keeps working with zero test-file edits. `app/main.py` and
`app/routers/race_analysis.py` also import `app.services.race.observability` directly — the shim
keeps both alive. **Shims are removed in a follow-up feature, never in this one** — deleting them
here would couple this migration to a full rewrite of the race test suite's patch targets, which
is out of scope (`plan.md` Complexity Tracking, "shims left in race modules" row).

## 3. `LangChainProvider` — the adapter

```python
class LangChainProvider:
    """Implements LLMProvider (ChatCompletion + StructuredOutput) over a
    LangChain BaseChatModel from the shared factory. One instance per
    process, built once by create_llm_provider() — same singleton
    discipline as every other provider in _PROVIDERS."""

    name: str      # e.g. "google"
    model: str     # e.g. "gemini-3.1-flash-lite"

    def __init__(self, chat_model: "BaseChatModel", *, name: str, model: str) -> None: ...

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """
        1. Translate LLMRequest.system + LLMRequest.messages into
           [SystemMessage(system), *[HumanMessage|AIMessage per role]] —
           same shape race/agents/_llm.py::call_llm already uses.
        2. await self._chat_model.ainvoke(messages)  — no config= here;
           the five bridged use cases have no per-request Langfuse scope
           to thread today (contrast the anthro pipeline, §0, which DOES
           thread config explicitly through every step).
        3. text = extract_text(response); usage = extract_usage(response, ...)
        4. Map exceptions (§3.1) before returning; on success, build
           LLMResponse(text=text, usage=TokenUsage(...), model=self.model,
           provider=self.name, latency_ms=..., generated_at=utcnow()).
        """

    async def complete_json(self, req: LLMRequest, schema: dict) -> dict:
        """
        Same prompt-appended-schema + json.loads() + LLMSchemaError-on-
        failure strategy the hand-rolled providers already use
        (AnthropicProvider.complete_json, anthropic_provider.py:90-114) —
        NOT LangChain's with_structured_output(). langfuse.md §4 confirms
        this is the right call: two of the four providers (claude-cli,
        Ollama-backed openai) have unconfirmed tool-calling support, and
        the existing strategy already works uniformly across all four.
        Migrating to LangChain buys tracing and one client surface, not a
        structured-output mechanism — do not conflate the two goals.
        """
```

### 3.1 Exception mapping (`app/services/ai/errors.py`, unchanged hierarchy — `LLMError` ->
`LLMConfigError` / `LLMUnavailableError` -> `LLMTimeoutError` / `LLMSchemaError`)

| LangChain / provider-SDK exception | Mapped to |
|---|---|
| `ModelTimeoutError` (LangChain-standardised across chat models, wraps the provider SDK's own timeout type) | `LLMTimeoutError` |
| Any other connection/API error from the underlying provider SDK | `LLMUnavailableError` |
| `json.JSONDecodeError`, or the parsed JSON failing the caller-supplied `schema` | `LLMSchemaError` (`complete_json` only) |
| Adapter constructed with an unsupported `provider` string at factory time | `LLMConfigError` (raised once, at `create_llm_provider()`, never per-call) |

This is a genuinely **different exception type** than the pre-042 hand-rolled providers caught
(`AnthropicProvider.complete()` today catches `anthropic.APITimeoutError` specifically,
`anthropic_provider.py:67-68`) — the adapter's `except` clauses target LangChain's standardised
`ModelTimeoutError` and its documented provider-specific parents instead, per `langfuse.md` §4.
Router-facing behaviour (503/502/500 mapping in `ai.py`) is unchanged; only what the adapter
catches internally changes.

## 4. Anthropic — no `temperature`, ever (both call paths)

`claude-sonnet-5` (Claude 4.6+) rejects any non-default `temperature`/`top_p`/`top_k` with a
`400`. Both `_build_anthropic_llm` (reused verbatim from `_llm.py:53-72` — the builder function
body does not change, only its call site moves) and the pre-existing
`AnthropicProvider.complete()` (`anthropic_provider.py:57-60`) already enforce this by never
forwarding the parameter to the SDK constructor, regardless of what `config.temperature` holds.
The `claude-cli` builder does the same, for a different reason (`_build_claude_cli_llm`'s
docstring, `_llm.py:130-146`: the CLI subprocess also rejects non-default sampling params). This
rule does not move to the resolver — it stays exactly where the proven, tested code already
enforces it, at the builder level.

## 5. `claude-cli` — lazy import, local-only

`build_chat_llm`'s `claude-cli` branch keeps its `try: from langchain_claude_cli import
ChatClaudeCli except ImportError: raise ImportError(...)` (`_llm.py:148-157`) — the package stays
out of `requirements.txt` by design. `config-env.md` §2 adds the enforced production ban on top of
this existing convention; nothing here changes the lazy-import mechanics.

## 6. `FakeLLMProvider` — unchanged, and why it survives untouched

`create_llm_provider()` (`app/services/ai/factory.py:89`) short-circuits to `FakeLLMProvider`
**before** any LangChain dispatch, on two conditions that do not change: `AI_ENABLED=false`
(`factory.py:98`) and `AI_PROVIDER=fake` (`factory.py:83`). `LangChainProvider` is a sibling entry
in `_PROVIDERS`, never a wrapper around the fake — so the roughly 40 assertions reading
`fake.last_request.messages[-1].content` (proving no name, birth date or measurement reaches a
provider prompt, e.g. `test_pii_never_reaches_llm` at `test_ai_record_explainer.py:156` — a test
file that itself disappears with the use case it tests, but the *pattern* it establishes is what
the five bridged use cases' own equivalent tests still rely on) keep running against the identical
object, in the identical code path, with zero edits.

## 7. `GenericFakeChatModel` — exactly two legal locations

1. `tests/test_langchain_provider.py` — the adapter's own unit tests (translation correctness,
   exception mapping), stubbing `BaseChatModel` directly.
2. `tests/anthro/**` — the pipeline's integration tests, injected via a `set_chat_model_factory`-
   style override on `pipeline.py` (mirrors `race/ai/runner.py::set_graph_factory`,
   `runner.py:93`).

**Never** as a fixture for a use-case or router test outside those two locations. State this as a
standing rule in code review: a `GenericFakeChatModel` fixture appearing anywhere else is a sign
someone "modernised" a privacy assertion onto a LangChain fake and silently dropped the guarantee
`FakeLLMProvider`'s `last_request` surface exists to give (`architecture.md` §11.1, explicit).

## 8. `test_factory_openai_not_implemented` — the fix, not the inheritance

Pre-existing, unrelated to the LangChain migration but touched by this feature because it lives in
the file this feature edits (`app/services/ai/factory.py`). `tests/test_ai_factory.py::
test_factory_openai_not_implemented` asserts `AI_PROVIDER=openai` raises `LLMConfigError` — false
since `factory.py:83` gained a real `"openai"` entry (feature-unrelated, pre-existing drift) and
`openai>=1.0,<3` is installed. **Fix the test's assertion** (either delete it or repoint it at a
provider string that is genuinely unsupported, e.g. an invalid literal) — do not reintroduce a
`LLMConfigError` for a provider `factory.py` legitimately supports just to make the old assertion
pass again. Every other test in the area (117 across the six files `architecture.md` §1.5 lists)
passes; only this one assertion is stale.

## 9. Tests

- `test_langchain_provider_translates_request_and_response` — `GenericFakeChatModel` stub in,
  normalised `LLMResponse` out (text, `TokenUsage`, `model`, `provider`, `latency_ms`).
- `test_langchain_provider_complete_json_raises_schema_error_on_non_json` — malformed JSON from
  the stub model raises `LLMSchemaError`, not a bare `json.JSONDecodeError` escaping the adapter.
- `test_langchain_provider_maps_timeout_and_unavailable` — stub raises `ModelTimeoutError` and a
  generic connection error respectively; asserts `LLMTimeoutError`/`LLMUnavailableError`.
- `test_provider_inheritance_matrix` — parametrised over `(AI_PROVIDER, RACE_AI_PROVIDER)`,
  asserting `resolve_app_config` never returns the race provider and `resolve_race_config` still
  inherits (`config-env.md` §6 extends this to include `claude-cli`).
- `test_anthropic_never_receives_temperature` — build with `provider="anthropic",
  temperature=0.9` against a stubbed `ChatAnthropic`, assert `temperature` was never passed to the
  constructor — currently **missing** (`architecture.md` §9.3, item 2), added by this feature.
- `test_claude_cli_lazy_import` — importing `app.services.llm.factory` does not import
  `langchain_claude_cli`; building without the package installed raises a clear `ImportError`.
- `test_redact_always_preserved_after_factory_move` — `trace-metadata-allowlist.md` §1's mask,
  with `LANGFUSE_STRUCTURAL_METADATA=false`, is byte-for-byte identical to the pre-move behaviour.
- `test_shim_modules_expose_identical_public_names` — `dir(app.services.race.agents._llm)` (etc.,
  for the other two shims) contains every name the pre-042 module exported, so a stray
  `monkeypatch.setattr` target that this contract's author missed still resolves.
- `test_ai_use_langchain_flag_both_values_green` — the five bridged use cases' existing test
  files pass unmodified under both `AI_USE_LANGCHAIN=true` and `=false`.
- `test_race_temperature_bug_fix` — see `config-env.md` §6 (same test, cross-referenced, not
  duplicated).
