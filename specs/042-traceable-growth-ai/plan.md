# Implementation Plan: Traceable AI growth analysis

**Branch**: `feat/042-traceable-growth-ai` | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/042-traceable-growth-ai/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every AI text generation in the app (`app/services/ai/`: PHV explainer family/coach, per-measurement analysis, session clarify/draft, monthly report, monthly report blocks, newsletter v2) moves onto one LangChain transport so each generation is traced in the local Langfuse (redact-always, prod-forbidden) and accounted (model, provider, prompt version, tokens, latency, cost, verdict, trace id) on its own record. The transport is an **adapter** that implements the existing `LLMProvider` Protocol over a **shared chat-model factory** lifted out of the race stack into `app/services/llm/` — so the five non-anthropometry use cases keep their prompts, outputs and ~40 `fake.last_request` privacy assertions untouched behind an `AI_USE_LANGCHAIN` switch. The anthropometric analysis is **rebuilt** as a plain async five-step pipeline (`context → analyst → critic → guardrails → persist`, each step `(state, config) -> dict`, no LangGraph checkpointer, no HITL) in `app/services/ai/anthro/`: structured `AnthropometryInsightV1` output (summary ≤140 chars, four sections, confidence, data gaps), longitudinal context (full compacted history, growth-summary codes and expected velocity range, 28-day training-load aggregates, previous insight), a 26-week `velocity_confidence` gate over the unchanged 8-week floor, corroborated phase crossings, twelve deterministic prechecks (R01–R12) plus a cheap critic (`AI_CRITIC_MODEL`) with one bounded revision and a deterministic fallback, a blocking synthetic golden eval (composite ≥ 0.75), and nine nullable columns on `athlete_ai_explanations` (single Alembic head from `45cd705c6b54`). Langfuse gains a sentinel-typed mask with an audited operational-only metadata allow-list behind `LANGFUSE_STRUCTURAL_METADATA`, and a keyed-hash session id (HMAC from `JWT_SECRET_KEY`) that also replaces the race chat's truncated hash. UI: structured collapsed render in the measurement dialog (v1 prose rows unchanged), `latest_ai_analysis` embedded in the 040 growth summary (consent-gated, server-side staleness) feeding a summary line in the Crecimiento tab and a warning marker on history rows, family provenance line without model slug, coach technical disclosure, 48 px controls, shared `Dialog` focus trap, `AIBudgetHint`, neutral disclaimer colour, shared empty message. Bundled hygiene: `claude-cli` forbidden in production, CLAUDE.md Alembic head corrected, the red `test_factory_openai_not_implemented` fixed, race Google/OpenAI builders stop reading `AI_TEMPERATURE`. No spending cap and no change to the race budget guard (owner decision).

## Technical Context

**Language/Version**: Python 3.13 (backend, venv `backend/.venv`); TypeScript 5 / React 19 (frontend, Vite)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), Alembic, Pydantic v2, Jinja2; `langchain>=1.3` (installed 1.3.1), `langchain-core` 1.4.9, `langchain-google-genai` 4.2.2, `langchain-anthropic` 1.4.8, `langchain-openai` 1.3.5, `langgraph` 1.2.0 (not used by the new pipeline), `langfuse` 4.6.1; optional local-only `langchain-claude-cli` (absent from requirements by design). Frontend: shadcn/ui, Tailwind v4, TanStack Query, Zustand, RHF + Zod. **No new runtime dependency.**

**Storage**: MySQL 8.4 (Hostinger in prod); `athlete_ai_explanations` extended with nine nullable columns; no new table; Langfuse local Postgres/ClickHouse volumes only in dev.

**Testing**: pytest default lane (aiosqlite, `FakeLLMProvider`, `LANGFUSE_ENABLED=false`); opt-in `-m mysql` for the columns and `on_duplicate_key_update`; `-m golden -k anthropometry` (12 synthetic cases, judge + scorer reusing `race/eval/scorer.py::composite_score`); `hypothesis` privacy sentinels at the new prompt seam; vitest + Testing Library + MSW; jest-axe zero violations on the measurement dialog and `GrowthTab`; Playwright generate → render → reopen-from-cache.

