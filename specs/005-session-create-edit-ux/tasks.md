---
description: "Task list for Session Create/Edit Flow & UX Overhaul"
---

# Tasks: Session Create/Edit Flow & UX Overhaul

**Input**: Design documents from `/specs/005-session-create-edit-ux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/training-session-api.md

**Tests**: INCLUDED — the project constitution (Principle II) makes tests non-negotiable,
including a regression test for the persistence bug and privacy invariants.

**Organization**: Tasks grouped by user story (P1 → P2). User Story 5 (clone/prefill/review)
is OUT OF SCOPE per clarification and intentionally has no tasks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 (maps to spec.md user stories)
- All paths are repo-relative.

## Path Conventions

Web app: `backend/app/**`, `backend/tests/**`, `frontend/src/**`, `frontend/test/**`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding for the wizard and type/contract sanity.

- [ ] T001 [P] Create the wizard component folder `frontend/src/components/training/session-wizard/` with an `index.ts` barrel (empty re-exports for now).
- [ ] T002 [P] Verify `frontend/src/types/trainingSession.types.ts` already exposes `session_kind` and `objectives` on `TrainingSession`, `TrainingSessionCreate`, `TrainingSessionUpdate` (it does — confirm, no change needed) and note `SessionKind` is exported.
- [ ] T003 [P] Add a shared Strava URL constant `STRAVA_ACTIVITY_RE = /^https:\/\/www\.strava\.com\/activities\/\d+$/` in `frontend/src/schemas/trainingSession.schema.ts` (replaces the looser local regex; matches the backend rule).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The wizard shell, per-step schema split, and the draft hook that ALL stories build on.

**⚠️ CRITICAL**: No user-story phase can start until this phase is complete.

- [ ] T004 Refactor `frontend/src/schemas/trainingSession.schema.ts`: keep the single `trainingSessionCreateSchema` but add per-step field-name arrays (`STEP_GENERAL_FIELDS`, `STEP_ATHLETES_FIELDS`, `STEP_ROUTE_NOTES_FIELDS`) and add `coach_notes` (optional, ≤2000) to the schema; export `SESSION_KIND_OPTIONS` unchanged.
- [ ] T005 [P] Create `frontend/src/hooks/useFormDraft.ts`: debounced (~800 ms) `localStorage` autosave + restore keyed `tyr:session-draft:v1:{userId}:{new|<id>}`, storing `{version, values, step, updatedAt}`; SSR/quota-guarded try/catch; exposes `{restoreCandidate, saveDraft, clearDraft}`; never logs values.
- [ ] T006 Create `frontend/src/components/training/session-wizard/SessionStepper.tsx` (numbered stepper with `aria-current="step"`, reusing the `ImportWizard` visual pattern; ≥48 px tap areas on step controls).
- [ ] T007 Create `frontend/src/components/training/session-wizard/SessionWizard.tsx` shell: single `useForm` instance (`mode: "onTouched"`, `noValidate`), `step` state, Back/Next using `await trigger(fieldsForStep, {shouldFocus:true})`, mounts placeholder step bodies, renders `SessionStepper`. Accepts `mode` + optional loaded session/attendance defaults.
- [ ] T008 Rewrite `frontend/src/routes/training/SessionFormPage.tsx` to be a thin host: load session + attendance for edit mode (existing hooks), build default values (incl. `session_kind`, `objectives`, `coach_notes`), and mount `SessionWizard`; preserve cancel-confirm-if-dirty.
- [ ] T009 [P] Add MSW handlers/fixtures for create/update echoing `session_kind`/`objectives`/`coach_notes` in `frontend/test/msw/` (extend existing training-session handlers).

**Checkpoint**: Empty 4-step wizard renders for create and edit; draft hook + per-step schema available.

---

## Phase 3: User Story 1 — Persist every field + draft resilience (Priority: P1) 🎯 MVP

**Goal**: Every shown field (incl. `session_kind`, `objectives`) round-trips end-to-end, and unsaved work survives interruption.

**Independent Test**: Create a session setting kind+objectives, save, reopen → values persist. Fill partially, reload → restore brings everything back.

### Tests for User Story 1 ⚠️ (write first, must fail on current code)

- [ ] T010 [P] [US1] Backend regression test in `backend/tests/routers/test_training_sessions_fields.py`: POST with `session_kind="salida"` + `objectives` → 201 echoes both; GET detail round-trips. (Fails pre-fix.)
- [ ] T011 [P] [US1] Backend test in same file: PATCH `session_kind`/`objectives` persists; omitting `session_kind` on create defaults to `entrenamiento`; `objectives` >1000 → 422.
- [ ] T012 [P] [US1] Backend privacy test in `backend/tests/routers/test_training_sessions_privacy.py`: create/update with `send_notification=true` writes no athlete name to logs (caplog assertion).
- [ ] T013 [P] [US1] Frontend test `frontend/test/training/sessionDraft.test.tsx`: autosave then reload offers restore; restore repopulates all fields; successful save clears draft; discard clears draft.

### Implementation for User Story 1

- [ ] T014 [P] [US1] Add `session_kind: SessionKind | None` and `objectives: str | None = Field(default=None, max_length=1000)` to `TrainingSessionCreate` and `TrainingSessionUpdate` in `backend/app/schemas/training_session.py`.
- [ ] T015 [P] [US1] Add `session_kind` and `objectives` to `TrainingSessionRead` and `TrainingSessionReadParent` in `backend/app/schemas/training_session.py`.
- [ ] T016 [US1] In `backend/app/services/training/sessions.py::create_session`, set `session_kind` (fallback to model default when `None`) and `objectives` on the `TrainingSession`; add `_FIELD_LABELS` entries "Tipo de sesión" and "Objetivos" for the update diff. (depends on T014)
- [ ] T017 [US1] Wire draft autosave/restore into `SessionWizard.tsx` via `useFormDraft`: subscribe `watch`, render a non-blocking restore banner (Restaurar/Descartar), call `reset()` on restore, `clearDraft()` on successful save. (depends on T005, T007)
- [ ] T018 [US1] Ensure full create/edit submit sends `session_kind`, `objectives`, `coach_notes` (buildPayload) and that edit defaults load them; on failed save keep form populated + draft intact. (depends on T008)

**Checkpoint**: Kind/objectives persist on create AND edit; drafts restore; no PII in logs.

---

## Phase 4: User Story 2 — Guided stepped flow with clear validation (Priority: P1)

**Goal**: A 4-step wizard with inline per-step validation, a blocking error summary, ≥48 px targets, and 0 axe violations.

**Independent Test**: On a small viewport, advancing with an invalid field is blocked inline; the summary lists remaining blockers and focuses fields; axe reports 0 violations.

### Tests for User Story 2 ⚠️

- [ ] T019 [P] [US2] Frontend test `frontend/test/training/sessionWizardNav.test.tsx`: Next is blocked with inline error when a required step field is invalid; advances when valid; Back preserves values.
- [ ] T020 [P] [US2] Frontend a11y test `frontend/test/training/sessionWizardA11y.test.tsx`: `jest-axe` on the wizard page and each step + the notify dialog → 0 violations; assert interactive targets ≥48 px (class/style checks).

### Implementation for User Story 2

- [ ] T021 [P] [US2] Build `frontend/src/components/training/session-wizard/StepGeneral.tsx`: date, time, `DurationPicker`, location, technical focus, description, `session_kind` as `ToggleGroup` chips (≥48 px), objectives; inline errors via `aria-invalid`/`aria-describedby`.
- [ ] T022 [P] [US2] Build `frontend/src/components/training/session-wizard/SessionErrorSummary.tsx`: persistent, scannable list of current blockers; clicking an item focuses/reveals the field; shown on blocked Next/submit.
- [ ] T023 [US2] Integrate `SessionErrorSummary` into `SessionWizard.tsx` and set `mode:"onTouched"` inline feedback; ensure `noValidate` so HTML5 does not compete with Zod. (depends on T007, T022)
- [ ] T024 [US2] Add loading/empty/error + Render cold-start states to the host/wizard (sessions/athletes load, save) per Principle III/IV. (depends on T008)

**Checkpoint**: Guided flow is usable on touch, validates per step, 0 axe violations.

---

## Phase 5: User Story 3 — Efficient athlete call-up (Priority: P2)

**Goal**: Search + select-all/clear-all + removable selected chips + sticky count + ≥48 px rows for clubs with many athletes.

**Independent Test**: With ~60 athletes, search/select a subset; selected shown as chips and counted with a sticky indicator; saving with none blocks.

### Tests for User Story 3 ⚠️

- [ ] T025 [P] [US3] Frontend test `frontend/test/training/athletesMultiSelect.test.tsx`: search filters; select-all/clear-all; selected render as removable chips; count visible; ≥1 required message when empty.

### Implementation for User Story 3

- [ ] T026 [US3] Enhance `frontend/src/components/training/AthletesMultiSelect.tsx`: removable selected chips above the list, sticky selected-count, ≥48 px row targets, keep search + select-all/clear-all; preserve existing aria labels.
- [ ] T027 [US3] Build `frontend/src/components/training/session-wizard/StepAthletes.tsx` mounting the enhanced selector with the required (≥1) inline error. (depends on T026, T007)

**Checkpoint**: Call-up is fast and unambiguous; US1/US2 still pass.

---

## Phase 6: User Story 4 — Route file, coach notes & notification in one pass (Priority: P2)

**Goal**: Attach route text/Strava/route-file + coach notes in the same flow; route file auto-uploads after create; parent-notification choice yields an explicit success/failure-retry/no-recipients outcome.

**Independent Test**: Create attaching a `.gpx` + coach notes, choose notify → session saved, file uploaded, clear notification outcome; simulate upload/notify failure → session still saved, retryable message.

### Tests for User Story 4 ⚠️

- [ ] T028 [P] [US4] Frontend test `frontend/test/training/sessionRouteNotes.test.tsx`: invalid Strava URL shows shared-rule error; route file picked then auto-uploaded after create; upload failure keeps saved session + shows retry; coach notes submitted.
- [ ] T029 [P] [US4] Frontend test `frontend/test/training/notifyOutcome.test.tsx`: Review-step notify choice → success toast / failure-retry / no-recipients states rendered distinctly (no silent failure).

### Implementation for User Story 4

- [ ] T030 [P] [US4] Build `frontend/src/components/training/RouteFileDropzone.tsx`: pick `.gpx/.fit` (held in state), client-side size/extension hint, accessible, ≥48 px.
- [ ] T031 [US4] Build `frontend/src/components/training/session-wizard/StepRouteNotes.tsx`: route text, Strava URL (shared regex), `RouteFileDropzone`, coach notes textarea. (depends on T030, T004)
- [ ] T032 [US4] Build `frontend/src/components/training/session-wizard/StepReview.tsx`: read-only summary (date, kind, athlete count) + notify-parents choice; submit button. (depends on T007)
- [ ] T033 [US4] In `SessionWizard.tsx` submit flow: create session → if a route file was chosen call `uploadRouteFile` (existing `api/trainingSessions.ts`); on upload failure do NOT roll back, surface retryable error. (depends on T031, T032, T018)
- [ ] T034 [US4] Wire the parent-notification outcome: extend/reuse `NotifyParentsDialog`/toast to report success / failure-retry / no-recipients from the create/update mutation result. (depends on T032)

**Checkpoint**: One-pass planning works; failures never hide a saved session.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T035 [US1] [P] Add concurrent-edit guard in edit mode: capture `updated_at` at load, warn before overwrite if it changed (FR-019) in `SessionWizard.tsx`.
- [ ] T036 [P] Run `data-privacy-guard` audit over the diff (drafts cleared, no PII in logs, parent view still omits coach_notes/route_file_path) and record findings in `docs/09-training-planning/`.
- [ ] T037 [P] Update docs: `docs/09-training-planning/workflow.md` + `design.md` with the wizard flow and the `session_kind`/`objectives` contract fix; refresh CLAUDE.md training notes.
- [ ] T038 Run quickstart.md end-to-end manually (coach login) and confirm SC-001/002/005/007/010.
- [ ] T039 [P] Full gates: `cd backend && pytest -q` and `cd frontend && npm run lint && npx tsc --noEmit && npx vitest run`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup — BLOCKS all stories.
- **US1 (Phase 3)**: after Foundational. MVP.
- **US2 (Phase 4)**: after Foundational; renders inside the same wizard (coordinate edits to `SessionWizard.tsx`).
- **US3 (Phase 5)** / **US4 (Phase 6)**: after Foundational; mostly new step files (parallelizable across files).
- **Polish (Phase 7)**: after the desired stories.

### User Story Dependencies

- US1 (P1) — independent; backend + draft.
- US2 (P1) — independent; validation/a11y shell.
- US3 (P2) — independent; athlete selector.
- US4 (P2) — independent; route/notes/notification. Shares `SessionWizard.tsx` submit with US1 (T033 depends on T018).

### Within Each Story

- Tests first (must fail), then implementation. Models/schemas before services before UI wiring.

### Parallel Opportunities

- Setup T001/T002/T003 in parallel.
- Foundational T005 and T009 in parallel with T006.
- US1 backend (T014/T015) parallel with frontend draft (T013/T017) once schema lands.
- Step component files (T021, T026/T027, T030/T031, T032) are different files → parallel across stories; serialize only edits to `SessionWizard.tsx` (T007/T017/T023/T024/T033/T035).

---

## Parallel Example: User Story 1

```bash
# Tests (write first, expect failure on current backend):
Task: "T010 Backend round-trip test in backend/tests/routers/test_training_sessions_fields.py"
Task: "T012 Backend privacy test in backend/tests/routers/test_training_sessions_privacy.py"
Task: "T013 Frontend draft test in frontend/test/training/sessionDraft.test.tsx"

# Then implementation in parallel (different files):
Task: "T014 Add session_kind/objectives to Create/Update schemas"
Task: "T015 Add session_kind/objectives to Read/ReadParent schemas"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & VALIDATE**
   (kind/objectives persist on create+edit, drafts restore). This alone fixes the core defect.

### Incremental Delivery

US1 (MVP) → US2 (guided/validation) → US3 (athletes) → US4 (route/notes/notification) →
Polish. Each story is independently testable and shippable behind the same wizard.

---

## Notes

- [P] = different files, no incomplete dependencies. Edits to `SessionWizard.tsx` are a
  serialization point across stories.
- No Alembic migration (columns already exist).
- Keep all UI copy in español neutro; ≥48 px targets; 0 axe violations; no PII in logs/drafts.
- Commit after each task or logical group.
