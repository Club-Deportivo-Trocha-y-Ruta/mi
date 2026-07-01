# Tasks: Coach Dashboard — Phase A (Correctness, Performance & Club-Scope Fixes)

**Feature dir**: `specs/020-dashboard-coach-phase-a/` | **Branch**: `claude/spec-kit-agent-setup-poepvz`

**Scope**: Frontend-only. No backend, no migration. Reuses existing `GET /api/alerts`.

**Agent legend**: `@react-ui-engineer` (frontend refactor/UI), `@qa-engineer` (vitest), `@data-privacy-guard` (privacy/isolation review), `@ux-researcher` (states + a11y).

**Files in play**:
- `frontend/src/hooks/athletes/useDashboardStats.ts` (rewrite)
- `frontend/src/routes/dashboard/DashboardPage.tsx` (edit)
- `frontend/src/components/dashboard/MeasurementAlerts.tsx` (edit)
- `frontend/src/hooks/athletes/useAlerts.ts` (reuse as-is)
- test files under `__tests__/` (new/updated)

---

## Phase 1: Setup

- [ ] T001 [P] Confirm the working baseline: run `cd frontend && npm install && npm run test -- dashboard MeasurementAlerts` and record current pass/fail + the current `GET /api/athletes/{id}` fan-out in `frontend/src/hooks/athletes/useDashboardStats.ts` as the regression baseline. `@qa-engineer`

---

## Phase 2: Foundational (blocking prerequisites)

- [ ] T002 Rewrite `frontend/src/hooks/athletes/useDashboardStats.ts` to derive `{ total, lastEvaluation, phvVigentes, phvTotal, isLoading, isError }` from `useAlerts()` (shared `["alerts"]` query, no `club_id`); DELETE all `getAthlete`/`getAthletes` imports and per-id `Promise.all`. Mapping per `data-model.md`: `total = athletes.length`; `lastEvaluation = max(non-null last_measurement_date)`; `phvVigentes = count(status ∉ {overdue, never})`; `phvTotal = athletes.length`. `@react-ui-engineer`

**Checkpoint**: dashboard stats now come from `/alerts`; US1/US4 build on this. Blocks all US phases.

---

## Phase 3: User Story 1 — Fast load, no N+1 (P1)

**Goal**: 0 `GET /api/athletes/{id}` on load; O(1) athlete-data requests.
**Independent test**: load `DashboardPage`, assert no per-id calls + correct cards.

- [ ] T003 [US1] In `frontend/src/routes/dashboard/DashboardPage.tsx`, consume the rewritten `useDashboardStats`; render the PHV card from `phvVigentes`/`phvTotal` (formula in US4/T009) and keep card loading placeholders driven by `isLoading`. `@react-ui-engineer`
- [ ] T004 [P] [US1] Add vitest in `frontend/src/hooks/athletes/__tests__/useDashboardStats.test.ts` (or update existing) asserting: derives cards from a mocked `/alerts` payload, and a request spy shows **zero** `GET /api/athletes/{id}` calls (N+1 regression). `@qa-engineer`
- [ ] T005 [P] [US1] Add vitest in `frontend/src/routes/dashboard/__tests__/DashboardPage.test.tsx` asserting cards render correct `total`, `lastEvaluation` (max date / "--"), and PHV values from a mocked alerts fixture. `@qa-engineer`

**Checkpoint**: MVP — dashboard is fast and correct. Independently shippable.

---

## Phase 4: User Story 2 — Truncated actionable list (P1)

**Goal**: ≤8 rows, urgency-sorted, "Ver todas (M)" when M>8.
**Independent test**: 40 actionable athletes → ≤8 rows, correct order, link to `/athletes`.

- [ ] T006 [US2] In `frontend/src/components/dashboard/MeasurementAlerts.tsx`, sort `actionable` by urgency (`overdue` desc `days_overdue` → `due_soon` asc days-to-due → `never`), slice to 8, and render a "Ver todas (M)" `<Link to="/athletes">` shown iff `actionable.length > 8` (M = full actionable count). Copy in español neutro. `@react-ui-engineer`
- [ ] T007 [P] [US2] Add/extend vitest in `frontend/src/components/dashboard/__tests__/MeasurementAlerts.test.tsx`: 40 actionable → exactly ≤8 rows; assert sort order; "Ver todas (40)" present and links to `/athletes`; ≤8 actionable → no link; 0 actionable → list omitted. `@qa-engineer`

**Checkpoint**: list usable on tablet.

---

## Phase 5: User Story 3 — Club scoping + explicit states (P1) — PRIVACY

**Goal**: no other-club/seed athlete anywhere; explicit loading/error/empty states.
**Independent test**: coach of club X sees zero club Y / seed athletes.