**Target Platform**: Render free tier (backend, cold start ~50 s), Cloudflare Pages (frontend); coach on tablet, parents on mid-tier Android over 3G.

**Project Type**: Web application (FastAPI backend + React SPA), Spec Kit feature.

**Performance Goals**: coach analysis p95 ≤ 45 s locally with `gemini-3.8-flash` analyst + `gemini-3.1-flash-lite` critic (two sequential LLM calls; frontend already handles 20–80 s waits with cold-start copy); `latest_ai_analysis` adds zero extra round trips (embedded in the growth summary already fetched); default pytest lane stays network-free; growth-tab lazy chunk unchanged in size class (no new chart, no new dependency).

**Constraints**: minors' privacy (Ley 1581) — no name, birth date, measurement, z-score or coach free text in traces, logs, fixtures or prompts beyond the existing allow-lists; redact-always trace content; `LANGFUSE_ENABLED`, `LANGFUSE_STRUCTURAL_METADATA` and `claude-cli` are startup failures in production; family delivery only of `approved | revised` insights (flagged, fallback and unreviewed `skipped` rows are coach-only); legacy v1 prose rows must keep rendering; one-way env inheritance (race may read `AI_*`, app stack never reads `RACE_AI_*`); Anthropic must not receive `temperature`; single Alembic head; product copy in español neutro with diacritics; planning corpus in English.

**Scale/Scope**: ~20 athletes, ~4 measurements/athlete/year → ~80 analyses/year (≈ 0.007 USD each); 7 traced use cases; 9 new columns; ~12 backend modules new (llm package, adapter, anthro pipeline, eval), ~4 frontend components changed + 1 new; 4 docs files; 12 golden cases.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it | Status |
|---|---|---|
| I. Code Quality | One shared factory (`app/services/llm/`) replaces two divergent copies of provider dispatch (rule of three: `ai/factory.py`, `race/agents/_llm.py`, and the would-be third in the new pipeline); race modules become shims so `monkeypatch` targets survive; five pure `(state, config) -> dict` steps with docstrings; one allow-list module for trace metadata with a snapshot test; `ruff` + `tsc --noEmit` gates; the red `test_factory_openai_not_implemented` is fixed rather than inherited. | PASS |
| II. Testing (NON-NEGOTIABLE) | Every contract ends with tests: adapter translation/exception mapping with `GenericFakeChatModel` (only there and in pipeline tests); provider-inheritance matrix; Anthropic-no-temperature; claude-cli lazy import + prod validator; mask sentinel + allow-list snapshot; per-step unit tests; pipeline integration (happy, analyst failure → fallback, critic timeout → `skipped` + low confidence, precheck block → fallback, family blocked); privacy at the new seam (forbidden names never in the rendered prompt; context never carries z-scores/percentiles/raw bands/absolute dates — hypothesis); denied paths 403/451/503 re-run on the new path and on `latest_ai_analysis`; v1/v2/corrupt-JSON rendering; `-m mysql` for the nine columns and upsert; golden eval blocking; flag test (five bridged use cases pass under both `AI_USE_LANGCHAIN` values); vitest discriminated-union + renderer branches; jest-axe on dialog and `GrowthTab`; Playwright. Regression tests for the three bugs fixed (red factory test, race builders reading `AI_TEMPERATURE`, enumerable session hash). | PASS |
| III. UX Consistency | Shared `Dialog` primitive replaces the hand-rolled modal (focus trap, Escape, 48 px close); "Regenerar análisis"/"Copiar" become real ≥48 px buttons; `AIBudgetHint` reused at both cards; disclaimer on neutral token, amber reserved for conditional training implications, delta chips on `StatusBadge` tokens; family provenance "Generado por el asistente de IA del club"; shared passive empty message on both parent cards; loading/empty/error/stale/flagged states designed per surface in `contracts/` and `ui-design-analysis-summary`; all copy in español neutro with diacritics; WCAG AA via jest-axe. | PASS |
| IV. Performance | `latest_ai_analysis` computed in the existing growth-summary request (one extra indexed lookup on `athlete_ai_explanations` by athlete + record, no N+1, non-fatal); no new chart or dependency in the growth chunk; analysis endpoints already exceed the 1500 ms write budget by nature (single LLM call today) — the second sequential call is documented as a budget exception in the route docstring and in Complexity Tracking, with a p95 ≤ 45 s local target and a documented exit to submit-and-poll; tracing adds no synchronous network wait (batched exporter, degrades to no-op). | PASS (documented exception) |
| V. Youth Psych. Safeguards | Not a psychological instrument. Adjacent safeguards honoured and strengthened: no diagnosis (R02), no population comparison (R01), uncertainty language mandatory near boundaries, warning signs routed to coach/paediatrician, rule-based deterministic fallback when the LLM is unavailable, human (coach) in the loop for anything flagged, consent gate on every AI read including the embedded summary. | N/A / respected |
| Quality gate — Privacy | `data-privacy-guard` audit is a mandatory task for the widened context, the golden dataset (synthetic only) and the trace allow-list; k-anonymity arithmetic in research rules out any demographic/biological trace field; content redact-always; identifiers keyed-hashed; coach free text never traced (not even its length); `AI_LOG_PROMPTS=false` unchanged; fixtures synthetic. | PASS |
| Quality gate — Stack discipline | No new runtime dependency (langchain, langfuse, langchain-* already pinned); `langchain-claude-cli` stays out of requirements and is a prod startup failure; no Langfuse prompt management/datasets; structured output via JSON-in-prompt + Pydantic validation, not tool calling. | PASS |
| Quality gate — AI features | Guardrails remain the last defence on rendered text; forbidden-names list from DB reused (`load_club_forbidden_names`); word limits enforced by the system; consent gate on every path; property tests assert names never appear in prompt or output. | PASS |
| Quality gate — Observability | Trace ids stored on the record (empty in prod); one warning per process when Langfuse is misconfigured; no bodies in logs; structured log events for fallback/critic-skipped. | PASS |
| Workflow — Branching | `feat/042-traceable-growth-ai` (Spec Kit hook, project naming). Conventional Commits, no AI mention. | PASS |

