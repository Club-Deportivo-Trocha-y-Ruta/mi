---
description: "Task list — Prefill results import from an existing competition"
---

# Tasks: Prefill results import from an existing competition

**Input**: Design documents from `specs/015-prefill-import-from-competition/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: INCLUDED — Constitution II (Testing NON-NEGOTIABLE) + user request (Vitest unit, Playwright e2e, Stryker mutation).

**Scope**: Frontend-only. No backend, no migration, no new endpoint (FR-011/FR-012).

## Format: `[ID] [P?] [Story] Description (→ agent)`

- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: US1–US4 (from spec.md)
- `(→ agent)`: suggested specialized agent for the dynamic workflow (see bottom)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: wire mutation-testing tooling (deps already installed, no config yet).

- [X] T001 [P] Add `frontend/stryker.config.json` (vitest runner, `mutate` scoped to `src/hooks/race/useImportPrefill.ts` + `src/components/competitions/import/ImportWizard.tsx`, thresholds high 85 / low 70 / break 60) per research.md R5 (→ qa-engineer)
- [X] T002 Add `"test:mutation": "stryker run"` script to `frontend/package.json` (→ qa-engineer)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the prefill data plumbing both P1 stories build on. ⚠️ No user story work begins until this is done.

- [X] T003 [P] Define `ImportPrefill` view-model types (`ImportPrefillStatus`, `ImportPrefill`) in `frontend/src/types/raceImports.types.ts` per data-model.md (→ react-ui-engineer)
- [X] T004 Create `useImportPrefill(raceEventId)` hook in `frontend/src/hooks/race/useImportPrefill.ts` — composes `useRaceEvent` + `useRaceSeries`, resolves series by `event.series_id`, returns `loading | ready | blocked | error`, derives `series_kind`/`valida_num` (null for championship), builds `editMetadataHref` for blocked (FR-009) per contracts/prefill-data-contract.md (→ react-ui-engineer)
- [X] T005 [P] Extend MSW handlers for prefill tests in `frontend/src/test/msw/raceSeriesHandlers.ts` (+ race-event handler if missing) covering cup, championship, and unresolvable-series fixtures — competition metadata only, **zero minor PII** (→ qa-engineer)

**Checkpoint**: prefill view-model available; stories can start.

---

## Phase 3: User Story 1 — Launch a prefilled import from a competition (Priority: P1) 🎯 MVP

**Goal**: Opening import from a competition opens it populated with that competition's identity, name, date, type, and series; coach proceeds to results without re-entering metadata.

**Independent Test**: From a competition detail, launch import → step 1 shows the competition's name/date/city/series/type prefilled; reach the upload step with zero re-typed metadata.

### Tests for User Story 1 ⚠️ (write first, must fail)

- [X] T006 [P] [US1] Unit test `useImportPrefill` `ready` mapping (event+series → values, derived `series_kind`) in `frontend/src/hooks/race/__tests__/useImportPrefill.test.ts` (→ qa-engineer)
- [X] T007 [P] [US1] RTL test: wizard prefilled from `raceEventId` renders name/date/city/series/type values, no re-typing needed, in `frontend/src/components/competitions/import/__tests__/ImportWizard.prefill.test.tsx` (→ qa-engineer)
- [X] T008 [P] [US1] RTL test: `CompetitionImportPage` passes `raceEventId` to `ImportWizard` (with-id vs no-id) in `frontend/src/routes/competitions/__tests__/CompetitionImportPage.test.tsx` (→ qa-engineer)

### Implementation for User Story 1

- [X] T009 [US1] Add optional `raceEventId?: number` to `ImportWizardProps`; consume `useImportPrefill`; `reset()` RHF with prefilled values on `ready` in `frontend/src/components/competitions/import/ImportWizard.tsx` per contracts/import-wizard-props.md (→ react-ui-engineer)
- [X] T010 [US1] Pass `raceEventId={hasExistingEvent ? raceEventId : undefined}` into `<ImportWizard>` in `frontend/src/routes/competitions/CompetitionImportPage.tsx` (→ react-ui-engineer)
- [X] T011 [US1] Add designed `loading` state for prefill fetch (cold-start aware, no unbounded spinner) in `frontend/src/components/competitions/import/ImportWizard.tsx` (→ react-ui-engineer)

**Checkpoint**: import launched from a competition opens prefilled and reaches upload with zero re-typed fields (SC-001, SC-002).

---

## Phase 4: User Story 2 — Protect the competition link with locked, derived fields (Priority: P1)

**Goal**: prefilled identity fields are locked/read-only; type & series derived (no in-flow edit); explicit "Editar metadata" escape hatch; undeterminable series blocks the import (FR-009).

**Independent Test**: in a prefilled import, identity fields are read-only, no control edits type/series, escape hatch exists; an unresolvable-series competition shows the blocked state.

### Tests for User Story 2 ⚠️ (write first, must fail)

- [X] T012 [P] [US2] RTL test: identity fields render as locked read-only (not editable inputs), no type/series edit control, "Editar metadata" link present, in `frontend/src/components/competitions/import/__tests__/ImportWizard.locked.test.tsx` (→ qa-engineer)
- [X] T013 [P] [US2] Unit test `useImportPrefill` `blocked` path (series_id unresolvable → status `blocked` + `editMetadataHref`) in `frontend/src/hooks/race/__tests__/useImportPrefill.test.ts` (→ qa-engineer)
- [X] T014 [P] [US2] a11y test (jest-axe) on prefilled wizard step 1 — zero violations, read-only via `readOnly`/static text + `aria-disabled` (never `disabled` dropping focus/value) in `frontend/src/components/competitions/import/__tests__/ImportWizard.locked.test.tsx` (→ ux-researcher)

### Implementation for User Story 2

- [X] T015 [US2] Render derived identity fields (name, date, city, series, type, round) as a locked read-only summary block (styled like detail "Información" card); keep real values in RHF state for submit; remove in-flow type/series controls when prefilled in `frontend/src/components/competitions/import/ImportWizard.tsx` (FR-004/FR-005, research.md R3) (→ react-ui-engineer)
- [X] T016 [US2] Add explicit "Editar metadata" escape hatch link → `/competitions/{id}/edit` in prefilled wizard in `frontend/src/components/competitions/import/ImportWizard.tsx` (FR-006) (→ react-ui-engineer)
- [X] T017 [US2] Add designed `blocked` state (series/type undeterminable) — message + "Editar metadata" link, import cannot proceed — in `frontend/src/components/competitions/import/ImportWizard.tsx` (FR-009) (→ react-ui-engineer)

**Checkpoint**: prefilled import is link-safe; locked + derived + escape hatch + block all in place (SC-003, SC-004).

---

## Phase 5: User Story 3 — Keep the standalone (no-competition) import unchanged (Priority: P1)

**Goal**: `/competitions/import` (no id) behaves exactly as today — empty, editable, no locking.

**Independent Test**: launch standalone import → empty, all fields editable, type defaults to Copa, no locking.

### Tests for User Story 3 ⚠️ (write first, must fail)

- [X] T018 [P] [US3] RTL regression test: `ImportWizard` with no `raceEventId` is empty/editable, default `series_kind=cup`, no locked fields, in `frontend/src/components/competitions/import/__tests__/ImportWizard.standalone.test.tsx` (→ qa-engineer)

### Implementation for User Story 3

- [X] T019 [US3] Guard all prefill/lock logic behind `raceEventId != null` so the standalone path is untouched; verify existing standalone tests still pass in `frontend/src/components/competitions/import/ImportWizard.tsx` (FR-007, SC-005) (→ react-ui-engineer)

**Checkpoint**: standalone flow regression-free alongside the prefilled path.

---

## Phase 6: User Story 4 — Hide round numbering for championships (Priority: P2)

**Goal**: prefilled import from a championship shows no `válida #`; cup shows its round as locked metadata.

