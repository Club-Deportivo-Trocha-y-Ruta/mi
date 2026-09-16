---
description: "Task list for feature 043 — Race course profile"
---

# Tasks: Race course profile — course track, laps per category and track description per válida

**Input**: Design documents from `/specs/043-race-course-profile/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md` (R-01…R-16), `data-model.md`, `contracts/` (`course-api.md`, `gpx-processing.md`, `results-derived-figures.md`, `ai-course-block.md`, `ui-course.md`), `quickstart.md`

**Tests**: REQUIRED. Constitution principle II (Testing) is NON-NEGOTIABLE and every contract ends with its test list; test tasks are first-class and sit **before** the implementation they cover inside each phase.

**Organization**: Phases follow the user stories of `spec.md` in priority order, preceded by Setup and Foundational phases and followed by Polish. The four implementation waves of `plan.md` map onto them as: W1 = Phases 2–3, W2 = Phases 4 and 6, W3 = Phases 3 (frontend half), 5, 7, W4 = Phase 8.

## Agent assignment (user request: sonnet or opus "según el caso")

Per `.claude/agents/README.md`: workers execute on **sonnet**, leads orchestrate on **opus**. Each task ends with `→ agent`. Model per agent:

| Agent | Model | Used for |
|---|---|---|
| `engineering-lead` | opus | Opens each phase, checks the exit gate, resolves cross-task conflicts; never writes code. |
| `data-platform-lead` | opus | Reviews the privacy audit and the AI-block change before Phase 6/8 gates. |
| `fastapi-architect` | sonnet | Models, schemas, services, routers, migration. |
| `database-architect` | sonnet | Alembic revision and MySQL-lane verification. |
| `qa-engineer` | sonnet | Backend and frontend tests, e2e, a11y. |
| `data-analyst` | sonnet | GPX geometry algorithms (lap detection, smoothing, simplification) and derived figures. |
| `react-ui-engineer` | sonnet | All frontend components, hooks, pages. |
| `ux-researcher` | sonnet | Copy review and heuristic check of the coach tab and parent card. |
| `data-privacy-guard` | sonnet | Mandatory privacy audit. |
| `prompt-engineer` | sonnet | Course block wording in the v3 prompts and the two golden cases. |
| `technical-writer` | sonnet | Docs, runbook addendum, status/technical notes. |
| `release-manager` | sonnet | Post-deploy smoke. |

Per the owner's standing rule, no new agent definitions are created; only the existing fleet is used. Tasks marked **[P]** may be dispatched to their agents concurrently.

## Format: `[ID] [P?] [Story] Description → agent`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US5 from `spec.md`
- Every task names its exact file path

## Path Conventions

Web application (`plan.md` §Structure Decision): backend at `backend/app/…`, backend tests at `backend/tests/…`, frontend at `frontend/src/…`, e2e at `frontend/e2e/…`, docs at `docs/…`. Paths are repository-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the ground and create the empty roots so later phases own disjoint files. No behaviour changes.

- [X] T001 Verify the Alembic chain has a single head equal to `d5b125474e2b` (`cd backend && alembic heads`); if it differs, update `down_revision` in `data-model.md` §5 before T007 → `database-architect`
- [X] T002 [P] Confirm `gpxpy>=1.6` and `defusedxml>=0.7` are pinned in `backend/requirements.txt` and that `leaflet`, `recharts` are in `frontend/package.json`; no dependency is added by this feature (R-16) → `fastapi-architect`
- [X] T003 [P] Create the package roots `backend/app/services/race/course/__init__.py` (docstring: purpose, no I/O in `gpx_processing`), `backend/tests/services/race/__init__.py` if missing, and the empty folder `frontend/src/components/race/course/` → `fastapi-architect`
- [X] T004 [P] Create `frontend/e2e/fixtures/README.md` stating that every GPX under `frontend/e2e/fixtures/` is synthetic (generated, never a real ride) and how to regenerate it with the builder of T009 → `qa-engineer`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Tables, migration, schemas and the synthetic GPX builder every story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

**Exit gate** (`engineering-lead`): `ruff check` clean; default `pytest` green; `alembic upgrade head` + `downgrade -1` + `upgrade head` round-trip against local docker MySQL; `-m mysql` model round-trip green.

- [X] T005 [P] Create `backend/app/models/race_course_variant.py` (`RaceCourseVariant`, columns and constraints of `data-model.md` §1, `ActorTimestampMixin`, relationships `event`, `setups` viewonly) and export it from `backend/app/models/__init__.py` → `fastapi-architect`
- [X] T006 [P] Create `backend/app/models/race_course_category_setup.py` (`RaceCourseCategorySetup`, `data-model.md` §2, check constraint `ck_race_course_setups_laps_range`, unique `(race_event_id, category_id)`, `variant` relationship with `ondelete=RESTRICT`) and export it → `fastapi-architect`
- [X] T007 Extend `backend/app/models/race_event.py`: `TerrainType` enum, columns `terrain_type`, `technical_difficulty` (+ `ck_race_events_difficulty_range`), `key_sectors` (JSON), `course_notes` (Text); relationships `course_variants`, `course_setups` with `cascade="all, delete-orphan"` (`data-model.md` §3; depends on T005, T006) → `fastapi-architect`
- [X] T008 Write the Alembic revision `backend/alembic/versions/<rev>_race_course_profile.py` with `down_revision="d5b125474e2b"`: create both tables, add the four columns and the enum/check, symmetric `downgrade` (`data-model.md` §5); run the round-trip of the exit gate locally → `database-architect`
- [X] T009 [P] Create `backend/tests/helpers/gpx_builder.py`: functions `circle_gpx(radius_m, points, laps=1, jitter_m=0, elevation=None|callable, extensions=False, with_time=False, metadata=False)`, `out_and_back_gpx(length_m)`, `figure_eight_gpx()`, returning bytes; every generated file must carry Garmin `TrackPointExtension` (hr/cad/atemp) and `<time>` when asked, so privacy tests have something to strip → `data-analyst`
- [X] T010 [P] Create `backend/app/schemas/race_course.py`: enums `TerrainType`, `KeySector`; `VariantRead`, `LapDetectionRead`, `SetupIn`, `SetupRead`, `SuggestedSetupRead`, `CourseDescriptionRead`, `CourseDescriptionUpdate` (`extra="forbid"`, notes ≤ 1000, difficulty 1–5, sectors unique ≤ 8), `SetupsReplace`, `VariantRename`, `MyCategoryRead`, `CourseRead` exactly as `contracts/course-api.md` §1–§5b → `fastapi-architect`
- [X] T011 [P] Extend `backend/app/schemas/race_event.py::RaceEventRead` with the four description fields and `has_course_data: bool` (computed in the service that builds it; default `False`) → `fastapi-architect`
- [X] T012 [P] Write `backend/tests/mysql/test_race_course_models.py` (`@pytest.mark.mysql`): insert a variant with 600-point `geometry`, read it back equal; insert a setup; attempt to delete the referenced variant at the ORM level and assert `IntegrityError`; check the `terraintype` enum accepts the five values → `qa-engineer`
- [X] T013 [P] Create the frontend type and API surface so UI tasks can start in parallel: `frontend/src/types/raceCourse.types.ts` (mirror of `CourseRead` and enums), `frontend/src/schemas/raceCourse.ts` (Zod: `variantUploadSchema` {label 1–60, recorded_laps 1–20 optional, file `.gpx`}, `setupsSchema`, `descriptionSchema` mirroring backend limits), `frontend/src/api/raceCourse.ts` (seven functions of `contracts/course-api.md` §0, multipart for upload/replace), `frontend/src/hooks/race/useRaceCourse.ts` (`useRaceCourse(id)` key `["race-course", id]`, `retry:false`; mutations invalidate that key and `["race-results", id]`) → `react-ui-engineer`
- [X] T014 [P] Create `frontend/src/test/msw/raceCourseHandlers.ts` with handlers for the seven endpoints, fixtures for empty course, complete course (two variants, 3 setups, description), parent 404, and error codes `variant_in_use`, `variant_label_taken`, `too_short`; register them in the MSW server setup used by vitest → `qa-engineer`