- [ ] T008 [US3] In `frontend/src/routes/dashboard/DashboardPage.tsx`, add distinct render states (FR-006): loading (placeholders), error, and empty (`athletes: []`) → explicit español-neutro empty copy ("No tienes atletas asignados a un club"); cards show "--" consistently, never "0" as a loaded value. Ensure `MeasurementAlerts` empty path aligns. `@ux-researcher`
- [ ] T009 [US3] Cross-club isolation vitest in `frontend/src/routes/dashboard/__tests__/DashboardClubScope.test.tsx`: mock `/alerts` for coach of club X (only X athletes); assert no club Y / seed athlete (`ConsentTest`, `<script>alert(1)</script> Test`) renders in any block (cards, chips, rapid-growth, list). Encodes access-control guarantee G1. `@qa-engineer`
- [ ] T010 [US3] Privacy review of T009 + the `/alerts` consumption: confirm no athlete field beyond `AlertsSummary` is surfaced (NFR-003), no PII in any new log/console, and the isolation test truly fails if scope leaks. Sign off in a short note appended to `specs/020-dashboard-coach-phase-a/quickstart.md` (V4). `@data-privacy-guard`

**Checkpoint**: scoping proven by test; privacy signed off.

---

## Phase 6: User Story 4 — PHV metric reframe (P2)

**Goal**: card shows "V de A con medición vigente" ("--" when A=0).
**Independent test**: A athletes, V vigentes → exact copy.

- [ ] T011 [US4] In `frontend/src/routes/dashboard/DashboardPage.tsx`, render the PHV card as `"{phvVigentes} de {phvTotal} con medición vigente"` and "--" when `phvTotal === 0`. Remove the old "V / total evaluados" string. `@react-ui-engineer`
- [ ] T012 [P] [US4] Vitest asserting the PHV formula copy for A>0 and the "--" case for A=0 (in `DashboardPage.test.tsx`). `@qa-engineer`

---

## Phase 7: User Story 5 — training_implications in growth block (P3)

**Goal**: show `training_implications` in rapid-growth block; generic fallback when null.
**Independent test**: growth athlete with implications → text rendered.

- [ ] T013 [US5] In `frontend/src/components/dashboard/MeasurementAlerts.tsx` rapid-growth block, render `a.training_implications` when non-null (alongside the cm/mes line), falling back to the existing generic "Revisar carga de entrenamiento." when null — no empty gap. `@react-ui-engineer`
- [ ] T014 [P] [US5] Vitest in `MeasurementAlerts.test.tsx`: implications present → rendered; null → generic guidance, no gap. `@qa-engineer`

---

## Phase 8: Polish & Cross-Cutting

- [ ] T015 [P] `jest-axe` accessibility test on `DashboardPage` (loading, ready, empty states) → no violations; links keyboard-reachable, touch targets ≥44px. `@ux-researcher`
- [ ] T016 [P] Run `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- dashboard MeasurementAlerts useDashboardStats` → all green; confirm no backend/migration diff (`git status` shows only frontend + specs). `@qa-engineer`
- [ ] T017 Update `specs/020-dashboard-coach-phase-a/quickstart.md` "Definition of done" checkboxes (V1–V8 mapped to tasks) and note final request count observed. `@react-ui-engineer`

---

## Dependencies & Execution Order

- **T001** (baseline) → **T002** (foundational rewrite) blocks everything.
- **US1 (T003–T005)** depends on T002. This is the **MVP**.
- **US2 (T006–T007)**, **US3 (T008–T010)**, **US4 (T011–T012)**, **US5 (T013–T014)** all depend on T002 but are **independent of each other** (US2/US5 touch `MeasurementAlerts.tsx`; US1/US3/US4 touch `DashboardPage.tsx` — serialize edits within the same file).
- **Polish (T015–T017)** after all stories.

### Same-file serialization (no parallel edits within a file)
- `DashboardPage.tsx`: T003 → T008 → T011 (sequential).
- `MeasurementAlerts.tsx`: T006 → T013 (sequential).
- Test files are independent → `[P]`.

### Parallel opportunities
- After T002: T004, T005, T007, T012, T014 (tests, distinct files) can run `[P]`.
- Polish: T015, T016 `[P]`.

---

## MVP scope

**T001 → T002 → US1 (T003–T005)** = fast, correct, no-N+1 dashboard. Shippable alone. US2 (truncation) and US3 (scoping+privacy) are strongly recommended for the same release since they're the other two P1 fixes; US4/US5 are low-risk add-ons.

## Agent assignment summary

| Agent | Tasks |
|---|---|
| `@react-ui-engineer` | T002, T003, T006, T011, T013, T017 |
| `@qa-engineer` | T001, T004, T005, T007, T009, T012, T014, T016 |
| `@ux-researcher` | T008, T015 |
| `@data-privacy-guard` | T010 |
