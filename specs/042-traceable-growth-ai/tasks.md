---
description: "Task list for feature 042 — Traceable AI growth analysis"
---

# Tasks: Traceable AI growth analysis

**Input**: Design documents from `/specs/042-traceable-growth-ai/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/` (9 + 2 prompt drafts), `quickstart.md`

**Tests**: REQUIRED. Constitution principle II (Testing) is NON-NEGOTIABLE and `plan.md` §Constitution Check binds every contract to tests. Test tasks are therefore first-class here, not optional.

**Organization**: Tasks are grouped into the four implementation **waves** of `plan.md` §Phase 2 (disjoint file ownership, cumulative exit gates) and each task carries the user story it serves. Wave = phase; the mapping is:

| Phase | Wave | User stories served |
|---|---|---|
| Phase 1 | Setup | — |
| Phase 2 | **W1** shared factory, adapter, tracing, config | US2 (P1), US6 (P3, config half) |
| Phase 3 | **W2** anthro pipeline, eval, persistence, dialog renderer | US1 (P1), US3 (P2), US5 (P3) |
| Phase 4 | **W3** growth summary field, tab line, dialog migration, spend, switch verification | US4 (P2), US6 (P3), US2 (bridged use cases) |
| Phase 5 | **W4** docs and runbook | — (polish / cross-cutting) |

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US6 from `spec.md`
- Every task names its exact file path

## Path Conventions

Web application (`plan.md` §Structure Decision): backend at `backend/app/…`, backend tests at `backend/tests/…`, frontend at `frontend/src/…`, docs at `docs/…`. All paths below are repository-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the ground the four waves stand on. No production code changes.

- [X] T001 Verify the Alembic chain has a single head and that it is `45cd705c6b54` by running `alembic heads` from `backend/` (venv active); record the actual value in `specs/042-traceable-growth-ai/tasks.md` notes if it differs, because `data-model.md` §5 pins `down_revision` to it.
- [X] T002 [P] Verify the pinned versions in `backend/requirements.txt` cover `langchain`, `langchain-core`, `langchain-google-genai`, `langchain-anthropic`, `langchain-openai` and `langfuse`, and confirm `langchain-claude-cli` is **absent** by design; no dependency is added by this feature.
- [X] T003 [P] Create the empty package skeletons `backend/app/services/llm/__init__.py` and `backend/app/services/ai/anthro/__init__.py` (plus `anthro/prompts/` and `anthro/eval/`) so the two waves have disjoint, importable roots.
- [X] T004 [P] Create the test package roots `backend/tests/anthro/__init__.py` and confirm `backend/tests/mysql/` and `backend/tests/evals/` exist; add `__init__.py` where the existing convention requires one.

---

## Phase 2: Foundational — Wave 1 (Blocking Prerequisites)

**Purpose**: One shared, stack-neutral chat-model factory plus the traced LangChain transport and the config surface. **Every later wave depends on this.**

**Owns** (`plan.md` W1): `backend/app/services/llm/*`; the race shims; `backend/app/services/ai/factory.py`; `backend/app/services/ai/providers/langchain_provider.py`; `backend/app/config.py`; `backend/tests/test_llm_*.py`, `test_langchain_provider.py`, `test_ai_factory.py`.

**Exit gate**: `ruff check`; default `pytest`; `pytest -m golden -k race` green with zero behavioural diff; inheritance-matrix + Anthropic-no-temperature regression tests; `test_factory_openai_not_implemented` fixed; redact-always mask unit-tested; allow-list snapshot passing; existing suites green under **both** values of `AI_USE_LANGCHAIN`.

### Configuration