**Independent Test**: prefilled import from championship → no `válida #`; from cup → round shown locked.

### Tests for User Story 4 ⚠️ (write first, must fail)

- [X] T020 [P] [US4] RTL test: championship prefill hides `válida #` entirely; cup prefill shows it locked, in `frontend/src/components/competitions/import/__tests__/ImportWizard.championship.test.tsx` (→ qa-engineer)

### Implementation for User Story 4

- [X] T021 [US4] Hide the `válida #` field/concept when prefill `series_kind=championship` (driven by derived value, consistent with spec 014) in `frontend/src/components/competitions/import/ImportWizard.tsx` (FR-008, SC-006) (→ react-ui-engineer)

**Checkpoint**: all four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [US1] [US2] [US3] [US4] Add Playwright e2e `frontend/e2e/prefill-import-from-competition.spec.ts` covering: cup prefilled+locked reaches upload zero re-typed; championship hides válida; standalone unchanged; blocked path shows edit-metadata; privacy (no athlete name before dry-run) — per research.md R6 / quickstart.md (→ qa-engineer)
- [X] T023 Privacy audit: confirm prefill payloads/logs/test fixtures expose no minor PII (name/DOB/medical), only competition metadata (FR-013, Constitution privacy gate) (→ data-privacy-guard)
- [ ] T024 [P] Run mutation testing `npm run test:mutation`; raise weak assertions to ≥85 score on the prefill surface; fix below break (60) (→ qa-engineer)
- [X] T025 [P] Verify bundle/perf: import route stays lazy, no ≥10% bundle regression; cold-start state surfaced (Constitution IV) (→ react-ui-engineer)
- [ ] T026 Run `quickstart.md` manual verification end-to-end (coach login, cup/championship/standalone/block) (→ ux-researcher)
- [X] T027 [P] Update `docs/implementation-status.md` + CLAUDE.md status table row for spec 015 (→ technical-writer)

