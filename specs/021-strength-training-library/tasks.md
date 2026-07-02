---
description: "Task list for Strength Training Exercise Library (021)"
---

# Tasks: Strength Training Exercise Library

**Input**: Design documents from `/specs/021-strength-training-library/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/strength-api.md, quickstart.md

**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE for this project; every router/service/permission gets happy + negative path, every page-level component gets vitest + jest-axe.

**Organization**: By user story (US1 P1 → US4 P3). Pattern mirrors feature 018 (technique-gymkhana-library) 1:1 under `strength/` naming.

**Implementation crew**: tasks intended for execution by **Sonnet 5** agents. Each task is self-contained with exact paths; a `[P]` task touches files no other in-flight task touches.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US4 (user-story phases only)

## Path Conventions

Web app — `backend/app/...`, `backend/tests/...`, `frontend/src/...`. Migration `backend/alembic/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directories, router registration, frontend scaffolding — no business logic yet.

- [ ] T001 Create backend dirs `backend/app/services/strength/` (with `__init__.py`) and `backend/tests/strength/` (with `__init__.py`); create frontend dirs `frontend/src/routes/strength/`, `frontend/src/components/strength/`, `frontend/src/hooks/strength/`
- [ ] T002 [P] Register router in `backend/app/main.py`: add `from app.routers import strength` and `app.include_router(strength.router, prefix="/api/strength", tags=["strength"])`; create `backend/app/routers/strength.py` with an `APIRouter` and the `_require_coach_or_admin = require_role([UserRole.admin, UserRole.coach])` dependency (mirror `routers/technique.py:79`)
- [ ] T003 [P] Frontend scaffolding: `frontend/src/api/strength.ts` (`BASE = "/api/strength"` apiClient wrappers), `frontend/src/types/strength.types.ts`, `frontend/src/schemas/strength.schemas.ts` (empty Zod stubs), `frontend/src/hooks/strength/useStrength.ts` (`strengthKeys` key-factory skeleton), `frontend/src/test/msw/strengthHandlers.ts` (empty array), and lazy route registration block in `frontend/src/App.tsx` wrapped in `<ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>` (mirror technique block :614-698)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models, schemas, seed data, migration — every user story depends on the catalog + block tables existing.

**⚠️ CRITICAL**: No user story work begins until this phase completes.

- [ ] T004 Create `backend/app/models/strength.py`: enums `EquipmentKind` (`sin_equipo`/`equipo_gym`), `MovementCategory` (5 values), `StrengthProgressStatus` (`introducido`/`en_progreso`/`dominado`) via `SAEnum(values_callable=...)`; reuse `AgeBand` from `app.models.technique_exercise`; ORM tables `StrengthExercise`, `StrengthExerciseAgeBand`, `StrengthBlock`, `StrengthBlockEntry`, `StrengthSessionBlock`, `StrengthProgressNote` with columns/indexes/FK rules per data-model.md (note FK RESTRICT on block-entry→exercise and session-block→block; CASCADE on session-block→training_session)
- [ ] T005 [P] Create `backend/app/schemas/strength.py`: Pydantic v2 schemas `ExerciseOut`, `ExerciseDetailOut`, `BlockEntryIn`/`EntryOut`, `BlockCreate`/`BlockUpdate`/`BlockOut` (incl. computed `total_duration_min`), `AttachIn`/`AttachOut`, `ProgressIn`/`ProgressOut` per contracts/strength-api.md
- [ ] T006 [P] Create `backend/app/data/strength_catalog.py`: `EXERCISES` list (~22 rows: slug/name/summary/how_to/common_errors/illustration_ascii/illustration_alt/equipment/equipment_detail/movement_category/suggested_duration_min/suggested_reps/age_bands) honoring SC-007 distribution (every non-empty facet combo ≥1; `equipo_gym × 10-12` intentionally empty); EXCLUDE clean/snatch/deadlift/back-squat and 1RM protocols (FR-019). Original ASCII figures + Spanish alt text
- [ ] T007 Create Alembic migration `backend/alembic/versions/a7b8c9d0e1f2_strength_training_library.py` (`down_revision = "f1a2b3c4d5e6"`): `upgrade()` creates all 6 tables + indexes per data-model.md; `downgrade()` drops them in FK-safe order
- [ ] T008 Extend migration `a7b8c9d0e1f2` `upgrade()` to seed from `app.data.strength_catalog`: build slug→id maps, bulk-insert exercises + age-band child rows, idempotent by `slug` (mirror `e1f2a3b4c5d6` seed loop); verify `alembic upgrade head` then `alembic downgrade -1` round-trips clean
- [ ] T009 [P] Create `backend/tests/strength/conftest.py`: fixtures for coach/admin/parent JWT tokens, a seeded club, and an async client over aiosqlite (mirror `tests/technique/conftest.py`)

