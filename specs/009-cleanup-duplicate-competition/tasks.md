# Tasks: Cleanup Duplicate Competition

**Feature**: `009-cleanup-duplicate-competition` | **Branch**: `009-cleanup-duplicate-competition`
**Plan**: [plan.md](./plan.md) · **Spec**: [spec.md](./spec.md) · **Contract**: [contracts/cleanup-endpoint.md](./contracts/cleanup-endpoint.md)

Tests are included: Principle II (Testing) of the constitution is NON-NEGOTIABLE, and this is a
destructive flow over minors' data dependencies — backend happy/negative paths, a privacy invariant,
and frontend behavior/accessibility tests are required.

**No database migration.** Reuses existing tables, FKs, and the existing `ConfirmDeleteDialog`.

## Conventions
- `[P]` = parallelizable (different file, no dependency on an incomplete task).
- `[US1]` / `[US2]` map to the spec's user stories. Setup/Foundational/Polish carry no story label.

---

## Phase 1: Setup

- [X] T001 Confirm branch `009-cleanup-duplicate-competition` is checked out and the working tree is clean; verify backend venv (`source backend/.venv/bin/activate`) and frontend deps install, and that `cd backend && pytest -q` + `cd frontend && npm run test -- --run` are green on the baseline before changes.

---

## Phase 2: Foundational (blocking prerequisites)

- [X] T002 Add the service function signature and docstring `cleanup_duplicate_race_event(db: AsyncSession, race_event_id: int) -> None` in `backend/app/services/race_events.py` (no body logic yet beyond raising `NotImplementedError`), documenting inputs/outputs/side-effects and the 3-step delete order per `data-model.md`. This is the shared seam US1 and US2 both build on.

---

## Phase 3: User Story 1 — Coach removes a no-results duplicate competition (Priority: P1) 🎯 MVP

**Goal**: A coach removes a no-results duplicate competition together with its linked calendar event in
one confirmed action; the list and the calendar both reflect the removal.

**Independent test**: Seed a no-results competition linked to a calendar event; as coach call
`DELETE /api/race-analysis/race-events/{id}/cleanup` → 204; assert the `race_events` row, the
`calendar_events` row, and its `event_audiences`/`event_attendances` are gone; results untouched.

### Backend — implementation
- [X] T003 [US1] Implement `cleanup_duplicate_race_event` in `backend/app/services/race_events.py`: load the `RaceEvent` (404 if missing); guard `EXISTS(race_results.event_id == id)` → 409 "tiene resultados ingestados"; if `calendar_event_id` is set, null it + `flush`, load the `CalendarEvent` and `db.delete(cal)` + `flush` (cascades audiences/attendances); then `db.delete(event)` + `flush`. Log IDs only. (Reuses imports already in the module: `CalendarEvent`, `RaceResult`, `exists`, `select`.)
- [X] T004 [US1] Add endpoint `DELETE /{race_event_id}/cleanup` in `backend/app/routers/race_events.py` with `require_role([UserRole.coach])`, `status_code=204`, docstring listing 204/403/404/409; delegate to `race_events_svc.cleanup_duplicate_race_event(db, race_event_id)`; `logger.info("race_event_cleanup race_event_id=%s user_id=%s", ...)`.

### Backend — tests
- [X] T005 [P] [US1] In `backend/tests/routers/test_race_events_crud.py` (new class `TestCleanupDuplicateRaceEvent`, reusing existing fixtures) add happy-path test: coach cleans a no-results competition **with** a linked calendar event (reuse `coach_client_with_calendar` → evt 100 + cal 500) → 204; assert race_event 100, calendar_event 500, and its `event_audiences` rows are all deleted (query counts == 0).
- [X] T006 [P] [US1] Same file: happy-path-without-calendar test: coach cleans a no-results competition with **no** calendar event (reuse `coach_client` → evt 101) → 204; only the race_event is removed; no error.
- [X] T007 [P] [US1] Same file: privacy invariant test using `caplog`: the 204 cleanup response body is empty and the cleanup log record carries only IDs (no user email/name), per Ley 1581.