---

## Dependencies & Execution Order

### Phase dependencies
- Setup (P1) → no deps.
- Foundational (P2: T003–T005) → after Setup; **BLOCKS** all stories.
- US1 (P3) → after Foundational. MVP.
- US2 (P4) → after Foundational; ships **with** US1 (prefill without protection is unsafe — spec US2 rationale). Shares `ImportWizard.tsx` with US1 → US2 impl tasks run after US1 impl tasks (same file).
- US3 (P5) → after US1/US2 touch `ImportWizard.tsx` (guard verification).
- US4 (P6) → after Foundational; depends on derived `series_kind` (T004).
- Polish (P7) → after desired stories complete.

### Within-file serialization (same file `ImportWizard.tsx`)
T009 → T011 → T015 → T016 → T017 → T019 → T021 are **sequential** (same file). Their **tests** (T007, T012, T014, T018, T020) are `[P]` (different test files).

### Parallel opportunities
- T001 ∥ (T002 after T001’s file exists).
- T003 ∥ T005 (different files).
- All `[P]` test-authoring tasks per story run together (T006–T008; T012–T014; T018; T020) — different test files.
- T024 ∥ T025 ∥ T027 in polish.

---

## Parallel Example: User Story 1 tests

```bash
# author US1 tests together (distinct files):
Task: "Unit test useImportPrefill ready mapping — useImportPrefill.test.ts"   (qa-engineer)
Task: "RTL prefilled wizard render — ImportWizard.prefill.test.tsx"           (qa-engineer)
Task: "CompetitionImportPage passes raceEventId — CompetitionImportPage.test.tsx" (qa-engineer)
```

---

## Implementation Strategy

### MVP (US1 + US2 together)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. US1 (prefill) → 4. US2 (lock/derive/block) → **validate** → deploy.
> US1 and US2 are both P1 and ship together: prefill must be protected to be safe.

### Incremental
- + US3 (standalone regression guard) → + US4 (championship válida hiding) → Polish (e2e, mutation, privacy, docs).

### Dynamic workflow / agent assignment
Orchestrate via **engineering-lead** (decompose + checklist + delegate). Suggested fan-out:
- **react-ui-engineer** — T003, T004, T009–T011, T015–T017, T019, T021, T025 (component/hook/UI).
- **qa-engineer** — T001, T002, T005, T006–T008, T012, T013, T018, T020, T022, T024 (vitest, MSW, Playwright, Stryker).
- **ux-researcher** — T014 (jest-axe a11y), T026 (manual quickstart on tablet/mobile).
- **data-privacy-guard** — T023 (minors PII audit).
- **technical-writer** — T027 (status docs).

Same-file tasks (`ImportWizard.tsx`) must serialize even across agents — engineering-lead sequences T009→T011→T015→T017→T019→T021; test authors run in parallel.

---

## Notes
- [P] = different files, no incomplete deps.
- Write each story's tests first; ensure they fail before implementing (Constitution II).
- Commit after each task or logical group (Conventional Commits, español latino, no AI mention).
- No backend/migration; if any task implies one, stop — it's out of scope (FR-011/FR-012).