**Checkpoint**: Schema + seed live; RBAC dep wired; frontend shell routes resolve. User stories can begin.

---

## Phase 3: User Story 1 - Browse & search the illustrated catalog (Priority: P1) 🎯 MVP

**Goal**: Coach browses/searches/filters an illustrated strength catalog by equipment + age band, opens a detail with execution steps and common errors. Zero third-party photos.

**Independent Test**: Filter `sin_equipo` + `10-12` → only matching bodyweight exercises, each with ASCII illustration + guidance; free-text `q` respects filters; empty facet combo shows empty state.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [ ] T010 [P] [US1] Backend catalog filter + free-text search test in `backend/tests/strength/test_catalog_filter.py` (facets combinable, `q` LIKE over name+summary, hidden excluded, `{items,total}` shape)
- [ ] T011 [P] [US1] Backend exercise-detail + 404 test in `backend/tests/strength/test_exercise_detail.py` (full detail fields present; 404 for missing/hidden)
- [ ] T012 [P] [US1] Backend query-count / N+1 test in `backend/tests/strength/test_perf_queries.py` (catalog list eager-loads age_bands via selectinload; bounded query count)

### Implementation for User Story 1

- [ ] T013 [US1] Implement `backend/app/services/strength/catalog.py`: `_exercise_select()` with `selectinload(age_bands)`, combinable `.where()` for equipment/age_band/movement_category + `q` LIKE, `include_hidden` gate (mirror `services/technique/catalog.py`)
- [ ] T014 [US1] Implement `GET /exercises` and `GET /exercises/{exercise_id}` in `backend/app/routers/strength.py` (list returns card fields + `total`; detail adds how_to/common_errors/illustration_*; 404 rules)
- [ ] T015 [P] [US1] Add `useStrengthCatalog(filters)` + `useStrengthExercise(id)` + `usestrengthKeys` entries in `frontend/src/hooks/strength/useStrength.ts`; wire `api/strength.ts` + Zod response parse in `schemas/strength.schemas.ts`
- [ ] T016 [P] [US1] Build `frontend/src/components/strength/CatalogGrid.tsx`, `ExerciseCard.tsx`, `FilterBar.tsx` (equipment/age_band/movement_category + free-text), `ExerciseIllustration.tsx` (`<pre>` ASCII wrapped `role="img"` + `aria-label` from `illustration_alt`; 018 `CircuitLayout` fallback pattern)
- [ ] T017 [US1] Build `frontend/src/routes/strength/CatalogPage.tsx` (loading/empty/error states incl. sparse-combo empty message) and `ExerciseDetailPage.tsx`
- [ ] T018 [P] [US1] Add MSW handlers for `GET /exercises*` in `frontend/src/test/msw/strengthHandlers.ts`; vitest tests for `FilterBar`, `CatalogPage`, and `ExerciseIllustration` (jest-axe zero violations) under `frontend/src/components/strength/__tests__/` + `frontend/src/routes/strength/__tests__/`

**Checkpoint**: US1 fully functional — catalog is a usable field reference on its own (MVP).

---

## Phase 4: User Story 2 - Assemble a time-boxed block & attach to a session (Priority: P2)

**Goal**: Coach assembles a named strength block with a live within/at/over-30-min indicator, per-entry duration/reps, then attaches it (reusable) to a training session.

**Independent Test**: Build block, watch running total cross 29/30/31 min thresholds, save, reopen intact; attach to a session (appears in plan), attach to a 2nd (allowed), re-attach same (409), delete session (block survives).

### Tests for User Story 2 ⚠️

- [ ] T019 [P] [US2] Backend block CRUD + `total_duration_min` + position reindex test in `backend/tests/strength/test_blocks.py`
- [ ] T020 [P] [US2] Backend attach/detach test in `backend/tests/strength/test_attach.py` (201, 409 duplicate, session-delete leaves block via RESTRICT, GET sessions/{id}/blocks)

### Implementation for User Story 2