**Post-design re-check (after Phase 1)**: unchanged. The contracts introduce no new dependency and no PII-bearing field; the only budget item is the documented two-call latency exception. One spec-level deviation surfaced and is recorded: the owner's wording "small LangGraph graph" is discharged by a plain sequential orchestrator with LangGraph-compatible step signatures (research R-03); a StateGraph without checkpointer can be swapped in mechanically if the owner prefers the literal reading.

## Project Structure

### Documentation (this feature)

```text
specs/042-traceable-growth-ai/
├── plan.md                                  # This file
├── spec.md                                  # Feature specification (owner decisions in Assumptions)
├── research.md                              # Phase 0 — consolidated from the seven research briefs
├── data-model.md                            # Phase 1 — extended cache row, insight/context/verdict value objects
├── quickstart.md                            # Phase 1 — validation scenarios and wave gates
├── contracts/
│   ├── llm-transport.md                     # LangChainProvider adapter + shared factory API
│   ├── measurement-analysis-api.md          # per-record and PHV endpoints, v1|v2 discriminated response
│   ├── growth-summary-latest-analysis.md    # latest_ai_analysis on the 040 growth summary
│   ├── analysis-context.md                  # context-node keys, allow-list, 26-week/16-point rules
│   ├── insight-schema.md                    # AnthropometryInsightV1 (Pydantic + Zod), word budgets
│   ├── trace-metadata-allowlist.md          # Langfuse mask sentinel, allow-list table, tags, session id
│   ├── config-env.md                        # new Settings, validators, env matrix
│   ├── golden-eval-case.md                  # case JSON format, 12 cases, rubric, threshold, CI
│   └── prompts/
│       ├── anthropometry_analyst_v1.md      # analyst prompt draft (audience switch)
│       └── anthropometry_critic_v1.md       # critic prompt draft
├── checklists/requirements.md               # spec quality checklist
└── tasks.md                                 # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py                            # W1: AI_USE_LANGCHAIN, AI_ANALYST_MODEL, AI_CRITIC_MODEL, RACE_AI_TEMPERATURE,
│   │                                        #     AI_ANTHRO_PROMPT_VERSION, LANGFUSE_STRUCTURAL_METADATA,
│   │                                        #     claude-cli prod validator (both stacks)
│   ├── services/
│   │   ├── llm/                             # W1 (new) — shared, stack-neutral
│   │   │   ├── __init__.py
│   │   │   ├── factory.py                   # build_chat_llm(provider, model, role, ...), resolve_configured_model,
│   │   │   │                                #   DEFAULT_MODEL_BY_PROVIDER; per-stack config resolvers (one-way inheritance)
│   │   │   ├── calls.py                     # call_llm, extract_text, extract_usage, LLMCallResult
│   │   │   ├── pricing.py                   # moved from race/agents/pricing.py
│   │   │   ├── observability.py             # moved from race/observability.py: client singleton, llm_tracing,
│   │   │   │                                #   trace_id_for, keyed session id (HMAC), build_mask(sentinel)
│   │   │   └── observability_metadata.py    # ALLOWED_METADATA_KEYS, StructuralMetadata, build_structural_metadata()
│   │   ├── race/
│   │   │   ├── agents/_llm.py               # W1: shim re-exporting from app.services.llm (monkeypatch targets kept)
│   │   │   ├── agents/pricing.py            # W1: shim
│   │   │   ├── agents/chat.py               # W1: session id → keyed hash
│   │   │   └── observability.py             # W1: shim
│   │   └── ai/
│   │       ├── factory.py                   # W1: "langchain" branch behind AI_USE_LANGCHAIN; fake short-circuit first
│   │       ├── providers/langchain_provider.py   # W1 (new): LLMProvider + StructuredOutput over BaseChatModel
│   │       ├── context_builders.py          # W2: VELOCITY_RELIABLE_WEEKS, velocity_confidence,
│   │       │                                #     phase_crossing_corroborated, longitudinal series builder,
│   │       │                                #     ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS
│   │       ├── guardrails.py                # W2: use_case="anthropometry_insight_v1" branch (R04/R05/R11/R12)
│   │       ├── prompts/registry.py          # untouched (legacy specs stay)
│   │       ├── use_cases/*.py               # untouched (legacy paths; PHV/record explainers delegate to anthro in W2)
│   │       └── anthro/                      # W2 (new) — the rebuilt analysis
│   │           ├── __init__.py
│   │           ├── schemas.py               # AnthropometryInsightV1, Confidence, CriticIssue, CriticVerdict
│   │           ├── context.py               # step 1: AnalysisContext from records + growth summary + training window
│   │           ├── prechecks.py             # R01–R12 deterministic rules (reusing guardrails regexes)
│   │           ├── analyst.py               # step 2: render prompt, call (role="analyst"), tolerant JSON extract, 1 retry
│   │           ├── critic.py                # step 3: call (role="critic"), verdict, revision policy, skip-on-failure
│   │           ├── guardrails_step.py       # step 4: rendered-text scrub, family gating
│   │           ├── persist.py               # step 5: upsert nine columns + text, audit entry
│   │           ├── pipeline.py              # run_analysis(): root span, config threading, fallback orchestration
│   │           ├── fallback.py              # deterministic template per audience
│   │           ├── prompts/
│   │           │   ├── loader.py            # Jinja StrictUndefined loader (as race/agents)
│   │           │   ├── anthropometry_analyst_v1.md
│   │           │   └── anthropometry_critic_v1.md
│   │           └── eval/
│   │               ├── judge.py
│   │               └── scorer.py            # reuses race/eval/scorer.composite_score
│   ├── models/ai_explanation.py             # W2: nine nullable columns
│   ├── schemas/ai.py                        # W2: v1|v2 discriminated responses, LatestAiAnalysis
│   ├── schemas/growth.py                    # W3: GrowthSummaryOut.latest_ai_analysis
│   ├── routers/ai.py                        # W2: endpoints call anthro.pipeline; response mapping; family gating
│   ├── routers/growth.py                    # W3: latest_ai_analysis (consent-gated, non-fatal, server-side is_stale)
│   ├── routers/monthly_reports.py           # W3: no change expected (switch lives in factory) — verify only
│   ├── dependencies.py                      # W3: get_llm_provider honours AI_USE_LANGCHAIN
│   └── services/ai_spend.py (or 041 module) # W3: per-coach spend adds stack="app" rows from athlete_ai_explanations
├── alembic/versions/<rev>_ai_explanations_traceability.py   # W2: down_revision="45cd705c6b54"
├── evals/anthropometry_analyst/
│   ├── golden/case_001.json … case_012.json # W2 (synthetic)
│   └── baseline.json
└── tests/
    ├── test_llm_factory.py                  # W1: inheritance matrix, anthropic no-temperature, claude-cli lazy/prod
    ├── test_llm_observability.py            # W1: mask sentinel, allow-list snapshot, keyed session id, degrade-to-noop
    ├── test_langchain_provider.py           # W1: adapter translation + exception mapping (GenericFakeChatModel)
    ├── test_ai_factory.py                   # W1: fix red test; switch test
    ├── anthro/test_context.py …             # W2: per step, pipeline integration, privacy at the seam, versioning
    ├── test_ai_record_router.py, test_ai_router.py   # W2: denied paths on new path, v1/v2 responses
    ├── test_growth_summary_latest_analysis.py        # W3: null conditions, staleness, consent denied-path
    ├── evals/test_anthropometry_analyst_eval.py      # W2: -m golden -k anthropometry
    └── mysql/test_ai_explanation_columns.py          # W2: -m mysql upsert of nine columns

frontend/src/
├── schemas/ai.schemas.ts                    # W2: discriminated union on schema_version (default "v1")
├── types/ai.types.ts, types/growth.types.ts # W2/W3
├── api/ai.ts, hooks/ai/*                    # W3
├── components/ai/
│   ├── AIGeneratedContent.tsx               # W2: provenance by audience, disclaimer neutral token, 48 px Copiar
│   ├── AnthropometricRecordExplanationCard.tsx   # W2: v2 collapsed renderer, "Con observaciones", stale chip,
│   │                                        #     AIBudgetHint, technical disclosure (coach), shared empty message
│   ├── PHVExplanationCard.tsx               # W2: heading in success state (G-16), 48 px Regenerar, AIBudgetHint
│   └── StructuredInsight.tsx                # W2 (new): four labelled sections + expander (aria-expanded/controls)
├── components/athletes/
│   ├── AnthropometryHistory.tsx             # W3: shared Dialog (focus trap, 48 px close), row marker "Con señal para revisar"
│   └── growth/
│       ├── GrowthTab.tsx                    # W3: LatestAnalysisLine above history (coach + family)
│       └── LatestAnalysisLine.tsx           # W3 (new): states not-rendered/loading/none/current/stale/flagged/error
├── lib/ai/pendingMessage.ts                 # W2 (new): shared cold-start copy for both cards
└── e2e/growth-analysis.spec.ts              # W3: generate → render → reopen from cache

docs/
├── 01-marco-teorico.md                      # W4: §1 subsection "Interpreting maturity-offset estimates" + references
├── 20-traceable-growth-ai/{design.md, qa.md, runbook.md}   # W4 (new)
├── 10-race-results/runbook-ops.md           # W4: §8 traced entry points (7), structural metadata, purge
├── implementation-status.md, technical-notes.md            # W4
.github/workflows/anthropometry-eval.yml     # W2: cloned from race-eval.yml
CLAUDE.md                                    # W4: Alembic head, new env vars, anthro pipeline paragraph
```

