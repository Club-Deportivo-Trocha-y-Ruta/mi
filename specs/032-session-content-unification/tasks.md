# Tasks: Session Content Unification

**Input**: Design documents from `/specs/032-session-content-unification/`

**Prerequisites**: plan.md (required), spec.md (required — user stories), research.md, data-model.md, contracts/attach-technique-to-session.md, contracts/session-sections.md, contracts/unified-attach-flow.md, quickstart.md

**Cross-feature prerequisites**: `specs/028-frontend-design-foundation` (shared components: `EmptyState`, `ConfirmDialog`, `Stepper` focus convention, `sonner` Toaster) MUST be merged; `specs/029-coach-surface-subtraction` MUST have removed the standalone technique session builder (`frontend/src/routes/technique/SessionBuilderPage.tsx`, `ComposerPage.tsx`) first. As of this writing neither has shipped in this repo — see T001.

**Tests**: Constitution II (NON-NEGOTIABLE) and the feature's own Constitution Check both require tests for this feature: backend pytest for the new endpoint (happy + RBAC-negative + validation + idempotency), frontend vitest+MSW per attach flow, jest-axe on every new/changed page and dialog, and a Playwright end-to-end flow. Test tasks are included throughout and are not optional for this feature.

**Organization**: Tasks are grouped by user story (US1/US2/US3, matching spec.md's P1/P2/P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no ordering dependency on an incomplete task)
- **[Story]**: US1, US2, or US3 — only used in story phases
- File paths below are exact, taken from plan.md's Project Structure and verified against the live repo on 2026-07-11

## Path Conventions

Existing web application layout (unchanged by this feature): `backend/app/**`, `backend/tests/**` (FastAPI monolith); `frontend/src/**`, `frontend/e2e/**` (React SPA). No new top-level directory beyond one new frontend component folder, `frontend/src/components/training/session-plan/`.

<!-- ============================================================================
     All sample tasks from the template have been replaced with the actual
     tasks for feature 032. Nothing below is illustrative.
     ============================================================================ -->

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm cross-feature prerequisites and scaffold the one new backend endpoint's shape (router wiring, schemas, permissions) with no behavior yet.

- [X] T001 Verify cross-feature prerequisites before starting: confirm `specs/029-coach-surface-subtraction` has removed `frontend/src/routes/technique/SessionBuilderPage.tsx` and `frontend/src/routes/technique/ComposerPage.tsx` (and their routes in `frontend/src/App.tsx`), and confirm `specs/028-frontend-design-foundation` has shipped `frontend/src/components/shared/EmptyState.tsx`, `frontend/src/components/shared/ConfirmDialog.tsx`, `frontend/src/components/shared/Stepper.tsx`, and `frontend/src/components/ui/sonner.tsx`. This feature's Plan-section empty state (T021), retry feedback (T023), and section-focus behavior (T035) depend on them. If any is missing, resolve that dependency first rather than substituting ad-hoc code.
- [X] T002 [P] Add `AttachExercisesRequest` (`items: list[AssembleItem]`, `Field(min_length=1)`) and `AttachExercisesResponse` (`mixes_age_bands: bool`, `items: list[TechniqueSessionItem]`) Pydantic schemas to `backend/app/schemas/technique.py`, reusing the existing `AssembleItem` and `TechniqueSessionItem` models verbatim — no new fields, no new enum values (data-model.md).
- [X] T003 Add the `POST /api/technique/sessions/{training_session_id}/exercises` route handler scaffold in `backend/app/routers/technique.py`, as a sibling of the existing `GET` at the identical path (`:392-409`): wire the existing `_require_coach_or_admin` dependency (`:77-98`) and the existing `_coach_club_id` club-scoping helper (`:186-201`); body calls a not-yet-implemented `attach_exercises_to_session()` (raises `NotImplementedError` for now — real logic lands in T006). Depends on T002's schemas.
- [X] T004 [P] Verify no Alembic migration is required: from `backend/`, run `alembic revision --autogenerate -m "verify_no_schema_drift_032"`, confirm the generated revision's `upgrade()`/`downgrade()` bodies are both empty (no drift on `technique_session_exercises`, `strength_session_blocks`, `interval_structures`), then delete the generated file. This confirms data-model.md's "no migration" claim before any implementation begins.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement and fully test the one real backend gap (research.md R1), and build the one frontend piece shared by two different User Story 1 sub-flows (the library-initiated "which session?" picker, research.md R6).

**⚠️ CRITICAL**: User Story 1 cannot start until this phase is complete. User Stories 2 and 3 do **not** depend on this phase (see Dependencies & Execution Order below) — US3 may start as soon as Setup is done.

- [X] T005 Write the pytest suite in `backend/tests/technique/test_technique_attach_to_session.py` (new file, follows the `test_technique_assemble_combined_gymkhana.py` naming convention). Required cases (quickstart.md): (1) happy path — 2 new items on a session with no prior technique content → `201`, response `items` length 2, `mixes_age_bands` computed correctly for a mixed-band pair; (2) append onto existing content — 1 more item on a session that already has technique items → `201`, response includes old + new rows, old rows' `position` unchanged; (3) RBAC-negative — parent/athlete role → `403`; (4) not-found-negative — `training_session_id` belonging to another club → `404`, never `403`; (5) validation-negative — empty `items` → `422`; unknown `exercise_id` → `422` listing the id; (6) idempotency regression (FR-009) — submit the identical `items` payload twice, assert both calls `201` and the final DB row count equals the first call's count (assert directly against row count, not just response shape); (7) query-count guard — parametrize 1 vs 5 items, assert query count does not scale linearly (no N+1, Constitution IV). Run the suite now and confirm every case fails against T003's stub.
- [X] T006 Implement `attach_exercises_to_session()` in `backend/app/services/technique/assembler.py`: load the session's existing `TechniqueSessionExercise` rows; for each submitted item, skip it (no insert, no error) if a row with the same `(exercise_id, segment)` already exists for this session; for genuinely-new items, assign `position = current_max_position_in_that_segment + 1` (or `0` if the segment is empty) in submission order, then insert; recompute `mixes_age_bands` by reusing `_compute_mixes_age_bands` (`:226-251`); return the full current list (old + new rows) ordered like `get_session_exercises` (`:555-573`). Reuse `_load_exercises_by_ids` (`:197-223`) for 422-on-unknown-exercise validation. Wire this into T003's route handler in `backend/app/routers/technique.py`, replacing the stub: 404 on session not found/foreign-club, 422 via validation, 201 with `AttachExercisesResponse` on success. Re-run T005's suite and confirm every case now passes.
- [X] T007 [P] Add `attachExercisesToSession(sessionId, items)` to `frontend/src/api/technique.ts`, calling `POST /api/technique/sessions/{sessionId}/exercises` per contracts/attach-technique-to-session.md's request/response shape.
- [X] T008 [P] Build the shared `SessionPickerDialog.tsx` in `frontend/src/components/training/session-plan/SessionPickerDialog.tsx` — the "¿A qué sesión?" picker used by both library-initiated entry points (research.md R6). Backed by `useTrainingSessions({ status: "planned" })` (`frontend/src/api/trainingSessions.ts:80`); because the service's default order is `scheduled_date DESC` (`backend/app/services/training/sessions.py:906-907` — furthest-future first, the R6/R10 ordering gotcha), sort the fetched window client-side **ascending** by `(scheduled_date, scheduled_start_time)` before rendering. Shows the next ~5 upcoming sessions plus a text-search fallback for anything further out. Exposes `onSelect(sessionId)` so each consumer decides what happens next (technique: attach directly; strength: navigate with `?session_id=`).

**Checkpoint**: New endpoint implemented and fully tested; shared session picker ready. User Story 1 can now begin.

---

## Phase 3: User Story 1 - One way to build a complete session (Priority: P1) 🎯 MVP

**Goal**: Technique exercises, strength blocks, and interval structures all attach to an existing session through one identical interaction pattern, initiated from the session, and exactly zero new sessions are ever created as a side effect (FR-001, FR-002, FR-003; SC-001, SC-002, SC-003).

**Independent Test**: Create a session, then from that session attach one set of technique exercises, one strength block, and one interval structure — verify all three use the same interaction pattern, the session count does not grow, and each attachment is visible on the session afterward.

### Tests for User Story 1

> Write these tests first; T009–T013 fail until the corresponding Implementation tasks below land.

- [X] T009 [P] [US1] Component test `frontend/src/components/training/session-plan/__tests__/TechniqueAttachPicker.test.tsx` (new; MSW): multi-select → attach → success updates the Plan section's technique list; a failed attach preserves the coach's selections and allows retry; a retry that simulates "the server already committed, the client only saw an error" does not duplicate the rendered list; assert no request to create a training session is ever issued (SC-002). Include a `jest-axe` zero-violations assertion.
- [X] T010 [P] [US1] Component test `frontend/src/components/training/session-plan/__tests__/StrengthBlockPicker.test.tsx` (new; MSW): the club's existing blocks render as a pick-and-attach list; attach succeeds and the Plan section updates; a `409` response (already attached) renders as a soft "ya está adjunto" notice, not a blocking error; assert `AgeBandGuardrailDialog` is **not** invoked by this path (attach has no age logic — research.md R9) so a later regression can compare. Include a `jest-axe` zero-violations assertion.
- [X] T011 [P] [US1] Extend `frontend/src/routes/strength/__tests__/BlockBuilderPage.test.tsx` (existing file): with `?session_id=123` present, the session renders as a locked read-only summary (static text + Lock/Pencil icon, not a `disabled` input) and the existing searchable radiogroup (`:355-377`) does not render; with it absent, `SessionPickerDialog` (T008) appears before the build form; a successful save auto-attaches and navigates to `/training/sessions/123?section=plan`; add an assertion that `AgeBandGuardrailDialog` still opens unchanged from block create/update reached via this preselected path (SC-007 — the gate lives in save logic untouched by this feature, research.md R9).
- [X] T012 [P] [US1] Component test `frontend/src/components/training/session-plan/__tests__/SessionPickerDialog.test.tsx` (new): given a mocked API response in the service's real `scheduled_date DESC` order, assert the rendered list is re-sorted ascending by `(scheduled_date, scheduled_start_time)` (guards the R6/R10 ordering gotcha directly — this is the regression the ordering note exists to prevent); the text-search fallback filters the list; `onSelect` fires with the chosen session id. Include a `jest-axe` zero-violations assertion.
- [X] T013 [P] [US1] Extend `frontend/src/components/technique/__tests__/CatalogPage.test.tsx` (existing file — tests `frontend/src/routes/technique/CatalogPage.tsx`): a new "Adjuntar a una sesión" action opens `SessionPickerDialog`; selecting a session calls the attach endpoint directly (no page navigation) and renders a "Ver en la sesión" link to `/training/sessions/{id}?section=plan`.

### Implementation for User Story 1

- [X] T014 [US1] Add `useAttachTechniqueItems(sessionId)` TanStack Query mutation hook in `frontend/src/hooks/technique/useTechnique.ts`, calling T007's API function and invalidating `techniqueKeys.sessionExercises(sessionId)` on success (key already defined at `:43-44`).
- [X] T015 [US1] Build `TechniqueAttachPicker.tsx` in `frontend/src/components/training/session-plan/TechniqueAttachPicker.tsx`: filter bar (skill/age-band/material) via the existing `useTechniqueCatalog` (`useTechnique.ts:57-64`); multi-select grid with a per-item segment assignment, mirroring `SessionAssembler.tsx`'s `SegmentSection` pattern (`:116-288`) minus the session-metadata fields that component also collects (the session already exists); idle/pending/success/error states mirroring `TemplatePicker.tsx`'s "Adjuntando…" convention (`:634-639`); calls T014's mutation; renders the non-blocking `mixes_age_bands` notice via the existing `frontend/src/components/technique/MixedAgeNotice.tsx`. Depends on T014.
- [X] T016 [P] [US1] Build `StrengthBlockPicker.tsx` in `frontend/src/components/training/session-plan/StrengthBlockPicker.tsx`: list via the existing `useStrengthBlocks()` (`frontend/src/hooks/strength/useStrength.ts:100`); a per-card "Adjuntar a la sesión" button via the existing `useAttachBlock()` (`:165-184`); idle/pending/success/error states mirroring `TemplatePicker.tsx`; a `409` response renders as a soft "ya está adjunto" notice. Independent of T014/T015 (different domain and files) — may proceed in parallel.
- [X] T017 [US1] Add an "Adjuntar a una sesión" action to `frontend/src/routes/technique/CatalogPage.tsx` that opens `SessionPickerDialog` (T008); on selection, call T014's mutation directly (no navigation) and show a "Ver en la sesión" link to `/training/sessions/{id}?section=plan`. Depends on T008 and T014.
- [X] T018 [P] [US1] In `frontend/src/routes/strength/BlockBuilderPage.tsx`, read `session_id` via `useSearchParams` (the file currently reads only `useParams<{id}>`, `:80-113`): when present, render the target session as a locked read-only summary (static text + Lock/Pencil icon — the feature-015 "locked read-only summary" convention, per CLAUDE.md's `specs/015-prefill-import-from-competition` note) and skip the existing searchable radiogroup (`:283-398`, specifically `:355-377`) entirely; when absent, render `SessionPickerDialog` (T008) first and, on selection, `navigate('/strength/blocks/new?session_id=' + id, { replace: true })`. Different file from T014–T017 — may proceed in parallel with those.
- [X] T019 [US1] In `frontend/src/routes/strength/BlockBuilderPage.tsx`, on a successful block save while a session is locked (T018), automatically call `useAttachBlock` and `navigate('/training/sessions/{id}?section=plan')` — replacing today's "Ver sesión / Seguir editando" choice (`:303-329`). Same file as T018 — sequential after it.
- [X] T020 [P] [US1] Update the "Armar bloque de fuerza" link in `frontend/src/routes/training/SessionDetailPage.tsx` (`:774-779`, currently a plain `<Link to="/strength/blocks/new">`) to carry `?session_id={id}`. Different file from T014–T019 — may proceed in parallel; note T022 below returns to this same file.
- [X] T021 [US1] Build `PlanSection.tsx` in `frontend/src/components/training/session-plan/PlanSection.tsx`: hosts `TechniqueAttachPicker` (T015), `StrengthBlockPicker` (T016) alongside the existing "build new block" link, the existing unchanged intervals block (`StructureEditor`/`TemplatePicker`, `SessionDetailPage.tsx:855-1037`), and the plan-vs-actual `StructureMatchLink`s. When none of the three content types exist yet, render **one** `EmptyState` (`frontend/src/components/shared/EmptyState.tsx`) with all three attach actions passed together as a single multi-button `action` node (`EmptyStateProps.action?: ReactNode` — FR-005, Acceptance Scenario 4 of US2). Once any type has content, that type's own block renders normally and the other two keep their smaller inline empty prompts (e.g. today's "Sin bloques de fuerza adjuntos a esta sesión," `:794-798`). Depends on T015, T016.
- [X] T022 [US1] Mount `PlanSection.tsx` (T021) into `frontend/src/routes/training/SessionDetailPage.tsx` in place of today's separately-stacked "Bloques de fuerza" and "Estructura de intervalos" blocks (`:768-1037`), adding the new technique content alongside them. This is what makes all three attach flows reachable and independently testable ahead of User Story 2's tab refactor. Same file as T020 — sequential after it; depends on T021.
- [X] T023 [US1] Wire `sonner` success/error toasts (`frontend/src/components/ui/sonner.tsx` convention — `toast.success(msg)`/`toast.error(msg)` on mutation settle) for the technique attach (T014), strength pick-existing attach (T016), and strength auto-attach (T019) mutations. No page-local toast state.
- [X] T024 [US1] Add the client-side retry de-dupe guard across `frontend/src/components/training/session-plan/TechniqueAttachPicker.tsx` (T015), `frontend/src/components/training/session-plan/StrengthBlockPicker.tsx` (T016), and `frontend/src/routes/strength/BlockBuilderPage.tsx`'s auto-attach (T019): disable each confirm action while its mutation `isPending` (standard TanStack Query behavior already used throughout this file family). This is the first line of defense (research.md R11); T006's server-side de-dupe is the second line, covering the connection-loss-after-server-commit case a disabled button cannot detect.

**Checkpoint**: User Story 1 is fully functional and independently testable — MVP. A coach can attach all three content types from within a session, through one pattern, with zero duplicate sessions.

---

## Phase 4: User Story 2 - A session screen organized for work (Priority: P2)

**Goal**: The session screen is organized into at most four named sections — Resumen, Asistencia, Plan, Media — with the active section preserved across refresh and back-navigation, and attendance reachable in one tap (FR-004, FR-005, FR-008; SC-004, SC-006).

**Independent Test**: Open a session, switch between the four sections, refresh, and navigate back — the active section persists; verify attendance is reachable in one tap from the session header on a tablet.

### Tests for User Story 2

- [X] T025 [P] [US2] Extend `frontend/src/routes/training/SessionDetailPage.test.tsx` (existing file): setting each of the 4 `?section=` values renders the matching content and hides the others; an unknown/malformed value falls through to the default rule; omitting `?section=` on a session dated today (club timezone) defaults to `asistencia`; omitting it on a future-dated session defaults to `resumen`; an explicit tab click pushes a history entry (back returns to the previously active section, not out of the page — SC-006); a simulated remount with the same URL preserves the same active section; mounting directly with `?section=plan` (simulating a post-attach return) renders `plan` active without requiring a click; assert the separate route `/training/sessions/{id}/activity-match/{activityId}` (`App.tsx:385`) is unaffected by the section refactor (FR-008); add a regression assertion that `AgeGateDialog` still opens unchanged from the interval block now living inside `PlanSection` (SC-007 — intervals' container changes here via T033, so this is where the regression must be caught).
- [X] T026 [P] [US2] Create `frontend/src/routes/training/SessionDetailPage.a11y.test.tsx` (new — follows the `ParentSessionDetailPage.a11y.test.tsx` convention already established in this codebase): `jest-axe` zero-violations on the fully sectioned page.

### Implementation for User Story 2

- [X] T027 [P] [US2] Bump `frontend/src/components/ui/tabs.tsx`'s `TabsTrigger` from `min-h-11` (44px, `:42`) to `min-h-12` (48px) — the club's non-negotiable touch-target floor (Constitution III), first enforced here since `SessionDetailPage` is this shared primitive's first heavy adoption. Different file from all other US2 tasks — may proceed in parallel with them.
- [X] T028 [US2] Add section URL-sync to `frontend/src/routes/training/SessionDetailPage.tsx`: a `parseSectionParam` validating `resumen|asistencia|plan|media` (copies `AthleteDetailPage.tsx`'s `parseTabParam`, `:64-69`), a `searchParams`-change effect for back/forward navigation (copies `:417-426`), and a section-change handler that uses a normal push (`setSearchParams` without `replace`) for explicit coach-initiated clicks versus `{ replace: true }` for the initial auto-selected default — so back-navigation returns to the previously viewed section instead of leaving the page (SC-006, per contracts/session-sections.md's prescribed push/replace distinction).
- [X] T029 [US2] Implement the default-section rule in the same file: `asistencia` when `session.scheduled_date` is today in club timezone, else `resumen` (contracts/session-sections.md). Add `isToday(dateStr)` to `frontend/src/lib/datetime.ts` **if** User Story 3's T040 has not already landed it — the two stories both need this helper; whichever lands first owns the single export and the other reuses it (do not duplicate it). Same file as T028 — sequential after it.
- [X] T030 [US2] Restructure `SessionDetailPage.tsx` onto `components/ui/tabs.tsx`: wrap the four sections in `Tabs`/`TabsList`/4×`TabsTrigger`/4×`TabsContent`, keeping the page header (status badges, date/time/place, Editar/Cancelar/Marcar ejecutada actions, `:550-607`) outside the tab body exactly as today. Preserve every existing `lazy()` boundary (`StructureEditor`, `TemplatePicker`, `RouteViewer`, `MediaGallery` — all four defined at `:57-78`) — none may become a static import as part of this restructure (Constitution IV). Same file — sequential after T029.
- [X] T031 [US2] In `frontend/src/routes/training/SessionDetailPage.tsx`, move the Detalles + Recorrido content (`:609-731`) into the "Resumen" `TabsContent`. Same file — sequential after T030.
- [X] T032 [US2] In `frontend/src/routes/training/SessionDetailPage.tsx`, move the Asistencia content (`AttendanceTable`, `:732-767`) into the "Asistencia" `TabsContent`, unchanged. Same file — sequential after T030.
- [X] T033 [US2] Move `PlanSection.tsx` — already built and mounted by User Story 1's T021/T022 — into the "Plan" `TabsContent`. Pure relocation, no logic change. Same file — sequential after T030; **depends on US1's T021 and T022 being complete** (this is the one US2 task with a real cross-story dependency; see Dependencies & Execution Order).
- [X] T034 [US2] Move the Media content (`MediaUploadZone`/`MediaGallery`, `:1104-1141`) into the "Media" `TabsContent`, unchanged. Same file — sequential after T030.
- [X] T035 [US2] Add focus-on-section-change: each `TabsContent`'s top-level `<h2>` gets `tabIndex={-1}` and a `.focus()` call on mount, per 028's `Stepper` focus convention (`specs/028-frontend-design-foundation/contracts/shared-components.md`) — switching sections announces to screen readers the same way switching wizard steps does. Same file — sequential after T031–T034.
- [X] T036 [US2] In `frontend/src/routes/training/SessionDetailPage.tsx`, point the interval "Ver comparación plan vs. real" `StructureMatchLink` (`:190-197`) and every Plan-section attach-return path (T017, T019) at `?section=plan` explicitly. Same file — sequential after T033.
- [X] T037 [P] [US2] Recommended follow-on (flagged in contracts/session-sections.md as low-risk, not mandatory for this feature): gate `mediaQuery`, `strengthBlocksQuery`, `structureQuery`, `sessionActivitiesQuery`, `unlinkedActivitiesQuery` behind `enabled: activeSection === '...'` in `SessionDetailPage.tsx` so non-active-section queries stop firing unconditionally on mount (`:376-398`).

**Checkpoint**: User Stories 1 AND 2 both work — the session screen is sectioned, attendance is one tap away, and the Plan section (built in US1) hosts the unified attach flows.

---

## Phase 5: User Story 3 - Today's session is one tap away (Priority: P3)

**Goal**: The sessions list offers a "hoy" shortcut and today's row is visually distinct without relying on color alone (FR-007; SC-005).

**Independent Test**: With sessions seeded across a month including today, open the sessions list and reach today's session in one interaction via the "hoy" shortcut; verify today's row is visually distinct without relying on color alone.

**Note**: this story depends only on Setup (T001) — it does not require the Foundational phase or User Story 1 and may be built in parallel with them (see Dependencies & Execution Order).

### Tests for User Story 3

- [X] T038 [P] [US3] Extend `frontend/src/components/training/SessionsTable.test.tsx` (existing file): today's row/card carries both an icon/marker **and** a text label, in both the mobile-card branch (`:44-116`) and the desktop-table branch (`:118-232`) — assert on the accessible text, not a CSS class alone (guards against a color-only regression).
- [X] T039 [P] [US3] Create `frontend/src/components/training/__tests__/SessionFiltersBar.test.tsx` (new — no test file exists for this component yet): clicking "Hoy" sets the filter store to today's date against a fixed mocked `Date` (deterministic, not wall-clock); with a seeded session today, the list shows exactly that session; with none today, the fallback shows the next upcoming session labeled "No hay sesión hoy — próxima sesión:".

### Implementation for User Story 3

- [X] T040 [US3] Add `todayISODate()` and `isToday(dateStr)` to `frontend/src/lib/datetime.ts`, extracting the `CLUB_TIMEZONE` technique already used by `formatRelativeDay` (`:164-199`) — not the timezone-naive reimplementation in `AthleteDetailPage.tsx:106-117`. (See the note on T029 above: whichever of US2/US3 lands first owns this export.)
- [X] T041 [US3] Add a `setToday()` action to `frontend/src/store/trainingFiltersStore.ts` (sets `from_date = to_date = todayISODate()`), reusing the existing persisted `from_date`/`to_date`/`status` shape (`:18-46`) — no new persisted fields. Depends on T040.
- [X] T042 [US3] Add a "Hoy" quick-filter action to `frontend/src/components/training/SessionFiltersBar.tsx` calling T041's `setToday()`. Depends on T041.
- [X] T043 [US3] Implement the "no session today" fallback in the sessions-list data flow: when the "Hoy" filter yields zero rows, fetch a bounded forward window (`from=today`, `to=today+90d`), sort the result client-side **ascending** by `(scheduled_date, scheduled_start_time)` (the same R6/R10 DESC-ordering gotcha as T008 — the API's default order is furthest-future-first, do not trust it), take the first entry, and label the resulting view "No hay sesión hoy — próxima sesión:". Depends on T040.
- [X] T044 [US3] Add the non-color-alone today marker (icon + text label) to `frontend/src/components/training/SessionsTable.tsx`, in **both** the mobile card branch and the desktop table branch (the file's dual-render structure means a marker added to only one silently disappears on the other breakpoint), using `isToday()` from T040.

**Checkpoint**: All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end verification across all three stories together, regression sweeps, and success-criteria sign-off.

- [X] T045 [P] Playwright flow in `frontend/e2e/session-content-unification.spec.ts` (new file — `frontend/e2e/target-size.spec.ts`, referenced in research.md as planned 028 infra, does not exist yet in this repo, so this is a new spec, not an extension). Steps (quickstart.md): log in as coach (`entrenador@trochyruta.com` / `Coach2026!`); create a session; from its Plan section attach technique exercises (2+ items), a strength block via "pick existing," and an interval structure via inline create; assert no new row appears in `/training/sessions` (SC-002); assert all three appear together in the Plan section as one coherent list; assert every interactive control exercised has a rendered bounding box ≥48×48px; navigate away and back (or refresh) mid-flow and assert the active `?section=` persisted (SC-006).
- [X] T046 [P] Backend regression sweep: `cd backend && pytest tests/strength -v` and `pytest tests/technique -v` — confirm every pre-existing test still passes unmodified (no contract change to strength or intervals, research.md R2/R3).
- [X] T047 [P] Frontend regression sweep: `cd frontend && npm run test` (full suite) — confirm `SessionDetailPage.test.tsx`, `BlockBuilderPage.test.tsx`, `AgeGateDialog.test.tsx`, and `AgeBandGuardrailDialog.test.tsx` all still pass.
- [ ] T048 Run quickstart.md's manual validation scenarios end-to-end on a local Docker stack (`docker compose up`) with seed data, on an actual tablet or throttled-network desktop emulation: US1 AC1–AC5, US2 AC1–AC4, US3 AC1–AC2, the mid-attach connection-loss edge case, and both age-band gate edge cases (strength override recording; interval Z3+ hard block for age 10–12).
- [X] T049 Verify SC-001 through SC-007 against quickstart.md's "Success criteria cross-reference" table — confirm each success criterion has a passing automated test (from the tasks above) or a documented manual-validation result from T048.
- [X] T050 [P] Add a docstring to `attach_exercises_to_session()` (`backend/app/services/technique/assembler.py`, T006) describing inputs, outputs, and the de-dupe side effect, matching the convention already followed by every other function in `assembler.py`/`blocks.py` (Constitution I).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately, after confirming T001's cross-feature prerequisites.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks User Story 1 only** — not US2 or US3 (this feature's Foundational work is entirely backend-endpoint-and-picker, neither of which US2 or US3 touches).
- **User Story 1 (Phase 3)**: Depends on Foundational.
- **User Story 2 (Phase 4)**: Its tab-shell tasks (T025–T032, T034–T037) have no functional dependency on User Story 1 and could be developed in parallel on a separate branch once Foundational is done. Its one content-integration task, **T033** (moving `PlanSection.tsx` into the Plan tab), explicitly depends on US1's T021/T022. Because T027–T037 nearly all edit the same file US1 also edits (`SessionDetailPage.tsx`), a single-track team should sequence **US1 → US2** to avoid a large same-file merge conflict; a two-track team may build both in parallel and reconcile once at merge (the conflict is mechanical — file layout — not semantic).
- **User Story 3 (Phase 5)**: Depends **only** on Setup. Does not require Foundational or User Story 1 — it touches none of the files either produces. May be built entirely in parallel with Foundational + User Story 1.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational. No dependency on US2 or US3.
- **User Story 2 (P2)**: Depends on Foundational (for the section-shell work) and, specifically for T033/T036, on User Story 1 (for `PlanSection.tsx` and its attach-return paths to exist). See the precise split above.
- **User Story 3 (P3)**: Can start after Setup — independent of Foundational, US1, and US2. **One precise cross-story note**: US2's T029 (default-section rule) and US3's T040 (`isToday()` helper) both need the same club-timezone-today check on `frontend/src/lib/datetime.ts`. To avoid a duplicate export, whichever of the two lands first owns the extraction; the other imports it. Given US3 is scheduled in parallel with US1 (i.e., no later than US2, which starts after US1), T040 is expected to land first in practice — T029 is written to reuse it, falling back to performing the extraction itself only if US2 is executed first.

### Within Each User Story

- Tests are written before their corresponding implementation tasks and are expected to fail until that implementation lands (Constitution II).
- Tasks that edit the same file are listed in the order they must be applied and are never marked `[P]` against each other, even when the underlying concerns are logically independent (e.g. US2's T028–T036 all edit `SessionDetailPage.tsx` sequentially).
- Story complete (checkpoint) before moving to the next priority, for a single-track team.

### Parallel Opportunities

- Setup: T002 and T004 (different files/operations, no ordering dependency).
- Foundational: T007 and T008 (different frontend files).
- User Story 1 tests: T009, T010, T011, T012, T013 (five different test files).
- User Story 1 implementation: T016, T018, T020 (each in a file untouched by the others in this phase).
- User Story 2 tests: T025 and T026 (different files — `SessionDetailPage.test.tsx` vs the new `SessionDetailPage.a11y.test.tsx`).
- User Story 2 implementation: T027 (`ui/tabs.tsx`, independent of the rest of the phase).
- **User Story 2 as a whole may run in parallel with User Story 1** on a separate branch (T033/T036 excepted — see above).
- **User Story 3 as a whole may run in parallel with Foundational + User Story 1** — a different engineer/track can start on T038 immediately after T001.
- Polish: T045, T046, T047, T050 (independent verification passes).

---

## Parallel Example: Setup

```bash
Task: "Add AttachExercisesRequest/AttachExercisesResponse schemas in backend/app/schemas/technique.py"     # T002
Task: "Verify no Alembic migration is required (autogenerate check, then discard)"                          # T004
```

## Parallel Example: Foundational

```bash
Task: "Add attachExercisesToSession() API client function in frontend/src/api/technique.ts"                 # T007
Task: "Build shared SessionPickerDialog.tsx in frontend/src/components/training/session-plan/"              # T008
```

## Parallel Example: User Story 1 (tests)

```bash
Task: "TechniqueAttachPicker.test.tsx — multi-select, retry de-dupe, axe"                                    # T009
Task: "StrengthBlockPicker.test.tsx — list, attach, 409-as-soft-notice, axe"                                 # T010
Task: "BlockBuilderPage.test.tsx — preselect/lock, picker-when-absent, gate regression"                      # T011
Task: "SessionPickerDialog.test.tsx — ascending re-sort against a DESC-ordered mock, axe"                    # T012
Task: "CatalogPage.test.tsx (technique) — library-initiated attach entry point"                              # T013
```

## Parallel Example: User Story 1 (implementation)

```bash
Task: "Build StrengthBlockPicker.tsx"                                                                        # T016
Task: "Add ?session_id= read/lock in BlockBuilderPage.tsx"                                                   # T018
Task: "Update the Armar bloque de fuerza link in SessionDetailPage.tsx to carry ?session_id="                # T020
```

## Parallel Example: User Story 3 (runs alongside Foundational + User Story 1)

```bash
Task: "Extend SessionsTable.test.tsx — today marker, both render branches"                                   # T038
Task: "Create SessionFiltersBar.test.tsx — Hoy button + no-session-today fallback"                            # T039
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + User Story 1)

1. Complete Phase 1: Setup (T001–T004).
2. Complete Phase 2: Foundational (T005–T008) — the backend endpoint and the shared session picker.
3. Complete Phase 3: User Story 1 (T009–T024).
4. **STOP and VALIDATE**: run the Independent Test for US1 — attach technique + strength + intervals to a session from within it, confirm the session count does not grow.
5. This is the MVP: the attach unification is the feature's core value (spec.md's own framing) — deploy/demo here if time-boxed.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add User Story 1 → validate independently → deploy/demo (MVP!).
3. Add User Story 2 → validate independently (four sections, persists across refresh/back-nav) → deploy/demo.
4. Add User Story 3 → validate independently ("hoy" shortcut, non-color-alone marker) → deploy/demo.
5. Polish (Phase 6) → Playwright flow, regression sweeps, SC-001..SC-007 sign-off.

### Parallel Team Strategy

With more than one engineer:

1. Everyone completes Setup together (T001 first — it may surface a blocking cross-feature gap).
2. Once Setup is done:
   - Engineer/Track A: Foundational (T005–T008), then User Story 1 (T009–T024).
   - Engineer/Track B: User Story 3 (T038–T044) — no dependency on Foundational or US1.
   - Engineer/Track C (optional): begins User Story 2's tab-shell tasks (T025–T032, T034, T035, T037) on a separate branch once Foundational lands, holding T033/T036 until Track A finishes US1.
3. Reconcile Track A and Track C's overlapping edits to `SessionDetailPage.tsx` once, at the point US1 and US2's shell both land.

---

## Notes

- `[P]` tasks touch different files with no ordering dependency on an incomplete task.
- `[US1]`/`[US2]`/`[US3]` maps each task to its user story for traceability back to spec.md.
- No Alembic migration ships with this feature (verified by T004; data-model.md).
- Every existing age-band gate (`AgeBandGuardrailDialog`, `AgeGateDialog`) must fire identically to today at the end of this feature (SC-007) — T011, T025, T046, T047 are where that is verified, not where new gate logic is written; none should be touched.
- Commit after each task or logical group; stop at any Checkpoint to validate a story independently before continuing.
- Avoid: vague tasks, two tasks editing the same file marked `[P]` against each other, and cross-story dependencies beyond the two explicitly called out above (US2→US1 for T033/T036; the US2↔US3 `isToday()` reuse note).
