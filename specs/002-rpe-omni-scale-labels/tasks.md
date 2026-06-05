---
description: "Task list for RPE OMNI Scale Labels Refactor"
---

# Tasks: RPE OMNI Scale Labels Refactor

**Input**: Design documents from `/specs/002-rpe-omni-scale-labels/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/rpe-omni-labels.md, quickstart.md

**Tests**: INCLUDED — required by Constitution II (Testing NON-NEGOTIABLE) and plan.md. The defect (label wrong at value 3) lands with a regression test.

**Organization**: Grouped by user story. This is a small, single-file frontend copy change, so all stories touch the same component (`frontend/src/components/training/RubricSliders.tsx`); cross-story parallelism is therefore limited — see Dependencies.

## Agent assignment legend

Per the request, each task names a **subagent** to execute it; **`engineering-lead`** is the lead/orchestrator that sequences phases, reviews diffs, and enforces the Constitution gate.

| Agent | Role on this feature |
|-------|----------------------|
| `engineering-lead` | **Lead** — orchestrates, reviews each diff, runs the gate, owns the final report |
| `react-ui-engineer` | Edits the React component (labels + faces) |
| `qa-engineer` | Writes/updates `vitest` tests; keeps a11y suite green |
| `ux-researcher` | Reviews wording (español neutro), monotonicity, talk-test consistency, WCAG |
| `technical-writer` | Updates CLAUDE.md status table + docs note |

## Format: `[ID] [P?] [Story] Description → @agent`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No project init needed — existing frontend. Just establish the working baseline.

- [x] T001 Confirm clean baseline: run `cd frontend && npx vitest run src/components/training/RubricSliders.test.tsx src/components/training/RubricSliders.a11y.test.tsx && npx tsc --noEmit` and record current green state in the branch → **@engineering-lead** (lead, orchestration)

**Checkpoint**: Baseline green; ready for foundational alignment.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock the agreed canonical mapping so all downstream tasks share one source of truth.

**⚠️ CRITICAL**: No US work begins until the mapping is ratified.

- [x] T002 Validate the final 0–10 Spanish mapping in `specs/002-rpe-omni-scale-labels/research.md` against `docs/01-marco-teorico.md` (OMNI talk-test cues) and the contract guarantees in `specs/002-rpe-omni-scale-labels/contracts/rpe-omni-labels.md`; confirm monotonic, español neutro with diacritics, "Moderado" at index 5 → **@ux-researcher** (reviewer)

**Checkpoint**: Mapping ratified — implementation can begin.

---

## Phase 3: User Story 1 - Coach reads an effort descriptor that matches the number (Priority: P1) 🎯 MVP

**Goal**: Redistribute OMNI descriptors so each value 0–10 shows an intuitive word with "Moderado" centered at 5 (no longer at 3), faces aligned. Stored value unchanged.

**Independent Test**: Move the RPE OMNI slider 0→10 and confirm "Moderado" appears at 5, wording rises monotonically, endpoints are Reposo/Máximo, and the highlighted face matches the word.

### Tests for User Story 1 (write FIRST, ensure they FAIL on current code) ⚠️

- [x] T003 [P] [US1] Add regression tests to `frontend/src/components/training/RubricSliders.test.tsx` asserting contract guarantees G1–G3: `5 — Moderado` renders, `3 — Moderado` does NOT, and endpoints `0 — Reposo` / `10 — Máximo` (must FAIL on current labels) → **@qa-engineer**

### Implementation for User Story 1

- [x] T004 [US1] Replace the `RPE_LABELS` array in `frontend/src/components/training/RubricSliders.tsx` with the ratified mapping from research.md (Reposo, Muy fácil, Fácil, Ligero, Algo fácil, Moderado, Algo duro, Duro, Muy duro, Muy muy duro, Máximo) + source-citing comment; leave slider `min/max/aria-*` and `field.onChange` untouched → **@react-ui-engineer** (depends on T002, T003)
- [x] T005 [US1] Align `RPE_FACES` in the same file so index 5 reads neutral/moderate and the rest-to-max ramp matches the new wording; keep array length 11 (contract G4) → **@react-ui-engineer** (same file as T004 — sequential, not [P])
- [x] T006 [US1] Run `npx vitest run src/components/training/RubricSliders.test.tsx` (T003 now passes) and `npx tsc --noEmit`; review the diff for behavioral-regression-free change → **@engineering-lead** (lead review; depends on T004, T005)

**Checkpoint**: US1 functional — MVP. The reported defect is fixed and regression-tested.

---

## Phase 4: User Story 2 - Descriptors stay consistent with the club's training language (Priority: P2)

**Goal**: Confirm the refreshed wording is compatible with the club's effort vocabulary (talk-test) and accessible; no contradictory terminology.

**Independent Test**: Compare on-screen descriptors against `docs/01-marco-teorico.md` talk-test cues and run the a11y suite — non-contradictory wording, zero a11y violations.

- [x] T007 [US2] Run `npx vitest run src/components/training/RubricSliders.a11y.test.tsx` (must stay at zero violations) and verify the descriptors carry no clinical/judgmental terms and read in español neutro on the tablet layout → **@qa-engineer** (depends on US1)
- [x] T008 [US2] Cross-check final descriptors vs the club's talk-test language in `docs/01-marco-teorico.md`; flag any contradiction for a one-word adjustment in `RubricSliders.tsx` → **@ux-researcher** (depends on US1)

**Checkpoint**: US1 + US2 both satisfied — wording validated, accessible, consistent.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final gate.

- [x] T009 [P] Update the CLAUDE.md implementation-status section with a one-line note on the RPE OMNI label refactor (frontend-only, no migration) → **@technical-writer**
- [x] T010 Run `specs/002-rpe-omni-scale-labels/quickstart.md` Definition-of-Done checklist end-to-end (vitest + a11y + tsc + eslint clean, no backend/schema diff) and produce the compliance one-liner for the PR (Constitution I–IV) → **@engineering-lead** (lead; final gate, depends on all)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: none — start immediately.
- **Foundational (T002)**: after Setup — BLOCKS all stories (ratifies the mapping).
- **US1 (T003–T006)**: after T002. T003 (tests) before T004 (impl). T005 after T004 (same file). T006 after T004+T005.
- **US2 (T007–T008)**: after US1 (reviews the shipped wording).
- **Polish (T009–T010)**: T009 can run anytime after T004; T010 last.

### Why limited cross-story parallelism

US1 and US2 operate on the **same file** (`RubricSliders.tsx`). US1 implements; US2 reviews/validates the result. They are sequential by nature, not parallel.

### Parallel Opportunities

- T003 (write failing test) is `[P]` — independent file region from the constant edit, can be authored while T002 finishes.
- T009 (docs) is `[P]` — different file (`CLAUDE.md`), can run alongside US2.

---

## Parallel Example

```text
# After T002 ratifies the mapping, these can overlap:
@qa-engineer:        T003 — write failing regression tests (RubricSliders.test.tsx)
@technical-writer:   T009 — draft CLAUDE.md status note (CLAUDE.md)
# Then @react-ui-engineer does T004→T005 sequentially (same component file).
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001 baseline → T002 ratify mapping → T003 failing test → T004/T005 implement → T006 verify.
2. **STOP & VALIDATE**: "Moderado" at 5, defect gone, tests green. This alone resolves the coach's report and is shippable.

### Incremental

- Add US2 (T007–T008): wording/a11y/talk-test validation.
- Polish (T009–T010): docs + final Constitution gate.

### Agent orchestration (per request)

- **`engineering-lead`** owns T001, T006, T010 — sequencing, diff review, and the final gate — and dispatches the specialist subagents below in order.
- Subagents: `ux-researcher` (T002, T008), `qa-engineer` (T003, T007), `react-ui-engineer` (T004, T005), `technical-writer` (T009).

---

## Notes

- `[P]` = different file/region, no blocking dependency.
- Whole change is ~15 lines in one component + its test; no backend, schema, or migration.
- Privacy: no athlete-identifiable data → no `data-privacy-guard` audit required.
- Commit after T006 (MVP) and again after T010 (polished), per Conventional Commits.
