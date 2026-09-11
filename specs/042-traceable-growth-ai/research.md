# Research — Traceable growth AI (042)

**Date**: 2026-09-11 · **Inputs**: `spec.md`, `/tmp/042-research/LEAD-DECISIONS.md` (binding rulings on this feature's planning, 2026-09-11), `/tmp/042-research/architecture.md` (system-architect, revision 2), `/tmp/042-research/theory.md` (sports-science literature audit), `/tmp/042-research/ux.md` (heuristic + accessibility audit), `/tmp/042-research/ui-design-analysis-summary.md` (UI design handoff), `/tmp/042-research/langfuse.md` (Langfuse v4 + LangChain 1.x SDK research), `/tmp/042-research/privacy.md` (structural-metadata privacy audit), `/tmp/042-research/analysis-design.md` (pipeline/prompt design), `CLAUDE.md`, `specs/040-growth-module-redesign/research.md` (precedent for format and for the growth-summary/velocity constants this feature reuses).

Each entry: **Decision** · **Rationale** · **Alternatives considered** · (where useful) **Evidence**. Where a research brief's own recommendation was overridden by the lead's binding rulings, that supersession is stated explicitly rather than silently dropped — later implementers should not have to re-derive why the shipped decision differs from what one of the source documents argued for.

---

## R-01 Transport: the LangChain adapter (Option A), not a full rewrite or a two-system split

**Decision**: `app/services/ai/providers/langchain_provider.py` implements the existing `LLMProvider` Protocol over a LangChain `BaseChatModel` built by the shared factory (R-02), for **all** `app/services/ai/` use cases — the session assistant, monthly report, monthly report blocks, newsletter v2, and (until it is rebuilt in this same feature) the two anthropometry explainers. `create_llm_provider` gains one branch; every use case keeps its prompts, its `complete_json` strategy, its DI wiring and its tests untouched. `FakeLLMProvider` remains the `AI_ENABLED=false` / `AI_PROVIDER=fake` test double, selected **before** any LangChain dispatch — so the ~40 existing assertions that read `fake.last_request.messages[-1].content` (proving no athlete name, birth date or measurement reaches a provider prompt) keep running unchanged, in the identical code path, across all six test files that override `get_llm_provider`.

**Rationale**: The transport question and the anthropometry-quality question are independent. Bridging the five non-anthropometry use cases through the Protocol adapter (rather than rewriting them onto native LangChain structured output) preserves their existing golden-eval-free surfaces exactly as-is while still giving them Langfuse traces — the newsletter v2 (`athlete_monthly_newsletter_v2`) has no golden eval today, so a structured-output shape change there would reach families before a test could catch it. `AI_USE_LANGCHAIN` (default true; false routes the five migrated use cases to the legacy SDK providers) makes reverting a one-line config change, not a code revert.

**Alternatives considered**: A full LCEL rewrite of all seven use cases with native structured output (architecture.md's original "Option C exit gate", called Wave 3) — rejected for this feature: it requires deleting `protocols.py`/`models.py`/the four SDK adapters and needs a golden or characterization eval on all five bridged use cases first, which the newsletter does not have; listed as a later, explicitly out-of-scope step. A minimal two-use-case adapter (the original architecture.md revision-1 recommendation, covering only the anthropometry explainers) — superseded by the owner's 2026-09-11 decision to migrate the whole `app/services/ai/` stack's transport, while keeping only the anthropometry analysis itself rebuilt.

**Evidence**: LEAD-DECISIONS.md #1; architecture.md §11.1, §1.3 (blast-radius table), §1.4 (`fake.last_request` assertion count); spec.md FR-025.

---

## R-02 Shared factory extraction, one-way env inheritance, and the Anthropic-temperature bug fix

**Decision**: New provider-neutral, stack-neutral package `app/services/llm/` (factory, call helpers, pricing, tracing/observability, redaction), extracted from `app/services/race/agents/_llm.py`, `pricing.py` and `race/observability.py`, which become thin re-export shims so every existing test `monkeypatch.setattr` target keeps working. The one-way inheritance rule is preserved and now enforced by a parametrised regression test: the race stack may read `AI_*` as a fallback (`RACE_AI_PROVIDER` → `AI_PROVIDER`, etc.), but the app stack's resolver never reads `RACE_AI_*`. On the way, the factory is split into pure dispatch (`build_chat_llm(config)`) plus two named resolvers, `resolve_app_config()` and `resolve_race_config()`, fixing a latent bug: `_build_google_llm`/`_build_openai_llm` currently fall back to `settings.ai_temperature` even when serving the race stack, so the race pipeline's temperature has been silently governed by the *other* stack's variable. With `ProviderConfig.temperature` resolved by the caller, each stack owns its own value — a deliberate, called-out behaviour change.

**Rationale**: `get_llm_provider()` is a process-wide `lru_cache(maxsize=1)` singleton serving all seven `app/services/ai/` use cases; extracting shared LLM plumbing without a pure-config boundary would let a local `RACE_AI_PROVIDER=claude-cli` silently redirect the PHV explainer to the CLI. Shims (not a rename) keep four existing test files' `monkeypatch` targets alive without a mass find-and-replace.

**Alternatives considered**: Leaving `_llm.py` as the single owner and having the app stack import it directly — rejected, it is what caused the temperature bug in the first place and keeps the inheritance direction implicit rather than tested. Renaming the race modules outright instead of shimming — rejected, breaks four test files' patch targets in the same PR as the extraction, which the plan explicitly avoids (delete shims only in a later, separate cleanup).

**Evidence**: LEAD-DECISIONS.md #2; architecture.md §3.1-§3.2 (`_llm.py:89`, `:113` for the temperature bug), §9.3 items 2-3 (the two new regression tests).

---

## R-03 Anthropometry pipeline: a plain async sequential orchestrator, not LangGraph

**Decision**: Five pure `async def step(state, config: RunnableConfig) -> dict` functions (`context.py`, `analyst.py`, `critic.py`, `guardrails_step.py`, `persist.py`) called in sequence by `pipeline.py`, with **no LangGraph `StateGraph`, no checkpointer, no HITL**. Each step's signature is deliberately identical to a LangGraph node's, so promotion to a `StateGraph` later — if p95 latency or a future branching need justifies it — is a mechanical wrapping, not a rewrite.

**Rationale**: LangGraph earns its cost through checkpointing, `interrupt()`, conditional routing and fan-out; this pipeline has none of those — no HITL, no resume, no branch except a single conditional edge on early failure. Without a checkpointer, a `StateGraph` here is a dict-threading loop plus an import. Per `langfuse.md` §1, LangGraph also gives no tracing-propagation advantage: nodes must declare `config: RunnableConfig` and thread it explicitly into every `ainvoke` regardless of framework, because implicit contextvar propagation is exactly the fragility that document flags (and that the *existing* race nodes rely on today, `nodes/analyst_agent.py` declaring `async def analyst_agent(state: dict)` with no `config` parameter — a pattern this pipeline should not copy).

**Alternatives considered**: A small LangGraph graph, as the owner's initial framing in `architecture.md`'s revision-2 header suggested ("Designed as a small LangGraph graph"). The system architect flagged this tension explicitly in its own §11.2 as a deviation pending the lead's call; the lead resolved it in favor of the plain orchestrator, since the cost of being wrong is near zero (the step signatures already match a LangGraph node) and the orchestrator avoids importing a graph-execution framework for a five-step linear pipeline with no branching.

**Evidence**: LEAD-DECISIONS.md #3; architecture.md §11.2 (code sketch, the deviation note), §4.1 (the graph topology this replaces 1:1).

---

## R-04 Module location: `app/services/ai/anthro/`, not a `growth_ai` sibling package

**Decision**: `app/services/ai/anthro/` — `context.py`, `analyst.py`, `critic.py`, `prechecks.py`, `guardrails_step.py`, `persist.py`, `pipeline.py`, `schemas.py`, `prompts/anthropometry_analyst_v1.md` + `anthropometry_critic_v1.md` with their own Jinja loader (the existing `PromptRegistry` at `app/services/ai/prompts/registry.py` is not touched, since it serves the single-shot `BaseUseCase._ask` pattern the new pipeline does not use).

**Rationale**: The pipeline is a rebuild of two existing `app/services/ai/` use cases (the PHV explainer and the record explainer), not a new top-level domain; nesting it under `app/services/ai/` keeps it next to the shared factory, the provider adapter and the other five use cases it will eventually share a transport switch with.

**Alternatives considered**: `app/services/growth_ai/` mirroring `app/services/race/{ai,agents,prompts,eval}/` 1:1 (analysis-design.md's own recommendation, on the reasoning that the input is the growth-module surface from feature 040 rather than raw ingestion) — rejected by the lead as introducing a third top-level AI package name for what is functionally two `app/services/ai/` use cases being rebuilt, not a new independent stack. `app/services/anthropometry/ai/` (analysis-design.md's own listed alternative) — not adopted either, for the same reason.

**Evidence**: LEAD-DECISIONS.md #3; analysis-design.md §0.

---

## R-05 Per-role env vars and the transport switch — new names, not a reuse of `RACE_AI_*`

**Decision**: `AI_ANALYST_MODEL`, `AI_CRITIC_MODEL` (both default `""` → fall back to `AI_MODEL`). Prompt version: `AI_ANTHRO_PROMPT_VERSION`, default `anthropometry_analyst_v1`. Transport switch: `AI_USE_LANGCHAIN`, default `true` (false routes the five migrated use cases in R-01 back to the legacy SDK providers). No `ANTHRO_AI_*` prefix.

**Rationale**: CLAUDE.md's inheritance rule is deliberately one-way — race may inherit `AI_PROVIDER`, the app stack must never read `RACE_AI_*`. Reusing `RACE_AI_ANALYST_MODEL`/`RACE_AI_CRITIC_MODEL` would invert that and turn the `RACE_AI_` prefix into a de-facto global namespace. It also removes an operational dial the club may want: the coach could reasonably run the race analyst on a stronger model while anthropometry stays cheap, or the reverse. Cost is zero — both new variables default to `""`, so a fresh checkout needs no new required configuration.

**Alternatives considered**: Reusing `RACE_AI_ANALYST_MODEL`/`RACE_AI_CRITIC_MODEL` directly (raised as an open question in `architecture.md` §3.3 and again in `analysis-design.md` §3.4, which had provisionally proposed a distinct `ANTHRO_AI_*` prefix mirroring the race pattern) — rejected on both counts by the lead in favor of the flatter `AI_ANALYST_MODEL`/`AI_CRITIC_MODEL` naming, since the pipeline lives inside `app/services/ai/`, not as a third independent stack.

**Evidence**: LEAD-DECISIONS.md #4; architecture.md §3.3-§3.4 (resolution order and env-var compatibility matrix); analysis-design.md §3.4 (superseded proposal, noted there as pending the architect's addendum).

---

## R-06 No spending cap for this stack — the architect's warn-only proposal is rejected

**Decision**: No cap, no warn-only `AI_BUDGET_USD_30D`, no rate limit, and no change to `budget_guard.py` or `RACE_AI_BUDGET_USD_30D`. Cost is recorded per generation (`cost_usd`, R-07) and shown in the feature-041 per-coach spend view with a `stack` label (`app` vs `race`), never counted against or refused by the race spending limit.

**Rationale**: At roughly 3,000 input / 800 output tokens for the analyst on `gemini-3.8-flash` (≈0.0053 USD) and 4,000/300 for the critic on `gemini-3.1-flash-lite` (≈0.0015 USD), one analysis costs ≈0.0068 USD; at roughly 20 athletes × 4 measurements a year (~80 analyses/year), that is well under 1 USD/year against a 20 USD/30-day race budget — anthropometry cannot realistically exhaust any plausible pool, which removes the argument for guarding it at all.

**Alternatives considered**: A club-wide shared pool with `RACE_AI_BUDGET_USD_30D` widened to cover both stacks (`architecture.md` §8's original recommendation, with a concrete query-widening plan) — rejected because it makes a live production `503` gate depend on a second cost source for no safety benefit, risking the coach's race analyses being blocked by anthropometry noise. A separate, warn-only `AI_BUDGET_USD_30D` (default 5 USD, ERROR-level log with a 1-hour cooldown, mirroring the race stack's current log-only overrun path) plus a regeneration rate limit — this was the architect's own revised §11.3 recommendation after the shared-pool idea was dropped; the lead rejected it too, judging that even a non-blocking warning threshold adds an operational dial with no corresponding risk to manage at these costs.

**Evidence**: LEAD-DECISIONS.md #5; architecture.md §8 (pricing table), §11.3 (rejected warn-only proposal, the specific numbers above).

---

## R-07 Persistence on `athlete_ai_explanations`, nine nullable columns, single Alembic head

**Decision**: Extend `athlete_ai_explanations` (not a new table, not `agent_runs`) with nine nullable columns: `schema_version` (`VARCHAR(8)`), `structured_json` (`JSON`), `critic_verdict` (`VARCHAR(16)`), `prompt_version` (`VARCHAR(32)`), `tokens_in` (`INT`), `tokens_out` (`INT`), `cost_usd` (`DECIMAL(10,6)`), `latency_ms` (`INT`), `langfuse_trace_id` (`VARCHAR(64)`). `text` stays `NOT NULL` and holds the rendered prose for v2 rows too (rendered from the structured output, the same move `race/insight_v3.py` makes with `_action_bullet`). One Alembic revision, `down_revision="45cd705c6b54"`. Legacy free-prose rows have `schema_version` `NULL` and render exactly as v1 today; no backfill.

**Rationale**: `agent_runs` is shaped for the race pipeline's runner (`graph_name`, `checkpoint_thread_id`, `external_run_id` all `NOT NULL`; a status enum including `awaiting_hitl`) — the anthropometry pipeline has no thread, no HITL and no external run id, so a row would either need those columns faked or the model relaxed for a use case that doesn't need its semantics. Reading cost off `athlete_ai_explanations` also keeps anthropometry spend visibly separate from the race cost rollup, which matters now that R-06 keeps the two pools unmixed. The `45cd705c6b54` head was independently re-verified by walking every `down_revision` in `backend/alembic/versions/`; CLAUDE.md currently names the wrong one (`2a8baa967cc6`, actually that revision's own parent).

**Alternatives considered**: A new dedicated table (`athlete_growth_insights`, floated as an open architecture question in `analysis-design.md` §1.6) — not adopted; extending the existing cache table keeps one place per (athlete, record, use_case) key and avoids a second query path for the growth-tab summary line (R-23). Writing `agent_runs` rows to reuse the race cost rollup mechanically — rejected for the schema-mismatch reason above, and because cost-sharing should be a deliberate decision (R-06), not a side effect of writing into a table shaped for something else.

**Evidence**: LEAD-DECISIONS.md #6; architecture.md §1.5 (verified Alembic head), §6.1-§6.3, §11.5 (final nine-column list, superseding the architect's own earlier eight-column draft).

---

## R-08 Structured-output strategy: JSON-in-prompt plus validation, not `with_structured_output`

**Decision**: The analyst and critic steps keep the pattern already proven in `AnthropicProvider.complete_json` — a system-prompt instruction to return JSON matching the schema, `json.loads()`, then Pydantic `model_validate` with `extra="forbid"`; on failure, one retry with the validation error appended, then the deterministic fallback (R-15). No LangChain `with_structured_output()` call for this feature.

**Rationale**: Two of the four supported providers have no confirmed reliable tool-calling/native-structured-output path: `ChatClaudeCli` is a thin, project-local CLI wrapper whose `bind_tools` support is undocumented and unverified, and `ChatOpenAI` via the local Ollama endpoint depends entirely on the specific local model's tool-calling support. LangChain's `method=` choices (`json_schema`, `function_calling`, `json_mode`) require picking one explicitly per provider with no universal auto-detect outside `langchain.agents.create_agent` — there is no single call that works uniformly across all four. The prompt-instructs-JSON approach already does, and it is what `race/agents/_llm.py::call_llm` and the hand-rolled providers already rely on. `ChatAnthropic` continues to omit `temperature` entirely from its constructor (Claude 4.6+/claude-sonnet-5 return 400 on any non-default sampling parameter) — reuse the existing builder verbatim rather than re-deriving it.

**Alternatives considered**: `model.with_structured_output()` per provider — rejected as the primary mechanism for exactly the reason above; migrating to LangChain buys tracing and a unified client surface, not structured output, and the two goals should not be conflated in this feature.

**Evidence**: LEAD-DECISIONS.md #7 (implicit — no `with_structured_output` requirement); langfuse.md §4 (provider matrix, `with_structured_output` method options, `ChatClaudeCli`/Ollama uncertainty); analysis-design.md §5.1 (tolerant extractor, one retry, then fallback).

---

## R-09 Structured insight schema and the versioning discriminator

**Decision**: `AnthropometryInsightV1` (`app/services/ai/anthro/schemas.py`), per `analysis-design.md` §4: `summary_line` (≤140 chars), `changes` (1–4 items), `meaning` (1–4), `next_weeks` (1–3), `warning_signs` (0–2), `confidence` (`{level, reason≤200 chars}`), `data_gaps` (0–3), `word_count` (telemetry only, never used to enforce the budget). **Note the deliberate naming split**: the Pydantic class is named `V1` because it is the first version of the *new* structured schema, but the value **persisted** in the `schema_version` column for these rows is `"v2"` — `"v1"` is reserved for the legacy free-prose rows written before this feature. Implementers must not conflate the class name with the discriminator value. Critic verdict enum, also persisted: `approved | revised | flagged | fallback | skipped`. Family delivery is blocked unless the verdict is `approved` or `revised` (R-24).

**Rationale**: A closed `extra="forbid"` schema turns a hallucinated extra field into a parse error rather than a silent leak, matching the race stack's `InsightV3` precedent. Keeping the persisted `schema_version` semantics anchored to "prose vs. structured" (not "first vs. second structured schema") means a future `AnthropometryInsightV2` class, if one is ever built, can persist as `schema_version="v3"` without disturbing the v1/v2 discriminator meaning already shipped.

**Alternatives considered**: `min_length=2` on `changes`/`what_changed` (the race pattern) — rejected for the first-measurement case, where there is exactly one thing to say; forcing a second observation on a first measurement is how a model starts inventing a trend, the same failure race's N=1 veto exists to stop.

**Evidence**: LEAD-DECISIONS.md #7; analysis-design.md §4 (full schema); architecture.md §4.2 (the race-parallel design points, in particular the `min_length=1` rationale, there attached to an earlier `AnthroInsightV2` name subsequently superseded by the lead's naming).

---

## R-10 Velocity reliability gate: 8-week compute floor, 26-week confidence threshold

**Decision**: `MIN_WEEKS_FOR_VELOCITY=8` stays unchanged as the floor for *computing* a velocity number at all. A new `VELOCITY_RELIABLE_WEEKS=26` threshold drives a `velocity_confidence: reliable | early_signal | null` field: `reliable` at ≥26 weeks, `early_signal` at 8–25 weeks, `null` below 8. Only `reliable` velocity may be classified as typical/high/low for the athlete's stage; `early_signal` velocity is described as a first signal that does not yet confirm a trend and is never given a typical/high/low label. `phase_crossing_corroborated` is computed deterministically (not left to the model): true only when the reading before the previous one shows the same prior phase **and** the pair spans at least the stage's own re-test interval (30/90/120 days, from the existing `measurement_alerts.MEASUREMENT_INTERVALS`).

**Rationale**: Clinical pediatric growth-monitoring literature is consistent that height velocity should be derived from measurements at least six months (26 weeks) apart — shorter intervals are dominated by measurement imprecision and by children's well-documented "saltatory" short-term growth pattern, where a child can be at the 95th percentile of growth rate one month and the 20th the next. The repo's existing 8-week floor is roughly a third of that clinical minimum. Rather than raise the floor outright (which would silently stop showing any number for the club's actual ~monthly Circa-PHV measurement cadence), the confidence *language* is gated instead — the softer of the two options the literature audit weighed, chosen because this is a coach/family communication problem, not a clinical-monitoring one, and because it preserves earlier partial signal instead of discarding it.

**Alternatives considered**: Raising `MIN_WEEKS_FOR_VELOCITY` itself to 26 weeks (the audit's "conservative, literature-aligned" first-preference option) — rejected as the pragmatic default, since it would suppress velocity feedback entirely for the club's own 30-day Circa-PHV re-test cadence, in tension with the "flexible plan, fun first" club principles.

**Evidence**: LEAD-DECISIONS.md #8; theory.md §1.6 (the clinical literature: Children's Mercy pediatric endocrinology guide, AMBOSS/Resident360 reference, general pediatric growth-monitoring review) and §1.8 (Kozieł & Malina 2018's sex/age bias pattern, reinforcing why confidence language should degrade near the roster's edges); analysis-design.md §1.2.

---

## R-11 Maturity-offset method: keep Mirwald, reject Moore/Fransen/Khamis-Roche; instrument-noise thresholds unchanged

**Decision**: No change to `phv.py::calculate_mirwald_offset` (Mirwald et al. 2002, both sexes, unmodified). The phase thresholds (Pre-PHV offset < -1.0, Circa-PHV -1.0..1.0, Post-PHV > 1.0) and the delta-significance noise floors (`DELTA_HEIGHT_SIGNIFICANT_CM=0.7`, `DELTA_WEIGHT_SIGNIFICANT_KG=1.5`) are also unchanged.

**Rationale**: Independent longitudinal validation (Kozieł & Malina, 2018) confirms three properties the redesigned prompt must communicate rather than paper over: predicted offset tracks the age at which the child was measured almost as strongly as true biological timing (r ≈ 0.95–0.97); early and late maturers are systematically pulled toward the sample mean; and error grows the further the athlete sits from the mid-teens (best within roughly the 12–15-year window for boys, degrading for girls from age 10 onward). Given the constitution's youth-psychological-safeguard principle, this is a deliberate "keep the formula, tighten the language" decision, not silent drift. The 0.7 cm / 1.5 kg noise floors are comfortably above published single-measurement TEM (≈0.3–0.6 cm for standing height per Hardy et al. 2018 and Ulijaszek & Kerr 1999) and appropriately larger to absorb the compounding error of a two-measurement difference.

**Alternatives considered**: **Moore et al. 2015** — a validated, simpler recalibration (no leg-length/weight term for at least one variant), independently re-validated by Kozieł & Malina (2018) with comparable or somewhat better mean bias for boys 12–15y; not adopted now, explicitly flagged as a possible future, deliberate migration rather than a prompt-level change. **Fransen et al. 2018** — boys-only maturity-ratio model; rejected outright, since chronological age appears on both sides of its equation, a statistical-coupling flaw documented in the same journal's own commentary (Nevill & Burton, 2018) and reproduced independently (Teunissen et al., 2020). **Khamis-Roche (1994)** — predicts adult stature, not age at PHV, and requires parental height, which the club does not collect and which raises its own minors'-privacy question (identifying data about a family attached to a minor's record); not a drop-in replacement.

**Evidence**: theory.md §1.1-§1.3 (full citation list, reproduced in the "Sources" section below); spec.md Assumptions ("Research… motivates the anchors"); §3 of theory.md (the ready-to-paste `docs/01-marco-teorico.md` §1 diff this feature ships, per FR-036).

---

## R-12 Circa-PHV velocity anchors: single source moves to the growth summary

**Decision**: The prompts no longer embed their own numeric Circa-PHV velocity anchors (previously 8–10 cm/y boys / 7–9 cm/y girls, duplicated across three prompt files). The analyst context instead receives `expected_velocity_range_cm_year`, read directly from feature 040's `growth_summary.py::EXPECTED_VELOCITY_CM_YEAR` constants — the same table the Crecimiento tab already renders. Velocity above the upper bound of that range is described as "above typical", never as alarming.

**Rationale**: The repo's existing Circa-PHV anchor sits *inside* rather than *spans* the standard pediatric pubertal-peak envelope (Tanner & Davies, 1985: ≈7–12 cm/y boys, ≈6–10.5 cm/y girls) — a genuinely normal fast peak grower could be flagged as "high for phase" by the old anchor when still within normal variation. Rather than independently widen the numeric band embedded in three prompt files (and risk the same drift the theory audit found between them), the fix is structural: one source of truth for the number, shared by the framework document, the growth module, and the AI analysis, so they can never disagree again.

**Alternatives considered**: Widening the prompt-embedded anchor numerically (e.g. boys 8–11, girls 7–10), the theory audit's own first-listed option — superseded by the architecturally cleaner single-source fix, which also closes the drift risk the audit flagged as the reason for the mismatch in the first place.

**Evidence**: LEAD-DECISIONS.md #8; theory.md §1.7 (Tanner-Davies citation and the anchor-mismatch finding); spec.md FR-007; specs/040-growth-module-redesign/research.md R-05 (`EXPECTED_VELOCITY_CM_YEAR` origin).

---

## R-13 Longitudinal context contract and its privacy caps

**Decision**: The analyst context carries the athlete's full measurement history, compacted as `weeks_offset_from_latest` with height, weight and maturation status per point — **never absolute dates**, and never `sitting_height_cm`/`arm_span_cm` per point (only the latest `arm_span_cm`, as today). Above `HISTORY_MAX_POINTS=16`, the oldest points are compacted into yearly checkpoints rather than dropped, so the series stays complete but token-bounded. Z-scores, percentiles and raw band *values* are excluded from the context entirely (FR-003); only qualitative bands (`nutritional_status`, height/weight band labels) and the growth summary's stage/offset/expected-range codes are passed.

**Rationale**: This directly extends the privacy discipline `context_builders.py` already documents for the existing single-record context (its own comment: z-scores can re-identify a minor even before any name is attached). Widening the context for full longitudinal grounding must not quietly widen that allowlist — an uninterrupted numeric series is *more* identifying than a lone delta in a club this small, so the no-absolute-dates and no-per-point-secondary-measurement rules matter more, not less, as the series grows.

**Alternatives considered**: Passing raw dates instead of week offsets, for a more "natural" prompt — rejected; dates are independently correlatable with public race calendars and club social posts, a risk already documented for session titles in `privacy.md` §2.

**Evidence**: spec.md FR-003; architecture.md §4.3 ("privacy constraints that do not move"); analysis-design.md §1.3 (compaction, cap, and the `HISTORY_MAX_POINTS` design).

---

## R-14 Training-load window: reuse `race/ai/athlete_context.py::load_training_window` verbatim

**Decision**: The 28-day training-load aggregate (session count, mean effort/RPE, hours) is computed by importing `app.services.race.ai.athlete_context.load_training_window(db, athlete_id, club_id, date_from, date_to)` directly, rather than writing a second aggregation query.

**Rationale**: The function is already tested, already club-scoped, and already excludes archived sessions — duplicating it would create a second place for the same aggregation logic to drift, exactly the "rule of three" the project's own conventions warn against (per feature 040's research.md R-04, citing the same principle for the Mirwald/LMS mirrors).

**Alternatives considered**: A new anthropometry-local aggregator — rejected as unnecessary duplication for a pure, already-correct query; cross-module import from `race/` into `app/services/ai/anthro/` is judged acceptable since the function has no race-specific state.

**Evidence**: LEAD-DECISIONS.md #3 (implicit, via architecture.md §4.3's table of directly-reusable race assets); architecture.md §1.4, §4.3.

---

## R-15 Review pipeline: deterministic prechecks, a cheap critic, one bounded revision, deterministic fallback

**Decision**: Before persistence, a Python-only precheck stage evaluates the draft against a twelve-rule catalogue (R01–R12, covering population/peer comparison, diagnostic labels, invented numbers, exact PHV date/age, unreliable velocity presented as reliable, leaked names, ±10% word-budget tolerance, sycophancy over a non-significant delta, supplement mentions, Markdown inside fields, an uncorroborated phase crossing, and coach-only content leaking into a family text). Privacy and developmental-safety rules (R01/R02/R04/R06/R09/R11/R12) block delivery outright; the rest only lower confidence. A cheap LLM critic then judges only what the prechecks cannot — contradiction with the growth summary, honesty of the confidence reason, and tone — returning `approve | revise | reject`. At most one revision is attempted: mechanical fixes are adopted directly from the critic's own `revised_output`; interpretive violations trigger exactly one re-invocation of the analyst with the violations attached. After that single attempt, any still-unapproved or blocked result becomes the deterministic fallback text with `confidence=low`. If the critic step itself fails or times out and no precheck found a blocking issue, the draft is delivered with confidence downgraded to low and the unavailability recorded; if a precheck found a blocking issue, the fallback is delivered regardless of what the critic would have said.

**Rationale**: This is a three-layer defence — deterministic rules, a cheap semantic critic, and the existing rendered-text guardrails as the last line — one layer more than the race pipeline's two, justified because this feature's failure mode (re-identifying a minor, false clinical certainty about a child's development) tolerates fewer false negatives than a wrong training recommendation. The critic never blocking on its own unavailability (degrade, never fail) matches the existing `_analyst_agent_with_fallback` philosophy the race pipeline already uses, extended here because anthropometry has no human-in-the-loop gate to fall back on.

**Alternatives considered**: A single-pass critic with no bounded revision (approve/reject only) — rejected; a mechanical fix (e.g. a word-budget overrun by a few words) does not need a full re-analysis, and bounding revisions to exactly one keeps the pipeline's worst-case latency predictable.

**Evidence**: spec.md FR-011 through FR-014; analysis-design.md §3 (full rule catalogue table with `guardrails.py` reuse mapping) and §5.2 (critic-unavailable policy).

---

## R-16 Langfuse tracing: single client reuse, root span with an unpinned `CallbackHandler`, explicit config threading

**Decision**: Reuse `observability.py`'s existing Langfuse client singleton (no second `Langfuse(...)` instantiation, no second flush thread). A root span is opened **before** the pipeline runs, with a deterministic trace id (`Langfuse.create_trace_id(seed=...)`, seeded from a keyed hash of `athlete_id:record_id:use_case`, R-20). `CallbackHandler()` is constructed **without** `trace_context` and passed into the pipeline's `RunnableConfig`. Every step is declared `async def step(state, config: RunnableConfig) -> dict` and threads that same `config` into every `llm.ainvoke(...)` call explicitly.

**Rationale**: Each call to `trace_context={"trace_id": X}` independently forces `AS_ROOT=True` on the span it creates. If both the manually opened root span **and** the `CallbackHandler` were pinned with the same trace id, the result would be two *sibling* root-level entries sharing one trace id, not a parent/child tree — because the handler's synthetic parent is built purely from the trace-id string, not from the actual span object the `with` block opened. Leaving `trace_context` unset on the handler lets it inherit whatever OTel context is active, so every node's generation nests correctly under the root span as long as the whole pipeline runs inside the `with root:` block. Explicit `config` threading (rather than relying on implicit contextvar propagation, which happens to work on this repo's Python 3.13 but is documented by LangGraph itself as unreliable in general, and is the exact gap the *existing* race nodes have) is the one thing standing between "one coherent trace" and orphaned, unparented generations.

**Alternatives considered**: Pinning `trace_context` on both the root span and the handler for "extra certainty" — this is the specific anti-pattern above; explicitly avoided.

**Evidence**: LEAD-DECISIONS.md #9; langfuse.md §1 (the sibling-root-span failure mode, the Context7-sourced confirmation, and the config-threading gap versus the existing race nodes).

---

## R-17 Mask design: a sentinel wrapper type, not a shape heuristic

**Decision**: A dataclass `_StructuralMetadata` marker type wraps only pre-validated, allow-listed fields; the mask function recognises **only** that type and passes it through, redacting everything else — including any bare dict, even one LangChain's `CallbackHandler` auto-populates — to `"[redacted]"` by default.

**Rationale**: Langfuse's `mask()` callback (`MaskFunction` protocol, `def __call__(self, *, data: Any, **kwargs) -> Any`) is not told which field (input, output, or metadata) it is being called for, confirmed against every documented example in the SDK. That rules out a naive "if it looks like metadata, allow it" heuristic — a `isinstance(data, dict)` check is unsafe, since LangChain message `content` can itself be a `list[dict]` for multimodal input, so a shape-only rule risks accidentally unmasking part of a real prompt. Making the allow-list decision at the *call site* instead — wrap only pre-validated fields, reject unknown keys at construction (`ValueError`, not a silent drop) — keeps the default maximally strict and the allow-list opt-in and explicit per field, enforceable and testable in one place.

**Alternatives considered**: A field-identity check inside `mask()` itself (the naive approach above) — ruled unsafe by the Context7-sourced SDK behaviour; a `LANGFUSE_METADATA_ALLOWLIST` comma-separated env var read at mask time (`architecture.md`'s own earlier `redaction.py` sketch) — superseded by the sentinel-type approach, which the privacy and Langfuse research agents both converged on as the only safe construction.

**Evidence**: LEAD-DECISIONS.md #9; langfuse.md §1 (full reasoning and the `_StructuralMetadata` code sketch); architecture.md §11.6 (the architect's own supersession note adopting this over its earlier draft).

---

## R-18 Structural-metadata allow-list, gated and k-anonymity-audited

**Decision**: `app/services/llm/observability_metadata.py` owns `ALLOWED_METADATA_KEYS` (a frozenset) and a single `build_structural_metadata(...) -> dict` entry point every call site must go through — no call site hand-assembles a metadata dict. Gated by `LANGFUSE_STRUCTURAL_METADATA` (default `false`, forbidden in production the same way `LANGFUSE_ENABLED` already is). Fields, condensed from `privacy.md` §2's audited table:

| Allowed (transformed or as-is) | Never allowed |
|---|---|
| `athlete_id` / `anthropometric_record_id` / `user_id` — hashed | `sex`, `category`, `age_decimal`, `age_group` |
| `club_id` — raw (single-club deployment today) | `maturation_status`, `phv_offset` / `age_at_phv`, `months_from_phv` |
| `delta_height_significant` / `delta_weight_significant` — booleans only | `growth_velocity_cm_per_year`, raw `delta_height_cm` / `delta_weight_kg` |
| `weeks_since_prev_measurement` — bucketed `<8w`/`8-26w`/`26w+` | `nutritional_status`, `crossed_phv_phase` |
| `num_previous_measurements` — bucketed `0`/`1`/`2+` | `training_implications` / any coach free text, session titles/dates |
| newsletter month/year — month granularity, no day | — |
| guardrail rule ids + counts, critic verdict codes, cache hit/miss, `use_case`, model/provider/prompt_version, tokens, latency, `cost_usd` | — |

A combination rule applies on top of the per-field column: never emit more than one of `{sex, age_group, maturation_status, category}` in the same call — moot today since all four are excluded, but binding if a future roster-growth decision ever reopens one of them; re-derive the k-anonymity arithmetic below before flipping any of those four from `no` to `transformed`.

**Rationale — the arithmetic that decides it**: for a club of ~20 minors, `sex × age_group` alone gives an equivalence-class size of `20/(2×2) = 5` — already at the threshold the codebase itself treats as unsafe (`monthly_report.py`'s `MIN_ATHLETES_FOR_INDIVIDUAL_ROWS = 5`). Adding `maturation_status` (3 states, unevenly distributed since PHV phase correlates with age) drops the mean cell size to ≈1.7 — below k=1 for a meaningful fraction of the roster, with no fourth field needed. Rounding or bucketing does not rescue these fields; two buckets coarsened into two buckets is still two buckets. The only mitigation that works for a *combinable* demographic field at this club size is exclusion, not coarsening — the same conclusion the codebase already reached independently in `context_builders.py` (dropping z-scores from the LLM-prompt allowlist) and `monthly_report.py`'s row-suppression threshold.

**Alternatives considered**: The literal reading of the owner's original brief — "age → 2-year bucket, deltas → rounded, PHV phase as a category" — this is exactly what the privacy audit rejects field-by-field once combination is accounted for; several fields the brief asked to transform are marked `no` instead, with the reasoning above superseding the brief's proposal.

**Evidence**: LEAD-DECISIONS.md #9; privacy.md §0 (headline finding), §1.3 (the arithmetic), §2 (full allow-list table).

---

## R-19 Tags and scores bypass the mask entirely — treated as more sensitive, not less

**Decision**: Because `mask()`'s documented scope is `input`/`output`/`metadata` only, **tags** and **score payloads** (`value`/`comment`) are not covered by it at all. Tags therefore carry only the already-operational set: provider, model, role (`analyst`/`critic`), prompt version, audience, cache create/overwrite, guardrail clean/scrubbed/rejected, rule ids, critic verdict — **never** `age_group`, `sex`, `category`, or `maturation_status`, even though those would otherwise look like reasonable tag material. Scores carry numbers/booleans only (e.g. a guardrail violation count), never a `comment=` string built from generated text.

**Rationale**: A field that bypasses redaction is *more* dangerous to populate carelessly, not less — the discipline that applies to the allow-listed metadata in R-18 applies with the same strictness to tags and scores, since there is no masking safety net for either channel. This closes an open question the system architect flagged (`architecture.md` §10, "is `age_group` acceptable as a trace tag?") with a "no": it is the coarsest form of data already stored in the app database, but redact-always exists precisely because quasi-identifiers combine, and R-18's arithmetic shows the combination risk is real at this club's size.

**Alternatives considered**: Allowing `age_group` as a tag on the reasoning that it "adds nothing a database holder lacks" (the architect's own tentative framing before the privacy audit landed) — explicitly withdrawn once the k-anonymity arithmetic in R-18 was run.

**Evidence**: LEAD-DECISIONS.md #9; langfuse.md §1 (score/tag masking scope, Context7-confirmed); privacy.md §1.4, §2 (the closed "genuinely safe" field list); architecture.md §11.6 (the architect's own withdrawal of the `age_group`-as-tag idea).

---

## R-20 Session identifier: HMAC keyed from the JWT secret, replacing the truncated-hash scheme everywhere

**Decision**: `session_id = HMAC-SHA256(key=JWT_SECRET_KEY, msg=f"anthro:{use_case}:{athlete_id}:{record_id}")`, truncated to 16 hex characters, with a domain separator (`"langfuse-session"`). This replaces the race chat trace's existing `anonymous_session_id` (a bare truncated `sha256`, with no key) — both now use the same keyed scheme (FR-024).

**Rationale**: A bare `sha256(...)[:16]` over `(athlete_id, record_id, use_case)` is enumerable — with roughly 20 athletes and a few hundred records, the whole preimage space is under 10,000 hashes, invertible in seconds by anyone holding both the Langfuse volume and the database. Keying the hash on `JWT_SECRET_KEY` (already forbidden from its default value in production by an existing `Settings` validator) makes it non-invertible without the server secret while staying stable across restarts, so a coach's repeated regenerations of one measurement still group into one Langfuse session.

**Alternatives considered**: A per-process salt, which the privacy research brief initially proposed as the stricter option — the owner explicitly chose the HMAC-on-JWT-secret approach instead, accepting the trade-off that it is stable (and therefore weaker if the JWT secret were ever compromised) in exchange for keeping cross-restart session grouping, which a per-process salt would lose on every backend restart. This is recorded as a deliberate, informed trade-off, not an oversight: the JWT secret is already the production trust boundary for authentication, so reusing it (with domain separation) does not introduce a new secret to protect, only a new derived use of an existing one.

**Evidence**: LEAD-DECISIONS.md #9; langfuse.md §1 (the enumerability argument, `observability.py:114`'s existing weakness); privacy.md §2 (the brief's original per-process-salt proposal, superseded); spec.md FR-024.

---

## R-21 Prompt registry stays the source of truth; Langfuse prompt management and hosted Datasets are not adopted

**Decision**: `PromptRegistry`/`PROMPT_SPECS` remains the single source of truth for prompt content and versioning, including for the new anthropometry prompts (which use their own local Jinja loader, R-04, but the same "versioned file in git" philosophy). Prompt version is surfaced to Langfuse only as a tag (`prompt:<template_id>:v<version>`), never by registering the prompt itself in Langfuse's prompt-management feature.

**Rationale**: Langfuse's `get_prompt(name, version=, label=, fallback=)` duplicates versioning the repo's own `PromptSpec` already does, with no privacy upside (Langfuse is local-only here, so there is no cross-environment sync benefit) and a genuine new failure mode: it is a network call to the local Langfuse instance with a 5-minute cache, so every deploy config would need a `fallback=` string to survive the container not having Langfuse up yet — strictly worse than reading a `.md`/`.j2` file that ships with the code. Production has Langfuse disabled entirely (a hard `Settings` startup failure), so if prompt source-of-truth ever moved there, production would need a *different* prompt-loading path than development — precisely the kind of drift the repo has already fought once (the `DEFAULT_MODEL_BY_PROVIDER` comment in `_llm.py`).

**Alternatives considered**: Registering prompts in Langfuse for its versioning UI — rejected for the reasons above; Langfuse Datasets/Experiments for the golden eval — see R-22.

**Evidence**: langfuse.md §2; LEAD-DECISIONS.md Assumptions ("the prompt registry remains the source of truth for prompt versions").

---

## R-22 Golden evaluation stays in pytest; Langfuse Experiments/Datasets are not adopted

**Decision**: `backend/evals/anthropometry_analyst/{golden/case_001..012.json, baseline.json}`, a judge + scorer under `app/services/ai/anthro/eval/` reusing `race/eval/scorer.py::composite_score`, run via the existing `golden` pytest marker with `-k anthropometry` (no new marker), threshold 0.75, blocking in a cloned CI workflow `.github/workflows/anthropometry-eval.yml`.

**Rationale**: Langfuse v4's `run_experiment(dataset=, task=, evaluators=)` accepts a plain local list, so it does not strictly require uploading data to the Langfuse instance — but it has no native CI gate, so making it blocking would mean writing a pytest wrapper around it anyway, at which point the existing pytest-marker + CI-gate pattern has simply been reinvented with an extra network dependency (a local Langfuse instance must be up, which it never is in CI). The anthropometry explainers are also a much smaller pipeline (single prompt → single structured completion → scrub) than the race analyst's multi-node graph, so a small (~12-item) fixture-based pytest set with the same composite-score judge is proportionate. A dataset uploaded via `create_dataset_item` also persists to the local Langfuse Postgres — one more place with athlete-shaped synthetic data to audit, versus a pytest fixtures file under `backend/evals/`, which has exactly the audit surface `data-privacy-guard` already checks.

**Alternatives considered**: Langfuse Datasets + `run_experiment` for both storage and execution — rejected on the CI-integration and privacy-audit-surface grounds above; the spec's own requirement that this gate be *blocking* (FR-035) makes the pytest/CI pattern the only one that already satisfies the requirement without new plumbing.

**Evidence**: LEAD-DECISIONS.md #12; langfuse.md §3; analysis-design.md §6 (12-case list and rubric).

---

## R-23 Growth-summary embedding of `latest_ai_analysis`, with a consent-gate amendment and server-computed staleness

**Decision**: `GrowthSummaryOut.latest_ai_analysis: LatestAiAnalysis | null`, folded into the **existing** growth-summary endpoint the tab already fetches (`GET /api/athletes/{id}/growth-summary`, feature 040) rather than a new endpoint. Shape: `{record_id, generated_at, schema_version, summary_line, has_warning_signs, critic_verdict (coach only), is_stale}`. `is_stale` = a newer record exists for the athlete OR `record.updated_at > generated_at`, computed server-side. The field is `null` whenever AI consent is absent, `AI_ENABLED=false`, or nothing approved/revised exists for the requested audience — and a failure computing it must never fail the growth summary itself.

**Rationale — the consent-gate amendment**: `routers/growth.py`'s growth-summary endpoint has **no AI-consent gate today**, unlike `routers/ai.py`'s `_ensure_ai_consent` (HTTP 451). Embedding AI-derived content in an otherwise ungated endpoint would move consent-gated data into a surface that does not check consent — this is a real gap the embedding decision surfaces, not a pre-existing property of the 040 endpoint being reused as-is. The field must therefore be null under exactly the same conditions `_ensure_ai_consent` would refuse, with its own denied-path test. Folding into the existing endpoint (rather than a new one) matters for Principle IV on the parent's mid-tier Android/3G device: the tab already fetches this endpoint, so the summary line costs zero extra round trips. It also avoids re-deriving "what counts as latest" or "what counts as stale" in two places (backend `growth-summary` and the frontend tab), which is exactly the class of bug feature 040's own audit (`docs/18-growth-module-redesign/proposal.md` G-02) already documented once for this codebase — the frontend guessed "latest" from array order and got it backwards.

**Rationale — `critic_verdict` coach-only**: it is internal quality signal, not family-facing copy; a parent reading "needs revision" about their child's growth analysis is alarming without being actionable for them.

**Alternatives considered**: A separate `latest-analysis` endpoint — rejected for the extra-round-trip reason above. Client-side "latest"/"stale" derivation from records already in memory — rejected as the exact bug class G-02 already taught this codebase to avoid.

**Evidence**: LEAD-DECISIONS.md #10; architecture.md §11.4 (the five amendments, in particular the consent-gate gap); ui-design-analysis-summary.md §0, D-2.

---

## R-24 UI: structured collapsed render, family gating of flagged analyses, and the bundled constitution fixes

**Decision**, bundled per `LEAD-DECISIONS.md` #11 (ui-design-analysis-summary.md's P1 list, F-02/F-05/F-06/F-07/F-09/F-10/F-11/F-12/F-13, plus the growth-tab summary line and history-row marker):

- **Structured render**: v2 rows render collapsed by default — summary line and warning signs always visible; "qué significa" and "próximas 2-4 semanas" sit behind a "Ver análisis completo" expander with `aria-expanded`/`aria-controls`. v1 free-prose rows render exactly as today, forever, with no forced migration; regenerating a v1 row always produces v2, which is the de facto (never explicit) upgrade path.
- **Family gating**: any analysis whose critic verdict is not `approved` or `revised` (i.e. revised-and-still-unapproved, `rejected`, or `fallback` — FR-016) is **never** delivered to a family audience. Both the modal's read-only card and the growth-tab summary line show the identical shared passive placeholder ("Aún no hay análisis disponible para esta medición. El entrenador lo generará pronto.") for "no analysis yet" and "flagged" alike — a parent cannot distinguish the two states, by design. This mirrors how a guardrail rejection (HTTP 502) already blocks delivery outright today rather than showing flagged content with a caveat, so the new critic-flagged case is treated as the same category of signal rather than inventing a new, softer policy.
- **Provenance**: the family line drops provider/model entirely ("Generado por el asistente de IA del club" + date); the coach gets a technical-details disclosure (model, prompt version, trace reference).
- **Constitution fixes bundled into this change** (all pre-existing violations on the exact surfaces this feature rebuilds, fixed once rather than in a second pass): "Regenerar análisis"/"Copiar"/the dialog close control raised to real ≥48px buttons; the measurement dialog migrates onto the shared `Dialog` primitive with an actual focus trap (Tab cannot escape to background content, focus returns to the triggering row on close); `AIBudgetHint` wired above every generate/regenerate control on both AI cards (previously wired at only three other launch points), so a budget-exhausted state is visible before the tap, not after a failed round-trip; the AI disclaimer moves off the amber token to neutral/informational, reserving amber strictly for the conditional training-implications box; delta chips move to the shared `StatusBadge` tokens.
- **Growth-tab summary line and history-row marker**: "Último análisis de IA" sits directly above `AnthropometryHistory` in both modes (not a full tab reorder — that stays a tracked P3), with a "Desactualizado" badge in coach mode only when `is_stale`, and history rows (desktop and mobile) get a "Con señal para revisar" marker, paired with an icon rather than colour alone, when the row's analysis has a warning sign.

**Rationale**: The gating decision (`D-1` in `ui-design-analysis-summary.md`) was explicitly flagged there as a policy question, not a pure UI call, and the lead resolved it in favour of gating rather than a softened caveat, for consistency with the existing guardrail-rejection behaviour. Bundling the constitution fixes avoids a second PR touching the same components a second time.

**Alternatives considered**: Showing flagged content to families with a softened caveat ("Este análisis puede necesitar un ajuste…") — the UI design document's own documented non-default option; not chosen.

**Evidence**: LEAD-DECISIONS.md #11; ux.md §1.b (F-05 through F-13), §4 (P1 list); ui-design-analysis-summary.md §3 (D-1), §1-§4.

---

## R-25 Config-hygiene validators: `claude-cli` and structural metadata forbidden in production

**Decision**: A `Settings` validator fails production startup when `AI_PROVIDER` or the effective race provider resolves to `claude-cli` (mirroring the existing `forbid_langfuse_in_prod` pattern). `LANGFUSE_STRUCTURAL_METADATA` gets the same prod-forbidden treatment as `LANGFUSE_ENABLED`, independently satisfiable-or-not (belt-and-suspenders in case a future refactor decouples the two flags). CLAUDE.md's Alembic head is corrected from the stale `2a8baa967cc6` to the verified single head `45cd705c6b54` (R-07). The pre-existing red test `test_ai_factory.py::test_factory_openai_not_implemented` (asserting `AI_PROVIDER=openai` raises, but the factory gained a real `"openai"` branch once `openai>=1.0,<3` was installed) is fixed rather than inherited into this feature.

**Rationale**: Nothing currently *enforces* `claude-cli`'s local-only status beyond convention plus the package's deliberate absence from `requirements.txt` — a real gap, since Anthropic's consumer terms forbid serving end users off a personal CLI subscription, and this is exactly the kind of configuration mistake that should fail loudly at startup rather than silently at request time. Fixing the pre-existing red test rather than inheriting it is a Principle II requirement (no silent skips) that this feature is well-positioned to close, since it is already editing `factory.py`.

**Alternatives considered**: Leaving `claude-cli` enforcement as documentation-only — rejected; a documented rule with no enforcement is exactly the gap analysis.

**Evidence**: LEAD-DECISIONS.md #13; architecture.md §1.5 (both pre-existing defects), §3.5 (the new validator).

---

## R-26 Test strategy: `FakeLLMProvider` preserved, `GenericFakeChatModel` scoped narrowly

**Decision**: `FakeLLMProvider` remains the test double selected by `create_llm_provider` *before* any LangChain dispatch, for `AI_ENABLED=false` and `AI_PROVIDER=fake`, across every use case and router test — preserving the ~40 existing assertions reading `fake.last_request.messages[-1].content`. LangChain's `GenericFakeChatModel` is scoped exclusively to `tests/test_langchain_provider.py` (adapter translation, usage extraction, exception mapping) and the anthropometry pipeline's own tests — **never** substituted into a use-case or router test. Persistence round-trip tests for the nine new columns and the dialect-specific `mysql_insert(...).on_duplicate_key_update(...)` call run in the opt-in `pytest -m mysql` lane, not the default aiosqlite lane. Denied-path tests (parent → 403, missing consent → 451, `AI_ENABLED=false` → 503) are re-run against the new pipeline path, matching the existing pattern in `test_ai_record_router.py`.

**Rationale**: Stating the `GenericFakeChatModel` scoping rule explicitly, rather than leaving it as an implicit convention, is deliberate: without it, a future contributor "modernising" a privacy assertion onto a LangChain-native fake could silently drop the guarantee that `FakeLLMProvider` currently gives — that no name, birth date or measurement reaches a provider prompt — since `GenericFakeChatModel` has no equivalent `last_request` inspection surface built for that purpose.

**Alternatives considered**: Migrating all fake-model tests onto `GenericFakeChatModel` for consistency with the new LangChain transport — rejected; it would require rebuilding the ~40 privacy assertions from scratch for no functional gain, and risks losing assertion coverage during the rewrite.

**Evidence**: architecture.md §9.2 (the assertion count and the fakes-by-wave breakdown), §9.3 items 9, 12; langfuse.md §4 (`GenericFakeChatModel` vs `FakeListChatModel`).

---

## R-27 Sequencing against feature 040's deferred items, and the synthetic-only golden dataset

**Decision**: Feature 040's own deferred items (T027/T028 MySQL `_test` recompute, Playwright specs, T077–T079) touch the same anthropometry/growth-tab surface this feature rebuilds; the plan states their relative order explicitly rather than letting the two land in an undefined interleaving. Work proceeds in four waves with disjoint file ownership and cumulative gates: **W1** shared factory + adapter + tracing + config; **W2** anthropometry pipeline + golden eval + cache columns + modal renderer; **W3** the five migrated use cases behind the transport switch + the growth-summary field + `GrowthTab` line + the bundled UI fixes; **W4** docs. Each wave's gate is cumulative — `ruff`, default `pytest`, `pytest -m mysql`, the *race* golden eval (since W1 touches the shared factory the race analyst depends on), the *anthropometry* golden eval from W2 onward, `npm run build`/`npm test`, `jest-axe`, and Playwright in W3 — so a later wave's regression is always caught by re-running an earlier wave's own gate. The golden dataset (R-22) is synthetic-only by hard constraint: all 12 cases are fabricated, physiologically plausible measurement series, never copied or lightly edited from production rows, since an anthropometry case carries height, weight and PHV offset by construction and CLAUDE.md forbids a minor's identifying data in git-committed fixtures. `data-privacy-guard`'s standing audit checklist covers `backend/evals/anthropometry_analyst/` by name.

**Rationale**: Sequencing waves by risk (weakest-tested surfaces last) and giving each wave sole ownership of its files means a wave can be reverted independently without untangling a shared diff. Re-running the race golden eval at the end of every wave — not just W1 — catches a shared-factory regression at the last point one could plausibly surface, since W2 and W3 both touch config and tracing code the race pipeline also depends on.

**Alternatives considered**: A single combined PR for the whole feature — rejected given the blast radius (`app/services/llm/` alone is imported by both stacks); scoping the golden dataset partly from anonymised real measurement series (faster to build, closer to real failure modes) — rejected outright as a CLAUDE.md violation regardless of anonymisation effort, since the values themselves (height, weight, PHV offset) are the identifying content, not just a name attached to them.

**Evidence**: LEAD-DECISIONS.md #15; architecture.md §10 (feature-040 collision finding), §4.7 ("hard privacy requirement on the dataset"), §11.7 (wave table and gates).

---

## Resolved unknowns from Technical Context

| Unknown | Resolution |
|---|---|
| Full transport rewrite vs. adapter vs. two-system split | R-01 — Option A adapter for all seven use cases; anthropometry separately rebuilt |
| LangGraph vs. plain orchestrator for the anthropometry pipeline | R-03 — plain async orchestrator, no checkpointer; step signatures kept LangGraph-compatible for a mechanical future promotion |
| Module location (`growth_ai/` vs `anthro/`) | R-04 — `app/services/ai/anthro/` |
| Per-role model env-var naming (new vars vs. reusing `RACE_AI_*`) | R-05 — new `AI_ANALYST_MODEL`/`AI_CRITIC_MODEL`, one-way inheritance preserved |
| Budget model (shared pool, separate cap, warn-only, or none) | R-06 — no cap of any kind; cost recorded and shown per-coach, per-stack only |
| Persistence table (new table, `agent_runs`, or extend the cache table) | R-07 — extend `athlete_ai_explanations`, nine nullable columns |
| Structured-output mechanism (`with_structured_output` vs. prompt-JSON) | R-08 — prompt-instructs-JSON + Pydantic validation, uniform across all four providers |
| Schema-version discriminator semantics | R-09 — class `AnthropometryInsightV1` persists as `schema_version="v2"`; `"v1"` reserved for legacy prose |
| Velocity reliability threshold (raise the floor vs. gate confidence language) | R-10 — floor stays 8 weeks; confidence gated at 26 weeks (the softer of two literature-backed options) |
| Maturity-offset formula (keep Mirwald vs. migrate to Moore/Fransen/Khamis-Roche) | R-11 — keep Mirwald; alternatives evaluated and rejected with citations |
| Circa-PHV anchor mismatch (widen the prompt number vs. single-source it) | R-12 — single source moves to the growth summary's `expected_velocity_range_cm_year` |
| Does Langfuse `mask()` know which field it is masking? | R-17 — no; solved with a sentinel wrapper type, not a shape heuristic |
| Do Langfuse scores/tags bypass the mask? | R-19 — yes, both bypass it entirely; treated as more sensitive, requiring the same discipline as metadata |
| Is `age_group` acceptable as a trace tag? | R-19 — no; the k-anonymity arithmetic in R-18 rules it out at this club's size |
| Session-id scheme (per-process salt vs. keyed HMAC) | R-20 — HMAC keyed on `JWT_SECRET_KEY`, owner's explicit trade-off over the stricter but restart-unstable per-process salt |
| Prompt versioning system (local registry vs. Langfuse prompt management) | R-21 — local registry kept; version surfaced only as a trace tag |
| Golden-eval execution (pytest vs. Langfuse Experiments/Datasets) | R-22 — pytest, reusing the existing `golden` marker and CI pattern |
| Does the growth-summary embedding need its own consent gate? | R-23 — yes; the existing growth-summary endpoint has none today, closed as part of this change |
| Does a family ever see a critic-flagged analysis, even with a caveat? | R-24 (D-1) — no; gated identically to "no analysis yet" |
| Does `latest_ai_analysis` fold into the existing growth-summary endpoint or a new one? | R-23 (D-2) — folded in, avoiding a second round trip and a second "what counts as latest" implementation |
| Is `critic.note` (the critic's free-text reason) ever safe to render, even coach-only? | **Still open** (D-3 in `ui-design-analysis-summary.md`) — not resolved by `LEAD-DECISIONS.md`; the shipped `critic_verdict` enum carries no free-text reason field, so this question is currently moot for what ships, but any future addition of a critic free-text field needs its own `data-privacy-guard` review before rendering, even coach-only |

---

## Sources

**Binding planning artifacts (2026-09-11)**
- `specs/042-traceable-growth-ai/spec.md`
- `/tmp/042-research/LEAD-DECISIONS.md`

**Agent research briefs (2026-09-11)**
- `/tmp/042-research/architecture.md` — system-architect, revision 2 (current-state map, wave plan, shared-factory design, persistence, UI/schema versioning, budget-guard analysis, testing strategy, open risks, reconciled plan §11)
- `/tmp/042-research/theory.md` — sports-science literature audit (maturity-offset methods, velocity-interval literature, Circa-PHV anchors, `docs/01-marco-teorico.md` §1 diff)
- `/tmp/042-research/ux.md` — heuristic evaluation and WCAG AA audit of the growth tab and AI cards
- `/tmp/042-research/ui-design-analysis-summary.md` — UI design handoff (summary line, modal rendering, critic-verdict handling, open decisions D-1/D-2/D-3)
- `/tmp/042-research/langfuse.md` — Langfuse v4 + LangChain 1.x SDK research (instrumentation, masking, tracing, prompt management, datasets/experiments, provider specifics)
- `/tmp/042-research/privacy.md` — structural-metadata privacy audit and allow-list
- `/tmp/042-research/analysis-design.md` — pipeline/prompt/schema design (prompt-design agent)

**Codebase precedent**
- `CLAUDE.md` (project constitution summary, Alembic head, env-var conventions)
- `specs/040-growth-module-redesign/research.md` — format precedent; origin of `EXPECTED_VELOCITY_CM_YEAR`, `MIN_ATHLETES_FOR_INDIVIDUAL_ROWS`, the G-02 "guessed latest" bug class

**Literature cited in theory.md (reproduced here for traceability, no repetition of theory.md's full reference list)**
- Mirwald RL, Baxter-Jones ADG, Bailey DA, Beunen GP. An assessment of maturity from anthropometric measurements. *Med Sci Sports Exerc*. 2002;34(4):689–694.
- Moore SA, McKay HA, Macdonald H, Nettlefold L, Baxter-Jones ADG, Cameron N, Brasher P. Enhancing a somatic maturity prediction model. *Med Sci Sports Exerc*. 2015;47(8):1755–1764.
- Kozieł SM, Malina RM. Modified maturity offset prediction equations: validation in independent longitudinal samples of boys and girls. *Sports Med*. 2018;48(1):221–236.
- Fransen J, Bush S, Woodcock S, Novak A, Deprez D, Baxter-Jones ADG, Vaeyens R, Lenoir M. Improving the prediction of maturity from anthropometric variables using a maturity ratio. *Pediatr Exerc Sci*. 2018;30(2):296–307.
- Nevill A, Burton RF. Commentary on the article "Improving the prediction of maturity from anthropometric variables using a maturity ratio." *Pediatr Exerc Sci*. 2018;30(2):308–310.
- Khamis HJ, Roche AF. Predicting adult stature without using skeletal age: The Khamis-Roche method. *Pediatrics*. 1994;94(4):504–507.
- Malina RM, Rogol AD, Cumming SP, Coelho-e-Silva MJ, Figueiredo AJ. Biological maturation of youth athletes: assessment and implications. *Br J Sports Med*. 2015;49(13):852–859.
- Malina RM, Cumming SP, Rogol AD, Coelho-e-Silva MJ, Figueiredo AJ, Konarski JM, Kozieł SM. Bio-Banding in Youth Sports: Background, Concept, and Application. *Sports Med*. 2019;49(11):1671–1685.
- Tanner JM, Davies PSW. Clinical longitudinal standards for height and height velocity for North American children. *J Pediatr*. 1985;107(3):317–329.
- Ulijaszek SJ, Kerr DA. Anthropometric measurement error and the assessment of nutritional status. *Br J Nutr*. 1999;82(3):165–177.

**SDK documentation (via Context7, cited in `langfuse.md`)**
- `langfuse/langfuse-python` (Langfuse Python SDK v4, source-linked to `_autodocs/` and `langfuse/_client/*.py`)
- `docs.langchain.com/oss/python/langchain/*` (LangChain 1.x — messages, structured output, testing, LangGraph streaming/config)