**Structure Decision**: Web application (backend + frontend) with the existing modular-monolith layout. The new shared package is `backend/app/services/llm/` (stack-neutral; both `race/` and `ai/` consume it, race keeps shims). The rebuilt analysis lives inside the app AI stack at `backend/app/services/ai/anthro/` so it shares the adapter, guardrails and prompt conventions of that stack; it deliberately does **not** live under `race/` and does **not** create a third stack. No new frontend route; one new growth component and one new AI presentational component.

## Phase 0 — Research (complete)

Seven research briefs were produced by specialist agents on 2026-09-11 (architecture — Opus; sports science, UX, UI design, Langfuse/LangChain, privacy, prompt design — Sonnet) and reconciled by the lead in `research.md` (R-01 … R-27). Decisions that override individual briefs: no spending cap and no change to the race budget guard (owner) over the architect's shared-pool/warn-only proposals; plain sequential orchestrator over LangGraph; module `app/services/ai/anthro/` over `app/services/growth_ai/`; `AI_ANALYST_MODEL`/`AI_CRITIC_MODEL` over an `ANTHRO_AI_*` prefix; HMAC session id keyed from the server secret (owner) over the privacy brief's per-process salt; `age_group` and every demographic/biological field excluded from trace tags and metadata (privacy) over the architect's initial tag list. All "NEEDS CLARIFICATION" items are resolved; none remain.

