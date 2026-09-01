# Research: AI Insights Tab — Full-Stack Review

**Feature**: `036-ai-insights-tab-review` | **Date**: 2026-08-31

Phase 0 output. Resolves the unknowns flagged in `plan.md` (budget calibration T062, HITL checkpoint durability T065, Langfuse OQ4, prompt few-shot design T054/T056, eval CI matrix T051) with external sources where the answer lives outside the repo.

## R1 — Budget guard calibration for Anthropic (T062)

**Decision**: Keep `race_ai_budget_usd_30d=20.0` for now, but treat it as covering roughly **one full-season regeneration wave, not a comfortable margin**. Recalibrate against measured spend after T060 fixes provenance (until then, per-model cost cannot be correlated from the DB). If the coach plans a bulk re-analysis after the US2 prompt rewrite ships, raise the guard to 40 first.

**Rationale**: Verified pricing — `claude-sonnet-5` is **$2.00 input / $10.00 output per MTok** (Anthropic first-party rates, cached 2026-06-24 in the claude-api reference). `gemini-2.5-flash-lite`, the model the guard was written against, is **$0.10 / $0.40 per MTok** — a **20× input / 25× output** ratio, confirming the plan's "roughly ten times" as an underestimate. Estimate at v2's up-to-5 calls per analysis, ~4K input + ~1K output per call: ≈ **$0.09 per analysis**. Club scale (~30 athletes × 7 válidas ≈ 210 analyses) ≈ **$19 per full season pass** — exactly at the guard.

**Alternatives considered**: (a) Raise the guard unconditionally — rejected: the guard exists to protect a personal budget; better to measure first. (b) Route race analysis to Haiku 4.5 ($1/$5) — out of scope for this feature; would need its own golden-eval pass before switching.

## R2 — HITL sqlite checkpoint on Render free tier (T065)

**Decision**: **The checkpoint does NOT survive.** Render free-tier web services have an ephemeral filesystem — all local changes (including `./data/langgraph_state.sqlite`) are lost on every deploy, restart, or spin-down, and persistent disks are paid-only ($0.25/GB/mo). Therefore: treat pending HITL decisions as ephemeral by design. T016's startup orphan reconciliation is the primary mitigation (stale `running`/`awaiting_hitl` runs → `failed` with an explanatory `error_message`), and the UI must present an expired HITL as "run no longer available — relaunch", never as a silent hang.

**Rationale**: Since the backend redeploys on **every push to `main`** and free instances also spin down on idle, any durability strategy short of external storage is fiction. Accepting ephemerality + reconciliation is honest and free.

**Alternatives considered**: (a) Paid persistent disk — rejected: cost for a club project, and disks don't attach to free services at all. (b) MySQL-backed LangGraph checkpointer — no first-party `langgraph-checkpoint-mysql` exists (official savers are sqlite/Postgres); a community package would need vetting. Revisit only if HITL loss becomes a real coach pain. (c) Render free Postgres just for checkpoints — adds a second DB engine to the stack for a corner case; rejected.

