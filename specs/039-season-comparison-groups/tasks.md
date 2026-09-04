---

description: "Task list for feature 039 — season evolution charts read cup rounds and championships as separate comparison groups"
---

# Tasks: Season comparison groups

**Input**: Design documents from `/specs/039-season-comparison-groups/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md; contracts in `contracts/evolution-api.md`, `contracts/newsletter-context.md`, `contracts/ai-context.md`

**Tests**: Included — the constitution (Principle II) makes tests part of the deliverable, and the spec defines independent tests per story. Test tasks are written first inside each story and must fail before the implementation task lands.

**Organization**: Tasks are grouped by user story (US1 newsletter, US2 athlete detail, US3 AI, US4 multi-cup). Each story is independently testable after Phase 2.

## Format: `[ID] [P?] [Story] Description → agent · model`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1..US4 from spec.md
- **→ agent · model**: subagent from `.claude/agents/` (or global `~/.claude/agents/`) and the model tier to launch it with. Policy from `.claude/agents/README.md`: bounded execution → `sonnet`; reasoning-heavy authoring, orchestration and final integration review → `opus`. **Effort**: automatic — do not pass a reasoning-effort override; let each agent use its default.

## Path Conventions

Web app: `backend/app/…`, `backend/tests/…`, `backend/templates/…`, `backend/evals/…`, `frontend/src/…`.

## Agent roster for this feature

| Agent | Model | Used for |
|---|---|---|
| `engineering-lead` | opus | Wave coordination, integration review, PR description |
| `fastapi-architect` | sonnet (opus on T033, T035) | Backend services, schemas, router, Jinja PDF wiring; AI node resolution logic gets opus |
| `react-ui-engineer` | sonnet | Frontend components, hooks, types |
| `qa-engineer` | sonnet | pytest / vitest / jest-axe / MSW, real-dataset regeneration |
| `prompt-engineer` (global) | opus | Prompt rule, golden case authoring, golden run interpretation |
| `data-privacy-guard` | sonnet | Mandatory privacy audit |
| `technical-writer` | sonnet | Docs updates |
| `release-manager` | sonnet | Post-deploy smoke |

---

## Phase 1: Setup

**Purpose**: Branch and shared test fixtures every story reuses.

- [X] T001 Create and check out branch `feat/039-season-comparison-groups` from `main` (constitution: feature work happens on a branch; the owner deferred this until implementation) → engineering-lead · opus
- [X] T002 [P] Add reusable backend fixtures for a season with one cup (5 rounds), a departmental championship and a national championship, plus a two-cup variant and a DNF-championship variant, in `backend/tests/fixtures/race_groups.py` (register in `backend/tests/conftest.py`); use synthetic names only → qa-engineer · sonnet
- [X] T003 [P] Extend `mockEvolution()` and add `multiGroupEvolutionHandler`, `championshipOnlyEvolutionHandler`, `twoCupsEvolutionHandler` with the new `groups` and point fields per `contracts/evolution-api.md` in `frontend/src/test/msw/athleteRaceAnalysisHandlers.ts` → qa-engineer · sonnet

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The derived comparison group and the enriched progression rows that every consumer reads.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Write failing unit tests for `build_comparison_group`, `group_label` and `split_progression` (cup rows grouped by `series_id` in first-raced order, championships apart and chronological, empty input) in `backend/tests/services/race/test_comparison_groups.py` → qa-engineer · sonnet
- [X] T005 Implement the pure module `backend/app/services/race/comparison_groups.py` (`build_comparison_group(kind, series_id)`, `group_label(kind, level, name, season_year, location)`, `split_progression(rows) -> SplitProgression`) with docstrings per research D1/D2; reuse `race_labels.build_race_label` for championships → fastapi-architect · sonnet
- [X] T006 [P] Extend failing tests in `backend/tests/services/race/test_analytics.py` so `athlete_progression` returns `event_id`, `series_id`, `series_name`, `comparison_group` and keeps existing columns → qa-engineer · sonnet
- [X] T007 Add `event_id`, `series_id`, `series_name`, `comparison_group` columns to `athlete_progression` in `backend/app/services/race/analytics.py` (extend `series_meta` with name/season_year; keep ordering by `event_date`) → fastapi-architect · sonnet

**Checkpoint**: `pytest backend/tests/services/race/test_comparison_groups.py backend/tests/services/race/test_analytics.py` green; `ruff check` clean.

---

## Phase 3: User Story 1 — The family newsletter reads the cup and the championships separately (Priority: P1) 🎯 MVP

**Goal**: Newsletter charts only over cup rounds (one block per cup); new "Campeonatos" card block with position, field size, gap to P1 and percentile per championship; absent when not applicable.

**Independent Test**: Generate the newsletter for the T002 fixture athlete (5 rounds + CD + CN): three charts show V1..V5 only, accumulated points end at the cup total, "Campeonatos" shows two cards; for an athlete without championships the block is absent; for one with only championships the charts are absent.

### Tests for User Story 1

- [X] T008 [P] [US1] Write failing tests in `backend/tests/services/training/test_newsletter_builder.py` for `_build_race_block` → `cups[]` / `championships[]` shape per `contracts/newsletter-context.md`: dedupe by `event_id` across linked competitors, DNF championship → `finished=false` + nulls, no championship → `championships=[]`, only championships → `cups=[]`, `progression_history` still present → qa-engineer · sonnet
- [X] T009 [P] [US1] Write failing tests in `backend/tests/services/training/test_newsletter_builder.py` for `_build_charts_context` → `cups[]` with per-cup `positions`/`gap_pcts`/`points_accumulated`, `has_data` only when a cup has rows, `low_confidence` per cup, and `points_accumulated[-1].y` equal to the standings total from `services/race/standings.py` for the fixture athlete → qa-engineer · sonnet
- [X] T010 [P] [US1] Write a failing PDF render test in `backend/tests/test_newsletter_builder_024.py` (or a new `backend/tests/test_newsletter_pdf_groups.py`) that renders `athlete_stage_log.html` with (a) a new snapshot containing `cups` + `championships`, asserting the heading `Evolución en la …`, the `Campeonatos` section and the note sentence, and (b) an old snapshot without those keys, asserting no error and no `Campeonatos` section → qa-engineer · sonnet

### Implementation for User Story 1

- [X] T011 [US1] Refactor `_build_race_block` in `backend/app/services/training/newsletter_builder.py`: dedupe `progression_df` by `event_id`, call `split_progression`, emit `cups[]` (`series_id`, `label`, `history`) and `championships[]` as `ChampionshipReading` built from `services/race/field_metrics.compute_field_metrics` (position, `field_size`, `gap_pct`, `percentile`, `finished`, `category_label` via `_lookup_category_labels`); keep `results`, `progression_history`, `projection` → fastapi-architect · sonnet
- [X] T012 [US1] Rewrite `_build_charts_context` in `backend/app/services/training/newsletter_builder.py` to return `has_data`, `has_championship`, `cups[]` (ordinal `x` per cup, accumulated points per cup, `n_samples`, `low_confidence`) per `contracts/newsletter-context.md` → fastapi-architect · sonnet
- [X] T013 [P] [US1] Create the stat-tile partial `backend/templates/documents/pdf/charts/championship_card.html.jinja` (macro `championship_card(reading)`): heading `{label} · {location} · {fecha}`, tiles `Posición` / `Pelotón` / `Gap al P1` / `Percentil`, not-finished state `No completó la prueba.`, text in document text colors only (research D5/D13) → fastapi-architect · sonnet
- [X] T014 [US1] Update `backend/templates/documents/pdf/athlete_stage_log.html`: import the new macro; loop `charts_context.cups` rendering `Evolución en la {label}` + the three existing SVG macros per cup with `break-inside: avoid`; after the loop render the `Campeonatos` section from `race_results.championships` with the note sentence; treat missing `cups`/`championships` keys as empty → fastapi-architect · sonnet
- [X] T015 [US1] Regenerate the newsletter with the real dataset for one athlete with CD + CN and one without championships (`pytest -m mysql` lane or the running app per `specs/039-season-comparison-groups/quickstart.md` §3), open the PDFs rendered from `backend/templates/documents/pdf/athlete_stage_log.html` and confirm layout, page breaks and copy; attach findings to the PR (no athlete names in the PR text) → qa-engineer · sonnet

**Checkpoint**: US1 tests green; PDF visually verified; email template untouched.

---

## Phase 4: User Story 2 — The athlete detail lets the viewer choose the competition (Priority: P2)

**Goal**: `GET /evolution` returns `groups` and accepts `series_id`; the Insights evolution chart gets a "Competencia" selector, renders a card + table for championships, and the Panorama sparkline draws only the first cup.

**Independent Test**: With `multiGroupEvolutionHandler`, the selector lists cup → CD → CN, the default view shows cup points only, selecting CN shows `ChampionshipReadingCard` + table with `Cto. Nal.` and no line; the sparkline renders cup points only; jest-axe reports zero violations. Backend: parent requesting another athlete with `series_id` is denied.

### Tests for User Story 2

- [X] T016 [P] [US2] Write failing tests in `backend/tests/services/race/test_analytics_charts.py` for `build_evolution`: `groups` order (cups by first raced round, then championships by date), `series_id` filter, unknown `series_id` → empty `series` with populated `groups`, `confidence` computed on the filtered series, new point fields (`series_id`, `series_name`, `series_level`, `comparison_group`, `field_size`, `percentile`), `list_athlete_races` items carry `series_id`/`series_name`/`series_level` → qa-engineer · sonnet
- [X] T017 [P] [US2] Write failing router tests in `backend/tests/routers/test_athlete_race_analysis_evolution_groups.py`: coach gets 200 with `groups`; parent of the athlete gets 200 with pseudonym-free payload; parent of another athlete with `series_id` gets the same denial as today; invalid `series_id=0` → 422 → qa-engineer · sonnet
- [X] T018 [P] [US2] Add a `-m mysql` case in `backend/tests/services/race/test_mysql_dialect.py` asserting the extended `build_evolution` CTE returns `series_id` / `series_name` / `series_level` under MySQL enums → qa-engineer · sonnet
- [X] T019 [P] [US2] Write failing vitest specs in `frontend/src/components/athletes/ai/__tests__/EvolutionChart.test.tsx`: selector `Competencia` populated and ordered, default first cup, cup view has no championship labels, championship view renders `ChampionshipReadingCard` + table and no line, national label reads `Cto. Nal.`, season change resets the selection, loading/empty/error states → qa-engineer · sonnet
- [X] T020 [P] [US2] Write failing vitest specs in `frontend/src/components/athletes/ai/__tests__/MiniSparkline.test.tsx` (first cup only; empty state `Sin válidas de copa en esta temporada.` for championship-only data) and extend `frontend/src/components/athletes/ai/__tests__/a11y.v2.test.tsx` to run jest-axe on `EvolutionChart` with the selector and the card → qa-engineer · sonnet

### Implementation for User Story 2

- [X] T021 [US2] Extend schemas in `backend/app/schemas/athlete_race_analysis.py`: `EvolutionPoint` (+ `series_id`, `series_name`, `series_level`, `comparison_group`, `field_size`, `percentile`), new `ComparisonGroupOption`, `EvolutionResponse` (+ `groups`, `selected_group`), `RaceParticipationOption` (+ `series_id`, `series_name`, `series_level`); keep `extra="forbid"` → fastapi-architect · sonnet
- [X] T022 [US2] Implement `build_evolution(..., series_id: int | None = None)` in `backend/app/services/race/analytics_charts.py` per research D4 (single CTE with added select columns, groups computed in Python, filter after, `confidence` on filtered series, `field_size`/`percentile` via position-based formula from `field_metrics`), and add the series fields to `list_athlete_races` → fastapi-architect · sonnet
- [X] T023 [US2] Add the optional `series_id: int | None = Query(default=None, ge=1)` param to `get_evolution` in `backend/app/routers/athlete_race_analysis.py` and pass it through; update the route docstring → fastapi-architect · sonnet
- [X] T024 [P] [US2] Update `frontend/src/types/athleteRaceAnalysis.types.ts` (`EvolutionPoint`, `ComparisonGroupOption`, `EvolutionResponse`, `RaceParticipationOption`), `frontend/src/api/athleteRaceAnalysis.ts` (`getAthleteEvolution(..., seriesId?)`) and `frontend/src/hooks/athletes/useAthleteEvolution.ts` (queryKey includes `seriesId`) → react-ui-engineer · sonnet
- [X] T025 [P] [US2] Create `frontend/src/components/athletes/ai/ChampionshipReadingCard.tsx`: stat-tile row (`Posición`, `Pelotón`, `Gap al P1`, `Percentil`) from an `EvolutionPoint` + group option, not-finished state, values in text tokens, `data-testid="championship-reading-card"` → react-ui-engineer · sonnet
- [X] T026 [US2] Update `frontend/src/components/athletes/ai/EvolutionChart.tsx`: third native `<select id="evo-group">` labeled `Competencia` fed by `response.groups` (cups then championships), default first cup else first championship, reset on season change, subtitle per group type, render `ChampionshipReadingCard` + `EvolutionTable` for championship groups, `ChampionshipDot` text from `payload.series_level`, legend `<ol>` and table rows level-aware → react-ui-engineer · sonnet
- [X] T027 [US2] Update `frontend/src/components/athletes/ai/MiniSparkline.tsx`: request the first cup only (`groups.find(g => g.kind === "cup")`, second fetch with `seriesId` or client filter by `comparison_group`), tooltip `CD`/`CN` by `series_level`, empty state when no cup → react-ui-engineer · sonnet
- [X] T028 [US2] Update integration specs that consume the evolution mock — `frontend/src/components/athletes/ai/__tests__/PanoramaView.test.tsx`, `AthleteAIAnalysisTab.integration.test.tsx`, `AthleteAIAnalysisTab.parent.test.tsx` — for the new payload shape; confirm parent view shows no real names → qa-engineer · sonnet

**Checkpoint**: backend + frontend US2 tests green; `npm run typecheck` clean; manual check per `quickstart.md` §4.

---

## Phase 5: User Story 3 — AI insights never compare a championship with a cup round (Priority: P3)

**Goal**: Progression split in the AI state, race resolution by `event_id`, season comparative restricted to the same cup, prompt rule in `race_analyst_v3.md`, level-aware insight labels, golden gate kept.

**Independent Test**: Offline: an anchored run for the CD fixture (`event_id` of the championship, `valida_num=1`) picks the championship row (not Válida I), yields `season_comparative=[]` and `progression_assessment="first_reference"`; a cup-round run lists only earlier rounds of the same cup. Golden: `pytest -m golden` average ≥ 0.75 with case 009 included.

### Tests for User Story 3

- [X] T029 [P] [US3] Rewrite `backend/tests/services/test_compute_metrics_season.py`: records carry `series_id`/`series_kind`/`event_date`; assert same-series priors only, date ordering, championship → `([], first_reference)`, `event_label` from `build_race_label` (no `99`) → qa-engineer · sonnet
- [X] T030 [P] [US3] Add failing tests in `backend/tests/services/race/ai/nodes/test_compute_metrics.py` for `metrics.progression_groups` shape and in a new `backend/tests/services/race/ai/nodes/test_analyst_agent_resolution.py` for `_build_v3_inputs` / v2 `records_for_vn` resolving the analyzed row by anchored `event_id` (CD vs Válida I collision) and cup-only fallback by `valida_num` → qa-engineer · sonnet
- [X] T031 [P] [US3] Add a FakeLLM graph test in `backend/tests/services/race/ai/test_graph.py` (or a sibling file) launching an anchored championship analysis and asserting the analyst input received the championship `race_row`, `field_metrics.is_championship=true` and `valida_label` with `Cto. Nal.` → qa-engineer · sonnet

### Implementation for User Story 3

- [X] T032 [US3] Add `series_id`, `series_kind`, `series_level` to `_compacted_season_record` in `backend/app/services/race/ai/nodes/load_race_data.py` (resolve via `events_by_id` → `series`; reuse `queries.load_series`) → fastapi-architect · sonnet
- [X] T033 [US3] In `backend/app/services/race/ai/nodes/compute_metrics.py`: emit `metrics.progression_groups` via `split_progression`; rewrite `_compute_season_comparative(full_season_results, analyzed_valida_nums, *, anchored_event_id=None)` to locate the analyzed record by `event_id` (else `(series_kind=="cup", valida_num)`), restrict priors to the same `series_id` with earlier `event_date`, order by date, return `[]`/`first_reference` for championships; replace `_event_label` with `race_labels.build_race_label` → fastapi-architect · opus
- [X] T034 [US3] Update `_progression_to_md` in `backend/app/services/race/agents/analyst.py` to add a `serie` column (`Válida N · Copa` / `Cto. Departamental` / `Cto. Nacional`) built from `series_kind` + `series_level` → fastapi-architect · sonnet
- [X] T035 [US3] In `backend/app/services/race/ai/nodes/analyst_agent.py`: resolve `race_row` in `_build_v3_inputs` and `records_for_vn` in the v2 path by anchored `state["event_id"]` first, cup-only `valida_num` fallback; keep `_field_metrics_by_valida` behavior; pass `anchored_event_id` into the season comparative call → fastapi-architect · opus
- [X] T036 [P] [US3] Add inviolable rule 10 to `backend/app/services/race/prompts/race_analyst_v3.md` per `contracts/ai-context.md` (championship ≠ cup round; read by percentile / field size / strength; no "subió/cayó N posiciones" against a válida); verify `race_season_summary_v3.md` rule 3 and method step 1 need no edit; keep `race_analyst_v2.md` untouched → prompt-engineer · opus
- [X] T037 [P] [US3] Author `backend/evals/race_analyst/golden_v3/case_009.json` (national championship, `is_championship=true`, `series_level="national"`, `season_rows` with cup rounds + CD + CN, `forbidden_terms` with cross-competition position comparisons, `expected_themes` on field reading), validating against `_validate_case_schema` in `backend/tests/evals/test_race_analyst_eval.py` → prompt-engineer · opus
- [X] T038 [US3] Add `series_level` to the insight read schema and service (`backend/app/schemas/athlete_race_analysis.py::AthleteInsightOut`, `backend/app/services/race/insights_history.py` join on `race_series.level`) so timeline / hero card can label the level → fastapi-architect · sonnet
- [X] T039 [US3] Make `validaLabel` in `frontend/src/lib/insights.ts` level-aware (`Cto. Departamental` / `Cto. Nacional`), add `series_level` to `AthleteInsightOut` in `frontend/src/types/athleteRaceAnalysis.types.ts`, and pass it from `HeroLastInsightCard.tsx`, `AthleteAIAnalysisTab.tsx` and `InsightsTimeline.tsx`; update `frontend/src/components/athletes/ai/__tests__/InsightsTimeline.test.tsx` → react-ui-engineer · sonnet
- [X] T040 [US3] Run `RACE_AI_API_KEY=… pytest -m golden -q` in `backend/`, read `backend/evals/race_analyst/results/last_run.md`; if the average is < 0.75, fork `race_analyst_v4.md` per research D9 and point `RACE_AI_PROMPT_VERSION` at it instead of weakening the rule; report per-case scores in the PR (no athlete data) → prompt-engineer · opus

**Checkpoint**: `pytest backend/tests/services/race/ai backend/tests/services/test_compute_metrics_season.py` green offline; golden gate met.

---

## Phase 6: User Story 4 — A season with more than one cup keeps each cup separate (Priority: P4)

**Goal**: Prove by tests and a rendered PDF that two cups in one season produce separate blocks, selector entries and comparatives (the implementation above handles it by construction).

**Independent Test**: With the two-cup fixture: newsletter `charts_context.cups` has two entries each with only its rounds and its own accumulated points; `GET /evolution` `groups` lists both cups then the championship, default = cup with the earliest raced round; season comparative for a round of cup A never includes cup B.

- [X] T041 [P] [US4] Add two-cup assertions to `backend/tests/services/training/test_newsletter_builder.py` (two `cups` entries, per-cup accumulated points, PDF renders two `Evolución en la …` headings) → qa-engineer · sonnet
- [X] T042 [P] [US4] Add two-cup assertions to `backend/tests/services/race/test_analytics_charts.py` (groups order and default) and `backend/tests/services/test_compute_metrics_season.py` (no cross-cup priors) → qa-engineer · sonnet
- [X] T043 [P] [US4] Add a `twoCupsEvolutionHandler` case to `frontend/src/components/athletes/ai/__tests__/EvolutionChart.test.tsx` (both cups listed by name, switching never shows the other cup's rounds) → qa-engineer · sonnet
- [X] T044 [US4] Render the two-cup fixture newsletter to PDF (offline test artifact) and check page breaks between cup blocks; adjust `break-inside` rules in `backend/templates/documents/pdf/athlete_stage_log.html` if a block splits → fastapi-architect · sonnet

**Checkpoint**: All four stories independently green.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045 Run the mandatory privacy audit on the branch diff (championship readings, new schema fields, prompt inputs, test fixtures, logs), record it in `specs/039-season-comparison-groups/checklists/privacy-audit.md` and fix findings → data-privacy-guard · sonnet
- [X] T046 [P] Update `docs/implementation-status.md` (feature 039 step table), `docs/technical-notes.md` (dated entry: derived comparison groups, `series_id` on `/evolution`, AI resolution by `event_id`, prompt rule 10) and `docs/06-parents/003-newsletter-improvements.md` (Campeonatos block) → technical-writer · sonnet
- [X] T047 [P] Full gates: `ruff check`, `pytest` (offline lane), `npm run typecheck`, `npm test` in `frontend/`; fix regressions → qa-engineer · sonnet
- [X] T048 Walk `specs/039-season-comparison-groups/quickstart.md` end to end (§1–§5) and record results in the PR → qa-engineer · sonnet
- [X] T049 Integration review of the whole branch against the five constitution principles and the three contracts in `specs/039-season-comparison-groups/contracts/`; record it in `specs/039-season-comparison-groups/checklists/integration-review.md` and draft the PR description with the compliance line (Conventional Commits, español latino, no AI tooling mentions) → engineering-lead · opus
- [ ] T050 After merge and Render deploy: smoke `/health` and an authenticated `GET /api/athletes/{id}/race-analysis/evolution?season=2026&metric=ranking&series_id=<cup>`; confirm the dashboard loads on a real device → release-manager · sonnet

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 first; T002 and T003 in parallel.
- **Foundational (Phase 2)**: T004/T006 (tests) in parallel, then T005 → T007. Blocks every story.
- **US1 (Phase 3)**: after Phase 2. T008–T010 parallel → T011 → T012 → T013 ∥ T014 → T015.
- **US2 (Phase 4)**: after Phase 2; independent of US1. T016–T020 parallel → T021 → T022 → T023; frontend T024 ∥ T025 → T026 → T027 → T028 (T024 can start once T021 fixes the contract).
- **US3 (Phase 5)**: after Phase 2; T038/T039 also need nothing from US2. T029–T031 parallel → T032 → T033 → T034 ∥ T035 → T036 ∥ T037 → T038 → T039 → T040 (golden run last, needs API key).
- **US4 (Phase 6)**: after US1, US2 and US3 (it asserts their behavior with the two-cup fixture).
- **Polish (Phase 7)**: after all stories; T045 before T049; T050 after merge.

### User Story Dependencies

- **US1** and **US2** are independent of each other (both read Phase 2 output).
- **US3** is independent of US1/US2 for code, but T039 shares `lib/insights.ts` with US2's level-aware labels — coordinate in the same wave or land US2 first.
- **US4** depends on US1–US3 being merged.

### Parallel Opportunities

- Phase 1: T002 ∥ T003.
- Phase 2: T004 ∥ T006; then T005 ∥ nothing (T007 depends on T005 only for label reuse — may run in parallel if the agent imports the helper stub).
- US1: T008 ∥ T009 ∥ T010; T013 ∥ T014.
- US2: T016 ∥ T017 ∥ T018 ∥ T019 ∥ T020; T024 ∥ T025.
- US3: T029 ∥ T030 ∥ T031; T034 ∥ T035; T036 ∥ T037.
- US4: T041 ∥ T042 ∥ T043.
- Polish: T046 ∥ T047.

---

## Execution strategy — Workflow waves (per project convention)

Run with the Workflow tool in waves; `engineering-lead` (opus) coordinates and reviews each wave. Effort stays automatic.

| Wave | Tasks | Agents (model) |
|---|---|---|
| W0 | T001–T003 | engineering-lead (opus), qa-engineer (sonnet) ×2 |
| W1 | T004–T007 | qa-engineer (sonnet), fastapi-architect (sonnet) |
| W2 | T008–T015 (US1) ∥ T016–T028 (US2) | qa-engineer, fastapi-architect, react-ui-engineer (all sonnet) |
| W3 | T029–T040 (US3) | qa-engineer (sonnet), fastapi-architect (sonnet; **opus** for T033/T035), prompt-engineer (opus) |
| W4 | T041–T044 (US4) | qa-engineer, fastapi-architect (sonnet) |
| W5 | T045–T049 | data-privacy-guard, technical-writer, qa-engineer (sonnet), engineering-lead (opus) |
| Post-merge | T050 | release-manager (sonnet) |

Reminder from project memory: pause before launching a new wave when the session is at ~80 % usage; start a fresh workflow rather than `resumeFromRunId` after a pause.

---

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + US1**: the family newsletter stops mixing championships with the cup. Deliverable and deployable on its own (backend + PDF only).
- **Increment 2 = US2**: the coach's chart tells the same story as the newsletter.
- **Increment 3 = US3**: the AI narrative stops comparing across fields; golden gate re-validated.
- **Increment 4 = US4 + Polish**: multi-cup proof, privacy audit, docs, review, smoke.