## Phase 1 — Design (complete)

- `data-model.md` — extended `AthleteAIExplanation` (nine nullable columns), `AnthropometryInsightV1`, `AnalysisContext`, `PrecheckResult`, `CriticVerdict`, `LatestAiAnalysis`, `StructuralMetadata`; generation state machine; staleness rule; migration sketch; invariants.
- `contracts/` — nine contracts listed above plus the two prompt drafts.
- `quickstart.md` — eleven validation scenarios mapped to SC-001…SC-009, wave gate checklist, post-deploy smoke.
- Agent context — `CLAUDE.md` Spec Kit block updated to point at this plan.

## Phase 2 — Task generation (next: `/speckit-tasks`)

Waves with **disjoint file ownership** (Sonnet workers; an Opus gate runs `ruff`, default `pytest`, `-m mysql`, race golden, anthro golden (from W2), `npm run build`, `npm test`, jest-axe, Playwright (W3) between waves; gates are cumulative):

| Wave | Goal | Owns (no other wave touches) | Exit gate |
|---|---|---|---|
| **W1** Shared factory, adapter, tracing, config | `app/services/llm/*` (new); race shims (`agents/_llm.py`, `agents/pricing.py`, `observability.py`, `agents/chat.py` session id); `app/services/ai/factory.py`, `providers/langchain_provider.py`; `app/config.py`; `tests/test_llm_*.py`, `tests/test_langchain_provider.py`, `tests/test_ai_factory.py` | race golden unchanged; inheritance matrix + no-temperature + lazy-import + prod-validator tests; mask sentinel + allow-list snapshot; red test fixed; both `AI_USE_LANGCHAIN` values green on existing suites |
| **W2** Anthro pipeline, eval, persistence, dialog renderer | `app/services/ai/anthro/**` (new); `context_builders.py`, `guardrails.py`; `models/ai_explanation.py`; one Alembic revision; `routers/ai.py`, `schemas/ai.py`; `evals/anthropometry_analyst/**`; `.github/workflows/anthropometry-eval.yml`; `tests/anthro/**`, `tests/evals/test_anthropometry_analyst_eval.py`, `tests/mysql/test_ai_explanation_columns.py`, `tests/test_ai_record_router.py`, `tests/test_ai_router.py`; frontend `schemas/ai.schemas.ts`, `types/ai.types.ts`, `components/ai/**`, `lib/ai/pendingMessage.ts` | anthro golden ≥ 0.75 blocking; `-m mysql` columns; denied paths 403/451/503; privacy at the seam (hypothesis); `data-privacy-guard` audit of context, dataset and allow-list; v1/v2/corrupt render tests; jest-axe on both cards |
| **W3** Growth summary field, growth-tab line, dialog migration, spend view, switch verification | `routers/growth.py`, `schemas/growth.py`; `dependencies.py`; spend view module of 041; `tests/test_growth_summary_latest_analysis.py`; frontend `types/growth.types.ts`, `api/ai.ts`, `hooks/ai/*`, `components/athletes/AnthropometryHistory.tsx`, `components/athletes/growth/GrowthTab.tsx`, `components/athletes/growth/LatestAnalysisLine.tsx` (new), `e2e/growth-analysis.spec.ts` | consent-gate denied path on `latest_ai_analysis`; staleness tests; five bridged use cases green under both switch values; jest-axe on dialog + `GrowthTab`; Playwright; race golden re-run (last shared-factory checkpoint) |
| **W4** Docs and runbook | `docs/01-marco-teorico.md`, `docs/20-traceable-growth-ai/**`, `docs/10-race-results/runbook-ops.md`, `docs/implementation-status.md`, `docs/technical-notes.md`, `CLAUDE.md`, `backend/.env.example` (names only) | docs match shipped behaviour; runbook lists 7 traced entry points, structural-metadata switch and purge cadence; CLAUDE.md head = new 042 revision |