Sources: [Render — Deploy for Free](https://render.com/docs/free), [Render — Persistent Disks](https://render.com/docs/disks).

## R3 — Langfuse (Open Question 4 / T064)

**Decision**: **Correct `CLAUDE.md` now; do not implement Langfuse in this feature.** If observability is wanted later, the viable shape is a **dev-only, self-hosted Langfuse via docker compose** (v3, `from langfuse.langchain import CallbackHandler`, passed in `config={"callbacks": [...]}` on graph invocation) as its own small feature.

**Rationale**: Three forcing facts. (1) There is nowhere to run it in production: Render free tier cannot host the Langfuse stack alongside the API. (2) **Privacy**: Langfuse Cloud (the zero-infra option) would ship prompts containing minors' race context to a third party — the same class of exposure `AI_LOG_PROMPTS=false` exists to prevent; only self-hosting is compatible with the Ley 1581 posture. (3) The original v2 decision (2026-05) was "Langfuse local", i.e. dev-only, and it simply never landed; the documentation claim in `CLAUDE.md` is the actual defect today (`agent_run.py:22` is the only occurrence in code).

**Alternatives considered**: Langfuse Cloud free tier — rejected on privacy grounds above. Implement self-hosted now — rejected: pure infra work with zero user-visible value inside a feature that is already large.

Sources: [Langfuse — LangGraph integration](https://langfuse.com/guides/cookbook/integration_langgraph), [LangChain docs — Langfuse callbacks](https://python.langchain.com/docs/integrations/providers/langfuse/).

## R4 — Prompt rewrite technique (T054/T056)

**Decision**: Rewrite Section 1 of `race_analyst_v2.md` around **synthesis rules + one contrastive few-shot pair** (one "bad" checklist example, one "good" interpretive example), and **delete prescriptive constraints rather than adding more**: drop the five-field enumeration mandate, the `hh:mm:ss`-in-narrative requirement, the five-verb whitelist, and the lap-count demand (T055).

**Rationale**: Current Anthropic guidance for Claude 4.6+/5 models is explicit that **prompts written for prior models are often too prescriptive and reduce output quality** — the existing prompt is a textbook case (mandated fields + verb whitelist ⇒ the model's only safe output is the observed template). Multishot/contrastive examples are the highest-leverage single addition for shaping narrative structure; neither prompt version has any today. The tone safeguards for minors (no body judgement, no diagnostic language) are constraint-style rules that **should stay** — they are compliance, not style, and the audit rates them the prompt's strongest part (T058).

**Alternatives considered**: Adding more rules to force comparison ("always mention the previous race") — rejected: replaces one template with another. Fine-tuning / structured-output sections — out of proportion for this stack.

## R5 — Eval CI matrix for `anthropic`/`claude-sonnet-5` (T051)

**Decision**: Pin the CI eval to production's provider/model (`anthropic`/`claude-sonnet-5`). Requires an `ANTHROPIC_API_KEY` (or `RACE_AI_API_KEY`) secret in GitHub Actions and updating the skip-guard at `test_race_analyst_eval.py:122-129`. Estimated CI cost per run: ~10 golden cases × 1–5 calls ≈ **$0.10–0.50/run** — affordable as a blocking gate that runs on race-AI-touching PRs only (current trigger paths in `race-eval.yml` already scope it).

**Rationale**: An eval gate on a different provider, model *and* method (v1 vs v2) measures nothing — this is the root finding of US2. Reminder from the provider constraint already in `CLAUDE.md`: the Anthropic provider must **not** forward `temperature` (400 on non-default sampling params on Claude 4.6+); the eval runner must not reintroduce it for "determinism".

**Alternatives considered**: Keeping Gemini in CI as a cheap proxy — rejected: proxy divergence is exactly the bug being fixed. Running both providers in a matrix — acceptable later as non-blocking signal; blocking gate must be production's pair.

## R6 — Framework facts verified (no external research needed)

- **T010 (`key={athlete.id}`)**: React remount-on-key-change is the documented idiom for resetting all state on identity change; React Router param-only navigation does not unmount the element. Confirmed correct minimal fix.
- **T013 (TanStack Query v5)**: the mutation result object returned by `useMutation` is a new reference every render; effects must depend on stable fields (`isSuccess`) and use the stable `mutate`/`reset` references. Documented v5 behaviour, not a bug.
- **T021 (Alembic)**: run `alembic heads` before autogenerate — `docs/implementation-status.md` records the dangling head `e5f6a7b8c9d0` from feature 007; a new revision must not create a second branch point.
- **Repo verification during this phase**: `AthleteAiInsight` **already has** `event_id` (FK to `race_event`, nullable) — T030's migration is payload/schema-level (stop deriving labels from `valida_num===99`; expose `event_id` + series kind + race date in the insight responses), **no new DB column needed**. Backend `SeasonSummaryResponse` already returns `insight_id`/`summary_text` — T040 is a **frontend-only** contract fix. `AgentRunStatus` enum: `running | awaiting_hitl | completed | rejected | failed | cancelled` — reconciliation (T016) touches only `running` and `awaiting_hitl`.