- [X] T005 [US2] Add the new settings to `backend/app/config.py` per `contracts/config-env.md`: `AI_USE_LANGCHAIN` (bool, default off), `AI_ANALYST_MODEL`, `AI_CRITIC_MODEL`, `AI_ANTHRO_PROMPT_VERSION` (default `anthropometry_analyst_v1`), `RACE_AI_TEMPERATURE` (default 0.4), `LANGFUSE_STRUCTURAL_METADATA` (bool, default off).
- [X] T006 [US6] Add the production startup validators to `backend/app/config.py`: `APP_ENV=production` must fail when `LANGFUSE_ENABLED` is true, when `LANGFUSE_STRUCTURAL_METADATA` is true, or when either `AI_PROVIDER` or `RACE_AI_PROVIDER` resolves to `claude-cli`; each message must name the offending variable (FR-021, FR-037, SC-009).
- [ ] T007 [P] [US6] Write `backend/tests/test_ai_config.py` additions covering the three production-forbidden settings (three separate failures, each asserting the variable name appears in the message) and the defaults of the six new settings.

### Shared factory package (`app/services/llm/`)

- [X] T008 [US2] Create `backend/app/services/llm/factory.py` per `contracts/llm-transport.md`: `build_chat_llm(provider, model, role, temperature=None, **kw)`, `resolve_configured_model`, `DEFAULT_MODEL_BY_PROVIDER`, and the two per-stack config resolvers enforcing the one-way inheritance (race may read `AI_*`; the app stack never reads `RACE_AI_*`). Anthropic must never receive `temperature`; the `claude-cli` import stays lazy.
- [X] T009 [P] [US2] Create `backend/app/services/llm/calls.py`: `call_llm`, `extract_text`, `extract_usage`, `LLMCallResult` (text, tokens in/out, model, provider, latency), lifted from the race call path.
- [X] T010 [P] [US2] Move `backend/app/services/race/agents/pricing.py` to `backend/app/services/llm/pricing.py` (keep `compute_cost_usd`'s six-decimal rounding and the price table intact).
- [X] T011 [US2] Move `backend/app/services/race/observability.py` to `backend/app/services/llm/observability.py`: Langfuse client singleton, `llm_tracing` context manager, `trace_id_for`, degrade-to-no-op when the instance is unreachable (one warning per process), and `build_mask(sentinel)` implementing redact-always (FR-018, FR-021).
- [X] T012 [US2] Add the keyed session identifier to `backend/app/services/llm/observability.py`: HMAC derived from `JWT_SECRET_KEY` with a domain separator distinct from the race anonymiser, stable across restarts, never enumerable from the trace store (FR-019).
- [X] T013 [US2] Create `backend/app/services/llm/observability_metadata.py` per `contracts/trace-metadata-allowlist.md`: `ALLOWED_METADATA_KEYS`, the `StructuralMetadata` model and `build_structural_metadata()` returning `{}` unless `LANGFUSE_STRUCTURAL_METADATA` is on; no demographic or biological field may ever be emitted (FR-020).

### Race shims (monkeypatch targets preserved)

- [ ] T014 [US2] Reduce `backend/app/services/race/agents/_llm.py` to a shim re-exporting `build_chat_llm` and friends from `app.services.llm.factory`, keeping every symbol the ~30 race tests monkeypatch.
- [X] T015 [P] [US2] Reduce `backend/app/services/race/agents/pricing.py` to a shim re-exporting from `app.services.llm.pricing`.
- [X] T016 [P] [US2] Reduce `backend/app/services/race/observability.py` to a shim re-exporting from `app.services.llm.observability`.
- [X] T017 [US2] Stop the race Google and OpenAI builders from reading `AI_TEMPERATURE`; they now read the new `RACE_AI_TEMPERATURE` (default 0.4, today's effective value) inside `backend/app/services/llm/factory.py`.
- [ ] T018 [US2] Replace the truncated session hash in `backend/app/services/race/agents/chat.py` with the keyed hash from T012 (FR-024), and apply the same helper to the race eval judge trace (`plan.md` open decision 2).

### LangChain transport adapter

- [ ] T019 [US2] Create `backend/app/services/ai/providers/langchain_provider.py`: a `LangChainProvider` implementing the existing `LLMProvider` Protocol (and its structured-output method) over a `BaseChatModel` from the shared factory, mapping LangChain exceptions onto the stack's `app/services/ai/errors.py` types and exposing the same usage/latency data as the native providers.
- [ ] T020 [US2] Wire the `"langchain"` branch into `backend/app/services/ai/factory.py` behind `AI_USE_LANGCHAIN`, keeping the `FakeLLMProvider` short-circuit **first** so `AI_ENABLED=false` and the ~40 `fake.last_request` privacy assertions are untouched (FR-025, FR-038).

### Wave 1 tests

- [ ] T021 [P] [US2] Write `backend/tests/test_llm_factory.py`: the provider-inheritance matrix (empty `RACE_AI_PROVIDER` inherits `AI_PROVIDER`; the app stack never reads `RACE_AI_*`; empty `RACE_AI_MODEL` resolves to the per-provider default, not `AI_MODEL`; `RACE_AI_API_KEY` falls back to `AI_API_KEY` only on a matching effective provider), the Anthropic-no-temperature regression, and the `claude-cli` lazy-import behaviour.
- [ ] T022 [P] [US2] Write `backend/tests/test_llm_observability.py`: mask sentinel redacts every content field, the allow-list snapshot test over `ALLOWED_METADATA_KEYS`, the keyed session id (stable, non-enumerable, domain-separated), and degrade-to-no-op with exactly one warning per process when Langfuse is unreachable.
- [ ] T023 [P] [US2] Write `backend/tests/test_langchain_provider.py`: adapter translation and exception mapping using `GenericFakeChatModel`, including usage extraction and the structured-output path.
- [ ] T024 [US2] Fix the red `test_factory_openai_not_implemented` in `backend/tests/test_ai_factory.py` and add the `AI_USE_LANGCHAIN` switch test (off → native provider, on → `LangChainProvider`, `AI_ENABLED=false` → `FakeLLMProvider` under both).
- [ ] T025 [US2] Run the Wave 1 exit gate from `backend/`: `ruff check`, default `pytest`, `pytest -m golden -k race`, and the full default lane once with `AI_USE_LANGCHAIN=true` — record any behavioural diff in the race golden as a blocker.

**Checkpoint**: the shared transport exists, traces redacted, race behaviour unchanged. W2 and W3 may start.

---

## Phase 3: Wave 2 — US1 (P1), US3 (P2), US5 (P3)

**Goal**: The rebuilt anthropometric analysis — structured, longitudinally grounded, self-reviewed, persisted with accounting, rendered in the dialog, guarded by a blocking golden eval.

**Independent test criteria**: With W1 in place, a coach request for one measurement returns a six-part `AnthropometryInsightV1`; a family request never returns a flagged, fallback or unreviewed text; `pytest -m golden -k anthropometry` scores ≥ 0.75; legacy prose rows still render.

**Owns** (`plan.md` W2): `backend/app/services/ai/anthro/**`; `context_builders.py`; `guardrails.py`; `models/ai_explanation.py`; one Alembic revision; `routers/ai.py`; `schemas/ai.py`; `backend/evals/anthropometry_analyst/**`; `.github/workflows/anthropometry-eval.yml`; `backend/tests/anthro/**` and the listed test files; frontend `schemas/ai.schemas.ts`, `types/ai.types.ts`, `components/ai/**`, `lib/ai/pendingMessage.ts`.

### Schemas and context

- [ ] T026 [US1] Create `backend/app/services/ai/anthro/schemas.py` per `contracts/insight-schema.md` and `data-model.md` §2.1: `AnthropometryInsightV1` (summary ≤140 chars; `que_cambio` 1–4, `que_significa` 1–4, `proximas_semanas` 1–3, `senales_aviso` 0–2, `data_gaps` 0–3; plain prose, no Markdown), `Confidence`, `CriticIssue`, `CriticVerdict` — with the word budgets (family ≤180, coach ≤110) validated by the model itself (FR-001, FR-002).
- [ ] T027 [US1] Add the longitudinal helpers to `backend/app/services/ai/context_builders.py`: `VELOCITY_RELIABLE_WEEKS = 26`, `velocity_confidence()` (8-week computation floor unchanged, `reliable` only at ≥26 weeks), `phase_crossing_corroborated()`, the compacted series builder (offsets in weeks, yearly checkpoints beyond 16 points, no sitting height or arm span per point) and `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS` (FR-003, FR-004, FR-005).
- [ ] T028 [US1] Create `backend/app/services/ai/anthro/context.py` (pipeline step 1) per `contracts/analysis-context.md`: assemble `AnalysisContext` from the measurement deltas with significance flags, the compacted history, the 040 growth summary (stage, maturity offset, qualitative bands, expected velocity range, alert codes, next-measurement status), the 28-day training-load aggregates and the previous structured insight. Z-scores, percentiles, raw band values and absolute dates must never enter (FR-003).

### Deterministic rules and prompts

- [ ] T029 [P] [US1] Create `backend/app/services/ai/anthro/prechecks.py`: rules R01–R12 per `contracts/insight-schema.md` and `data-model.md` §2.3, reusing the existing regexes in `backend/app/services/ai/guardrails.py`; privacy and developmental-safety rules block delivery, the rest lower confidence; word budget carries a 10 % tolerance (FR-011).
- [ ] T030 [P] [US1] Create `backend/app/services/ai/anthro/prompts/loader.py` — a Jinja `StrictUndefined` loader mirroring the race `agents` prompt loader.
- [ ] T031 [US1] Write `backend/app/services/ai/anthro/prompts/anthropometry_analyst_v1.md` from `contracts/prompts/anthropometry_analyst_v1.md`: audience switch (family "su hijo"/"su hija", coach "tu deportista"), JSON-only output contract, velocity anchors taken **only** from the growth summary's expected range, mandatory uncertainty wording near a phase boundary or outside ages 11–15, warning signs routed to the coach, no population comparison, no clinical label, no exact PHV date (FR-002, FR-006, FR-007, FR-008, FR-036).
- [ ] T032 [P] [US1] Write `backend/app/services/ai/anthro/prompts/anthropometry_critic_v1.md` from `contracts/prompts/anthropometry_critic_v1.md`: judge only contradiction with the growth summary, honesty of the confidence reason and tone; return `approve | revise | reject` with rule-coded violations (FR-012).

### Pipeline steps

- [ ] T033 [US1] Create `backend/app/services/ai/anthro/analyst.py` (step 2): render the prompt, call the shared transport with `role="analyst"` (`AI_ANALYST_MODEL`), tolerant JSON extraction, one retry on invalid structure, returning the draft plus usage.
- [ ] T034 [US1] Create `backend/app/services/ai/anthro/critic.py` (step 3): call with `role="critic"` (`AI_CRITIC_MODEL`), parse the verdict, apply the revision policy (mechanical fixes adopted directly; interpretive violations sent back once with the violations attached), and skip-on-failure semantics — verdict `skipped`, confidence lowered to low, unavailability recorded (FR-013, FR-014).
- [ ] T035 [P] [US1] Create `backend/app/services/ai/anthro/fallback.py`: the deterministic template per audience producing a valid `AnthropometryInsightV1` with low confidence and the fallback flag (FR-013).
- [ ] T036 [US3] Create `backend/app/services/ai/anthro/guardrails_step.py` (step 4): run the existing rendered-text guardrails as the last defence and gate family delivery so only `approved | revised` reaches a family audience; `flagged`, `fallback` and `skipped` are coach-only (FR-015, FR-016).
- [ ] T037 [US1] Add the `use_case="anthropometry_insight_v1"` branch to `backend/app/services/ai/guardrails.py` covering R04/R05/R11/R12 on the rendered text, reusing `load_club_forbidden_names`.
- [ ] T038 [US1] Create `backend/app/services/ai/anthro/persist.py` (step 5): upsert the nine new columns plus the prose rendering of the insight into `text` (which stays `NOT NULL`), and write the audit entry; extend the two `on_duplicate_key_update` lists by nine entries each (`data-model.md` §1).
- [ ] T039 [US1] Create `backend/app/services/ai/anthro/pipeline.py`: `run_analysis()` threading `(state, config)` through the five steps, opening the root trace span, orchestrating the precheck-block → fallback and analyst-failure → fallback paths, and measuring whole-run latency for `latency_ms`.

### Persistence and API

- [ ] T040 [US1] Add the nine nullable columns to `backend/app/models/ai_explanation.py` exactly as `data-model.md` §1 specifies: `schema_version`, `structured_json`, `critic_verdict`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `langfuse_trace_id`. No `server_default`, no new index.
- [ ] T041 [US1] Create the Alembic revision `backend/alembic/versions/<rev>_ai_explanations_traceability.py` with `down_revision="45cd705c6b54"` adding the nine columns and a working `downgrade()`; confirm `alembic heads` still shows a single head.
- [ ] T042 [US1] Extend `backend/app/schemas/ai.py` with the `v1 | v2` discriminated response (discriminator `schema_version`, legacy `NULL` rows surfacing as `"v1"`), the structured payload and the coach-only technical fields (model, prompt version, trace reference).
- [ ] T043 [US1] Rewire the per-measurement and PHV endpoints in `backend/app/routers/ai.py` to `anthro.pipeline.run_analysis`, add the `?audience=family|coach` parameter (default `family`, separate coach cache row) per `plan.md` open decision 0, map the response, and keep family gating keyed on the caller's role (FR-016). Document the two-call latency budget exception in the route docstring (`plan.md` Complexity Tracking).

### Golden eval (US5)

- [ ] T044 [P] [US5] Create `backend/app/services/ai/anthro/eval/scorer.py` reusing `backend/app/services/race/eval/scorer.py::composite_score` with the 042 weights: grounding 0.30, uncertainty calibration 0.20, privacy and developmental safety 0.20, tone and format 0.15, actionability 0.15 (FR-035).
- [ ] T045 [P] [US5] Create `backend/app/services/ai/anthro/eval/judge.py` per `contracts/golden-eval-case.md`, skipping explicitly (never silently passing) when no real model key is configured.
- [ ] T046 [US5] Author the twelve **synthetic** golden cases `backend/evals/anthropometry_analyst/golden/case_001.json` … `case_012.json` per `contracts/golden-eval-case.md` — covering first measurement, <8-week interval, <26-week interval, ≥26-week reliable velocity, uncorroborated phase crossing, corroborated crossing, boundary/age-outside-11–15 uncertainty, above-typical velocity, warning signs, missing training window, >16-point history, family vs coach audience — with no real athlete data.
- [ ] T047 [US5] Create `backend/evals/anthropometry_analyst/baseline.json` with the shipped prompt/model baseline scores and the 0.75 composite threshold.
- [ ] T048 [US5] Write `backend/tests/evals/test_anthropometry_analyst_eval.py` marked `golden`, blocking below composite 0.75, asserting SC-003 (100 % of <26-week cases call velocity an early signal; 0 uncorroborated crossings stated as confirmed).
- [ ] T049 [P] [US5] Create `.github/workflows/anthropometry-eval.yml` cloned from `.github/workflows/race-eval.yml`, blocking at composite ≥ 0.75.

### Wave 2 backend tests

- [ ] T050 [P] [US1] Write `backend/tests/anthro/test_context.py`: allow-list enforcement, the 26-week/8-week velocity rules, the 16-point compaction to yearly checkpoints, corroboration logic, and the first-measurement/no-previous-analysis edge cases.
- [ ] T051 [P] [US1] Write `backend/tests/anthro/test_prechecks.py`: one test per rule R01–R12, asserting blocking vs confidence-lowering behaviour and the 10 % word-budget tolerance.
- [ ] T052 [P] [US1] Write `backend/tests/anthro/test_analyst.py` and `backend/tests/anthro/test_critic.py` using `GenericFakeChatModel`: tolerant JSON extraction, one retry, verdict parsing, the single bounded revision, and critic timeout → `skipped` with confidence lowered.
- [ ] T053 [US1] Write `backend/tests/anthro/test_pipeline.py`: happy path, analyst failure → fallback, critic timeout → `skipped`, precheck block → fallback, and family blocked; assert `schema_version="v2"` and `structured_json` always populated including for fallback rows.
- [ ] T054 [P] [US1] Write `backend/tests/anthro/test_privacy_seam.py` with `hypothesis`: forbidden names from the club list never appear in the rendered prompt; the context never carries z-scores, percentiles, raw band values or absolute dates.
- [ ] T055 [US3] Extend `backend/tests/test_ai_record_router.py` and `backend/tests/test_ai_router.py`: denied paths on the new path (parent → 403, no consent → 451, `AI_ENABLED=false` → 503), the `audience` parameter, v1/v2/corrupt-JSON response shapes, and a parent whose child has only flagged analyses seeing the shared "not yet available" state (FR-016, SC-004).
- [ ] T056 [P] [US1] Write `backend/tests/mysql/test_ai_explanation_columns.py` marked `mysql`: the nine columns round-trip and the `on_duplicate_key_update` upsert overwrites all nine.
- [ ] T057 [US1] Run the `data-privacy-guard` audit over the widened context (`anthro/context.py`, `context_builders.py`), the golden dataset `backend/evals/anthropometry_analyst/` and the trace allow-list; record findings and fix before the wave gate (mandatory quality gate).

### Wave 2 frontend

- [ ] T058 [P] [US1] Extend `frontend/src/schemas/ai.schemas.ts` with the Zod discriminated union on `schema_version` (default `"v1"`) mirroring `AnthropometryInsightV1`, and update `frontend/src/types/ai.types.ts`.
- [ ] T059 [P] [US1] Create `frontend/src/lib/ai/pendingMessage.ts` — the shared escalating cold-start copy used by both AI cards, in español neutro with diacritics.
- [ ] T060 [US1] Create `frontend/src/components/ai/StructuredInsight.tsx`: summary line and warning signs visible; "qué significa" and "próximas 2–4 semanas" behind a "Ver análisis completo" expander with `aria-expanded`/`aria-controls`; confidence with its reason and the data-gaps list (FR-026).
- [ ] T061 [US1] Update `frontend/src/components/ai/AIGeneratedContent.tsx`: family provenance "Generado por el asistente de IA del club" with the generation date and no model slug, coach technical-details disclosure (model, prompt version, trace reference), disclaimer on the neutral informational token, and a ≥48 px "Copiar" control (FR-029, FR-030, FR-031).
- [ ] T062 [US1] Update `frontend/src/components/ai/AnthropometricRecordExplanationCard.tsx`: render v2 collapsed via `StructuredInsight`, keep v1 prose rows rendering exactly as before, add the "Con observaciones" marker, the stale chip, `AIBudgetHint` above the generate control, and the shared passive empty message (FR-026, FR-032, FR-033).
- [ ] T063 [P] [US1] Update `frontend/src/components/ai/PHVExplanationCard.tsx`: heading in the success state (G-16), ≥48 px "Regenerar análisis", `AIBudgetHint`, and the same shared empty message.
- [ ] T064 [P] [US1] Write vitest suites for `StructuredInsight`, the v1/v2/corrupt-JSON branches of `AnthropometricRecordExplanationCard` and the discriminated union in `ai.schemas.ts`, with MSW fixtures; add jest-axe zero-violation assertions on both cards.
- [ ] T065 [US1] Run the Wave 2 exit gate: `pytest -m golden -k anthropometry` ≥ 0.75, `pytest -m mysql`, default `pytest`, `ruff check`, `npm run build`, `npm test`.

**Checkpoint**: the structured analysis is generated, reviewed, persisted with accounting and rendered; families are safe. W3 may start.

---

## Phase 4: Wave 3 — US4 (P2), US6 (P3), US2 (bridged use cases)

**Goal**: The Crecimiento tab tells the coach whether the latest analysis is current; the dialog moves to the shared primitive; the five bridged use cases are verified under both switch values; the coach sees this stack's spend.

**Independent test criteria**: The growth summary carries `latest_ai_analysis` (consent-gated, server-computed `is_stale`, no extra round trip); the tab renders the summary line and the history rows carry the warning marker; every existing test of the five bridged use cases passes with `AI_USE_LANGCHAIN` in either position.

**Owns** (`plan.md` W3): `backend/app/routers/growth.py`, `backend/app/schemas/growth.py`, `backend/app/dependencies.py`, the 041 spend module; `backend/tests/test_growth_summary_latest_analysis.py`; frontend `types/growth.types.ts`, `api/ai.ts`, `hooks/ai/*`, `components/athletes/AnthropometryHistory.tsx`, `components/athletes/growth/GrowthTab.tsx`, `components/athletes/growth/LatestAnalysisLine.tsx`, `e2e/growth-analysis.spec.ts`.

### Backend

- [ ] T066 [US4] Add `LatestAiAnalysis` and `GrowthSummaryOut.latest_ai_analysis` to `backend/app/schemas/growth.py` per `contracts/growth-summary-latest-analysis.md` and `data-model.md` §4: measurement, generation time, version, summary line, verdict, warning-sign presence, `is_stale`.
- [ ] T067 [US4] Populate `latest_ai_analysis` in `backend/app/routers/growth.py` from the family-audience per-measurement row: one extra indexed lookup on `athlete_ai_explanations` (no N+1), consent-gated, non-fatal on error, with `is_stale` computed server-side (newer measurement recorded, or the analysed measurement corrected after generation).
- [ ] T068 [P] [US2] Update `backend/app/dependencies.py` so `get_llm_provider` honours `AI_USE_LANGCHAIN` for the session assistant, and verify `backend/app/routers/monthly_reports.py` and `backend/app/routers/athlete_monthly_newsletters.py` need no change because the switch lives in the factory.
- [ ] T069 [US2] Extend the per-coach spend view (041 module) to include this stack's rows from `athlete_ai_explanations` with a `stack="app"` label, kept separate from the race spend and never counted against `RACE_AI_BUDGET_USD_30D` (FR-022, FR-023).
- [ ] T070 [P] [US4] Write `backend/tests/test_growth_summary_latest_analysis.py`: null conditions (no analysis, flagged-only for a parent, consent denied → the field is absent, never an error), both staleness triggers, the coach/parent visibility split, and that no additional query fires per athlete.
- [ ] T071 [US2] Write the switch-matrix test asserting every existing test of the five bridged use cases (session clarify, session draft, monthly report, report blocks, newsletter v2) passes under both values of `AI_USE_LANGCHAIN`, and that fake-model inputs produce byte-identical outputs across transports (SC-006).

### Frontend

- [ ] T072 [P] [US4] Extend `frontend/src/types/growth.types.ts` with `LatestAiAnalysis` and update `frontend/src/api/ai.ts` plus `frontend/src/hooks/ai/*` for the `audience` parameter and the v2 payload.
- [ ] T073 [US4] Create `frontend/src/components/athletes/growth/LatestAnalysisLine.tsx` with all seven states: not-rendered, loading, none, current, stale, flagged, error — coach mode showing "Desactualizado" with the previous summary muted, family mode omitting the generate action, the "Desactualizado" wording and the link when there is nothing to open (FR-027).
- [ ] T074 [US4] Render `LatestAnalysisLine` above the measurement history in `frontend/src/components/athletes/growth/GrowthTab.tsx` for both coach and family mode, with the link that opens that measurement's dialog.
- [ ] T075 [US6] Migrate the modal in `frontend/src/components/athletes/AnthropometryHistory.tsx` to the shared `Dialog` primitive (focus trap, Escape, focus returned to the trigger, ≥48 px close control) and add the "Con señal para revisar" row marker on desktop and mobile rows (FR-028, FR-031).
- [ ] T076 [P] [US6] Write vitest + jest-axe suites for `LatestAnalysisLine` (all seven states), `GrowthTab` and the migrated dialog (focus trap and Escape), asserting zero accessibility violations.
- [ ] T077 [US4] Write `frontend/e2e/growth-analysis.spec.ts`: generate → render → reopen from cache, in coach mode.
- [ ] T078 [US2] Run the Wave 3 exit gate: default `pytest` (both switch values), `ruff check`, `pytest -m golden -k race` re-run clean (last shared-factory checkpoint), `npm run build`, `npm test`, `npm run test:e2e`.

**Checkpoint**: the feature is functionally complete and verified end to end.

---

## Phase 5: Wave 4 — Polish, Documentation and Cross-Cutting Concerns

**Purpose**: Make the shipped behaviour findable and operable. Docs only — no code.

- [ ] T079 [P] Add the subsection "Interpreting maturity-offset estimates" (uncertainty and safeguards) plus a references list with author, year and source to `docs/01-marco-teorico.md` §1 (FR-036).
- [ ] T080 [P] Write `docs/20-traceable-growth-ai/design.md`: the five-step pipeline, the state machine, the nine columns, the transport adapter and the shared factory.
- [ ] T081 [P] Write `docs/20-traceable-growth-ai/qa.md`: the eleven quickstart scenarios as executed, the golden-eval results, and the moderated SC-005 check recorded the way feature 041's SC-002 was.
- [ ] T082 [P] Write `docs/20-traceable-growth-ai/runbook.md`: enabling local Langfuse, reading a trace, the fallback and `skipped` signals, and how to roll the prompt version back.
- [ ] T083 Update `docs/10-race-results/runbook-ops.md` §8/§9: the seven traced entry points, the `LANGFUSE_STRUCTURAL_METADATA` switch (restating that it does not change the no-retention-policy story for local trace data), and the purge cadence.
- [ ] T084 [P] Update `docs/implementation-status.md` (per-module step table for 042) and `docs/technical-notes.md` (dated changelog entry).
- [ ] T085 Update `CLAUDE.md`: correct the Alembic head to the new 042 revision, document the six new env vars, and add the anthro-pipeline paragraph.
- [ ] T086 [P] Add the new variable **names only** (never values) to `backend/.env.example`.
- [ ] T087 Final verification pass: `ruff check`, default `pytest`, `pytest -m mysql`, `pytest -m golden`, `npm run build`, `npm test`, `npm run test:e2e`, and confirm `alembic heads` shows one head.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** → blocks everything.
- **Phase 2 (W1)** → blocks W2 and W3: both consume `app/services/llm/` and the adapter.
- **Phase 3 (W2)** → blocks W3: the `v1|v2` schema union, `LatestAiAnalysis` and the nine columns come from W2.
- **Phase 4 (W3)** → blocks W4 only in the sense that docs describe shipped behaviour.
- **Phase 5 (W4)** → last.

### Story dependencies

- **US2** (traceability) is the foundation — W1 — and is completed by T068–T071 in W3.
- **US1** (structured reading) depends on US2's transport; it is the bulk of W2.
- **US3** (family safety) depends on US1's pipeline (T036 gates on the verdict).
- **US5** (golden eval) depends on US1's prompts and schema.
- **US4** (tab currency) depends on US1's persisted verdict and warning signs.
- **US6** (touch, focus, colour) is split: the config half lands in W1 (T006, T007), the UI half in W3 (T075, T076).

### Parallel opportunities

- **Phase 1**: T002, T003, T004 together.
- **W1**: T009, T010 after T008; T015, T016 together; the three test files T021, T022, T023 together.
- **W2**: T029, T030, T032 together; T035 alongside T034; the eval trio T044, T045, T049 together; the test files T050, T051, T052, T054, T056 together; frontend T058, T059 together and T063 alongside T062.
- **W3**: T068, T070, T072 together; T076 alongside T077.
- **W4**: T079, T080, T081, T082, T084, T086 all together.

---

## Implementation Strategy

**MVP scope**: Phase 1 + Phase 2 (W1) + Phase 3 (W2). At that point the coach gets the structured, reviewed, traced and accounted analysis in the dialog, families are protected, and the golden eval guards changes — US1, US2, US3 and US5 are all delivered. W3 (the tab line and the dialog migration) and W4 (docs) are increments on top.

**Incremental delivery**: each wave's exit gate is cumulative — re-run the previous waves' gates before declaring a wave done. The race golden eval runs at the end of W1 **and** again at the end of W3, the last point where a shared-factory regression could surface.

**Constraints that hold across every task**: minors' privacy (no identifying data in logs, fixtures, prompts or traces), secrets never echoed into the transcript, product copy in español neutro with full diacritics, this planning corpus in English, a single Alembic head, and no new runtime dependency.