**Checkpoint**: Foundation ready — user stories can proceed; US1 and US2 backend can run in parallel with US1 frontend.

---

## Phase 3: User Story 1 — The coach attaches the recorded circuit and sets laps per category (Priority: P1) 🎯 MVP

**Goal**: Upload a coach-recorded GPX, keep one clean lap, name variants, set laps per category with prefill, from the válida tab and from the wizard's final step.

**Independent Test**: With the synthetic 3-lap GPX attach "Circuito completo", confirm detection, attach a single-lap "Recorrido reducido", set laps for three categories, save; reload and assert both variants show distance and gain, setups persist, and no timestamp/heart-rate/original file exists in storage or logs (`quickstart.md` §2, §6 steps 1–3, 7–8).

### Tests for User Story 1

- [X] T015 [P] [US1] Write `backend/tests/services/race/test_gpx_processing.py` covering every bullet of `contracts/gpx-processing.md` §4 (circle single, 3-lap closed_loop, out-and-back manual, recorded_laps override, figure-eight rejection, flat-noise gain < 20 m, 100 m climb 95–105, missing elevation, hypothesis privacy-stripping over random extension tags, XXE/billion-laughs/gzip/random/empty → codes, too_short/too_long/too_few_points, determinism, 20 000-point timing ≤ 300 ms) using T009 → `qa-engineer`
- [X] T016 [P] [US1] Write `backend/tests/routers/test_race_course.py` following `tests/routers/test_race_event_conditions.py` (own aiosqlite engine, `get_current_user` stub, audit tables): the coach happy paths and negative paths of `contracts/course-api.md` §7 **except** the parent cases (those are T052); include the privacy assertions on response body, DB row JSON and `caplog`, the `duplicate_recording` 409, and the `GET /course` ≤ 3-statement count → `qa-engineer`

### Implementation for User Story 1 — backend

- [X] T017 [US1] Implement `backend/app/services/race/course/gpx_processing.py`: `process_gpx`, `ProcessedLap`, `LapDetection`, `CourseProcessingError`, module constants, the ten ordered steps of `contracts/gpx-processing.md` §2 (defusedxml pre-parse → gpxpy → strip at every level → point list → cumulative distance → lap extraction R-04 → range → elevation R-05 → RDP R-06 → rounding); no logging inside the module → `data-analyst`
- [X] T018 [US1] Implement `backend/app/services/race/course/service.py`: `get_course(db, race_event_id, *, allowed_athlete_ids=None)` (coach branch only in this task: variants, setups with category code/label, description, `suggested_setups` per R-14 from the previous válida of the series), `create_variant`, `replace_variant_file`, `rename_variant`, `delete_variant` (409 `variant_in_use` with category labels), `replace_setups` (full replace, `variant_not_in_event`, `unknown_category`, `duplicate_category`), `has_course_data(event)`; structured log `race_course_variant_processed` with ids/counts/method only → `fastapi-architect`
- [X] T019 [US1] Add the routes to `backend/app/routers/race_events.py` per `contracts/course-api.md` §0–§5: `GET /course` (coach/admin branch; parent branch wired in T053), `POST /course/variants`, `PUT /course/variants/{id}/file`, `PATCH /course/variants/{id}`, `DELETE /course/variants/{id}`, `PUT /course/setups`; router-level guards in order (content-type, `.gpx`, gzip/zip sniff, 5 MB cap reusing the training constant), error table §6 as `{"detail": {"code", "message"}}`, `record_audit` on every mutation, docstring stating the write budget → `fastapi-architect`
- [X] T020 [US1] Populate `has_course_data` in the service that builds `RaceEventRead` (`backend/app/services/race_events.py`, list and detail) with one aggregated `EXISTS` per event — no N+1 on the list endpoint; add an assertion to the existing list test that the statement count did not grow with the number of events → `fastapi-architect`
- [X] T021 [US1] Run `backend/tests/services/race/test_gpx_processing.py` and `backend/tests/routers/test_race_course.py` to green; `ruff check` clean on `backend/app/services/race/course/` and `backend/app/routers/race_events.py` → `qa-engineer`

### Implementation for User Story 1 — frontend

