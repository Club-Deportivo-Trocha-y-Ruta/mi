---
description: "Task list — feature 045 Competitions in one place"
---

# Tasks: Competitions in one place

**Input**: Design documents from `specs/045-competitions-one-place/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**:
- Phases 0 and 0b are already in the working tree (spec Context, research R-05).
- Work on `main` with no branch. Skip auto-commit hooks.
- Another session owns `.specify/feature.json` (feature 046). Run Spec Kit scripts with `SPECIFY_FEATURE_DIRECTORY=specs/045-competitions-one-place`.

**Tests**: tests are mandatory (constitution II, NON-NEGOTIABLE).
- Every bug fix gets a regression test that fails first.
- Every router change gets a denied-path test.
- Page- and dialog-level components get jest-axe.

**Organization**: phases follow the five delivery waves of plan.md, and each task carries its user-story label. A gate task closes each wave. Tasks marked [P] inside a phase touch disjoint files.

**Shared-tree rules for every agent**:
- **Git**: never `git stash/clean/checkout/restore/reset/add/commit`. Use `git worktree add /tmp/wt-… HEAD` to compare with HEAD.
- **Frontend edits**: another session is migrating design tokens in `frontend/`, so re-read each file right before editing and make targeted edits only.
- **Do not touch**: `backend/app/database.py`, `backend/tests/test_database_pre_ping.py`, `backend/scripts/*`.
- **Databases**: tests that need MySQL use the local test DB, `MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test` (created 2026-09-23 and migrated to head). Never use the dev DB `trocha_ruta` and never production.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (shared)

- [ ] T001 Run `alembic heads` in `backend/` and confirm exactly one head (`b4e8d2f61a93` on 2026-09-23). Record the result in `specs/045-competitions-one-place/baseline.md`.
- [ ] T002 Record the pre-existing failures in `specs/045-competitions-one-place/baseline.md` so later gates can tell them apart:
  - `tests/test_langchain_provider.py` (collection ImportError, `ModelError`);
  - `test_invariants_v2.py::test_resolve_age_*`;
  - `frontend/src/routes/training/SessionWizardRouteNotify.test.tsx`.
- [ ] T003 [P] Add a "Local test DB lane" section to `specs/045-competitions-one-place/quickstart.md`:
  - create `trocha_ruta_test` through `docker compose exec mysql` using the container's root env, without echoing secrets;
  - `alembic upgrade head` with `MYSQL_HOST=127.0.0.1 MYSQL_DB=trocha_ruta_test`;
  - run the full `pytest` with the same overrides.

---

## Phase 2: Foundational — W1 engine core (blocks every story)

**Purpose**: `backend/app/services/race/field_metrics.py` becomes the single metrics engine (research R-01..R-04, data-model §1).

- [ ] T004 Write failing-first tests in `backend/tests/services/race/test_field_metrics.py` for the time-based percentile:
  - fastest = 100, slowest = 0;
  - ties get equal values;
  - `t_max == t_min` → `None`;
  - fewer than 5 FINISHED-with-time rows → `None`;
  - a MINUS_LAPS rider → `None` percentile, but counted in `field_size`;
  - DNF/DNS/DSQ → `None`.
- [ ] T005 Write failing-first tests in `backend/tests/services/race/test_field_metrics.py`:
  - for `timed_finishers`;
  - for `gap_to_podium_pct` (official P3 time; `None` when there is no P3 time);
  - showing that `gap_to_median_pct` stays `None` below 5 timed finishers.
- [ ] T006 Implement the time-based percentile in `backend/app/services/race/field_metrics.py`:
  - use `round(100 × (1 − (t − t_min) ÷ (t_max − t_min)))` over FINISHED rows with `race_time_ms`, replacing the position formula (~l.161);
  - apply `MIN_FIELD = 5` inside the engine for percentile and median gap.
- [ ] T007 Add `timed_finishers`, `gap_to_podium_pct` (keep `gap_to_p3_ms`) and a documented MetricSet shape to the output of `compute_field_metrics` in `backend/app/services/race/field_metrics.py`. Update the docstring (inputs, outputs, gates).
- [ ] T008 Add `compute_category_metrics(results, event_id, category_id) -> dict[result_id, MetricSet]` in `backend/app/services/race/field_metrics.py`. It is pure, O(n), and does not query the DB. Share the per-category math with `compute_field_metrics` and test it in `backend/tests/services/race/test_field_metrics.py`.

**Checkpoint**: T004/T005 pass and every existing test in `backend/tests/services/race/test_field_metrics.py` passes, or has an updated expectation because of the percentile change. Document each updated expectation in the test with a comment.

---

## Phase 3: US2 — One number means one thing (P1) · W1 consumers

**Goal**: every surface reads the engine, and parents never receive winner or podium fields.

**Independent Test**: the consistency test (T018) passes, and parent payloads omit the winner and podium fields (T013–T015).

- [ ] T009 [P] [US2] Write a failing-first regression test in `backend/tests/services/race/test_analytics_charts.py`: a 2-rider category exposes `percentile=None` on `EvolutionPoint`. Today it shows a value.
- [ ] T010 [US2] Make `build_evolution` in `backend/app/services/race/analytics_charts.py` take `percentile`, `gap_pct`, `gap_to_median_pct` and `field_size` from `compute_field_metrics`:
  - delete the homegrown formulas (~l.492-514, ~l.563-589) and the separate `cat_size` query (~l.279-280);
  - `EvolutionMetric.PERCENTILE` returns the engine value;
  - update `backend/tests/services/race/test_analytics_charts.py`.
- [ ] T011 [US2] Make `build_distribution` in `backend/app/services/race/analytics_charts.py` take the athlete's percentile from the engine, replacing the count formula (~l.827-831). Update `backend/tests/routers/test_athlete_race_analysis_distribution.py`.
- [ ] T012 [P] [US2] Simplify `backend/app/services/race/history.py` to read `timed_finishers` and the already-gated values from the engine: remove the local counting (~l.180-186) and the re-gating (~l.233-239). Add `gap_to_podium_pct` to the points and update `backend/tests/services/race/test_history.py`.
- [ ] T013 [US2] Write a failing-first test, then implement: the history route in `backend/app/routers/athlete_race_analysis.py` (`get_history`) serializes the parent variant **without** `gap_to_winner_pct` and `gap_to_podium_pct` (excluded, not nulled; data-model §2). Tests go in `backend/tests/routers/test_athlete_race_history.py` and cover coach (present), parent (absent) and another parent's athlete (denied).
- [ ] T014 [US2] Write a failing-first test, then implement: the evolution route in `backend/app/routers/athlete_race_analysis.py` returns 403 when a parent sends `metric=podium_gap_ms` (or any winner or podium metric), and parent points omit `gap_pct`. Tests go in `backend/tests/routers/test_athlete_race_analysis_evolution.py`.
- [ ] T015 [US2] Attach `metrics` per row in `backend/app/services/race/results_read.py` (`get_event_results`) through `compute_category_metrics`, and add the schema to `backend/app/schemas/race_results.py` (`EventResultsRead` rows). The parent variant carries only `field_size`, `timed_finishers`, `position`, `percentile` and `gap_to_median_pct`. Include a query-count test (no per-row queries) and parent/coach tests in `backend/tests/services/race/test_results_read_metrics.py`.
- [ ] T016 [P] [US2] Update the schemas in `backend/app/schemas/athlete_race_analysis.py`: add `HistoryPoint.gap_to_podium_pct` and update the field descriptions for the time-based `percentile` and `field_size` = Parrilla.
- [ ] T017 [US2] Verify that `backend/app/services/race/ai/nodes/compute_metrics.py` (~l.378-385) feeds the analyst from the engine. Update any race-AI test that asserts a position-based percentile (grep `percentile` under `backend/tests/services/race/`). Do not change prompts or golden fixtures (research R-02).
- [ ] T018 [US2] Write the SC-002 consistency test in `backend/tests/services/race/test_metrics_consistency.py`. It uses one category with 6 timed finishers, 1 MINUS_LAPS and 1 DNF. The history, evolution, results-read and analyst-context metrics must be identical per athlete, and every value must be `None` when there are 4 timed finishers.
- [ ] T019 [P] [US2] Update the frontend types and fixtures:
  - `frontend/src/types/raceHistory.types.ts` (`gap_to_podium_pct`);
  - `frontend/src/types/athleteRaceAnalysis.types.ts`;
  - `frontend/src/types/raceResults.types.ts` (row `metrics`, `MetricSet`);
  - the MSW handlers under `frontend/src/test/msw/`.
- [ ] T020 [US2] GATE G1. Run:
  - backend `pytest` (default lane plus the local test DB lane from T003);
  - `ruff check` on the changed backend files;
  - `npm run typecheck`;
  - `npx vitest run`.
  
  Compare the failures with `baseline.md` (T002). Stop if there is any new failure.

---

## Phase 4: W2 — loads, pending work and the family safeguard (backend) · US3, US5, US4

### US3 — Loading is never blocked by unrelated work and never lost (P1)

**Independent Test**: the three gate cases and the resume/discard cases in `contracts/api.md` pass.

- [ ] T021 [US3] Write failing-first tests in `backend/tests/routers/test_race_imports_identity_gate.py`. With the whole-queue gate these fail today:
  - (a) a pending candidate whose keys belong only to another import → commit 200;
  - (b) a candidate spanning this import and another one → 409;
  - (c) a candidate about a brand-new competitor of this import → 409;
  - the same three cases on `commit-pending`.
- [ ] T022 [US3] Add `pending_candidates_for_import(db, import_record_keys) -> list[RaceIdentityCandidate]` in `backend/app/services/race/identity_review.py`. Follow the `remove_out_of_scope` pattern (~l.984-1027) and match `left_record["key"]` or `right_record["key"]` (research R-08). Add a unit test in `backend/tests/services/race/test_identity_review.py`.
- [ ] T023 [US3] Replace `_identity_pending_count` at commit (~l.1223) and commit-pending (~l.1506) in `backend/app/routers/race_imports.py`:
  - build the import's keys with `load_identity_rows` plus `record_key`;
  - on block, return 409 with the body `{"detail": "identity_pending", "pending_for_import": n, "review_path": "/competitions/imports?seccion=identidades&import=<id>"}`;
  - T021 goes green.
- [ ] T024 [US3] Write the Alembic migration `backend/alembic/versions/<rev>_race_import_discarded.py`:
  - `down_revision` = the head recorded in T001;
  - add `discarded` to `race_imports.status`;
  - the downgrade updates `discarded` → `failed`, then drops the value;
  - add `RaceImportStatus.discarded` in `backend/app/models/race_import.py` using `values_callable`, as the other enums do.
- [ ] T025 [US3] Add `GET /api/race-analysis/imports/{import_id}` in `backend/app/routers/race_imports.py`. It returns `{id, status, source_filename, parse_meta, created_at, event_id, season}`, with a new schema in the race-imports schema module. Tests in `backend/tests/routers/test_race_imports.py`: coach 200, parent 403, another club 404.
- [ ] T026 [US3] Add `POST /api/race-analysis/imports/{import_id}/discard` in `backend/app/routers/race_imports.py`:
  - `pending|dry_run` → `discarded` (200); `committed` → 409; `discarded` again → 200; parent → 403;
  - exclude `discarded` from the default in-progress listing;
  - tests in `backend/tests/routers/test_race_imports.py`.

### US5 — Home tells the coach what is pending and takes them there (P2)

**Independent Test**: each count equals the number of items its list returns (SC-005).

- [ ] T027 [P] [US5] Extend `CoachSummaryOut` in `backend/app/schemas/dashboard.py` with `identity_decisions_pending: int | None`, `imports_in_progress: int | None` and `analyses_awaiting_approval: int | None`. Compute them in `backend/app/services/dashboard_summary.py`, following `compute_insights_stale` (~l.122-165):
  - awaiting approval = `AgentRun.status == awaiting_hitl` joined to the club's athletes;
  - `null` on error.
  
  Tests in `backend/tests/routers/test_dashboard_summary.py`: coach, admin, parent denied.
- [ ] T028 [US5] Add `GET /api/race-analysis/pending-analyses?season=&state=awaiting_approval|stale` in `backend/app/routers/race_analysis.py` (contracts/api.md). Its items must match the T027 counts exactly. Tests: coach 200 with an equality assertion against the counts, parent 403, unknown state 422. Never log `athlete_ref`.
- [ ] T029 [US5] Add `POST /api/race-analysis/runs/{run_id}/dismiss-stale` in `backend/app/routers/race_analysis.py`. It wraps `backend/app/services/race/run_staleness.py::mark_run_fresh` and writes an audit event (`action=dismiss_stale`). Tests: 200 (the run leaves the stale list), 409 when not stale, parent 403.

### US4 — Family safeguard, backend part (P2)

- [ ] T030 [P] [US4] Create `backend/app/services/race/family_gap_mentions.py` with `find_family_gap_mentions(text_fields) -> list[str]`. It matches mentions of leader, winner, P1, P3, first or third place and podium (Spanish variants, accent-insensitive) and returns at most 3 snippets of 80 characters or fewer. Add pure tests in `backend/tests/services/race/test_family_gap_mentions.py` with positive, negative and accent cases, using fictitious text only.
- [ ] T031 [US4] Add `family_gap_mentions` to the awaiting-HITL event of `GET /api/race-analysis/runs/{run_id}/status` in `backend/app/routers/race_analysis.py`. It is computed only from the family-visible fields of the draft (list them in the docstring) and is never included for parents. Tests: coach sees the mentions, clean text gives `[]`, parent never receives the field.
- [ ] T032 [US3] GATE G2. Run:
  - the T020 gate commands;
  - `pytest -m mysql` against `trocha_ruta_test` (T024 upgrade and downgrade).
  
  Then send research R-08 and the T021–T023 diff to the `data-platform-lead` agent (Sonnet) to validate points (a) and (b). Record the verdict in `specs/045-competitions-one-place/research.md` §R-08.

---

## Phase 5: W3 — the athlete «Carreras» tab (frontend) · US1, US4

### US1 — The coach reads the whole race story in one tab (P1) 🎯 MVP

**Independent Test**: open `/athletes/:id?tab=races` and see Progresión with every season, the championship cards and median gap selected. `?tab=ai_analysis&insight=<iid>` opens that analysis.

- [ ] T033 [P] [US1] Write failing-first tests in `frontend/src/components/athletes/races/__tests__/CarrerasTab.test.tsx`:
  - it opens on Progresión;
  - only the history request fires on first paint (MSW request log);
  - switching to Análisis IA triggers the insights and runs requests;
  - `view=` syncs with the URL;
  - jest-axe reports zero violations.
- [ ] T034 [P] [US1] Write failing-first tests in `frontend/src/routes/athletes/AthleteDetailPage.test.tsx`:
  - `?tab=ai_analysis` → `?tab=races&view=analisis`;
  - `insight=<iid>` is kept and expands that analysis;
  - there is a single «Carreras» tab and no «Insights IA» tab.
- [ ] T035 [US1] Extend `frontend/src/hooks/race/useAthleteRaceHistory.ts` to accept `seriesKind: "cup" | "championship" | "all"` (default `"cup"` for existing callers).
- [ ] T036 [US1] Extend `frontend/src/components/race/history/HistoryChart.tsx` with a `metric` prop:
  - `gap_to_median_pct` is the default;
  - also `percentile`, `position`, `gap_to_winner_pct` and `gap_to_podium_pct`;
  - reuse `EvolutionChart`'s signed and inverted axis logic;
  - an `audience` prop limits the family to median, percentile and position.
  
  Update the tests in `frontend/src/components/race/history/__tests__/HistoryChart.test.tsx`.
- [ ] T037 [US1] Create `frontend/src/components/athletes/races/ProgressionView.tsx`:
  - `HistoryProgressionCard`-style shell with `seriesKind="all"`;
  - cup points go to `HistoryChart`, and championships to `ChampionshipReadingCard` (audience-aware);
  - a metric selector with a competition-group filter (the 039 comparison groups);
  - `HistoryTable` underneath;
  - loading, empty and error states.
- [ ] T038 [US1] Create `frontend/src/components/athletes/races/AnalysisView.tsx`:
  - in order: pending (`HITLApprovalCard`/`AnalysisRunTimeline`) → latest (`HeroLastInsightCard` with the `PanoramaView` KPI cards in the header) → history (`InsightsTimeline` with `controlledInsightId` from `insight=`) → coach-only `LaunchAnalysisForm`, `AthleteAnalystChatPanel` and `SeasonSummaryButton`;
  - move `useAthleteInsights` and `useAthleteRuns` here from `AthleteAIAnalysisTab.tsx` (~l.196-239).
- [ ] T039 [US1] Create `frontend/src/components/athletes/races/CompareView.tsx` (coach only) with `DistributionChart` + `ComparatorPanel`.
  - Remove the dead `viewMode="parent"` prop in `frontend/src/components/athletes/ai/ComparatorPanel.tsx` (~l.230).
  - Make `ComparatorPanel` read the server points.
  - Delete `frontend/src/lib/raceMetrics.ts` and its tests.
- [ ] T040 [US1] Create `frontend/src/components/athletes/races/CarrerasTab.tsx`:
  - a view switch «Progresión · Análisis IA · Comparar», with one `React.lazy` chunk per view;
  - URL sync for `view` and `insight`;
  - `insight` forces `analisis`;
  - the family gets no Comparar (fallback to `progresion`).
  
  T033 goes green.
- [ ] T041 [US1] In `frontend/src/routes/athletes/AthleteDetailPage.tsx`, replace the `ai_analysis` and `races` tabs with one lazy «Carreras» tab (key `races`) and add the alias parsing for `ai_analysis`. T034 goes green.
- [ ] T042 [US1] Retire the unused pieces:
  - `frontend/src/components/athletes/ai/AthleteAIAnalysisTab.tsx` (delete it if nothing imports it);
  - `EvolutionChart` usage in the athlete tab.
  
  Re-home or update the affected suites in `frontend/src/components/athletes/ai/__tests__/`, and update `aiIdentityRenameSweep.test.ts` deliberately.
- [ ] T043 [US1] Point `frontend/src/routes/RaceInsightEmailRedirect.tsx` to `?tab=races&view=analisis&insight=<iid>` for both roles, and update its test.

### US4 — Family follows their child's races safely, frontend part (P2)

**Independent Test**: as a parent, «Carreras» shows only the family metrics and approved analyses with the AI label; `view=comparar` falls back.

- [ ] T044 [P] [US4] Write failing-first tests in `frontend/src/routes/parents/MyAthleteDetailPage.test.tsx`:
  - there is a single «Carreras» tab;
  - `?tab=ai-analysis` → `?tab=races&view=analisis`;
  - `view=comparar` → Progresión;
  - no «Brecha vs. 1.ª posición» or «Brecha vs. podio» anywhere;
  - the label «Análisis generado con IA y revisado por el entrenador.» is present;
  - jest-axe reports zero violations.
- [ ] T045 [US4] In `frontend/src/routes/parents/MyAthleteDetailPage.tsx`, replace the `ai-analysis` and `races` tabs with a lazy «Carreras» (`CarrerasTab` with `audience="family"`). Parse the `ai-analysis` alias and keep the path from the family home at two taps or fewer (FR-018). T044 goes green.
- [ ] T046 [US1] GATE G3. Run:
  - `npm run typecheck`;
  - `npx vitest run` (compare against `baseline.md`);
  - a bundle check: `npm run build`, and confirm each new lazy chunk is 150 KB gzipped or less.

---

## Phase 6: W4 — the «Competencias» area (frontend) · US6, US3, US5, US2

### US6 — One area, one vocabulary (P3)

- [ ] T047 [P] [US6] In `frontend/src/lib/navigation.ts`, make the area «Competencias» with the items «Competencias» (`/competitions`), «Temporada» (`/competitions/season/:currentYear`) and «Cargas e identidades» (`/competitions/imports`), and remove «Válidas». Test the menu labels.
- [ ] T048 [US6] Add the routes `/competitions/season/:year` and `/competitions/imports` to `frontend/src/App.tsx`, plus the redirects from `contracts/ui-routes.md`:
  - `/competitions/insights/season/:year`;
  - `/competitions/history`;
  - `/competitions/identity-review`;
  - `/competitions/unlinked`.
  
  Add a redirect test file, `frontend/src/routes/__tests__/competitionsRedirects.test.tsx`.
- [ ] T049 [P] [US6] Create `frontend/src/components/competitions/tabs/CircuitAndConditionsTab.tsx`, composing `ConditionsTab` and `race/course/CourseTab`. In `frontend/src/routes/competitions/CompetitionDetailPage.tsx`:
  - use the tab «Circuito y condiciones» (`?tab=circuito`), with `?tab=conditions` as an alias;
  - show «Clasificación» only for cup válidas.
  
  Add tests and jest-axe.
- [ ] T050 [P] [US6] Vocabulary sweep:
  - «Válidas» → «Competencias» in `frontend/src/routes/competitions/UnlinkedCompetitorsPage.tsx` (~l.24), `CompetitionsListPage.tsx` (~l.135) and `SeasonInsightsPage.tsx` (~l.91);
  - «Editar metadata» → «Editar datos» in `frontend/src/components/competitions/import/ImportWizard.tsx` (~l.435, ~l.509), `CompetitionsListPage.tsx` (~l.702) and `CompetitionDetailPage.tsx` (~l.438);
  - update the affected tests.
- [ ] T051 [P] [US6] Replace «Crítico LLM dice» with «Revisión automática» in `frontend/src/components/ai/HITLApprovalCard.tsx` (~l.207), and add `min-h-12` to «Editar» (~l.263) and «Rechazar» (~l.273). Test the labels and target classes.
- [ ] T052 [P] [US6] Add `min-h-12` to the `CompetitionsListPage.tsx` header buttons (~l.198-225), and spell out the priority codes through one label map (grep for the raw «CD» rendering). Add tests.

### US3 — «Cargas e identidades» and resumable imports, frontend part (P1)

- [ ] T053 [US3] Extract the page bodies of `frontend/src/routes/competitions/history/HistoricalLoadPage.tsx`, `history/IdentityReviewPage.tsx` and `UnlinkedCompetitorsPage.tsx` into section components under `frontend/src/components/competitions/imports/` (`LoadsSection.tsx`, `IdentitySection.tsx`, `UnlinkedSection.tsx`). Then create `frontend/src/routes/competitions/CompetitionImportsPage.tsx` with `?seccion=cargas|identidades|sin-enlazar`. Add tests and jest-axe.
- [ ] T054 [US3] Add `getRaceImport(id)` and `discardRaceImport(id)` to `frontend/src/api/raceImports.ts`, with hooks. In `ImportWizard.tsx`:
  - resume from `?import=<id>`: `pending` → review, `dry_run` → confirm;
  - add a discard action with confirmation;
  - on a 409 `identity_pending`, show the `contracts/ui-copy.md` message with a link to `review_path` and keep the import.
  
  Add tests, including a regression test for "leaving no longer loses the import".
- [ ] T055 [P] [US3] In `frontend/src/hooks/layout/useNavBadges.ts`, show the «Cargas e identidades» badge as `identity_decisions_pending + imports_in_progress`, and extend the coach-summary types in `frontend/src/hooks/dashboard/useCoachSummary.ts` and `frontend/src/api/dashboard.ts`. Add tests.

### US5 — «Pendientes» and «Temporada», frontend part (P2)

- [ ] T056 [US5] In `frontend/src/components/dashboard/PendingInbox.tsx`:
  - add «Identidades por decidir» → `/competitions/imports?seccion=identidades` and «Análisis por aprobar» → `/competitions/season/:year?analisis=por-aprobar`;
  - repoint «Insights IA desactualizados» → `?analisis=desactualizados`;
  - a `null` count omits the row.
  
  Add tests.
- [ ] T057 [US5] In `frontend/src/routes/competitions/SeasonInsightsPage.tsx` («Temporada»):
  - add an analyses panel driven by `?analisis=por-aprobar|desactualizados`, using `GET /pending-analyses`;
  - actions: open the analysis (`/athletes/:id?tab=races&view=analisis&insight=`), re-run (existing launch), and dismiss (`POST dismiss-stale`);
  - loading, empty and error states.
  
  Add tests and jest-axe.

### US2 — Per-row metrics on competition results, frontend part (P1)

- [ ] T058 [US2] In `frontend/src/components/competitions/results/ResultsTable.tsx`, add the columns «Parrilla» (per category header), «Percentil» and «Brecha vs. mediana», plus «Brecha vs. 1.ª posición» and «Brecha vs. podio» for the coach variant only. `ParentCompetitionResultsPage.tsx` uses the family variant. Add tests for both audiences.
- [ ] T059 [US6] GATE G4. Run the T046 commands and the T020 backend commands. Also check that the user's untracked scripts in `backend/scripts/` still exist.

---

## Phase 7: W5 — family copy and the approval warning · US4

- [ ] T060 [P] [US4] In `backend/app/services/training/stage_log_builder.py` (~l.180-190), replace the waypoint sublabel «±N% al P1» with «Brecha vs. mediana», computed live from the engine at render time. Test in the stage-log builder tests (grep `stage_log_builder` under `backend/tests/`) that no «P1» or winner text remains.
- [ ] T061 [P] [US4] In `backend/app/services/training/newsletter_builder.py` (~l.1460-1554), replace the `gap_pcts` chart series with the median gap from the engine for family renders, and add a test.
- [ ] T062 [US4] In `frontend/src/components/ai/HITLApprovalCard.tsx`, when `family_gap_mentions` is not empty, show the warning from `contracts/ui-copy.md` plus the snippets, and keep «Aprobar» and «Rechazar» available. Add tests for the warning shown and hidden, and jest-axe.
- [ ] T063 [US4] In `frontend/src/components/newsletter/studio/BlockPanel.tsx`, add a one-click «Insertar aviso de cambios» that pre-fills `coach_note` with the notice from `contracts/ui-copy.md` (446 characters, within the 600 limit). The coach can edit it. Remember a dismissal per coach in the `localStorage` key `tyr:045-notice-dismissed:v1:{userId}`, and never send anything automatically. Add tests.

---

## Phase 8: Polish, audits and closing

- [ ] T064 [P] Update the e2e specs in `frontend/e2e/`:
  - `ai-insights-coach.spec.ts`, `ai-insights-parent.spec.ts`, `ai-insights-hitl.spec.ts` and `ai-insights-newsletter.spec.ts` (new tab and views);
  - `race-analysis-championship.spec.ts`, `race-history.spec.ts`, `race-course.spec.ts` (Circuito y condiciones) and `prefill-import-from-competition.spec.ts`;
  - `target-size.spec.ts` (~l.1054-1201: sweep the new views).
  
  Check `competitions-unification.spec.ts` for its stale 410 assumptions and fix it or record why.
- [ ] T065 Run the `data-privacy-guard` agent (Sonnet) over the whole 045 diff: parent payload omissions, no PII in logs or fixtures, `athlete_ref` never logged, `family_gap_mentions` scoped to coaches. Fix its findings and record the verdict in `specs/045-competitions-one-place/qa.md`.
- [ ] T066 [P] Update `CLAUDE.md` § Cross-feature invariants (Race identity): commits are gated by pending candidates that involve that import's record keys, and imports can be `discarded`. Add a dated entry to `docs/technical-notes.md` and a 045 row to `docs/implementation-status.md`.
- [ ] T067 [P] Write `docs/10-race-results/competitions-one-place.md` (English), covering the area map, the glossary, the metric definitions and the alias table. Link it from `docs/README.md` if that index lists feature docs.
- [ ] T068 Deferred lane: run `pytest -m mysql` against `trocha_ruta_test` (the full lane, including the T024 downgrade), and record the result in `qa.md`.
- [ ] T069 Deferred lane: `pytest -m golden` (SC-008), only if a race AI key is available. Otherwise record it as not run in `qa.md`. Open a follow-up in `docs/implementation-status.md` to regenerate the golden fixtures with the time-based percentile (research R-02).
- [ ] T070 Deferred lane: run the Playwright specs from T064 on the isolated e2e stack (never on the dev or production DB), and record the result in `qa.md`.
- [ ] T071 Deferred lane: measure the LCP of family «Carreras» on a mid-tier Android over simulated 3G (target ≤ 3.5 s, SC-007), and record it in `qa.md`.
- [ ] T072 Deferred lane: the coach tablet check (SC-009) — five tasks, of which four or more must be completed on the first attempt. Record the outcome in `qa.md`.
- [ ] T073 FINAL GATE. Run:
  - backend `pytest` (default plus the local test DB lane) and `ruff` on the changed files;
  - `npm run typecheck`, `npx vitest run` and `npm run build`;
  - a comparison against `baseline.md`, plus a check that the untracked user scripts are intact.
  
  Then summarize, for the owner, which lanes ran and which were deferred.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 (engine)** blocks everything.
- **Phase 3 (US2 consumers)** needs Phase 2. G1 (T020) closes W1.
- **Phase 4 (W2 backend)** can start after G1. Its three blocks are independent: US3 T021–T026, US5 T027–T029, US4 T030–T031. G2 (T032) includes the data-platform-lead validation.
- **Phase 5 (W3)** needs G1 (history and evolution contracts) and T031 (the HITL field type). US1 and US4 share `CarrerasTab`, so T040 comes before T045.
- **Phase 6 (W4)** needs G2 (the imports, summary and pending-analyses endpoints) and G3 (the «Carreras» deep-link target).
- **Phase 7 (W5)** needs G1 (the engine) and T031. Phase 8 comes last.

### Parallel opportunities (disjoint files)

- **W1**: T009, T012, T016 and T019 in parallel after T008.
- **W2**: the three story blocks in parallel (three agents). Inside US3, T024 in parallel with T022.
- **W3**: T033, T034 and T044 in parallel, then T035–T039 in parallel, then T040 → T041/T045.
- **W4**: T047, T049, T050, T051, T052 and T055 in parallel. T053 → T054. T056 and T057 run in parallel with T058.
- **W5**: T060 and T061 in parallel with T062 and T063.

## Implementation Strategy

- **MVP**: Phases 1–3, then Phase 5 US1 (T033–T043). The coach gets one «Carreras» tab on consistent metrics.
- **Increments**, in order:
  - US3 backend + frontend: unblocks Sunday loads, the most time-sensitive part;
  - US4, the family safeguard;
  - US5, pending work;
  - US6, vocabulary and area;
  - W5 copy.
- **Agents**: new agents run on Sonnet (owner rule). Between waves, the orchestrator runs the gate. Pause launches if the owner reports reaching 80 % of session usage.
