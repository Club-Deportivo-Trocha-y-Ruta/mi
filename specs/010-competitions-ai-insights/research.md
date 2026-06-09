# Research: AI Race Analysis in the Competitions Module (010)

**Date**: 2026-06-09 | **Inputs**: spec.md, backend + frontend codebase exploration (agent team)

## R1 — How to launch a "whole competition" analysis when runs are athlete-scoped

**Decision**: Add a coach-only group-launch endpoint `POST /api/race-analysis/race-events/{race_event_id}/runs` that resolves all club athletes with committed results in the event (via `race_results.athlete_id IS NOT NULL`, `deleted_at IS NULL`), derives `season` (from `race_series.season_year`) and `valida_num` (from `race_events.sequence_number`), and starts one standard run per athlete through the existing `submit_run()` path. The response reports per-athlete outcomes (`run_id` or a typed error: `budget_exceeded`, `backpressure`, `already_running`, `no_results`). A companion `GET /api/race-analysis/race-events/{race_event_id}/runs` lists active/recent runs for the event so the UI can recover progress after a refresh (FR-012).

**Rationale**: `StartRunRequest` is `(athlete_id, season, valida_nums, explain_mode)` — `backend/app/routers/race_analysis.py:536`. Reusing `submit_run()` keeps every existing safeguard (budget guard `check_budget()`, `BoundedSemaphore(10)` backpressure, HITL gate, anonymizer) without duplication, and per-athlete fan-out gives FR-011 partial-failure semantics for free. No new table is required: `agent_runs.input_json` already carries `(athlete_id, season, valida_nums)`, and `run_staleness.invalidate_runs_for_event()` already proves event→runs resolution is possible with existing data.

**Alternatives considered**:
- *Frontend loops `startAthleteRun` per athlete*: rejected — N HTTP round-trips, no atomic budget pre-check, partial-failure bookkeeping pushed to the client, no refresh recovery.
- *New "group run" entity/table*: rejected — adds a migration and lifecycle for what is derivable from existing `agent_runs`; violates the constitution's simplicity bias.
- *One mega-run analyzing all athletes in a single graph execution*: rejected — breaks anonymization mapping (one pseudonym per run), HITL granularity, and per-athlete insight versioning (`UNIQUE (athlete_id, season, valida_num) WHERE is_active=1`).

## R2 — Concurrency: group size vs. the 10-run semaphore

**Decision**: The group endpoint starts runs up to the available semaphore capacity and returns the rest as `backpressure` entries; the frontend offers "Reintentar pendientes" which re-invokes the group endpoint with `athlete_ids` filter (the endpoint accepts an optional `athlete_ids: list[int]` to retry a subset — also used by FR-011 failed-only retry).

**Rationale**: `MAX_CONCURRENT_RUNS = 10` (`backend/app/services/race/ai/runner.py:43`) is module-global. A 15-athlete squad cannot start atomically; surfacing the overflow as typed per-athlete results matches the existing 429 contract instead of inventing a queue.

**Alternatives considered**: server-side queueing of overflow runs — rejected (new persistent state, Render free tier has no worker; existing semantics are "try again shortly").

## R3 — Where season comparatives and progression live

**Decision**: Enrich the existing graph, not a new one. `load_race_data` already loads `full_season_results`; `compute_metrics` already produces `progression` records. Add: (a) a `season_comparative` block in `compute_metrics` output — per prior válida: position, time, field size, delta vs. analyzed válida — plus a derived `progression_assessment` enum (`improving | stable | declining | mixed | first_reference`); (b) extend `AnalysisInput` and the `race_analyst_v2` prompt template with this block and explicit instructions to (i) state progression direction, (ii) never fabricate comparisons when `first_reference`; (c) extend `AnalysisOutput`/persisted `summary_text` sections so the InsightsTab/athlete views render the season context.

**Rationale**: All the data is already loaded per run (`backend/app/services/race/ai/nodes/` — `load_race_data`, `compute_metrics`, `analyst_agent`); the gap is purely that comparatives are not computed into the prompt input nor demanded by the prompt. Computing deltas in Python (not asking the LLM to do arithmetic) keeps outputs trustworthy.

**Alternatives considered**: separate "season insight" run type (`valida_num=0` aggregate) — rejected for this feature; the spec asks for season context *inside* each válida's insight, and the `0` sentinel already serves a different use case.

## R4 — Competition-scoped chat

**Decision**: Extend `ChatRequest` with optional `race_event_id: int | None` (additive, backward compatible). `RaceChatAgent` tools gain event scoping: when present, the results/insights tools filter by that event, and the session seed mentions the event label. Frontend gets a new `CompetitionChatPanel` (no chat UI exists today) generating a `session_id` per competition (`uuid v4`, kept in component state), calling the existing `chatTurn()` client.