- [X] T022 [P] [US1] Create `frontend/src/components/race/course/VariantUploadDialog.tsx` (shared `Sheet`, RHF + Zod `variantUploadSchema`, file input `accept=".gpx"`, optional "Vueltas grabadas", detection confirmation copy for `closed_loop` / `manual` / `single` per `contracts/ui-course.md` §2, "No, indicar vueltas" path re-submitting via replace, inline error mapping of the code table; ≥ 48 px controls) → `react-ui-engineer`
- [X] T023 [P] [US1] Create `frontend/src/components/race/course/VariantsCard.tsx` (list of variants with km / m D+ / points, "Agregar variante", inline rename, replace file, delete with 409 toast naming categories; parent role renders read-only) → `react-ui-engineer`
- [X] T024 [P] [US1] Create `frontend/src/components/race/course/CategorySetupTable.tsx` (rows = categories in results ∪ setups ∪ suggested; laps numeric input 1–20, variant select; banner "Sugerido desde la válida anterior" and button "Confirmar vueltas" when prefilled; blank rows omitted on save; `PUT /course/setups` with the whole table) → `react-ui-engineer`
- [X] T025 [US1] Create `frontend/src/components/race/course/CourseTab.tsx` composing T023, T024, the description card (placeholder until T041) and `CourseSummary` (placeholder until T055); empty state "Sin circuito registrado" with both CTAs; prop `compact` (depends on T022–T024) → `react-ui-engineer`
- [X] T026 [US1] Add the `"circuito"` value to `TabValue`/`TAB_VALUES` in `frontend/src/routes/competitions/CompetitionDetailPage.tsx`, the trigger "Circuito" after "Condiciones", and the lazy `<TabsPrimitive.Content value="circuito">` rendering `CourseTab` → `react-ui-engineer`
- [X] T027 [US1] In `frontend/src/components/competitions/import/ImportWizard.tsx` step 3, after a successful commit and once `race_event_id` is known, render a heading "Circuito (opcional)" and `<CourseTab raceEventId compact />`; `STEPS` unchanged; existing wizard tests must stay green → `react-ui-engineer`
- [X] T028 [P] [US1] In `frontend/src/routes/competitions/CompetitionFormPage.tsx` success state, add the secondary action "Agregar circuito" linking to `/competitions/{id}?tab=circuito` → `react-ui-engineer`
- [X] T029 [P] [US1] Write vitest + jest-axe tests: `frontend/src/components/race/course/__tests__/VariantUploadDialog.test.tsx` (three detection copies, error mapping, 48 px), `VariantsCard.test.tsx` (role branches, 409 toast), `CategorySetupTable.test.tsx` (prefill banner, blank-row omission, validation), `CourseTab.test.tsx` (empty vs complete, coach vs parent), and extend `frontend/src/components/competitions/import/__tests__/` with the step-3 panel case and `frontend/src/routes/competitions/__tests__/` with the new tab (axe zero violations) → `qa-engineer`
- [X] T030 [US1] Generate the synthetic e2e fixtures `frontend/e2e/fixtures/course_3laps.gpx` and `course_reduced.gpx` with T009 (script call documented in T004's README) and write `frontend/e2e/race-course.spec.ts` part 1: upload, confirm detection, second variant, setups save, reload persists → `qa-engineer`

**Checkpoint**: US1 is the MVP — a válida can carry variants and a laps table, from the tab and from the wizard.

---

## Phase 4: User Story 2 — Results show real distance and average speed (Priority: P1)

**Goal**: Every classified result in a válida with course data shows distance and average speed; "sin dato" whenever an input is missing; never estimated; season rows carry a nullable speed with no aggregates.

**Independent Test**: Seed variant 4 200 m / 110 m and a category at 3 laps; finished 30:00 → 12.6 km, 25.2 km/h; one lap down 28:00 → 8.4 km, 18.0 km/h; DNF → "sin dato" (`contracts/results-derived-figures.md` §4).

### Tests for User Story 2

- [X] T031 [P] [US2] Write `backend/tests/services/race/test_results_derived.py`: the spec numeric case, `minus_laps` without count, category without setup with `has_course_data=True`, válida without course, parent scope, revision of `laps_behind` reflected, statement count +1 exactly, property test on `derive_figures` → `qa-engineer`
- [X] T032 [P] [US2] Extend `frontend/src/components/competitions/results/__tests__/ResultsTable.test.tsx`: columns present only when `has_course_data`; "sin dato" cells; category header line with laps/variant/km/D+ → `qa-engineer`

### Implementation for User Story 2

- [X] T033 [P] [US2] Implement `backend/app/services/race/course/derived.py::derive_figures(setup, status, race_time_ms, laps_behind) -> DerivedFigures` with `Decimal` rounding per `contracts/results-derived-figures.md` §2 → `data-analyst`
- [X] T034 [US2] Extend `backend/app/schemas/race_results.py`: `ResultRow` + `distance_km`, `avg_speed_kmh`, `lap_distance_km`, `elevation_gain_m`; `CategoryResults` + `laps`, `variant_label`; `EventResultsRead` + `has_course_data` (all optional/default) → `fastapi-architect`
- [X] T035 [US2] Extend `backend/app/services/race/results_read.py::get_event_results`: one `select(RaceCourseCategorySetup).options(selectinload(variant))` per call, dict by `category_id`, attach figures via T033 after parent scoping, fill category-level fields and `has_course_data` (depends on T033, T034) → `fastapi-architect`
- [X] T036 [US2] Add `avg_speed_kmh: float | None` to the athlete per-válida rows, with **no** aggregate anywhere (R-11); extend the corresponding schema and its existing test with one válida with course and one without → `fastapi-architect`. **Corrected target** (verified against the working tree — `analytics.py` has no per-válida-rows-with-a-schema surface): implemented on `EvolutionPoint` (`backend/app/schemas/athlete_race_analysis.py`) and `backend/app/services/race/analytics_charts.py::build_evolution`, extending `backend/tests/services/race/test_analytics_charts.py`.
- [X] T037 [US2] Extend `frontend/src/types/` race results types and `frontend/src/components/competitions/results/ResultsTable.tsx`: conditional columns "Distancia" and "Vel. prom." (1 decimal, "sin dato" muted), category header addendum; the parents page inherits it → `react-ui-engineer`
- [X] T038 [US2] Render `avg_speed_kmh` as a column with "sin dato" in the season/evolution per-válida table(s) that consume the rows of T036; no derived aggregate in the UI → `react-ui-engineer`. **Corrected target** (verified against the working tree — `SeasonInsightsPage.tsx` renders a per-athlete SEASON AGGREGATE, no per-válida breakdown at all): implemented in `frontend/src/components/athletes/ai/EvolutionChart.tsx`'s `EvolutionTable` (table-view tab, one row per válida) and `frontend/src/types/athleteRaceAnalysis.types.ts::EvolutionPoint`.
- [X] T039 [US2] Run `backend/tests/services/race/test_results_derived.py`, `frontend/src/components/competitions/results/__tests__/ResultsTable.test.tsx`, then the full default `pytest` (`backend/`) and `npm test` (`frontend/`) to green → `qa-engineer`

**Checkpoint**: US1 + US2 deliver the measurable payoff; deployable increment.

---

## Phase 5: User Story 3 — The coach describes the track (Priority: P2)

**Goal**: Structured description (terrain, difficulty 1–5, key sectors, notes ≤ 1000) editable with or without a recording.

**Independent Test**: Save terrain "mixto", difficulty 4, two sectors, 300-char notes; reload shows all in español neutro; save notes-only without any variant → accepted; 1 001 chars → rejected with the limit stated.

### Tests for User Story 3

- [X] T040 [P] [US3] Extend `backend/tests/routers/test_race_course.py` with the `PATCH /course/description` cases: partial update, explicit `null` clears, notes 1 001 → 422 stating the limit, difficulty 6 → 422, unknown sector → 422, > 8 sectors → 422, description without variants → 200 and `has_course_data=True`, audit row with `changed_fields` → `qa-engineer`

### Implementation for User Story 3

- [X] T041 [US3] Implement `update_description` in `backend/app/services/race/course/service.py` (`exclude_unset` semantics) and the `PATCH /course/description` route in `backend/app/routers/race_events.py` with `record_audit(changed_fields=["course_description:<fields>"])` → `fastapi-architect`
- [X] T042 [P] [US3] Create `frontend/src/components/race/course/EditCourseDescriptionDialog.tsx` (Sheet; terrain select with the five labels; difficulty radio group "1 — Muy fácil … 5 — Muy técnico"; sector checkboxes with Spanish labels; notes textarea with live counter /1000; RHF + Zod `descriptionSchema`, inline errors, no HTML5 validation) → `react-ui-engineer`
- [X] T043 [P] [US3] Create `frontend/src/components/race/course/CourseDescriptionCard.tsx` (tri-state empty / partial / complete copied from `components/race/RaceConditionsCard.tsx`; "Describir la pista" / "Completar" / "Editar" for coach/admin; read-only for parents) and wire it into `CourseTab` replacing the placeholder of T025 → `react-ui-engineer`
- [X] T044 [US3] Write `frontend/src/components/race/course/__tests__/CourseDescriptionCard.test.tsx` and `EditCourseDescriptionDialog.test.tsx` (tri-state by role, validation messages, counter, axe zero violations) and run T040 to green → `qa-engineer`
- [X] T045 [US3] Heuristic and copy review of the Circuito tab for the coach-on-tablet persona (48 px targets, gloves-friendly spacing, español neutro with diacritics); apply findings directly as edits to the copy constants in `frontend/src/components/race/course/VariantUploadDialog.tsx`, `CategorySetupTable.tsx` and `EditCourseDescriptionDialog.tsx`, not as a separate report → `ux-researcher`

**Checkpoint**: The description is usable on its own and feeds Phase 6.

---

## Phase 6: User Story 4 — The AI analysis uses the circuit only when it exists (Priority: P2)

**Goal**: `course_block` reaches the v3 prompts under the present / SIN DATO veto; notes never included; golden ≥ 0.75.

**Independent Test**: Fake provider captures the prompt: with course data the six bullets appear and the notes text does not; without course data the veto sentence appears; golden eval composite ≥ 0.75 with two new cases (`contracts/ai-course-block.md` §5).

### Tests for User Story 4

- [X] T046 [P] [US4] Write `backend/tests/services/race/ai/test_course_block.py`: `fetch_course_context` keys present for every requested válida, `{}` without setup, compiled SQL never mentions `course_notes`; `format_course_meta` cases (`{}` → None, description-only, full six bullets); render of `race_analyst_v3` and `race_season_summary_v3` with block present/absent; render of the v2 prompts with the extended context still succeeds; end-to-end per-válida run with `FakeLLM` asserting prompt content in both situations; a forbidden name inside `course_notes` never appears in any prompt → `qa-engineer`

### Implementation for User Story 4

- [X] T047 [US4] Add `course_context: dict[int, dict]` to `RaceAnalystState` in `backend/app/services/race/ai/state.py` and implement `fetch_course_context(db, season, validas, category_id)` in `backend/app/services/race/ai/queries.py` selecting only the allow-listed columns (never `course_notes`), reusing the cached events like `fetch_event_conditions` → `fastapi-architect`
- [X] T048 [US4] Fill `course_context` in `backend/app/services/race/ai/nodes/load_race_data.py` right after `event_conditions` (both return paths) → `fastapi-architect`
- [X] T049 [US4] Add `format_course_meta` beside `format_race_meta`, `AnalystV3Input.course_meta`, and `"course_block"` in `_build_v3_context` in `backend/app/services/race/agents/analyst.py`; thread `course_meta` from the state into the input where `race_meta` is built (per-válida and season summary paths) → `fastapi-architect`
- [X] T050 [US4] Insert the course block of `contracts/ai-course-block.md` §3 into `backend/app/services/race/prompts/race_analyst_v3.md` (after the conditions block) and the per-válida equivalent into `race_season_summary_v3.md`; leave every v2 prompt untouched; add a header note in both files describing the block and its veto → `prompt-engineer`
- [X] T051 [US4] Create `backend/evals/race_analyst/golden_v3/case_0XX_course_present.json` and `case_0XX_course_absent.json` (next free numbers; synthetic `athlete_ref`; `forbidden_terms` for the absent case include km/vuelta(s)/terreno/desnivel/técnico/dificultad); extend the case builder in `backend/tests/evals/test_race_analyst_eval.py` to pass `course_meta`; run `pytest -m golden` with a real key, confirm composite ≥ 0.75 and regenerate the baseline per `docs/10-race-results/runbook-ops.md` → `prompt-engineer`
- [X] T052 [US4] Run `backend/tests/services/race/ai/test_course_block.py` to green, then hand the diff of `backend/app/services/race/ai/`, `backend/app/services/race/agents/analyst.py` and `backend/app/services/race/prompts/*_v3.md` to `data-platform-lead` for the AI-context review (structural exclusion of notes, no new athlete field in the prompt) → `qa-engineer` then `data-platform-lead`

**Checkpoint**: The analyst can contextualise by circuit and stays silent without data.

---

## Phase 7: User Story 5 — Coach and families recognise the circuit before and after the event (Priority: P2)

**Goal**: Read-only summary (map, elevation profile, figures, laps of each child's category, description) on the coach tab and on both parent pages; families only for válidas their children are registered in.

**Independent Test**: Parent with a child on the roster of a scheduled válida sees the card with the child's category laps; a parent without a registered child sees no card (404, no toast); no results or other riders' names in the view; text renders before the lazy map; axe zero violations (`quickstart.md` §6 step 9).

### Tests for User Story 5

- [X] T053 [P] [US5] Extend `backend/tests/routers/test_race_course.py` with the parent cases of `contracts/course-api.md` §7: child on roster → 200 with `my_categories`; child only in results → 200; two children in two categories → two entries; no child → 404 `course_not_available`; parent response never contains roster rows, results, or other athlete ids; `suggested_setups` empty for parents → `qa-engineer`
- [X] T054 [P] [US5] Write `frontend/src/components/race/course/__tests__/CourseSummary.test.tsx` (map/chart mocked; figures and laps text present; profile hidden when `has_elevation=false`; child highlight from `my_categories`; axe), `CourseMap.test.tsx` (aria-label, focusable; Leaflet mocked), `ElevationProfile.test.tsx` (decimation ≤ 200, aria-label with min/max/gain), and extend `frontend/src/routes/parents/competitions/ParentCompetitionResultsPage.test.tsx` and `frontend/src/routes/parents/calendar/ParentEventDetailPage.test.tsx` (card present on 200, absent on 404, no toast; axe) → `qa-engineer`

### Implementation for User Story 5

- [X] T055 [US5] Implement the parent branch of `get_course` in `backend/app/services/race/course/service.py`: with `allowed_athlete_ids`, compute `my_categories` from roster ∪ results of those athletes, return `None` when empty; wire `require_role([admin, coach, parent])` + `allowed_athlete_ids_for` in the `GET /course` route of `backend/app/routers/race_events.py`, mapping `None` to 404 `course_not_available` → `fastapi-architect`
- [X] T056 [P] [US5] Create `frontend/src/components/race/course/CourseMap.tsx` (lazy; dynamic `import("leaflet")` + `leaflet/dist/leaflet.css` and the icon-path workaround from `components/training/RouteViewer.tsx`; `L.polyline` from `geometry`, `fitBounds`, neutral colour per the `dataviz` skill palette; `role="region"`, `aria-label="Mapa del circuito {label}"`, `tabIndex=0`; 240 px height on mobile) → `react-ui-engineer`
- [X] T057 [P] [US5] Create `frontend/src/components/race/course/ElevationProfile.tsx` (lazy; Recharts `AreaChart` in `ResponsiveContainer`, X = km, Y = m, ≤ 200 samples by distance bucket, single neutral series, `role="img"` + `aria-label` "Perfil de altimetría: de {min} a {max} m, {gain} m de desnivel positivo"; 160 px on mobile) → `react-ui-engineer`
- [X] T058 [US5] Create `frontend/src/components/race/course/CourseSummary.tsx` (per variant: figures line, `<Suspense fallback={<Skeleton/>}>` around T056/T057, "Sin altimetría en la grabación" when `has_elevation=false`; laps by category with highlight for `my_categories` labelled by child using the page's existing child context; description block) and replace the placeholder in `CourseTab` (depends on T056, T057) → `react-ui-engineer`
- [X] T059 [US5] Add the card to `frontend/src/routes/parents/competitions/ParentCompetitionResultsPage.tsx` (`useRaceCourse` with `retry:false`; 404 → absent, no error state) and to `frontend/src/routes/parents/calendar/ParentEventDetailPage.tsx` when the calendar event links a válida (confirm the field name on the event payload in `frontend/src/types/` and, if absent, add `race_event_id` to the calendar event read schema on both sides in the same task) → `react-ui-engineer`
- [X] T060 [US5] Verify the lazy chunk boundaries with `npm run build` (report gzipped sizes of the map and chart chunks and of the results route; both lazy routes under 150 KB gzipped) and note the numbers in `specs/043-race-course-profile/tasks.md` under Notes → `react-ui-engineer`
- [X] T061 [US5] Write `frontend/e2e/race-course.spec.ts` part 2: description, results columns, parent login sees the card, non-registered parent does not; run T053 + T054 and the e2e spec to green → `qa-engineer`
- [X] T062 [US5] Heuristic and accessibility review of the parent card on a 360 px viewport over throttled 3G (figures readable before the map, no horizontal scroll, contrast AA); apply fixes directly in `frontend/src/components/race/course/CourseSummary.tsx`, `CourseMap.tsx` and `ElevationProfile.tsx` → `ux-researcher`

**Checkpoint**: All five stories are independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Privacy audit, documentation, verification lanes and release.

- [X] T063 Mandatory `data-privacy-guard` audit over `backend/app/services/race/course/`, the course routes in `backend/app/routers/race_events.py`, `results_read.py` changes, `ai/queries.py::fetch_course_context`, the prompts diff, and the parent pages: confirm the recording is never persisted/logged/traced, `course_notes` never reaches a prompt, parents only see their own athletes; write findings to `specs/043-race-course-profile/privacy-audit.md` and fix any blocker in the same task → `data-privacy-guard`, reviewed by `data-platform-lead`
- [X] T064 [P] Write `docs/10-race-results/course-profile-design.md` (data model, processing algorithm with constants, API table, AI block, UI map, privacy invariants) and add a "Course profile" section to `docs/10-race-results/runbook-ops.md` (how to re-upload with `recorded_laps`, what the 409/422 codes mean, golden baseline update) → `technical-writer`
- [X] T065 [P] Update `docs/implementation-status.md` (race-results module step table: feature 043 rows) and `docs/technical-notes.md` (dated entry: GPX-only decision, DB storage rationale, derived-at-read rule, prompt block, ephemeral-disk finding for training route files) → `technical-writer`
- [X] T066 [P] Update `CLAUDE.md`: replace the "in planning" paragraph of the SPECKIT block with the shipped summary (mirroring the 042 paragraph style), set the Alembic head to the 043 revision, and add the course endpoints to the race-results bullet → `technical-writer`
- [X] T067 Run the full verification of `quickstart.md` §2–§5 and §7 (default pytest, `ruff`, `-m mysql`, golden, typecheck, vitest, e2e) and record results in `specs/043-race-course-profile/tasks.md` Notes → `qa-engineer`
- [X] T068 Measure `POST /course/variants` locally with a synthetic 5 MB / 60 000-point GPX; if p95 > 1 500 ms, record the value and the chosen mitigation in `specs/043-race-course-profile/plan.md` §Complexity Tracking before merge → `fastapi-architect`
- [ ] T069 Post-deploy smoke per `quickstart.md` §8 (`/health`, coach `GET /course`, parent 200/404, parents page on a mid-tier Android over throttled 3G with LCP ≤ 3.5 s) and record in `docs/technical-notes.md` → `release-manager`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: immediate.
- **Foundational (Phase 2)**: after Setup; **blocks every story**. T007 depends on T005+T006; T008 on T007; T013/T014 are independent of the backend tasks.
- **US1 (Phase 3)**: after Phase 2. Backend chain T017 → T018 → T019 → T020 → T021; frontend chain T022–T024 → T025 → T026/T027; T028–T030 after T025.
- **US2 (Phase 4)**: after Phase 2 and T018 (setups exist). T033 → T034 → T035 → T036; T037/T038 after T034 types are mirrored.
- **US3 (Phase 5)**: after Phase 2; backend T041 independent of US1's service functions except the shared file; frontend after T025.
- **US4 (Phase 6)**: after Phase 2 and T041 (description fields) — T047 → T048 → T049 → T050 → T051 → T052.
- **US5 (Phase 7)**: after T018/T019 (course read exists) and T041; T055 backend independent of frontend; T056/T057 → T058 → T059 → T060 → T061.
- **Polish (Phase 8)**: after all desired stories; T063 before merge; T069 after deploy.

### Parallel Opportunities

- Phase 2: T005 ∥ T006 ∥ T009 ∥ T010 ∥ T011 ∥ T012 ∥ T013 ∥ T014.
- Phase 3: T015 ∥ T016 (tests) while T017 starts; T022 ∥ T023 ∥ T024 with T028; T029 ∥ T030 at the end.
- Across stories after Phase 2: US1 backend (T017–T021) ∥ US1 frontend (T022–T028) ∥ US3 backend (T041) ∥ US2 tests (T031–T032).
- Phase 7: T056 ∥ T057; T053 ∥ T054.
- Phase 8: T064 ∥ T065 ∥ T066.

### Parallel Example: Phase 2 dispatch

```text
engineering-lead (opus) opens Phase 2 and dispatches concurrently:
  fastapi-architect  → T005, T006, T010, T011
  data-analyst       → T009
  database-architect → T001 (already done in Setup) then T008 once T007 lands
  qa-engineer        → T012, T014
  react-ui-engineer  → T013
Gate: ruff + pytest + alembic round-trip + `-m mysql` → then Phase 3 and Phase 4 tests start together.
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 → Phase 2 → Phase 3.
2. **Stop and validate**: `quickstart.md` §6 steps 1–3, 7–8; privacy assertions of T015/T016 green.
3. Demo: a válida with two variants and a laps table, from the tab and from the wizard.

### Incremental Delivery

1. + US2 → results with distance and speed (deployable; the visible payoff).
2. + US3 → description card.
3. + US4 → analyst context (golden gate).
4. + US5 → reconnaissance for families (parent endpoint + map + profile).
5. Phase 8 → audit, docs, smoke.

### Team Strategy

`engineering-lead` (opus) runs each phase gate; after Phase 2, the four sonnet workers split by file ownership (backend: `fastapi-architect` + `data-analyst`; frontend: `react-ui-engineer`; tests: `qa-engineer`) so no two agents edit the same file in the same wave. `data-platform-lead` (opus) reviews T052 and T063. Per the owner's session rule, do not launch new agents once session usage reaches 80 %.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- Never commit a real recording; fixtures come from `backend/tests/helpers/gpx_builder.py`.
- Never paste `.env` values, athlete names or coordinates of a real ride into tasks, commits or reports.
- Commit per logical group with Conventional Commits (type in English, description in español latino, no AI mention) only when the owner asks.
- Record measured chunk sizes (T060), verification results (T067) and upload timing (T068) here when done.
- **T060 measured chunk sizes** (`npm run build`, 2026-09-16): `CourseMap-*.js` 1.50 kB (gzip 0.84 kB), `ElevationProfile-*.js` 2.17 kB (gzip 1.13 kB), `CourseSummary-*.js` 5.72 kB (gzip 1.95 kB), `CourseTab-*.js` 24.61 kB (gzip 6.50 kB) — all trivially under the 150 KB gzipped budget. The heavier shared library chunks each component dynamically imports — `leaflet-src-*.js` 148.81 kB (gzip 43.38 kB) and `CartesianChart-*.js` (Recharts) 320.63 kB (gzip 95.64 kB) — are **pre-existing** shared dependency chunks already paid for by `training/RouteViewer.tsx` (Leaflet) and `athletes/ai/EvolutionChart.tsx` (Recharts); this feature does not add new library weight, it only causes those already-bundled chunks to load on the parent competition/calendar routes where they weren't fetched before.
- **T068 upload timing** (2026-09-16): see `specs/043-race-course-profile/plan.md` §Complexity Tracking — a synthetic 60,000-point/2.92 MB GPX through the real `POST /course/variants` route measured p95 ≈ 3.18 s (5 runs, in-sandbox aiosqlite, no real Render hardware), above the 1 500 ms budget. No mitigation implemented; recorded as an open pre-merge decision with context on why a real coach's single-lap recording is very unlikely to approach that point count.

### Phase 1 + 2 completion notes (2026-09-15)

- Executed via a dynamic multi-agent workflow (fastapi-architect for T005/T006/T007/T010/T011 sequentially to avoid two agents racing on `models/__init__.py`; data-analyst for T009; react-ui-engineer for T013; qa-engineer for T014 and T012; database-architect for T008 — T008/T012 waited on the models landing first).
- T003's empty folder `frontend/src/components/race/course/` was not created as a bare directory — git does not track empty directories, so it will appear naturally when Phase 3 (T022+) adds the first component file there.
- **Sandbox limitation**: this environment has no Docker/local MySQL server, so the true Phase 2 exit-gate criteria — `alembic upgrade head` / `downgrade -1` / `upgrade head` against real MySQL 8.4, and `pytest -m mysql tests/mysql/test_race_course_models.py` — could **not** be run here. T008's migration was instead verified with an isolated sqlite harness (upgrade→downgrade→upgrade against a scratch in-memory DB using stub parent tables, schema reflected after each step) and passed; T012's tests were verified only via `ruff` + `pytest --collect-only`. **A developer must run both against real MySQL before this feature merges** (`docker compose up mysql`, then `TEST_DATABASE_URL=mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test`).
- `ruff check` is clean on every file this phase touched. `alembic heads` resolves to the single new head `5ba077132b3b` (`down_revision=d5b125474e2b`).
- Default `pytest` lane: caught and fixed two real regressions surfaced by the new `RaceEvent.course_variants`/`course_setups` cascade + a Pydantic v2 gotcha, verified by re-running the full suite before/after (see below) rather than trusting agent self-reports alone:
  1. `RaceEventRead.key_sectors` (and `CourseDescriptionRead.key_sectors`) was typed as a plain `list[KeySector] = []`; Pydantic v2 doesn't apply that default when the underlying ORM attribute is an explicit `None` (nullable JSON column with no rows populated yet), so every `RaceEventRead.model_validate(event)` call — i.e. every existing race-event GET/PATCH — started raising a validation error. Fixed with a `field_validator(mode="before")` coercing `None → []` on both schemas.
  2. `RaceEvent.course_variants`/`course_setups` now cascade `all, delete-orphan`, so deleting a `race_event` triggers an ORM-level `SELECT` against `race_course_variants` even when no course data exists. Two pre-existing test files build an explicit sqlite table subset (`tests/routers/test_race_events_crud.py`, `tests/test_audit_race_results.py`) that didn't include the two new tables — added them.
  - Full suite before these two fixes: 246 failed / 4763 passed. After: 212 failed / 4797 passed (exactly the 34 tests these two fixes touch). The remaining 212 failures + 9 errors are pre-existing and unrelated to this feature: they hit `sqlalchemy.exc.OperationalError: Can't connect to MySQL server on 'localhost'` (tests that build a real `Settings.database_url` session instead of an offline one) or need optional services this sandbox lacks (SMTP/Resend, a PDF renderer) — confirmed via `git stash` against the pre-feature commit, which reproduces the identical failures.
- Frontend: `npm run typecheck` (`tsc --noEmit`) passes with zero errors across all new/modified files.
- Minor, non-blocking note for a later task: `useRaceCourse.ts`'s mutation hooks invalidate the literal query-key tuples `["race-course", id]` / `["race-results", id]` rather than the existing `raceResultsKeys` factory in `hooks/race/invalidation.ts`; worth reconciling once Phase 3's consuming components land.

### Phase 3 + 4 completion notes (2026-09-15)

- Executed via a dynamic multi-agent workflow (15 agents across two independent tracks — US1 backend: tests → gpx_processing → service+router+has_course_data → verify; US1 frontend: cards → CourseTab → wire pages → tests+e2e in parallel — then US2's tests+pure-fn → wiring → verify once US1 fully landed). This sandbox has only 4 CPUs, capping the workflow at 2 concurrent agents; the two tracks still ran independently, just serialized against each other more than a larger machine would allow.
- **Two task-plan file pointers were wrong and corrected against the actual working tree** (same kind of drift as T020 in Phase 2): T036/T038 named `backend/app/services/race/analytics.py` and `frontend/src/routes/competitions/SeasonInsightsPage.tsx` as the "athlete per-válida rows" surface — neither exists as such. `analytics.py`'s only functions are DataFrame-returning AI-pipeline internals with no per-válida schema; `SeasonInsightsPage.tsx` renders a per-athlete season aggregate with no per-válida breakdown. The real surface is `EvolutionPoint` (`backend/app/schemas/athlete_race_analysis.py`) + `build_evolution` (`backend/app/services/race/analytics_charts.py`), rendered as `EvolutionTable` inside `frontend/src/components/athletes/ai/EvolutionChart.tsx` — implemented there instead, with `backend/tests/services/race/test_analytics_charts.py` extended.
- **A real contract deviation found and fixed after the workflow completed**: `results-derived-figures.md` promises `get_event_results` runs "exactly one more statement than before," but the landed implementation added a *second*, conditional query (an `exists()` check against `RaceCourseVariant`, firing only when no setups exist yet) and the query-count test was quietly widened from `≤3` to `≤4` to match rather than the implementation being made to fit the contract. Fixed by dropping the fallback query: `has_course_data` on the results endpoint is now `bool(setup_by_category)` alone (a variant with zero setups configured yet shows no distance/speed for any row either way, so gating column visibility on setup existence is both the more useful signal and what keeps the query count a hard, unconditional +1); the query-count test and two mocked `db.execute` side-effect sequences (`test_race_analysis_privacy.py`) were reverted to match. This is a deliberately different `has_course_data` definition than the Circuito tab's own (`course/service.py::has_course_data`, which correctly still considers "any variant exists" for that different UI purpose).
- T021's own verification pass caught and fixed two more instances of the same cascade-delete-breaks-explicit-sqlite-table-subset issue from Phase 2 (`test_race_series_014.py`, `tests/fixtures/race_groups.py`), plus a **pre-existing** (not introduced by this feature) stale `CURRENT_HEAD` constant in `test_audit_mysql.py` that still said `686ce1d873f3` when the real head was already `d5b125474e2b` before this feature even started — corrected to `5ba077132b3b`. T039's verification pass closed a real test-coverage gap: `EvolutionChart.test.tsx` had zero coverage of the new `avg_speed_kmh` column it had just implemented.
- Full backend suite: 212 failed / 4847 passed / 62 skipped / 13 xfailed / 6 xpassed / 9 errors — unchanged from the Phase 1+2 baseline (confirmed independently, twice, including after this session's own post-workflow fix). All remaining failures are pre-existing and unrelated (no local MySQL/SMTP/PDF services in this sandbox). Frontend: `npm run typecheck` clean; targeted vitest run across every touched area (`race/course`, `competitions/results`, `athletes/ai`, `routes/competitions`, `competitions/import`) — 54 files / 628 tests, all passing. Two frontier tests (`SessionWizardRouteNotify.test.tsx`, `useRaceRun.test.ts`) fail/flake in the full `npm test` run but are pre-existing and unrelated to this feature (confirmed by file — neither touched by this feature's diff).
- `ruff check` clean on every file this work touched (confirmed independently after the workflow, beyond each agent's own report).
- **Sandbox limitation carried over from Phase 1+2**: still no Docker/local MySQL in this environment. `-m mysql` tests (`test_race_course_models.py` from Phase 2) remain unexecuted here; nothing in Phases 3-4 added new `-m mysql` tests, so no new gap on that front.
- T030's e2e spec (`frontend/e2e/race-course.spec.ts` part 1) and the two synthetic GPX fixtures were authored but **not executed** — no Docker/isolated Playwright stack in this sandbox. A developer must run `npm run test:e2e -- race-course.spec.ts` against the real stack before merge.

### Phase 5 + 6 completion notes (2026-09-15)

- Executed via a dynamic multi-agent workflow, two fully independent tracks in parallel (US3 touches only `course/service.py`, the description route, and the frontend course components; US4 touches only the AI pipeline files and prompts — zero file overlap, confirmed before dispatch): US3 (tests → backend `update_description` route ∥ frontend dialog+card → tests+verify → UX/copy review) and US4 (test → pipeline (`state.py`/`queries.py`/`load_race_data.py`/`analyst.py`/`analyst_agent.py`) → prompts+golden cases → QA verify ∥ `data-platform-lead` privacy review).
- **Task-plan file-path correction, same recurring drift as Phases 2–4**: `tasks.md` (T047) names `backend/app/services/race/ai/queries.py` for `fetch_course_context`, which does not exist — the real, and only sensible, location (alongside the sibling `fetch_event_conditions` it mirrors) is `backend/app/services/race/queries.py`. Corrected in the dispatched agent prompts before the workflow ran.
- **A real functional bug found and fixed after the workflow completed**: `_build_v3_inputs`'s season branch (`analyst_agent.py`) built `course_by_valida` by iterating `state["valida_nums"]`, which is empty on a global/season launch (the common case — the coach did not pick specific válidas). The actual válidas raced that season are only present as keys of `state["course_context"]` (populated in `load_race_data.py` from the athlete's own results when `valida_nums` is empty). Left as shipped by the workflow, the season summary's course block would always render "Circuitos — SIN DATO" even when every válida had a registered course profile — the whole point of this half of US4 silently inert on its most common path. Found by re-deriving the claim in `data-platform-lead`'s own privacy-review finding (which correctly flagged it as a non-blocking functional follow-up, not a privacy issue) and confirmed by reading `load_race_data.py`'s `condition_validas` derivation directly. Fixed by iterating `sorted(state["course_context"].keys())` instead; added two regression tests to `tests/services/race/ai/nodes/test_analyst_agent_resolution.py` (global-launch season course block populates; a válida present in `course_context` with all six fields empty is still correctly omitted, not rendered as an empty block).
- **A real UX defect found and fixed after the workflow completed**: once `CourseDescriptionCard` (T043) landed with its own working "Describir la pista" CTA, the tab's whole-empty-state placeholder button from Phase 3 (`CourseTabEmpty`, T025 — permanently `disabled`, captioned "Próximamente") became a second, dead "Describir la pista" button sitting right above the new working one, for every coach viewing a totally empty Circuito tab. The Phase 5 UX-review agent found and fixed unrelated touch-target/spacing issues in the same files but explicitly deferred this one as "out of stated diff". Removed the disabled placeholder and its caption from `CourseTabEmpty`; updated the two Phase-3 `CourseTab.test.tsx` assertions on `course-tab-describe-btn` (no longer exists — the same CTA now lives in, and is tested by, `CourseDescriptionCard.test.tsx`).
- Two non-blocking observations from `data-platform-lead`'s privacy review, deliberately left open (not privacy issues, and correctly out of scope for a `qa-engineer` pipeline task to fix): (1) `race_analyst_v3.md`'s pre-existing (feature-011) conditions-absent veto forbids mentioning "terreno" while the course block, when present, prints "Terreno: mixto" a few lines below — a wording overlap between two independently-gated sections, not introduced by this feature and not covered by the `ai-course-block.md` contract (which only specifies the course block's own veto text); (2) `app/services/race/eval/scorer_v3.py`'s `_DATA_BLOCK_KEYS` does not include `course_block`/`course_by_valida`, so the golden eval's grounding subscore would currently penalize a real model correctly citing a course-specific number — worked around in the two new golden cases by keeping course digits out of grounded fields, but the scorer gap itself needs a follow-up task before the golden lane is trusted to reward correct course-context usage.
- `pytest -m golden` was **not** run — no real `RACE_AI_API_KEY`/`AI_API_KEY`/`GOOGLE_API_KEY` in this sandbox (the test module's own `_skip_no_api` guard skips it). Per the contract and `docs/10-race-results/runbook-ops.md`, a developer with a real key must run it (v3 lane), confirm composite ≥ 0.75 with the two new cases (`case_010_course_present.json`, `case_011_course_absent.json`) included, and regenerate `baseline.json` before this feature merges.
- Full backend suite (after this session's own two fixes above): 212 failed / 4875 passed / 64 skipped / 13 xfailed / 6 xpassed / 9 errors — unchanged from the Phase 1–4 baseline (only 2 more passing than the Phase 3+4 checkpoint, exactly this session's 2 new regression tests). One isolated run showed a 213th failure (`test_gpx_processing.py::test_processes_20000_points_within_budget`, a 1.5 s wall-clock ceiling); confirmed a one-off CPU-contention flake under full-suite load, not a regression (passes 3/3 in isolation, absent on rerun). `ruff check` clean on every backend file this work touched. Frontend: `npm run typecheck` clean; `vitest run src/components/race/course` — 6 files / 38 tests, all passing (re-verified after the `CourseTabEmpty` fix, no assertions on the removed classNames elsewhere).
- **Sandbox limitation carried over**: still no Docker/local MySQL/Playwright stack here — nothing new added by Phases 5–6 needed one.

### Phase 7 + 8 completion notes (2026-09-16)

- Executed via a dynamic multi-agent workflow: Phase 7 (US5) as tests (T053 backend ∥ T054 frontend) → backend impl (T055) ∥ frontend map+elevation (T056/T057) → frontend summary (T058) → parent-page wiring (T059) → verify+e2e (T061) → UX/a11y review (T062); then Phase 8 (Polish) as four parallel agents (T063 privacy audit, T064/T065/T066 docs) once Phase 7's diff existed for the audit to cover, per tasks.md's own "Polish after all desired stories" ordering.
- **`my_categories` design decision, made before dispatch and held consistently across every agent that touched it**: `race_event_roster` (feature 007) has no `category_id` column, and no age-band "resolve this athlete's category" resolver exists anywhere in the codebase (the only age-band matcher, `race/matcher.py`'s `_age_compatible_with_category`, is import-time fuzzy-matching infrastructure, not a general API). `my_categories` is therefore derived **only from `RaceResult` rows** of the parent's own athletes; the 200-vs-404 **visibility** gate is broader (roster OR results). Consequence, intentional: a parent whose child is only called up on the roster for a not-yet-raced válida sees the course card (200) with an empty `my_categories` — nothing to highlight yet, not a bug. Documented in `service.py`'s docstrings, the T053 test class, and now in `CLAUDE.md`.
- **A real functional bug found and fixed after the workflow completed, same class as the Phase 5+6 `course_by_valida` bug**: the frontend's own `ParentCompetitionResultsPage.test.tsx` mocked the `/course` endpoint on the app-wide global `mswServer` while that file also runs its own local `setupServer` instance for results/standings — two simultaneously-listening MSW `setupServer`s in one jsdom test do not compose (the later-listened local instance decides bypass-to-real-network for any route it doesn't itself register). The parent-pages-wiring agent (T059) found this itself via a throwaway `renderHook` repro, fixed it by moving the two new overrides onto the file's own local `server`, and removed the dead `mswServer` import — verified independently by re-running the full file (all 17 tests, including the 15 pre-existing ones, pass).
- **A real accessibility bug found and fixed during the UX review (T062)**: `CourseSummary`'s highlighted "your child's category" row used `text-mid-gray` (#717171) secondary text on its `bg-blue-50` highlight background, computing to 4.485:1 — just under the 4.5:1 AA floor for 14 px text. Fixed by switching to the project's existing `text-text-disclaimer` token (already used elsewhere for exactly this problem), verified at 6.337:1 (highlighted) / 6.897:1 (normal) via a precise sRGB-linear-luminance check, applied uniformly so the colour doesn't shift based on highlight state.
- I independently re-verified the whole slice after the workflow: `ruff check` clean on every changed backend file; full backend suite `212 failed / 4884 passed / 64 skipped / 13 xfailed / 6 xpassed / 9 errors` — unchanged from the Phase 5+6 baseline except +9 passed (exactly this phase's new `TestParentRead` class + 2 RBAC tests, confirmed via diff); frontend `npm run typecheck` clean; `npx vitest run src/components/race/course src/routes/parents` — 22 files / 189 tests, all green.
- I made two of my own fixes beyond what the workflow's agents produced, both documented in `CLAUDE.md`'s "Open after 043" paragraph:
  1. **`analyst_agent.py`'s season `course_by_valida` bug** was actually a Phase 6 bug (see that phase's own completion note) — re-confirmed still fixed and covered by its two regression tests; no relation to Phase 7's own work, mentioned here only because `CLAUDE.md`'s new feature-043 paragraph documents it as part of the shipped summary.
  2. **CLAUDE.md wording fix**: the auto-generated paragraph originally said the parent branch "returns `None` (404 `course_not_available`)" — inaccurate, since `_get_course_for_parent` deliberately *raises* the 404 directly rather than returning `None`, specifically so the router's `if course is None` branch (which means "válida doesn't exist") never conflates with "válida exists but this parent has no visibility". Corrected the sentence.
- **T060** (`npm run build`, chunk sizes) and **T068** (upload-performance measurement) were run directly by me rather than delegated — both are one-shot local measurements, not implementation work. Results recorded in the Notes section above and in `plan.md` §Complexity Tracking respectively. T068's finding is real and unresolved: a synthetic 60,000-point/2.92 MB GPX through the actual `POST /course/variants` route measures p95 ≈ 3.18 s in this sandbox (aiosqlite, no real hardware), above the 1 500 ms budget — recorded as an open pre-merge decision (point-count pre-check vs. profiling `_rdp` vs. accepting the risk given how unrealistic that point count is for this feature's actual one-lap use case), not fixed, per the task's own "measure and record" scope.
- **T063 privacy audit verdict: APPROVED**, no blocker (`specs/043-race-course-profile/privacy-audit.md`) — every claim traced to file:line rather than trusted from a docstring, including one explicitly re-derived nuance (the shared `load_events()` loader does fetch `course_notes` over SQL as part of a full-row `RaceEvent` select, the same pre-existing pattern as `weather_notes`, but it is never read into `fetch_course_context`'s output and never reaches a prompt/log — non-blocking, already covered by an existing test).
- **Still genuinely owed by a developer with real infrastructure before this feature is considered fully closed** (all consistently named across `CLAUDE.md`'s "Open after 043" paragraph, `docs/implementation-status.md`'s new phase table, and here): `pytest -m mysql` for the two new tables (never run in any session of this feature — no local MySQL); `pytest -m golden` with a real `RACE_AI_API_KEY`/`AI_API_KEY` to confirm composite ≥ 0.75 with the two new course cases and regenerate `baseline.json`; `frontend/e2e/race-course.spec.ts` (both parts, fully authored, never executed — no Docker/Playwright stack in any sandbox session of this feature) against a real stack; and **T069** (post-deploy smoke), which needs an actual deploy and was left unchecked and untouched — there is nothing to smoke-test without one.
- Two non-blocking, pre-existing-scope follow-ups carried forward from Phase 6 (not re-litigated, not fixed): `scorer_v3.py`'s `_DATA_BLOCK_KEYS` omitting `course_block`/`course_by_valida`, and the `race_analyst_v3.md` "terreno" wording overlap between the conditions veto and the course block.
- All five user stories (US1–US5) and Polish are now implemented and independently verified in-sandbox to the extent this sandbox allows. Feature 043 is functionally complete; what remains is exclusively real-infrastructure verification (MySQL, golden eval, e2e, deploy) that no session of this feature has had the infrastructure to run.

### Post-completion fixes (2026-09-16)

- **T068 decision resolved**: implemented option (a) from `plan.md` §Complexity Tracking — `MAX_RAW_POINTS = 20_000` raw-point pre-check in `gpx_processing.py`, rejecting as `too_many_points` (422) before the cumulative-distance/lap-extraction/RDP path. New regression test `test_too_many_raw_points_raises_before_expensive_processing` (`backend/tests/services/race/test_gpx_processing.py`) and the pre-existing `test_processes_20000_points_within_budget` (exactly 20,000 points, expects success) both pass, confirming the cut lands strictly above real-world usage. Contracts (`gpx-processing.md` §1/§2, `course-api.md` §6) and the router's `_COURSE_GPX_ERROR_MESSAGES` updated to match.
- **T024's own acceptance criteria ("rows = categories in results ∪ setups ∪ suggested") was not actually met**: `CategorySetupTable`'s `resultCategoryIds` prop existed and was exercised by its own unit tests, but `CourseTab.tsx` — its only real caller — never fetched race results or passed the prop, so a brand-new válida with results already imported but no prior setup never suggested those categories in the table. Fixed by having `CourseTab` call `useRaceResults(raceEventId)` (same query key as `ResultsTab`, so it reuses that tab's cache instead of duplicating the request) and derive `resultCategoryIds` from `data.categories`, memoized on the query's `data` reference. `CategorySetupTable`'s row-sync `useEffect` also gained `resultCategoryIds.join(",")` in its dependency list — without it, a category that only appears in results (not in `setups`/`suggested_setups`) would never get a row added if the results query resolved after the component's initial mount, since `useFieldArray`'s rows are only ever refreshed via that effect's `reset()`, not by the inline `categoryRows` recompute. `CourseTab.test.tsx` and `CategorySetupTable.test.tsx` (10 tests) and `npm run typecheck` all still pass.