- [ ] T021 [US2] Implement `backend/app/services/strength/blocks.py`: create/update/list/archive, entries re-positioned 0..n-1, `total_duration_min = Σ duration_min`, club scope (no guardrail yet — added in US3)
- [ ] T022 [US2] Implement block endpoints in `backend/app/routers/strength.py`: `POST/GET/GET{id}/PUT /blocks`, `PATCH /blocks/{id}/archive`, `POST /blocks/{id}/attach`, `DELETE /blocks/{id}/attach/{sid}`, `GET /sessions/{sid}/blocks` per contract
- [ ] T023 [US2] Add back-populated `strength_blocks` relationship on `TrainingSession` in `backend/app/models/training_session.py` (additive only; table untouched)
- [ ] T024 [P] [US2] Add block query/mutation hooks (`useStrengthBlock`, `useStrengthBlocks`, `useSaveBlock`, `useAttachBlock`, `useSessionBlocks`) to `frontend/src/hooks/strength/useStrength.ts` with cache invalidation
- [ ] T025 [P] [US2] Build `frontend/src/components/strength/BlockAssembler.tsx`: running total + within (verde) / at (ámbar) / over (ámbar, non-blocking) indicator using consistent status tokens; per-entry duration/reps editors
- [ ] T026 [US2] Build `frontend/src/routes/strength/BlockBuilderPage.tsx` + attach-to-session picker UI
- [ ] T027 [P] [US2] MSW handlers for block/attach endpoints; vitest tests: `BlockAssembler` duration boundaries (29/30/31 min) + attach flow, jest-axe on BlockBuilderPage

**Checkpoint**: US1 + US2 both work independently — coach can plan and attach blocks.

---

## Phase 5: User Story 3 - Age-band safety guardrail (Priority: P2)

**Goal**: Adding an age-inappropriate exercise to a block warns with a Spanish explanation and blocks until explicit override, which is recorded.

**Independent Test**: Target `10-12` block, add a `13-15`-only exercise → 422 `AGE_BAND_GUARDRAIL` without override; resubmit with `is_age_override=true` → 201, entry flagged; UI dialog cancel leaves block unchanged.

### Tests for User Story 3 ⚠️

- [ ] T028 [P] [US3] Backend guardrail test in `backend/tests/strength/test_guardrail.py` (422 `AGE_BAND_GUARDRAIL` on mismatch w/o override; 201 + persisted `is_age_override`/`override_note` with override; matching band never triggers)

### Implementation for User Story 3

- [ ] T029 [US3] Extend `backend/app/services/strength/blocks.py`: on entry add/update where exercise bands ∌ block `target_age_band`, require `is_age_override=true` else raise 422 with Spanish detail + `AGE_BAND_GUARDRAIL` code; persist override fields on the entry
- [ ] T030 [P] [US3] Build `frontend/src/components/strength/AgeBandGuardrailDialog.tsx` (warn-and-allow, Spanish explanation, focus-trapped, Escape-dismissible, optional `override_note`)
- [ ] T031 [US3] Wire the dialog into `BlockAssembler` add-entry flow: catch 422, show dialog, resubmit with `is_age_override` on confirm; mark overridden entries visually
- [ ] T032 [P] [US3] Vitest test for the guardrail dialog flow (warn → cancel → unchanged; warn → confirm → override) + jest-axe

**Checkpoint**: Safety spine active — 10-12 blocks default to bodyweight-only unless the coach records an override (SC-004).

---

## Phase 6: User Story 4 - Per-athlete progress notes, coach-only (Priority: P3)

**Goal**: Coach records/updates per-athlete strength progress notes; no athlete-to-athlete comparison anywhere.

**Independent Test**: Record `en_progreso` + note; latest-status shown on reopen; parent login → all `/api/strength/*` 403; no comparison view exists.

### Tests for User Story 4 ⚠️

- [ ] T033 [P] [US4] Backend progress + privacy test in `backend/tests/strength/test_progress_privacy.py` (append-only, latest-per-exercise read, no athlete PII in responses/logs, club-scope 403)

### Implementation for User Story 4

