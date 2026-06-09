# Tasks: AI Race Analysis in the Competitions Module — Restore Access and Enhance Insights

**Input**: Design documents from `/specs/010-competitions-ai-insights/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE; every endpoint/component ships with tests.

**Organization**: Tasks grouped by user story (US1–US5 from spec.md) for independent implementation and testing.

## Phase 1: Setup

*No project initialization needed — existing backend/frontend. Single guard task.*

- [X] T001 Verify local harness: `cd backend && pytest -q` collects, and `cd frontend && npx vitest run --reporter=basic --passWithNoTests src/components/competitions` runs; record baseline failures (if any) in specs/010-competitions-ai-insights/notes.md

## Phase 2: Foundational (blocking prerequisites)

- [X] T002 Add API schemas to backend/app/schemas/race_ai.py: `GroupRunLaunchRequest`, `GroupRunItem` (outcome enum `started|backpressure|budget_exceeded|already_running|no_results|error`), `GroupRunLaunchResponse`, `RaceEventRunItem`, `RaceEventRunsResponse`, `ChatRequest.race_event_id: int | None = None`, and `ProgressionAssessment` str-enum (`improving|stable|declining|mixed|first_reference`) per data-model.md
- [X] T003 Create group-launch service backend/app/services/race/group_launch.py: `resolve_event_scope(db, race_event_id)` → (season, valida_num) with 404/422 semantics; `resolve_group_members(db, race_event_id, athlete_ids)` (distinct club athletes with non-deleted results); `launch_group(db, ...)` fan-out via existing `submit_run()` catching `RunBackpressureError` per athlete and skipping `already_running` (active run for same athlete/season/valida); `list_event_runs(db, race_event_id, active_only)` reusing the event→runs resolution pattern from run_staleness — see contracts/race-event-runs.md
- [X] T004 [P] Mirror TS types in frontend/src/types/raceAnalysis.types.ts: `GroupRunLaunchRequest/Response`, `GroupRunItem`, `RaceEventRunsResponse`, `ChatRequestBody.race_event_id?: number | null`

**Checkpoint**: schemas + service importable; nothing user-visible yet.

## Phase 3: User Story 1 — Group launch from the Insights tab (P1) 🎯 MVP

**Goal**: Coach launches one AI analysis covering all club athletes of a válida from the competition's Insights tab; HITL preserved; progress survives refresh.
**Independent test**: quickstart.md §1 — import results, launch from Insights tab, approve HITL, insights appear; refresh restores progress; no-results event disables button; parent sees nothing.

- [X] T005 [US1] Add `POST /api/race-analysis/race-events/{race_event_id}/runs` to backend/app/routers/race_analysis.py: `require_role([coach, admin])`, `AI_ENABLED` gate, upfront `check_budget()` → 503, delegate to group_launch.launch_group, error mapping per contracts/race-event-runs.md (200 partial, 422 no results, 429 zero-start, 404)
- [X] T006 [US1] Add `GET /api/race-analysis/race-events/{race_event_id}/runs?active_only=` to backend/app/routers/race_analysis.py returning `RaceEventRunsResponse` (active states `running|awaiting_hitl`; `active_only=false` adds last-7-days terminal runs)
- [X] T007 [P] [US1] Backend tests in backend/tests/routers/test_race_event_runs.py (pattern: httpx.AsyncClient + aiosqlite + fake_db + set_graph_factory stub): happy fan-out, partial backpressure items, budget 503, no-results 422, unknown event 404, parent 403 / anon 401, `athlete_ids` subset retry, `already_running` skip, GET recovery list
- [X] T008 [US1] Frontend API clients in frontend/src/api/raceAnalysis.ts: `launchGroupAnalysis(raceEventId, body)`, `getRaceEventRuns(raceEventId, opts)` typed per T004
- [X] T009 [US1] Hook frontend/src/hooks/ai/useGroupAnalysis.ts: launch mutation + recovery query (key `["race-analysis","event-runs",raceEventId]`) + aggregation over per-run `useRunStatus`; derived group state (`en progreso|parcial|completado|listo`); invalidate `["club-insights-by-race", raceEventId]` on run completion; retry-failed via `athlete_ids` subset
- [X] T010 [US1] Components frontend/src/components/competitions/insights/GroupAnalysisPanel.tsx and GroupRunRow.tsx: launch button ("Analizar con IA"; disabled + tooltip "La competencia no tiene resultados importados." when `!hasResults`; in-progress state blocks duplicate launch), per-athlete state chips, HITL approval surfacing via existing `useApproveStep` + approval card pattern from athlete profile, "Reintentar pendientes/fallidos" action, es-CO error copy per quickstart.md inventory
- [X] T011 [US1] Mount GroupAnalysisPanel in frontend/src/components/competitions/tabs/InsightsTab.tsx (coach/admin only via `useAuthStore` role check; pass `hasResults` from CompetitionDetailPage props)
- [X] T012 [P] [US1] Vitest suites frontend/src/components/competitions/insights/__tests__/GroupAnalysisPanel.test.tsx and updated tabs/__tests__/InsightsTab.test.tsx: launch flow, disabled no-results, parent hidden, partial outcomes rendering, retry, refresh-recovery (mock `getRaceEventRuns`)

**Checkpoint**: US1 fully functional and testable on its own — this is the MVP.

## Phase 4: User Story 2 — Season-aware richer insights (P2)

**Goal**: Each insight carries season comparatives (prior válidas), an explicit progression assessment, and a development-framed narrative; no fabricated comparisons for first-reference athletes.
**Independent test**: quickstart.md §2 — run analysis for a ≥2-válida athlete vs a 1-válida athlete and inspect insight content.

- [X] T013 [US2] Compute season context in backend/app/services/race/ai/nodes/compute_metrics.py: build `season_comparative: list[SeasonComparativeEntry]` (per prior válida: valida_num, event_label, position, race_time_ms, field_size, delta_position, delta_time_ms — computed in Python from `full_season_results`) and derive `progression_assessment` per data-model.md rule; verify backend/app/services/race/ai/nodes/load_race_data.py loads prior-válida rows for the season (extend query if it filters to requested válidas only)
- [X] T014 [US2] Inject into LLM input: extend `AnalysisInput` (backend/app/services/race/schemas) with `season_comparative` + `progression_assessment`; update backend/app/services/race/agents/analyst.py input construction; update prompt template race_analyst_v2.md (backend/app/services/race/prompts/): add "Contexto de temporada" section, demand explicit progression statement, hard rule: when `first_reference`, state "primera referencia de la temporada" and NEVER compare; keep alignment with club principles (fun first, skills > fitness, bio age)
- [X] T015 [US2] Persist enrichment: include `season_comparative` + `progression_assessment` keys in `metrics_snapshot_json` and a "Contexto de temporada" section in `summary_text` via backend/app/services/race/ai/nodes/persist_insight.py and render_outputs (additive — old insights without keys must keep rendering, FR-013)
- [X] T016 [P] [US2] Unit tests backend/tests/services/test_compute_metrics_season.py: comparative deltas correctness, assessment derivation matrix (improving/declining/stable/mixed), single-válida → `first_reference` with empty comparatives, missing times handled (DNF/minus_laps)
- [X] T017 [US2] Frontend rendering: surface season-context section + progression label in insight cards/detail (frontend/src/components/competitions/tabs/InsightsTab.tsx excerpt handling and frontend/src/lib/insights.ts `extractSection`/`getV2Preview` extension); graceful absence for pre-feature insights
- [X] T018 [P] [US2] Vitest test for season-context rendering and legacy-insight fallback in frontend/src/lib/__tests__/insights.test.ts (or extend existing suite)

**Checkpoint**: US1 + US2 = restored access with enriched output.

## Phase 5: User Story 3 — Post-import launch offer (P3)

**Goal**: After committing a results import, the coach can launch the group analysis in one click.
**Independent test**: quickstart.md §3.

- [X] T019 [US3] Add "Analizar con IA ahora" to the post-commit success panel in frontend/src/components/competitions/import/ImportWizard.tsx (next to "Ver resultados de la válida", coach-gated): calls `launchGroupAnalysis(commitMutation.data.race_event_id)` then navigates to `/competitions/{id}?tab=insights`; declining (not clicking) has zero side effects; budget/backpressure errors surfaced with es-CO copy
- [X] T020 [P] [US3] Vitest test in frontend/src/components/competitions/import/__tests__/ImportWizard.postimport.test.tsx: offer rendered on success, launch + navigate on accept, nothing on decline, error copy on 503

**Checkpoint**: import→insights single flow complete.

## Phase 6: User Story 4 — Per-athlete launch in the competition results list (P4)

**Goal**: Launch/re-launch one athlete's analysis from the results row.
**Independent test**: quickstart.md §4.

- [X] T021 [US4] Add coach-gated row action in frontend/src/components/competitions/results/ResultsTable.tsx for rows with `is_our_club && athlete_id != null`: "Analizar con IA" → `startAthleteRun(athleteId, {season, valida_nums:[event.sequence_number]})` (season/valida passed down from CompetitionDetailPage/ResultsTab props); when a fresh insight exists for that terna (from `useClubInsightsByRace`, `stale_run_id == null`) open `ConfirmModal` "Ya existe un análisis para este deportista. ¿Re-ejecutar?" before launching; show run started feedback linking to Insights tab
- [X] T022 [P] [US4] Vitest test frontend/src/components/competitions/results/__tests__/ResultsTableLaunch.test.tsx: action visibility rules (role, club, linked athlete), confirm-on-fresh, direct launch when none/stale

**Checkpoint**: correction loop covered without leaving the competition.

## Phase 7: User Story 5 — Competition-scoped AI chat (P5)

**Goal**: Coach asks follow-up questions grounded on the válida from inside the module.
**Independent test**: quickstart.md §5.

- [X] T023 [US5] Backend chat scoping: accept `race_event_id` in `ChatRequest` (schema done in T002); in backend/app/services/race/agents/chat.py (and its RAG/tools), filter insight + results retrieval by event and seed session with event label; 404 on unknown event; combinable with `athlete_id` — per contracts/chat-event-scope.md
- [X] T024 [P] [US5] Backend tests in backend/tests/routers/test_race_analysis.py: chat with `race_event_id` (scoped tools called), without (legacy behavior unchanged), unknown event 404, parent 403
- [X] T025 [US5] Component frontend/src/components/competitions/chat/CompetitionChatPanel.tsx: per-competition uuid-v4 `session_id`, `chatTurn()` with `race_event_id`, local `ChatMessage[]` rendering with citations/tools badges, loading/error states, unavailable state copy "El asistente de IA no está disponible en este momento."; mount it in the competition Insights tab (collapsible section) coach/admin-only
- [X] T026 [P] [US5] Vitest test frontend/src/components/competitions/chat/__tests__/CompetitionChatPanel.test.tsx: turn round-trip, session_id stability, unavailable state, role gating

## Phase 8: Polish & Cross-Cutting

- [X] T027 Privacy audit of prompt/persistence changes (anonymizer untouched, no minor PII in `season_comparative`/logs, `AI_LOG_PROMPTS` paths) — run as data-privacy-guard agent review; record outcome in specs/010-competitions-ai-insights/notes.md
- [X] T028 Full quality gates: `cd backend && ruff check . && pytest -q` and `cd frontend && npx eslint src --max-warnings=0 || npx eslint src; npx tsc --noEmit && npx vitest run` — all green (Constitution I & II)
- [X] T029 [P] Docs: add feature row to CLAUDE.md Implementation status table and entry in docs/implementation-status.md; update "Active Spec Kit feature" section to 010

## Dependencies

```
Phase 2 (T002–T004) ← blocks all stories
US1 (T005–T012): T005,T006 ← T002,T003; T008 ← T004; T009 ← T008; T010 ← T009; T011 ← T010; tests T007/T012 parallel to FE/BE counterparts
US2 (T013–T018): independent of US1 (graph-side); T014 ← T013; T015 ← T014; T017 ← T015
US3 (T019–T020): ← US1 (uses launchGroupAnalysis from T008)
US4 (T021–T022): ← Phase 2 only (uses existing startAthleteRun); independent of US1
US5 (T023–T026): T023 ← T002; T025 ← T023 (for real round-trip) but component buildable in parallel with mocks
Phase 8 ← all stories
```

## Parallel execution examples

- After Phase 2: **US1 backend (T005–T007)** ∥ **US1 frontend types/hook scaffolding (T008–T009 with mocked API)** ∥ **US2 backend (T013–T016)** ∥ **US5 backend (T023–T024)**
- Test tasks marked [P] run alongside their implementation pair (different files).
- US3/US4 frontend tasks parallelize once T008 lands.

## Implementation strategy

MVP = Phase 1 + 2 + US1 (T001–T012): restores the missing capability end-to-end. Then US2 (the enrichment), then US3/US4/US5 in any order (US3 after US1). Each checkpoint is independently demoable per quickstart.md.