### Frontend — implementation
- [X] T008 [P] [US1] Add `cleanupDuplicateRaceEvent(id, options?)` (DELETE `${BASE}/${id}/cleanup` → void) to `frontend/src/api/raceEvents.ts`, with a docstring noting 204/403/404/409 and coach-only RBAC.
- [X] T009 [US1] Add `useCleanupDuplicateRaceEvent()` mutation to `frontend/src/hooks/race/useRaceEvents.ts` (`mutationKey: ["raceEvents","cleanupDuplicate"]`, `mutationFn: ({id}) => cleanupDuplicateRaceEvent(id)`); `onSuccess` invalidate `raceEventKeys.lists()`, `CALENDAR_AVAILABLE_ROOT`, and `calendarQueryRoot` (the cleanup removes a calendar event, so the calendar must refresh).
- [X] T010 [US1] In `frontend/src/routes/competitions/CompetitionsListPage.tsx`: compute `isCoach = user?.role === UserRole.coach`; add a destructive "Eliminar duplicado" `DropdownMenuItem` to `ActionsKebab` shown when `isCoach && !item.has_results`; wire a separate `cleanupTarget` state + `ConfirmDeleteDialog` (title "Eliminar competencia duplicada", description in español neutro stating the competition **and** its evento de calendario asociado will be permanently removed and the action is irreversible, confirmLabel "Eliminar duplicado") using `useCleanupDuplicateRaceEvent` and `getRaceEventErrorMessage` for the error slot. Pass the new props through `CompetitionTableRow`, `CompetitionCard`, and `ActionsKebab`.

### Frontend — tests
- [X] T011 [P] [US1] In the existing `frontend/src/routes/competitions/__tests__/CompetitionsListPage.test.tsx` test: as a coach, a no-results competition shows "Eliminar duplicado"; confirming calls the mutation with the right id and closes the dialog on success.
- [X] T012 [P] [US1] Add a `jest-axe` accessibility assertion on the open cleanup `ConfirmDeleteDialog` (zero violations), per Principle III.

**Checkpoint**: US1 is independently shippable — the coach can fully remove a no-results duplicate +
its calendar event from the UI and via the API.

---

## Phase 4: User Story 2 — Authoritative competition with results is protected (Priority: P1)

**Goal**: A competition that holds results can never be removed by this flow — no action in the UI and a
hard 409 at the API, including the "results imported after the menu opened" race.

**Independent test**: For a competition with ≥1 result, assert the cleanup endpoint returns 409 and the
"Eliminar duplicado" action is not rendered.

### Backend — tests
- [X] T013 [P] [US2] In `backend/tests/routers/test_race_events_crud.py` add: cleanup on a competition **with** results (reuse `coach_client_with_result` → evt 100) → 409 and no rows deleted (race_event + results still present).
- [X] T014 [P] [US2] Add RBAC negative tests: parent → 403 and admin → 403 on the cleanup endpoint (coach-only), plus a non-existent id → 404. Assert no data is deleted on the 403/404 paths.

### Frontend — tests
- [X] T015 [P] [US2] In `CompetitionsListPage.test.tsx` assert that for a competition with `has_results === true` the "Eliminar duplicado" item is NOT rendered for a coach, and that a parent/athlete never sees it regardless of `has_results`.

**Checkpoint**: Results-bearing competitions are provably protected at both UI and API layers.

---

## Phase 5: Polish & Cross-Cutting

- [X] T016 [P] Update the router module docstring header in `backend/app/routers/race_events.py` to list the new `DELETE /{id}/cleanup` (coach-only) line alongside the existing endpoint inventory.
- [X] T017 [P] Update `frontend/src/api/raceEvents.ts` top-of-file endpoint inventory comment to include the cleanup endpoint.
- [X] T018 Run full gates: `cd backend && ruff check . && pytest -q` and `cd frontend && npm run lint && tsc --noEmit && npm run test -- --run`; fix any failures. Confirm `docs/implementation-status.md` + the CLAUDE.md status table get a row for feature 009 (status: deploy pending) — done as the final doc touch.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** → everything else.
- **US1 (T003–T012)** depends on T002. Backend impl T003 → T004 (endpoint calls service). Tests T005–T007 depend on T003/T004. Frontend T008 → T009 → T010; tests T011–T012 depend on T010.
- **US2 (T013–T015)** depends on the endpoint existing (T004) and the UI gating (T010). US2 is mostly tests over the same seam, so it can largely run alongside US1's test phase.
- **Polish (T016–T018)** last.

### Parallel opportunities
- Backend tests `T005, T006, T007` (and US2's `T013, T014`) are all `[P]` — different assertions in the same/new test file; write concurrently, run together.
- Frontend `T008` (api) is `[P]` vs backend impl. Frontend tests `T011, T012, T015` are `[P]`.
- Polish `T016, T017` are `[P]`.

## Implementation Strategy
- **MVP = Phase 1 + 2 + US1 (T001–T012)**: delivers the full coach cleanup flow end-to-end.
- **US2 (T013–T015)** hardens the protection guarantees — implement immediately after US1 (same PR) since the constitution requires the negative paths.
- Ship as one PR (small, surgical, no migration). Human review per Principle I before merge to `main`.

## Format validation
All tasks use `- [ ] [TaskID] [P?] [Story?] description + file path`. Setup/Foundational/Polish carry no
story label; US1/US2 tasks carry `[US1]`/`[US2]`.