Ordering notes: W2 depends on W1 (factory/adapter); W3 depends on W2 (schema union, `LatestAiAnalysis`); W4 last. Feature 040's deferred items (T027/T028, Playwright specs, T077–T079) collide with W2/W3 surfaces — 042 goes first (owner acknowledged); those specs are then written against the traced path.

## Open operational decisions (owner)

None blocking. Recorded for `/speckit-tasks`:

0. Design calls made by the contract writer and accepted by the lead (confirm or override before tasks): the per-measurement endpoints gain `?audience=family|coach` (default `family`, new coach cache row) mirroring the PHV endpoint; family gating is keyed on the caller's role, so a coach previewing `audience=family` still sees flagged content; `latest_ai_analysis` is sourced from the family-audience per-measurement row; a new `RACE_AI_TEMPERATURE` (default 0.4, today's effective value) gives the race builders their own sampling setting; an unreviewed (`skipped`) analysis is coach-only, like flagged.

1. Literal LangGraph vs plain orchestrator — plan chooses the orchestrator with LangGraph-compatible step signatures (research R-03); say the word and W2 builds a checkpointer-less `StateGraph` instead, same nodes.
2. Whether to also apply the keyed session hash to the race eval judge trace (same helper, one-line) — plan includes it for consistency.
3. Representative Android device for family-mode usability checks — tracked outside this feature.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Analysis endpoints exceed the p95 ≤ 1500 ms write budget (two sequential LLM calls, ~20–40 s locally) | The owner requires a critic review before persistence; a synchronous path avoids a checkpointer/poller on Render's ephemeral filesystem and reuses the frontend's existing long-wait UX | Submit-and-poll (as race) adds a runner, a stale-run reconciler and a polling hook for ~80 generations/year; documented exit: convert `pipeline.run_analysis` to a submitted run if local p95 exceeds 45 s. Single-call without critic rejected by the owner (safety). |
| Shims left in `race/agents/_llm.py`, `race/agents/pricing.py`, `race/observability.py` | ~30 race tests `monkeypatch` those module paths; removing them in the same wave couples W1 to the race suite refactor | Deleting the modules and rewriting every patch target in one wave rejected as needless risk to the blocking race golden eval; shims are removed in a follow-up once tests import from `app.services.llm`. |
| Nine nullable columns on `athlete_ai_explanations` instead of a normalised `ai_generation` table | The cache row *is* the generation (one per athlete × record × use case); telemetry belongs beside the text it describes; nullable columns keep v1 rows valid with no backfill | A new `ai_generations` table (or reuse of `agent_runs`) rejected: `agent_runs` has race-only NOT NULL columns and feeds the race budget guard, which the owner forbids counting this stack against. |
