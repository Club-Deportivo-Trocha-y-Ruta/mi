---

description: "Task list for Technique & Gymkhana Library + Session Builder (feature 018)"
---

# Tasks: Technique & Gymkhana Library + Session Builder

**Input**: Design documents from `specs/018-technique-gymkhana-library/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rest-api.md, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE for this minors-data platform.

**Agent assignment**: each task is tagged `(@agent)` per plan.md Appendix A. `/speckit-implement` (dynamic workflow) dispatches each task to its specialized agent, parallelizing `[P]` tasks and respecting dependencies. Orchestrated by `engineering-lead`; `head-coach-lead` consulted for methodology; `technique-coach` + `sports-science-advisor` review seeded content; `data-privacy-guard` audits the per-athlete (US4) minors surface.

## Format: `[ID] [P?] [Story] Description (@agent)`

- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: US1–US5 from spec.md
- All product copy and seeded content in español neutro; this corpus in English.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 [P] Create backend scaffolding: `backend/app/services/technique/` package (`__init__.py`), empty `backend/app/routers/technique.py`, `backend/app/schemas/technique.py`, `backend/app/data/technique_catalog.py` stub (@fastapi-architect)
- [X] T002 [P] Create frontend scaffolding: `frontend/src/routes/technique/`, `frontend/src/components/technique/`, `frontend/src/api/technique.ts`, technique hooks dir (@react-ui-engineer)
- [X] T003 [P] Extract the seed payload from `docs/14-tecnica-gymkana-7-15/research.md` into `backend/app/data/technique_catalog.py`: A–H skill taxonomy (§2 table), materials list (§3 "Materiales base", incl. `sin_material`), the 24-exercise bank (§3 table: name, summary, how_to with NICA 4-step + mastery framing, difficulty, is_game, is_gymkhana, age bands, skill codes, material slugs), and the §4 circuit `layout_ascii` + a plain-language `layout_alt` for each gymkhana — español neutro **verbatim**, no invented content (@data-analyst)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [X] T004 Create SQLAlchemy models with `values_callable` enums: `backend/app/models/technique_skill.py`, `technique_material.py`, `technique_exercise.py` (exercise + `technique_exercise_age_bands`, `technique_exercise_skills` & `technique_exercise_materials` secondary tables, `technique_session_exercises`, `athlete_skill_progress`); add a back-ref collection on `TrainingSession`; register in `app/models/__init__.py` (@database-architect)
- [X] T005 Alembic migration (down_revision = current head `c2d3e4f5a6b7`): create all `technique_*` tables + `athlete_skill_progress` with FKs (session link CASCADE, exercise/skill RESTRICT), indexes, and an **idempotent data seed** from `technique_catalog.py` (skip if any exercise exists; `is_seeded=true`); mirror `c4d5e6f7a8b9_seed_race_categories.py` (@database-architect)
- [X] T006 [P] Pydantic schemas in `backend/app/schemas/technique.py`: `ExerciseListItem`, `ExerciseDetail`, catalog `FilterParams`, `AssembleSessionRequest`/`Response`, `TechniqueSessionItem`, `SkillProgressEvent`/`Read`, curation `ExerciseCreate`/`Update` (gymkhana⇒layout, ≥1 age band, ≥1 skill validators) (@fastapi-architect)
- [X] T007 Register `technique` router under `/api/technique` in `app/main.py`; add a coach/admin + club-scope RBAC dependency reusing `services/permissions.py` (@fastapi-architect)
- [X] T008 [P] Catalog filter service `backend/app/services/technique/catalog.py`: list/filter by skill/age_band/difficulty + materials **subset** (`NOT EXISTS`, `sin_material` always matches) + `include_hidden`, eager-load skills/materials/age_bands with `selectinload` (@fastapi-architect)

**Checkpoint**: schema + models + seed + router foundation ready — user stories can begin.

---

## Phase 3: User Story 1 — Browse & search the catalog (Priority: P1) 🎯 MVP

**Goal**: A coach gets a pre-seeded, filterable reference library of age-appropriate drills.

**Independent Test**: Sign in as coach, open the catalog (pre-seeded ~24), apply skill/age/difficulty/material filters (alone + combined), confirm only matches show and a clear empty state otherwise.

### Tests

- [X] T009 [P] [US1] Backend test `backend/tests/technique/test_catalog_filter.py`: filter matrix (skill, age_band, difficulty, material subset incl. `sin_material`, combined) + empty-filter returns `200` empty list (not 404/500) (@qa-engineer)
- [X] T010 [P] [US1] Backend test `backend/tests/technique/test_rbac.py`: catalog read endpoints deny parent/athlete/cross-club (`403`) and allow coach/admin (@qa-engineer)

### Implementation

- [X] T011 [US1] Endpoints in `routers/technique.py`: `GET /exercises` (list+filter via catalog service), `GET /skills`, `GET /materials` (@fastapi-architect)
- [X] T012 [P] [US1] API client + `useTechniqueCatalog`/`useSkills`/`useMaterials` TanStack Query hooks in `frontend/src/api/technique.ts` + hooks (aggressive cache; cold-start aware) (@react-ui-engineer)
- [X] T013 [P] [US1] `FilterBar` component (skill/age/difficulty/materials) with RHF + localized labels, 48×48 targets in `frontend/src/components/technique/FilterBar.tsx` (@react-ui-engineer)
- [X] T014 [US1] `CatalogGrid` + `ExerciseCard` + `CatalogPage` route with loading/empty-filter/error/"servidor iniciando" states in `frontend/src/routes/technique/CatalogPage.tsx` (@react-ui-engineer)
- [X] T015 [P] [US1] Frontend tests: `FilterBar` branching + `CatalogGrid` empty state + `jest-axe` (@qa-engineer)
- [X] T016 [US1] Lazy route + coach/admin nav entry for `/technique` in `frontend/src/App.tsx` (@react-ui-engineer)
- [ ] T017 [US1] UX review: filter discoverability and empty/cold-start states on tablet over 3G (@ux-researcher)

**Checkpoint**: US1 independently functional — a usable filterable reference library.

---

## Phase 4: User Story 2 — Exercise detail with illustrative layout (Priority: P1)

**Goal**: Each exercise opens to a runnable card with skill/age/difficulty/materials, "cómo correrlo", and an illustrative circuit layout.

**Independent Test**: Open any seeded exercise; confirm full detail + (for gymkhana) the ASCII circuit layout with a screen-reader text alternative; a no-equipment exercise clearly says "sin material".

### Tests

- [X] T018 [P] [US2] Backend test `backend/tests/technique/test_exercise_detail.py`: `GET /exercises/{id}` returns full detail incl. non-null `layout_ascii`/`layout_alt` for gymkhana; `404` unknown id; `sin_material` surfaced (@qa-engineer)

### Implementation

- [X] T019 [US2] `GET /exercises/{id}` detail endpoint in `routers/technique.py` (@fastapi-architect)
- [X] T020 [P] [US2] `useTechniqueExercise(id)` hook + api (@react-ui-engineer)
- [X] T021 [US2] `CircuitLayout` component: responsive monospace `<pre>` (horizontal scroll), `role="img"` + visually-hidden `layout_alt`, shared legend in `frontend/src/components/technique/CircuitLayout.tsx` (@react-ui-engineer)
- [X] T022 [US2] `ExerciseDetailPage` route rendering skill/age/difficulty/materials/how_to + `CircuitLayout` (@react-ui-engineer)
- [X] T023 [P] [US2] Frontend test: `ExerciseDetailPage`/`CircuitLayout` exposes the text alternative + `jest-axe` (@qa-engineer)
- [ ] T024 [US2] A11y/legibility review of the layout on small screens (contrast, scroll, font) (@ux-researcher)

**Checkpoint**: US1+US2 deliver a complete field reference.

---

## Phase 5: User Story 3 — Assemble a session via the existing Training Sessions module (Priority: P1)

**Goal**: Selected exercises become a normal club training session (calendar/list, attendance, rubric) — no parallel store.

**Independent Test**: Assemble ≥2 exercises into segments, save, confirm a real `TrainingSession` appears in the existing list with the exercises listed and attendance/rubric available; mixing age bands saves with a visible notice.

### Tests

- [X] T025 [P] [US3] Backend test `backend/tests/technique/test_assemble_session.py`: `POST /sessions` creates a **real `TrainingSession`** (retrievable via existing `/api/training-sessions/{id}`), writes `technique_session_exercises`, returns `mixes_age_bands`; `422` on empty items/unknown exercise (@qa-engineer)
- [X] T026 [P] [US3] Backend test `backend/tests/technique/test_session_exercises.py`: `GET /sessions/{id}/exercises` returns ordered items grouped by segment and stays intact after an exercise is later hidden/edited (FR-020) (@qa-engineer)

### Implementation

- [X] T027 [US3] Assembler service `backend/app/services/technique/assembler.py`: reuse `training_svc.create_session`, write join rows in one transaction, compute `mixes_age_bands` (@fastapi-architect)
- [X] T028 [US3] `POST /sessions` + `GET /sessions/{id}/exercises` endpoints (@fastapi-architect)
- [X] T029 [P] [US3] `useAssembleTechniqueSession` hook + api (@react-ui-engineer)
- [X] T030 [US3] `SessionAssembler` component: place exercises into calentamiento/principal/vuelta_calma with ordering; `MixedAgeNotice` banner (@react-ui-engineer)
- [X] T031 [US3] `SessionBuilderPage`: assemble → save → confirm it shows in the existing session list; keep the flow under 3 minutes (@react-ui-engineer)
- [X] T032 [P] [US3] Frontend test: `SessionAssembler` segments + mixed-age notice + `jest-axe` (@qa-engineer)
- [ ] T033 [US3] UX review: validate the find-and-assemble flow completes in <3 min on a tablet (SC-001) (@ux-researcher)

**Checkpoint**: P1 MVP complete (US1–US3) — browse, view, and schedule technique sessions.

---

## Phase 6: User Story 4 — Per-athlete skill progress (Priority: P2, minors data)

**Goal**: Record/review per-skill progress (introducido/en progreso/dominado) across the season as individual growth — never comparative.

**Independent Test**: Set and later change a skill status for one athlete; view current status per skill + season evolution; confirm no surface compares athletes; a 7–9 rider without a record degrades gracefully.

### Tests

- [X] T034 [P] [US4] Backend test `backend/tests/technique/test_progress.py`: `POST` appends an event; `GET` returns current (latest per skill) + season history; `404` when the athlete has no record (graceful 7–9) (@qa-engineer)
- [X] T035 [P] [US4] Privacy invariant test `backend/tests/technique/test_progress_privacy.py`: a progress response contains ONLY that athlete (no second athlete/no ranking), no minor PII in logs, and no aggregate/comparison endpoint exists (SC-005/SC-007) (@qa-engineer)

### Implementation

- [X] T036 [US4] Progress service `backend/app/services/technique/progress.py`: append event; compute current + season history (@fastapi-architect)
- [X] T037 [US4] `GET`/`POST /athletes/{id}/progress` endpoints, coach/admin only, `404` graceful for no-record (@fastapi-architect)
- [X] T038 [P] [US4] `useAthleteSkillProgress` hook + api (@react-ui-engineer)
- [X] T039 [US4] `SkillProgressBoard` component (lazy-loaded): current status per skill + season evolution, anchored to biological age, **no comparison/leaderboard UI** (@react-ui-engineer)
- [X] T040 [US4] `AthleteProgressPage` wiring (coach/admin only) + graceful no-record state (@react-ui-engineer)
- [X] T041 [P] [US4] Frontend test: `SkillProgressBoard` shows status + history and asserts absence of any comparison element + `jest-axe` (@qa-engineer)
- [X] T042 [US4] Minors-privacy audit: no PII in logs, coach-only RBAC, zero comparison surface across views/exports (SC-005/SC-007) (@data-privacy-guard)

**Checkpoint**: per-athlete technical progress is visible and individual.

---

## Phase 7: User Story 5 — Curate the catalog (Priority: P3)

**Goal**: Coach/admin add/edit/hide exercises without destroying curated content or corrupting saved sessions.

**Independent Test**: Add a custom exercise (appears in filters), edit a seeded one (persists), hide one (drops from default catalog, not destroyed; a saved session referencing it stays intact).

### Tests

- [X] T043 [P] [US5] Backend test `backend/tests/technique/test_curation.py`: create/edit (incl. seeded)/hide; hidden drops from default catalog but is not destroyed; a saved session referencing a hidden exercise remains viewable (FR-019/FR-020) (@qa-engineer)

### Implementation

- [X] T044 [US5] `POST /exercises`, `PUT /exercises/{id}`, `PATCH /exercises/{id}/visibility` endpoints with validation (gymkhana⇒layout, ≥1 age band, ≥1 skill) (@fastapi-architect)
- [X] T045 [P] [US5] Curation hooks (create/update/visibility) + api with cache invalidation (@react-ui-engineer)
- [X] T046 [US5] `ExerciseForm` (RHF + Zod) + CatalogAdmin actions (add/edit/hide) on the catalog (@react-ui-engineer)
- [X] T047 [P] [US5] Frontend test: `ExerciseForm` validation + hide flow + `jest-axe` (@qa-engineer)

**Checkpoint**: the catalog is a living, club-specific resource.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T048 [P] Methodology review: seeded exercises embody the non-negotiables (fun first, skills > fitness, cadence ≥70, **never** <60 rpm, no structured intervals 7–9, mastery climate) (@technique-coach)
- [X] T049 [P] Sports-science review: age-band appropriateness and LTAD/PHV framing of progress and difficulty-vs-age warnings (@sports-science-advisor)
- [X] T050 [P] Performance pass: query-count test asserting no N+1 on catalog list (selectinload); confirm `SkillProgressBoard` is lazy-loaded and route bundle within budget (@qa-engineer)
- [X] T051 [P] Docs: add a module doc under `docs/` cross-linking `docs/14-tecnica-gymkana-7-15/research.md`; add a row to `docs/implementation-status.md` and the CLAUDE.md status table (@technical-writer)
- [ ] T052 Run the seed migration on Render + smoke test (catalog populated, coach-only access, cold-start banner) (@devops-engineer / @release-manager)
- [ ] T053 Execute quickstart.md end-to-end validation (Scenarios 1–5, SC trace) (@qa-engineer)

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → **Phase 2 (Foundational)** block everything. T004 (models) blocks T005/T006/T008; T003 (seed payload) blocks T005 (seed migration).
- **User stories**: US1, US2, US5 depend only on the foundation. **US3** depends on the existing Training Sessions module (present) + US1 selection UI. **US4** is independent (own tables) but is the only minors surface (privacy audit T042 gates it).
- **MVP = Phase 1 + Phase 2 + US1 (Phase 3)**. P1 increment = US1+US2+US3. US4 (P2) and US5 (P3) layer on after.
- **Polish (Phase 8)** runs after the stories it reviews; T052 deploy is last.

## Parallel Execution Examples

- **Setup**: T001, T002, T003 in parallel (different trees).
- **Foundational**: after T004, run T006 and T008 in parallel.
- **US1**: T009/T010 (tests) ∥ T012/T013 (frontend) while T011 (endpoints) proceeds; T015 ∥ once components exist.
- **Per story**: every `[P]` test/frontend task runs concurrently with same-story backend work in different files.
- **Reviews**: T048 and T049 (content/science) run in parallel during Phase 8.

## Implementation Strategy (MVP first)

1. Ship **US1** (catalog browse/filter) on top of the seeded foundation — immediately useful alone.
2. Add **US2** (detail + layout) → a complete field reference.
3. Add **US3** (assemble via existing sessions) → reference becomes planning. **This is the P1 release.**
4. Layer **US4** (per-athlete progress, P2) behind the privacy audit.
5. Layer **US5** (curation, P3) to keep the library living.