- [ ] T034 [US4] Implement `backend/app/services/strength/progress.py`: append note, latest-per-`(athlete,exercise)` read, `_require_athlete_club_scope` (mirror `technique.py:417`)
- [ ] T035 [US4] Implement `GET/POST /athletes/{athlete_id}/progress` in `backend/app/routers/strength.py`
- [ ] T036 [P] [US4] Add progress hooks (`useAthleteStrengthProgress`, `useAddStrengthProgress`) to `frontend/src/hooks/strength/useStrength.ts`
- [ ] T037 [US4] Build `frontend/src/components/strength/ProgressNotesBoard.tsx` + `frontend/src/routes/strength/AthleteProgressPage.tsx` (mastery-climate copy; NO comparison/leaderboard surface)
- [ ] T038 [P] [US4] MSW handlers + vitest test for `ProgressNotesBoard` (persist + latest-wins; assert no two-athlete comparison rendered) + jest-axe

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T039 [P] Backend RBAC negative-path test spanning all endpoints in `backend/tests/strength/test_rbac.py` (parent/athlete/unauth → 401/403 on catalog, blocks, attach, progress)
- [ ] T040 [P] Run `quickstart.md` scenarios 1–5 end-to-end against local stack; fix gaps
- [ ] T041 [P] Update `docs/implementation-status.md` and the CLAUDE.md status table with a feature 021 row (migration `a7b8c9d0e1f2`, deploy-pending)
- [ ] T042 Lint/type gate: `ruff` + `mypy` (backend), `eslint` + `tsc --noEmit` (frontend) clean; fix findings
- [ ] T043 Verify Constitution IV budgets: strength routes lazy-loaded ≤150 KB gzipped each; catalog query-count test green; no static import of heavy modules into shared layout

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: immediate.
- **Foundational (P2)**: after Setup — **BLOCKS all user stories**. Within P2: T004 → T005/T006 ([P], depend on models) → T007 → T008 (same migration file, sequential) ; T009 [P] after T004.
- **US1 (P3)**: after Foundational. **MVP.**
- **US2 (P4)**: after Foundational. Independent of US1 (different files); may demo alongside.
- **US3 (P5)**: after US2 (extends `blocks.py` + `BlockAssembler`).
- **US4 (P6)**: after Foundational. Independent of US1–US3.
- **Polish (P7)**: after all targeted stories.

### Within Each Story

Tests written first and FAIL → services → endpoints → frontend hooks → components → pages. Models before services (models are in Foundational).

### Parallel Opportunities

- Setup: T002, T003 in parallel.
- Foundational: T005, T006 in parallel after T004; T009 in parallel.
- US1: T010/T011/T012 (tests) in parallel; then T015/T016 in parallel; T018 in parallel with page work.
- US2: T019/T020 parallel; T024/T025 parallel.
- US4 is fully parallel to US1/US2/US3 if staffed separately.
- **Cross-story parallelization for a Sonnet-5 crew**: after Foundational, assign US1, US2, US4 to three concurrent agents; US3 follows US2 on the same agent.

---

## Parallel Example: User Story 1 (Sonnet-5 agents)

```bash
# Tests first, in parallel:
Task: "T010 catalog filter+search test backend/tests/strength/test_catalog_filter.py"
Task: "T011 exercise detail+404 test backend/tests/strength/test_exercise_detail.py"
Task: "T012 N+1 query-count test backend/tests/strength/test_perf_queries.py"

# Then implementation, parallel where files differ:
Task: "T015 catalog hooks frontend/src/hooks/strength/useStrength.ts"
Task: "T016 CatalogGrid/ExerciseCard/FilterBar/ExerciseIllustration components"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → **STOP & VALIDATE** (catalog usable as field reference) → demo.

### Incremental Delivery

Foundation → US1 (MVP catalog) → US2 (blocks + attach) → US3 (guardrail) → US4 (progress) → Polish. Each story ships without breaking the prior.

### Parallel Team Strategy (Sonnet-5 crew)

After Foundational: Agent A → US1, Agent B → US2 then US3, Agent C → US4. Converge on Polish (T039–T043).

---

## Task Count Summary

- **Total**: 43 tasks
- Setup: 3 · Foundational: 6 · US1: 9 · US2: 9 · US3: 5 · US4: 6 · Polish: 5
- **Tests**: 10 dedicated test tasks (backend + frontend), plus a11y (jest-axe) folded into component tasks
- **MVP scope**: Phases 1–3 (Setup + Foundational + US1) = 18 tasks

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Every user story is independently completable/testable.
- Commit after each task or logical group (Conventional Commits, español latino, no AI mention).
- No new runtime dependencies (Constitution stack discipline).
- Migration chains off head `f1a2b3c4d5e6`; seed carried in-migration (runs in prod via entrypoint.sh).