**Rationale**: `ChatRequest` is `(session_id, query, athlete_id?)` — `race_analysis.py:1119`; sessions are in-memory with 1h TTL, so per-competition session scoping is free. `chatTurn()` already exists in `frontend/src/api/raceAnalysis.ts` typed and unused by any UI.

**Alternatives considered**: reuse athlete-scoped chat with no event context — rejected, answers couldn't ground on "this válida"; building chat history persistence — out of scope (existing in-memory model retained).

## R5 — Per-athlete launch from the competition results list

**Decision**: Add a row action (visible for coach/admin on rows where `is_our_club && athlete_id != null`) in `ResultsTable.tsx` that calls the existing `startAthleteRun(athleteId, {season, valida_nums: [event.sequence_number]})`. A fresh-insight check (insight exists for that `(athlete, season, valida_num)` and not stale) drives the `ConfirmModal` re-run confirmation (FR-005).

**Rationale**: `startAthleteRun` (`frontend/src/api/athleteRaceAnalysis.ts`) plus `useRunStatus` polling already implement the whole lifecycle; only the entry point and the derived `(season, valida)` are new. Freshness is already answerable from `useClubInsightsByRace` data (`stale_run_id == null`).

## R6 — Post-import offer placement

**Decision**: In `ImportWizard.tsx` post-commit success panel (after the summary, beside "Ver resultados de la válida"), add "Analizar con IA ahora" which calls the group endpoint with `commitMutation.data.race_event_id` and navigates to `/competitions/{id}?tab=insights` where the group progress panel takes over. Declining = simply not clicking; zero side effects (FR-004).

**Rationale**: `ImportCommitResponse.race_event_id` is already returned (`backend/app/routers/race_imports.py:906`); the success panel already links to the competition detail.

## R7 — Group progress UI and refresh recovery

**Decision**: New `GroupAnalysisPanel` in the InsightsTab: launch button (disabled when `!hasResults`, with Spanish tooltip), per-athlete run list with state chips, HITL approval surfacing (reusing the existing `useRunStatus`/`useApproveStep` hooks and the athlete-profile HITL approval card pattern), retry-failed action. On mount it calls `GET .../race-events/{id}/runs` to rehydrate in-progress runs (survives refresh, prevents duplicate launches — FR-012). While any run for the event is `running|awaiting_hitl`, the launch button shows in-progress state.

**Rationale**: All polling/HITL machinery exists in `frontend/src/hooks/ai/useRaceRun.ts` (`useRunStatus` 2s polling with 304/ETag, `useApproveStep`); the panel is composition, not new protocol.

## R8 — Safeguards and error copy

**Decision**: No changes to guards. New endpoints call `check_budget()` and rely on `submit_run()` backpressure; group endpoint maps `BudgetExceededError → 503` and per-athlete `RunBackpressureError → typed entry` (global 429 only when *zero* runs could start). Frontend maps: 503 → "Presupuesto mensual de IA agotado…", 429/backpressure entries → "Límite de análisis simultáneos…", `AI_ENABLED=false` (503 from existing flag check) → "El asistente de IA no está disponible". All copy es-CO inline strings per project convention.

## R9 — Testing strategy

**Decision**: Backend: extend `backend/tests/routers/test_race_analysis.py` patterns (httpx.AsyncClient + aiosqlite, `fake_db` seed helpers, `set_graph_factory` stub graph) with a new `test_race_event_runs.py` covering group launch (happy, partial backpressure, budget 503, RBAC 401/403, no-results 422, retry subset) and chat event-scoping; unit tests for `season_comparative`/`progression_assessment` in `compute_metrics`. Frontend: vitest + Testing Library for `GroupAnalysisPanel`, ResultsTable row action, ImportWizard offer, `CompetitionChatPanel`, mocking hooks per existing `InsightsTab.test.tsx` pattern.

**Rationale**: Constitution Principle II (Testing NON-NEGOTIABLE); these patterns/fixtures already exist and are listed in the research reports.

## R10 — Out-of-scope confirmations

- AI provider/model unchanged: `build_chat_llm()` (Gemini via LangChain) untouched; no `services/ai` factory refactor in this feature (deferred Fable 5 work).
- No Alembic migration: all data needs are served by existing tables (`agent_runs`, `agent_run_events`, `athlete_ai_insights`, `race_results`, `race_events`, `race_series`).
- No changes to PDF import/parse behavior; the offer hooks in *after* commit.
